"""只读探测 OneSignal 侧的真实状态（排查「推送发不出去」，全程不发任何推送）

为什么需要它：后台的发送日志只告诉你「失败」，但失败有两类**完全不同的原因**，
排查方向相反 ——
  ① 配置/密钥问题：请求到不了 OneSignal，或 Key 与 App ID 不属于同一应用；
  ② 没有订阅者：配置全对，只是还没有人在浏览器上授权过通知。
本工具直接问 OneSignal 侧要事实，一次分清：

  - App 是否配了 **Web 平台**、`chrome_web_origin` 是否等于本站域名（不等则 Web 推送必失败）
  - 到底有多少订阅者，**其中几个是 Web Push**（Web 订阅的 identifier 是 http(s) 端点，
    Email 是邮箱 —— 按 identifier 形态判断比 device_type 数字可靠）
  - 最近几条通知的真实触达数（`recipients` / `successful` / `failed`）

典型结论对照：
  - `players = 0` 或全部非 Web  → 「没人订阅」：让用户先登录再点「允许通知」
  - HTTP 401                   → 密钥问题：Key 与 App ID 不是同一个应用，或 Key 已轮换
  - `chrome_web_origin` 不等于本站域名 → OneSignal 侧域名配错，Web 订阅收不到推送

用法（项目根目录执行；线上则用服务器上的 venv）：
  python tools/onesignal_probe.py                    # 概览（App 信息 + 订阅构成）
  python tools/onesignal_probe.py --players 50       # 多看几条订阅明细
  python tools/onesignal_probe.py --notifications 10 # 多看几条历史通知

⚠️ 只发 GET 请求；不发送推送、不改任何配置；不打印密钥明文。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from app.domains.platform.services import push  # noqa: E402

TIMEOUT = 20
V1 = "https://onesignal.com/api/v1"


def _headers() -> dict:
    """REST 鉴权头：**`Key <REST_API_KEY>`**（不是 Bearer，也不是 Basic）。"""
    return {"Authorization": "Key %s" % push._rest_key(), "Content-Type": "application/json"}


def _kind(identifier: str) -> str:
    """按 identifier 形态判断订阅类型。

    比 device_type 数字可靠：Web 订阅的 identifier 是推送端点 URL
    （fcm.googleapis.com / updates.push.services.mozilla.com 等），Email 是邮箱地址。
    """
    s = identifier or ""
    if s.startswith("http"):
        return "Web"
    if "@" in s:
        return "Email"
    return "移动端/未知"


def show_app(app_id: str) -> dict:
    """App 概览：名称、Web 平台配置、订阅数。"""
    r = requests.get("%s/apps/%s" % (V1, app_id), headers=_headers(), timeout=TIMEOUT)
    if r.status_code == 401:
        print("  ✘ HTTP 401：密钥无效，或该 Key 与这个 App ID 不属于同一个应用")
        print("    （去后台「系统配置 → 消息推送」核对 ONESIGNAL_APP_ID / ONESIGNAL_REST_API_KEY）")
        return {}
    if not r.ok:
        print("  ✘ 查询失败：HTTP %s %s" % (r.status_code, r.text[:200]))
        return {}

    d = r.json()
    site = push._base_url()
    origin = (d.get("chrome_web_origin") or "").rstrip("/")
    print("  App 名称        = %s" % d.get("name"))
    print("  创建 / 最近修改 = %s / %s" % (d.get("created_at"), d.get("updated_at")))
    print("  Web 平台域名    = %s" % (origin or "(未配置)"))
    print("  本站地址        = %s" % site)
    if origin and site and origin != site.rstrip("/"):
        print("  ⚠️ 域名不一致 —— OneSignal 侧 Web 订阅会收不到推送，"
              "请把 OneSignal 后台的站点 URL 改成 %s" % site)
    else:
        print("  ✓ 域名一致（或未配置，未配置时 Web 推送不可用）")
    print("  订阅总数        = %s（可触达 %s）" % (d.get("players"), d.get("messageable_players")))
    return d


def show_players(app_id: str, limit: int) -> int:
    """订阅明细：打印类型分布，返回 Web 订阅数。"""
    r = requests.get("%s/players" % V1,
                     params={"app_id": app_id, "limit": limit},
                     headers=_headers(), timeout=TIMEOUT)
    if not r.ok:
        print("  ✘ 查询失败：HTTP %s %s" % (r.status_code, r.text[:200]))
        return 0
    d = r.json()
    players = d.get("players") or []
    kinds = {}
    for p in players:
        k = _kind(p.get("identifier"))
        kinds[k] = kinds.get(k, 0) + 1
    print("  订阅构成        = %s" % (kinds or "(无任何订阅)"))
    for p in players:
        print("    - [%s] %s | device_type=%s | last_active=%s" % (
            _kind(p.get("identifier")), (p.get("identifier") or "")[:60],
            p.get("device_type"), p.get("last_active")))
    return kinds.get("Web", 0)


def show_notifications(app_id: str, limit: int) -> None:
    """最近通知：OneSignal 侧是否真的产生了通知、触达多少订阅。"""
    r = requests.get("https://api.onesignal.com/notifications",
                     params={"app_id": app_id, "limit": limit},
                     headers=_headers(), timeout=TIMEOUT)
    if not r.ok:
        print("  ✘ 查询失败：HTTP %s %s" % (r.status_code, r.text[:200]))
        return
    d = r.json()
    ns = d.get("notifications") or []
    print("  通知总数 = %s（本次列出 %d 条）" % (d.get("total_count"), len(ns)))
    for n in ns:
        print("    - id=%s recipients=%s successful=%s failed=%s headings=%s" % (
            (n.get("id") or "")[:12], n.get("recipients"), n.get("successful"),
            n.get("failed"), json.dumps(n.get("headings"), ensure_ascii=False)[:40]))


def main():
    ap = argparse.ArgumentParser(description="只读探测 OneSignal 侧状态（不发推送）")
    ap.add_argument("--players", type=int, default=20, help="列出多少条订阅明细（默认 20）")
    ap.add_argument("--notifications", type=int, default=5, help="列出多少条历史通知（默认 5）")
    args = ap.parse_args()

    app_id = push._app_id()
    if not app_id or not push._rest_key():
        print("[未配置] 缺少 ONESIGNAL_APP_ID / ONESIGNAL_REST_API_KEY，"
              "先在后台「系统配置 → 消息推送」填写（或写入 .env）。")
        sys.exit(2)
    print("App ID 后 6 位 = %s | push_configured() = %s"
          % (app_id[-6:], push.push_configured()))

    print("\n[1] App 概览")
    show_app(app_id)

    print("\n[2] 订阅明细")
    web = show_players(app_id, args.players)

    print("\n[3] 最近通知")
    show_notifications(app_id, args.notifications)

    print("\n[结论]")
    if web:
        print("  OneSignal 侧存在 %d 个 Web 订阅 —— 通道可用；若某些人收不到，"
              "去查偏好开关 / 免打扰 / 每日上限。" % web)
    else:
        print("  OneSignal 侧**没有任何 Web 订阅** —— 这就是发不出去的原因，"
              "不是配置错误。")
        print("  让用户：① 打开本站并**先登录**（未登录不初始化 SDK，订阅绑不上账号）")
        print("          ② 在浏览器弹窗点「允许通知」")
        print("          ③ 回后台看「已授权设备」是否 +1，再发测试推送")
        print("  注意：之前拒绝过授权时不会再弹窗，需到浏览器「站点设置」手动改为「允许」。")


if __name__ == "__main__":
    main()
