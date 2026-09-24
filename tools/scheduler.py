#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代码内置轻量定时器（部署到线上服务器，由 crontab 周期调用）。

为什么放在代码里：
    本定时器随代码提交、随 deploy 上线，在线上服务器运行，直接读写线上库
    （依赖服务器 .env 的 DB_HOST/DB_NAME），不依赖任何外部调度平台。

线上服务器 crontab 安装（只需一次；解释器必须用**项目自己的 venv**，
路径以 deploy.sh 的 $APP_DIR 为准，勿写 /opt/venv 之类的想当然路径）：
    */15 * * * * cd /home/PrimarySchoolExam && /home/PrimarySchoolExam/venv/bin/python tools/scheduler.py >> /var/log/scheduler.log 2>&1

（该行与 DEPLOY.md §15.2 必须逐字一致，tools/ops_check.py 会校验，
  防止运维照抄到过时的解释器路径 —— cron 指向不存在的解释器时任务完全不跑，
  而 cron 的错误输出只发给 root，等于静默失效。）

能力：
- 任务类型：once（一次性）/ daily（每日）/ weekly（每周）
- 停用开关：enabled=False 可临时停用某任务（保留配置，改回 True 即恢复；比删定义更安全）
- 限制次数：max_runs（None=不限）；有效期：valid_from / valid_until（日期，到期自动停）
- 幂等：用 tools/.scheduler_state.json 记录每个任务的 last_run 与 run_count，
  cron 高频触发（每 15 分钟）也不会重复执行；若某天服务器在指定时刻宕机，
  下一个 tick 会自动补跑（自愈）。

配置写错的代价（2026-09-24 加固，勿回退）
----------------------------------------
调度任务是**静默执行**的（cron 输出进 /var/log/scheduler.log，没有告警通道），
所以一处配置笔误的后果远比想象严重：

- `at="25:99"` / `valid_from="2026-13-45"` 这类非法值，历史上会让 `_job_due`
  抛 ValueError 并冒泡出 `run_due_jobs` —— **整轮调度中断**，排在它之后的任务
  一个都不执行；cron 每 15 分钟重跑、每次都崩在同一处 → 后续任务**永久停摆**。
- `kind="dailly"` 这类拼错只返回「未知 kind」，任务**永不执行**且无人察觉。

因此本文件做了三层防护（对应 `validate_job()` / `_job_due()` / `run_due_jobs()`）：
1. `validate_job(job)` 纯函数静态校验（调度规则与 tools/ops_check.py 共用，
   保证规则只有一处真相源）；配置有误的任务**只跳过自己**并在日志里醒目打印；
2. `_parse_hm()` 与日期解析不再抛异常，改为返回 None + 明确「配置错误」原因；
3. 单任务判定/执行异常一律就地兜住，**绝不终止整轮调度**。

新增/修改任务后请跑 `python tools/ops_check.py` 校验（含脚本存在性、依赖声明、
git 跟踪与调度状态体检），提交前的 `tools/regression_check.py` 也会自动带上。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, date, time as dtime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".scheduler_state.json")
LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".scheduler.lock")

