"""项目回归自检：一次跑完「不会报错但会静默失效」的静态一致性检查

用途
----
每次改动后、提交前跑一遍。单元测试只能证明「被覆盖的逻辑是对的」，
下面这几类问题 pytest 抓不到：

- **跨域直连**：绕过 `contracts.py` 直接 import 别的域的服务（`.importlinter` 才管）；
- **前后端契约错位**：后端返回 `id` 而前端读 `user_id`、前端请求了不存在的路径
  （页面不报错，只是按钮静默失效 —— 本项目真实踩过 IM 私聊/加好友全废）；
- **图标缺失**：`nav.js` 写了 `icon: 'xxx'` 但 `AppIcon.ICONS` 没定义，静默回落 placeholder；
- **路由漏注册**：新模块忘记 `app.include_router`，全部 404；
- **依赖未声明**：代码模块级硬导入了某个包，但 `requirements.txt` 没写
  —— 本地因为跑测试多装了包所以正常，**线上启动即崩**（2026-09-24 真实事故：
  weather.py 改用 httpx 未同步清单，线上 `ModuleNotFoundError` 全站 502）；
- **上线运维资产缺陷**：定时任务（`tools/scheduler.py`，线上 cron 每 15 分钟跑）
  配置笔误、command 指向的脚本被删/改名/忘记 `git add`、脚本依赖未声明 ——
  调度器**没有告警通道**，这些故障的症状就是「什么都不发生」（订单不关单、
  会员不降级、红包不退回），可安静积累成业务数据错误。

注意：`app.routes` 在本项目使用的 FastAPI 版本里，`include_router` 是**惰性**的
（元素是 `_IncludedRouter`，`path` 为 None），直接遍历拿不到路径。
必须走 `app.openapi()["paths"]` 才能拿到展开后的完整路由表 —— 这里踩过坑。

检查项编号只标序号（不写 /N），新增检查项时只需在末尾追加，不必回来改前面的编号。

用法
----
    .venv/Scripts/python.exe tools/regression_check.py

退出码 0 = 全部通过；非 0 = 有失败项（便于脚本/CI 判定）。
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
LINT = str(ROOT / ".venv" / "Scripts" / "lint-imports.exe")
WEB_SRC = ROOT / "web" / "src"

# 关键路由：四项新功能（A 签到 / B 成就 / C 等级 / D 收藏）必须存在
KEY_ROUTES = ["/api/checkin", "/api/favorites", "/api/badges", "/api/level"]

METHODS = ("get", "post", "put", "delete")
failures = []


def ok(name: str, detail: str = ""):
    print(f"  [PASS] {name}" + (f" —— {detail}" if detail else ""))


def bad(name: str, detail: str):
    failures.append(name)
    print(f"  [FAIL] {name} —— {detail}")


# ── 1. 域契约（import-linter）──
def check_contracts():
    print("\n[1] 域契约（import-linter）")
    if not Path(LINT).exists():
        bad("域契约", f"未找到 {LINT}")
        return
    r = subprocess.run([LINT], cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = [l for l in (r.stdout or "").splitlines() if "Contracts:" in l]
    if r.returncode == 0:
        ok("域契约", tail[-1].strip() if tail else "通过")
    else:
        bad("域契约", f"存在 broken 契约（退出码 {r.returncode}）：\n{r.stdout}")


# ── 2. 全量语法编译 ──
def check_compile():
    print("\n[2] 全量语法编译（app/ tools/ tests/）")
    r = subprocess.run([PY, "-m", "compileall", "-q", "app", "tools", "tests"],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode == 0:
        ok("语法编译")
    else:
        bad("语法编译", (r.stdout or "") + (r.stderr or ""))


# ── 3. 依赖完整性（代码硬导入 vs requirements.txt）──
def check_dependencies():
    print("\n[3] 依赖完整性（启动期硬导入 vs requirements.txt）")
    try:
        # 按路径加载同目录的审计模块（不依赖 cwd / 是否作为包运行）
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "dep_audit", ROOT / "tools" / "dep_audit.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:                       # pragma: no cover
        bad("依赖完整性", f"无法加载 tools/dep_audit.py：{e}")
        return

    result = mod.audit([ROOT / "app"])
    st = result["stats"]
    if result["errors"]:
        detail = "; ".join(f"{e['module']} <- {e['files'][0]}" for e in result["errors"])
        bad("依赖完整性", f"{len(result['errors'])} 个包未在 requirements.txt 声明，"
                          f"线上会启动失败：{detail}")
    else:
        ok("依赖完整性", f"{st['files_scanned']} 个文件扫描，"
                        f"启动期硬依赖 {st['third_party_modules']} 个第三方模块全部已声明")
    if result["warnings"]:
        print(f"         提示：{len(result['warnings'])} 个模块归属无法判定"
              f"（本地未安装），需人工确认：{[w['module'] for w in result['warnings']]}")


# ── 4 & 6. 路由一致性（OpenAPI 表 vs 前端 URL）+ 关键路由存在性 ──
def load_paths():
    """取展开后的完整路由表（必须经 openapi()，见模块 docstring 的说明）"""
    from app.main import app
    return app.openapi().get("paths", {})


def _norm(p: str) -> str:
    """参数段统一写成 {}：归一化 {gid}/{cid}，也归一化前端示例里的纯数字段"""
    p = re.sub(r"\{[^}]+\}", "{}", p)
    return re.sub(r"/\d+(?=/|$)", "/{}", p)


def check_key_routes(paths):
    print("\n[4] 关键路由注册（四项新功能端点）")
    missing = [t for t in KEY_ROUTES if not any(p.startswith(t) for p in paths)]
    if missing:
        bad("关键路由", f"未注册：{missing}")
    else:
        detail = ", ".join(f"{t}({sum(1 for p in paths if p.startswith(t))}条)"
                           for t in KEY_ROUTES)
        ok("关键路由", detail)


def check_frontend_urls(paths):
    print("\n[5] 前端请求路径 vs 后端路由")
    have = {(_norm(p), m.upper()) for p in paths for m in paths[p] if m in METHODS}
    # 匹配 web/src 下形如 '/api/...' / `/api/...${x}` 的字面量
    pat = re.compile(r"""['"`](/api/[A-Za-z0-9_\-/{}.$]*)['"`]""")
    files = sorted(list(WEB_SRC.rglob("*.js")) + list(WEB_SRC.rglob("*.vue")))
    # 动态拼接的前缀（'/api/xx/' 后接变量）无法静态判断，单独列出供人工确认
    dynamic, unmatched = [], []
    for f in files:
        txt = f.read_text(encoding="utf-8", errors="ignore")
        for raw in sorted(set(pat.findall(txt))):
            if raw.endswith("/"):        # 拼接前缀，非完整路径
                dynamic.append((f.name, raw))
                continue
            norm = re.sub(r"\$\{[^}]*\}", "{}", raw)   # ${id} -> {}
            if not any(_norm(p) == norm for p in paths):
                unmatched.append((f.name, raw))
    if unmatched:
        bad("前端路径", f"{len(unmatched)} 处找不到对应后端路由：{unmatched[:8]}")
    else:
        ok("前端路径", f"{len(files)} 个文件全部匹配")
    if dynamic:
        print(f"         提示：{len(dynamic)} 处为拼接前缀，需人工确认拼接结果，"
              f"如 {dynamic[:3]}")


