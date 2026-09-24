"""部署前置自检的行为回归（tools/preflight.py）

为什么值得单独测
----------------
`preflight.py` 是「部署的最后一道闸」：它判定不通过时 deploy.sh 会中止部署。
它本身出错有两种后果都很糟：
- **漏报**（该拦的没拦）→ 坏版本被推上线，全站 502（就是 2026-09-24 的事故）；
- **误报**（不该拦的拦了）→ 正常部署被卡住，运维会绕过它，闸门形同虚设。

所以这里既测「能拦住」，也测「不误拦」，以及两种诊断提示不要混淆：
「清单里没声明」vs「声明了但没装进这个解释器」——两者修法完全不同。
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_preflight():
    """按路径加载 tools/preflight.py（tools/ 不是包，不能直接 import）"""
    spec = importlib.util.spec_from_file_location("preflight", ROOT / "tools" / "preflight.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 阻断：能拦住 ──

def test_missing_env_file_blocks(tmp_path):
    """没有 .env 必须阻断（服务连不上数据库）"""
    pf = _load_preflight()
    findings = pf.check_env(tmp_path)
    assert any(f.level == "block" for f in findings), "缺少 .env 时应阻断"


def test_env_missing_db_keys_blocks(tmp_path):
    """DB_* 必需键缺失必须阻断；填好之后不得残留阻断项"""
    pf = _load_preflight()
    (tmp_path / ".env").write_text("DB_DRIVER=mysql\nDEEPSEEK_API_KEY=sk-x\n", encoding="utf-8")
    findings = pf.check_env(tmp_path)
    blocked = {f.name for f in findings if f.level == "block"}
    assert any("DB_HOST" in n for n in blocked), f"应报 DB_HOST 缺失，实际 {blocked}"
    assert any("DB_NAME" in n for n in blocked)

    (tmp_path / ".env").write_text(
        "DB_DRIVER=mysql\nDB_HOST=127.0.0.1\nDB_USER=u\nDB_NAME=db\nDB_PASSWORD=p\n",
        encoding="utf-8")
    assert not [f for f in pf.check_env(tmp_path) if f.level == "block"], "必需键齐备时不应阻断"


def test_broken_interpreter_blocks_without_crashing(tmp_path):
    """解释器路径无效时必须返回 BLOCK 结果，而不是抛异常把自检自己搞崩"""
    pf = _load_preflight()
    f = pf.check_import(ROOT, str(tmp_path / "no-such-python"))
    assert f.level == "block" and "无法执行" in f.detail


def test_report_exit_codes():
    """报告退出码：有 block -> 1；仅 ok/warn -> 0（deploy.sh 靠它决定是否中止）"""
    pf = _load_preflight()
    assert pf.report([pf.Finding("a", "ok"), pf.Finding("b", "warn")], "early") == 0
    assert pf.report([pf.Finding("a", "ok"), pf.Finding("b", "block")], "early") == 1


# ── 诊断提示：两种缺失原因不能混淆 ──

def _fake_missing(monkeypatch, pf, module_name):
    """让 check_import 认为缺了某个模块，返回产生的 Finding"""
    def fake_run(*a, **k):
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr=f"Traceback (most recent call last):\n"
                   f"ModuleNotFoundError: No module named '{module_name}'\n")
    monkeypatch.setattr(pf.subprocess, "run", fake_run)
    return pf.check_import(ROOT, sys.executable)


def test_hint_says_declare_when_dist_not_in_requirements(monkeypatch):
    """包名不在 requirements.txt -> 提示「漏声明」（本次线上事故的修法）"""
    pf = _load_preflight()
    f = _fake_missing(monkeypatch, pf, "definitely_not_a_real_pkg_xyz")
    assert f.level == "block"
    assert "漏声明" in f.hint, f"应提示补进清单，实际：{f.hint}"


def test_hint_says_install_when_dist_is_declared(monkeypatch):
    """包名已在 requirements.txt -> 提示「装了但没进这个 venv」（修法完全不同）"""
    pf = _load_preflight()
    f = _fake_missing(monkeypatch, pf, "httpx")
    assert f.level == "block"
    assert "已" in f.hint and "pip install" in f.hint, f"应提示装依赖，实际：{f.hint}"
    assert "漏声明" not in f.hint, "已声明的包不应被说成漏声明"


# ── 不误拦 ──

def test_repo_passes_preflight(monkeypatch):
    """当前仓库应通过 early 自检（否则正常部署会被自己拦住）"""
    pf = _load_preflight()
    monkeypatch.setattr(pf, "check_import", lambda *a, **k: pf.Finding("应用可导入", "ok"))
    findings = pf.run(ROOT, sys.executable, stage="early")
    assert not [f for f in findings if f.level == "block"], \
        f"正常仓库不应有阻断项：{[f.name for f in findings if f.level == 'block']}"


def test_stage_filtering(monkeypatch):
    """early 不查外部命令/产物（要快），full 才查；两者共用同一套阻断判定"""
    pf = _load_preflight()
    monkeypatch.setattr(pf, "check_import", lambda *a, **k: pf.Finding("应用可导入", "ok"))
    early = {f.name for f in pf.run(ROOT, sys.executable, stage="early")}
    full = {f.name for f in pf.run(ROOT, sys.executable, stage="full")}
    assert not any("外部命令" in n for n in early), f"early 不应包含外部命令检查：{early}"
    assert any("外部命令" in n for n in full), f"full 应包含外部命令检查：{full}"
    assert early <= full, "early 的检查项应是 full 的子集"


def test_optional_dependency_missing_is_warn_not_block():
    """外部命令缺失只降级不阻断（缺 ffmpeg 不该拦住整个部署）"""
    pf = _load_preflight()
    for f in pf.check_external_bins():
        assert f.level in ("ok", "warn"), f"外部命令 {f.name} 不应为阻断级"