# ---- 任务定义（新增定时/采集/汇总类任务在此追加）---------------------------
JOBS = [
    {
        # 【已停用 2026-09-05】数据源已枯竭，连续多日无新内容生成，暂停以免白烧 AI 额度。
        # 恢复：把下面的 enabled 改回 True（或删掉该行），再确认 valid_from/valid_until 仍在有效期内。
        "name": "seed_junior_grade7",
        "enabled": False,             # 显式停用开关：False 时调度器直接跳过，不判断时间/次数
        "kind": "daily",              # once | daily | weekly
        "at": "01:00",                # HH:MM，当天到达该时刻后触发
        "valid_from": "2026-08-25",   # 可选，YYYY-MM-DD
        "valid_until": "2026-09-10",  # 可选，YYYY-MM-DD；到期自动停止（"限制次数"的日期兜底）
        "max_runs": 30,               # 可选，None=不限；到达即停止
        "weekday": None,              # weekly 时 0=周一..6=周日
        "command": ["tools/seed_junior_grade7.py"],  # 相对 REPO_ROOT，用 sys.executable 运行
        "timeout": 10800,             # 单任务超时（秒）：大纲拆细后 ~80 次 AI 调用，放宽到 3h
    },
    {
        # 【已停用 2026-09-05】缺答案题目已补完（连续多日无新增补答案），暂停以免白烧 AI 额度。
        # 恢复：把下面的 enabled 改回 True（或删掉该行）。脚本幂等，只会补 correct_answer 为空的题。
        "name": "backfill_paper_answers",
        "enabled": False,
        "kind": "daily",
        "at": "01:00",
        "valid_from": "2026-08-27",
        "valid_until": "2026-09-15",   # 每晚限量补，多晚补完（幂等：只补缺答案的）
        "max_runs": 15,
        "weekday": None,
        "command": ["tools/backfill_paper_answers.py"],
        "timeout": 10800,              # 每晚最多约 3000 题（智谱 ~2s/题）
    },
    {
        "name": "close_expired_orders",
        "kind": "daily",
        "at": "00:15",
        "valid_from": "2026-09-05",
        "valid_until": None,
        "max_runs": None,
        "weekday": None,
        "command": ["tools/close_expired_orders.py"],
        "timeout": 120,
    },
    {
        "name": "vip_expire_downgrade",
        "kind": "daily",
        "at": "02:00",
        "valid_from": "2026-09-05",
        "valid_until": None,
        "max_runs": None,
        "weekday": None,
        "command": ["tools/vip_expire_downgrade.py"],
        "timeout": 120,
    },
    {
        # 账本周期交易每日自动执行（B9）：全量扫描到期周期交易，生成账单并联动余额。
        # 幂等：执行后 next_run 推进到未来，重跑不产生重复账单。
        "name": "ledger_recurring_daily",
        "kind": "daily",
        "at": "01:00",
        "valid_from": "2026-09-08",
        "valid_until": None,
        "max_runs": None,
        "weekday": None,
        "command": ["tools/run_due_recurring.py"],
        "timeout": 600,
    },
    {
        # IM 红包过期原路退回（B12）：24h 未领完的剩余钻石退回发送者。
        # 与账本周期交易错峰 10 分钟，避免同刻并发。幂等：状态置 EXPIRED 后不再命中。
        "name": "im_red_packet_expire",
        "kind": "daily",
        "at": "01:10",
        "valid_from": "2026-09-08",
        "valid_until": None,
        "max_runs": None,
        "weekday": None,
        "command": ["tools/expire_red_packets.py"],
        "timeout": 300,
    },
]


def _load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001
            # 静默返回 {} 会让当天的 daily 任务被判定为「今日未运行」而重复执行；
            # 多数任务幂等（无害），但必须能在日志里看到，故显式打印。
            print(f"[scheduler] 状态文件损坏，按空状态继续（当日 daily 任务可能重复执行一次）："
                  f"{type(e).__name__}: {e}", flush=True)
    return {}


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _parse_hm(s):
    """解析 "HH:MM" -> time；非法返回 None（**不抛异常**，避免拖垮整轮调度）"""
    try:
        h, m = str(s).split(":")
        return dtime(int(h), int(m))
    except (ValueError, AttributeError):
        return None


VALID_KINDS = ("once", "daily", "weekly")