def check_icons():
    print("\n[6] 导航图标完整性（nav.js vs AppIcon.ICONS）")
    nav_f = WEB_SRC / "nav.js"
    ico_f = WEB_SRC / "components" / "AppIcon.vue"
    if not nav_f.exists() or not ico_f.exists():
        bad("导航图标", "nav.js 或 AppIcon.vue 不存在")
        return
    nav_txt = nav_f.read_text(encoding="utf-8", errors="ignore")
    ico_lines = ico_f.read_text(encoding="utf-8", errors="ignore").splitlines()
    used = {m for m in re.findall(r"icon:\s*'([^']+)'", nav_txt)}

    # 只取 `const ICONS = {` 到顶层 `}` 之间，避免把 export default 的
    # name/props/computed 等 Vue 选项误当成图标键（取固定字符数会带进这类噪音）
    start = next((i for i, l in enumerate(ico_lines) if re.match(r"^const ICONS\s*=", l)), None)
    if start is None:
        bad("导航图标", "未找到 `const ICONS = {` 定义")
        return
    end = next((i for i in range(start + 1, len(ico_lines)) if re.match(r"^\}", ico_lines[i])),
               len(ico_lines))
    defined = set(re.findall(r"^\s{2}([A-Za-z0-9_]+)\s*:", "\n".join(ico_lines[start:end + 1]), re.M))

    missing = sorted(used - defined)
    if missing:
        bad("导航图标", f"nav 引用但未定义（会回落 placeholder）：{missing}")
    else:
        ok("导航图标", f"引用 {len(used)} 个，全部已定义（ICONS 共 {len(defined)} 个）")


def check_ops():
    print("\n[7] 上线运维资产（定时任务配置 / 脚本依赖 / 运行时文件）")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ops_check", ROOT / "tools" / "ops_check.py")
        mod = importlib.util.module_from_spec(spec)
        # 必须注册进 sys.modules：ops_check 内部还会按路径加载别的模块
        sys.modules["ops_check"] = mod
        spec.loader.exec_module(mod)
    except Exception as e:                       # pragma: no cover
        bad("运维资产", f"无法加载 tools/ops_check.py：{e}")
        return

    result = mod.run()
    j = result["jobs"]
    errors = [i for i in result["items"] if i["level"] == "error"]
    if errors:
        detail = "; ".join(f"{i['title']}（{i['detail']}）" for i in errors)
        bad("运维资产", f"{len(errors)} 个错误 -> {detail[:280]}")
    else:
        ok("运维资产", f"任务 {j['total']} 个（启用 {j['enabled']} / 停用 {j['disabled']}）："
                      f"配置合法、脚本存在且依赖已声明")
    for i in result["items"]:
        if i["level"] == "warn":
            print(f"         提示：[{i['title']}] {i['detail'][:110]}")


def main() -> int:
    print("=" * 68)
    print("项目回归自检")
    print("=" * 68)
    check_contracts()
    check_compile()
    check_dependencies()
    paths = load_paths()
    print(f"\n      （后端路由总数 = {len(paths)}）")
    check_key_routes(paths)
    check_frontend_urls(paths)
    check_icons()
    check_ops()

    print("\n" + "=" * 68)
    if failures:
        print(f"结论：{len(failures)} 项失败 -> {failures}")
        print("=" * 68)
        return 1
    print("结论：全部通过")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
