"""依赖完整性回归：app/ 的启动期硬导入必须都在 requirements.txt 里声明

背景（真实线上事故，2026-09-24）
--------------------------------
commit `7c7592c` 把 `weather.py` 从 requests 改成 httpx 异步（消除线程池阻塞，
改动本身是对的），但**没有同步 requirements.txt**。结果：

- 本地 `.venv` 因为跑测试装了 httpx（starlette 的 TestClient 依赖它）→ 一切正常；
- 线上 `deploy.sh` 只 `pip install -r requirements.txt` → 没有 httpx；
- uvicorn 启动即崩：`ModuleNotFoundError: No module named 'httpx'`，
  崩在 `app/main.py:24` 的 platform 路由导入处（其中包含 weather）→ 全站 502。

**这类问题常规单元测试抓不到**，因为本地环境天然比别人多装了包（测试依赖）。
所以单独加一条「清单完整性」断言：以后新增第三方依赖忘了写 requirements.txt，
pytest 会立刻变红，而不是等到线上启动失败才发现。

审计实现见 `tools/dep_audit.py`（只认「模块级、非 try、非 TYPE_CHECKING」的硬导入，
函数内或 try 内的优雅降级导入不算）。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_audit():
    """按路径加载 tools/dep_audit.py（tools/ 不是包，不能直接 import）"""
    spec = importlib.util.spec_from_file_location("dep_audit", ROOT / "tools" / "dep_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_app_hard_imports_all_declared():
    """app/ 全部启动期硬导入，都能在 requirements.txt 找到对应发行包"""
    audit = _load_audit()
    result = audit.audit([ROOT / "app"])

    detail = "\n".join(
        f"  ✗ {e['module']}（发行包 {e['dist']}）被以下位置模块级导入：\n"
        + "\n".join(f"      {f}" for f in e["files"])
        for e in result["errors"]
    )
    assert not result["errors"], (
        "以下依赖被硬导入但 requirements.txt 未声明 —— 线上 deploy.sh 按清单装包，会启动失败：\n"
        f"{detail}\n\n"
        "修复：把对应包（含版本）加进 requirements.txt；"
        "若该依赖确实是可选的，请改为在 try/except 中导入以优雅降级。"
    )


def test_detector_catches_missing_httpx(tmp_path):
    """守卫守卫：把 httpx 从清单里删掉后，审计**必须**报出来

    这条用来证明上面的断言不是「永远通过」的摆设 —— 它复刻 2026-09-24 线上故障的
    前置状态（requirements 缺 httpx，而 weather.py 模块级 import httpx），
    要求审计精确定位到 weather.py。
    """
    audit = _load_audit()
    raw = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    stripped = "\n".join(l for l in raw.splitlines() if not l.startswith("httpx=="))
    fake_req = tmp_path / "requirements.txt"
    fake_req.write_text(stripped, encoding="utf-8")

    result = audit.audit([ROOT / "app"], requirements=fake_req)
    flagged = {e["module"] for e in result["errors"]}
    assert "httpx" in flagged, f"审计未能发现缺失的 httpx，检出：{flagged}"
    files = " ".join(f for e in result["errors"] if e["module"] == "httpx" for f in e["files"])
    assert "weather.py" in files, f"应精确定位到 weather.py:15，实际：{files}"


def test_optional_guarded_imports_not_flagged():
    """优雅降级的可选依赖不算错误（否则审计会被误报淹没、失去意义）

    `bs4` 在 paper_crawler/question_parser 里是「函数内 + try/except + `_BS4 = False` 兜底」，
    缺失时功能降级而非崩溃，属于设计如此 —— 审计不得把它报成启动期硬依赖。
    """
    audit = _load_audit()
    result = audit.audit([ROOT / "app"])
    flagged = {e["module"] for e in result["errors"]} | {w["module"] for w in result["warnings"]}
    assert "bs4" not in flagged, (
        "bs4 是按优雅降级方式导入的可选依赖（try/except + 兜底），不应被判定为硬依赖"
    )