def validate_job(job) -> list:
    """静态校验一条任务定义，返回错误说明列表（空列表 = 合法）

    纯函数、无副作用，且**不依赖任何第三方包**：调度器启动自检与
    tools/ops_check.py 共用同一份规则（单一真相源，避免两处校验漂移）。

    校验范围覆盖那些「写错了也不报错」的陷阱：
    - kind 拼错 -> 任务永不执行（历史上只打印「未知 kind」）；
    - at 非法 -> 历史上抛异常打断整轮调度；
    - enabled 写成字符串 "False" -> `is False` 判定不成立，任务照旧启用；
    - weekday 写在非 weekly 任务上 -> 被静默忽略；
    - valid_from 晚于 valid_until -> 窗口为空，永远不会执行。
    """
    if not isinstance(job, dict):
        return ["任务定义必须是 dict"]

    errs: list[str] = []

    name = job.get("name")
    if not isinstance(name, str) or not name.strip():
        errs.append("缺少 name（应为非空字符串）")

    en = job.get("enabled")
    if en is not None and not isinstance(en, bool):
        errs.append(f"enabled={en!r} 非法（应为 True/False 布尔值；"
                    f"写字符串 'False' 会因 `is False` 判定不成立而失效）")

    kind = job.get("kind", "daily")
    if kind not in VALID_KINDS:
        errs.append(f"kind={kind!r} 非法（可选 {'/'.join(VALID_KINDS)}）")

    at_raw = job.get("at", "01:00")
    if _parse_hm(at_raw) is None:
        errs.append(f"at={at_raw!r} 非法（应为 HH:MM，例 01:00）")

    for key in ("valid_from", "valid_until"):
        v = job.get(key)
        if v is None:
            continue
        try:
            date.fromisoformat(str(v))
        except ValueError:
            errs.append(f"{key}={v!r} 非法（应为 YYYY-MM-DD）")

    vf, vu = job.get("valid_from"), job.get("valid_until")
    if vf and vu and str(vf) > str(vu):
        errs.append(f"valid_from({vf}) 晚于 valid_until({vu})，有效期为空 -> 永远不会执行")

    mr = job.get("max_runs")
    if mr is not None and (isinstance(mr, bool) or not isinstance(mr, int) or mr <= 0):
        errs.append(f"max_runs={mr!r} 非法（应为正整数或 None）")

    to = job.get("timeout")
    if to is not None and (isinstance(to, bool) or not isinstance(to, (int, float)) or to <= 0):
        errs.append(f"timeout={to!r} 非法（应为正数秒）")

    wd = job.get("weekday")
    if wd is not None:
        if isinstance(wd, bool) or not isinstance(wd, int) or not 0 <= wd <= 6:
            errs.append(f"weekday={wd!r} 非法（应为 0..6 的整数，0=周一）")
        elif kind != "weekly":
            errs.append(f"weekday={wd} 仅在 kind='weekly' 时生效，"
                        f"当前 kind={kind!r} -> 会被静默忽略")

    cmd = job.get("command")
    if not isinstance(cmd, (list, tuple)) or not cmd or not all(isinstance(c, str) for c in cmd):
        errs.append("command 非法（应为非空字符串列表，例 ['tools/close_expired_orders.py']）")
    elif not cmd[0].endswith(".py"):
        errs.append(f"command[0]={cmd[0]!r} 不是 .py 脚本"
                    f"（调度器固定用 sys.executable 运行它）")
    elif os.path.isabs(cmd[0]):
        errs.append(f"command[0]={cmd[0]!r} 是绝对路径（应写仓库内相对路径，"
                    f"如 tools/xxx.py；绝对路径在换服务器/换目录后必失效）")

    return errs


def validate_jobs(jobs=None) -> dict:
    """校验全部任务 -> {任务名: [错误...]}（只含配置有误的任务）

    另外检查两处整体性问题：任务重名（state 会互相覆盖）、无启用任务。
    """
    jobs = JOBS if jobs is None else jobs
    bad: dict[str, list[str]] = {}
    seen: dict[str, int] = {}
    for job in jobs:
        name = (job.get("name") if isinstance(job, dict) else None) or "?"
        errs = validate_job(job)
        if name in seen:
            errs.append(f"任务名重复（第 {seen[name]} 与当前定义同名）-> "
                        f"状态 (.scheduler_state.json) 会互相覆盖")
        seen.setdefault(name, len(seen) + 1)
        if errs:
            # 合并而非覆盖：同名任务的两份错误都要能看见
            bad[name] = bad.get(name, []) + errs
    return bad


def _job_due(job, now, st):
    if job.get("enabled") is False:
        return False, "已停用（enabled=False）"
    try:
        vf = date.fromisoformat(job["valid_from"]) if job.get("valid_from") else None
        vu = date.fromisoformat(job["valid_until"]) if job.get("valid_until") else None
    except ValueError:
        # 不再抛异常：非法日期曾让整轮调度中断（见文件头「配置写错的代价」）
        return False, (f"配置错误：valid_from/valid_until 日期非法"
                       f"（{job.get('valid_from')!r}/{job.get('valid_until')!r}，应为 YYYY-MM-DD）")
    if vf and now.date() < vf:
        return False, "未到 valid_from"
    if vu and now.date() > vu:
        return False, "已过 valid_until"
    mr = job.get("max_runs")
    if mr is not None and st.get("run_count", 0) >= mr:
        return False, "已达 max_runs"
    at = _parse_hm(job.get("at", "01:00"))
    if at is None:
        return False, f"配置错误：at={job.get('at')!r} 非法（应为 HH:MM）"
    if now.time() < at:
        return False, "未到 at 时刻"
    kind = job.get("kind", "daily")
    last = st.get("last_run")
    last_dt = datetime.fromisoformat(last) if last else None
    if kind == "daily":
        if last_dt and last_dt.date() == now.date():
            return False, "今日已运行"
        return True, ""
    if kind == "weekly":
        wd = job.get("weekday")
        if wd is not None and now.weekday() != wd:
            return False, "非指定星期"
        if last_dt and last_dt.isocalendar()[:2] == now.isocalendar()[:2]:
            return False, "本周已运行"
        return True, ""
    if kind == "once":
        if last_dt:
            return False, "已运行一次"
        return True, ""
    return False, f"配置错误：kind={kind!r} 非法（可选 {'/'.join(VALID_KINDS)}）"


def _run_job(job, now):
    cmd = [sys.executable, os.path.join(REPO_ROOT, job["command"][0]), *job["command"][1:]]
    print(f"[{now.isoformat()}] 运行任务 {job['name']}: {' '.join(cmd)}", flush=True)
    try:
        r = subprocess.run(
            cmd, cwd=REPO_ROOT, timeout=job.get("timeout", 7200),
            capture_output=True, text=True,
        )
        out = (r.stdout + r.stderr)[-2000:]
        ok = r.returncode == 0
        print(f"    返回码={r.returncode}\n{out}", flush=True)
        return ok, out
    except Exception as e:  # noqa: BLE001
        print(f"    异常: {e}", flush=True)
        return False, str(e)


def _acquire_lock() -> bool:
    """单实例锁：防止 cron 每 15 分钟触发时，上一个长任务还没跑完就再起一个进程。

    锁文件存 PID；若 PID 对应的进程仍存活 → 已有实例在跑，本次跳过；
    PID 无效/进程已退出（陈旧锁）→ 清理后重新占用。
    """
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)  # 进程存活则不抛异常
            print(f"[scheduler] 已有实例运行中（pid={pid}），本次跳过", flush=True)
            return False
        except (ValueError, OSError):
            try:
                os.remove(LOCK_FILE)  # 陈旧锁：进程已退出
            except OSError:
                pass
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except OSError as e:
        print(f"[scheduler] 无法创建锁文件: {e}", flush=True)
        return False


def _release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError:
        pass


def _mark_config_error(state, name, errs):
    """把「配置有误」记进 state（不写 last_run —— 任务并未真正执行）

    只写 last_status/last_error，便于 `tools/ops_check.py --state` 事后发现
    「某个任务连续多日因配置错误被跳过」。
    """
    st = state.get(name, {})
    st["last_status"] = "config_error"
    st["last_error"] = "; ".join(errs)[:500]
    state[name] = st
    _save_state(state)


def run_due_jobs():
    now = datetime.now()
    if not _acquire_lock():
        return
    try:
        state = _load_state()

        # 先做配置体检：有误的任务只跳过自己。
        # 历史教训：一个写错的 at（如 "25:99"）会让 _job_due 抛 ValueError 冒泡出本函数
        # -> 整轮调度中断 -> 排在它之后的任务永久停摆（cron 每次重跑都崩在同一处）。
        bad = validate_jobs()
        if bad:
            print("!" * 68, flush=True)
            print("[scheduler] 任务配置有误：以下任务本次跳过，请修复 tools/scheduler.py 后重试",
                  flush=True)
            for name, errs in bad.items():
                for e in errs:
                    print(f"    ✗ {name}: {e}", flush=True)
            print("    校验命令：python tools/ops_check.py", flush=True)
            print("!" * 68, flush=True)

        for job in JOBS:
            name = job.get("name", "?")
            if name in bad:
                _mark_config_error(state, name, bad[name])
                continue
            st = state.get(name, {})
            try:
                due, reason = _job_due(job, now, st)
            except Exception as e:  # noqa: BLE001  兜底：任何判定异常都不得终止整轮调度
                print(f"[{now.isoformat()}] 任务 {name} 判定异常：{type(e).__name__}: {e}",
                      flush=True)
                st["last_status"] = "judge_error"
                st["last_error"] = f"{type(e).__name__}: {e}"[:500]
                state[name] = st
                _save_state(state)
                continue
            if not due:
                print(f"[{now.isoformat()}] 跳过 {name}: {reason}", flush=True)
                if "配置错误" in reason:
                    _mark_config_error(state, name, [reason])
                continue
            ok, out = _run_job(job, now)
            st["last_run"] = now.isoformat()
            st["run_count"] = st.get("run_count", 0) + 1
            st["last_status"] = "ok" if ok else "fail"
            st["last_output"] = out[-500:]
            state[name] = st
            _save_state(state)
        print(f"[{now.isoformat()}] 调度检查完成", flush=True)
    finally:
        _release_lock()


if __name__ == "__main__":
    run_due_jobs()
