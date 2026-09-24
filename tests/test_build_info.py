"""前端构建溯源与「前后端契约」检查的测试（tools/build_info.py + preflight 接入）

覆盖两类真实故障（都会"静默"发生）：
1. 前端源码改了但 dist 没重建 → 线上一直跑旧界面，且没有任何提示；
2. 接口改名/删除后前端没跟上 → 线上 404，按钮点了没反应。

另外用静态断言守住部署闸门的顺序：自检必须在 `systemctl restart` **之前**
（2026-09-24 事故就是"检查在重启之后"，坏版本已经被换上才报错）。
"""
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy.sh"


def _load(name: str, rel: str):
    """按路径加载脚本（与 preflight 里的加载方式一致 —— 也顺带验证它不会因注解解析崩）"""
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bi():
    return _load("build_info_under_test", "tools/build_info.py")


@pytest.fixture(scope="module")
def pf():
    return _load("preflight_under_test", "tools/preflight.py")


def _make_app(tmp_path: Path, project: str = "web") -> tuple:
    """造一个最小前端工程（目录名必须是 web/admin —— 输入清单按工程名匹配）"""
    app = tmp_path / "app"
    (app / "tools").mkdir(parents=True)
    shutil.copy(ROOT / "tools" / "build_info.py", app / "tools" / "build_info.py")
    proj = app / project
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "a.js").write_text("// a\n", encoding="utf-8")
    (proj / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (proj / "package.json").write_text("{}\n", encoding="utf-8")
    (proj / "dist" / "assets").mkdir(parents=True)
    (proj / "dist" / "index.html").write_text(
        '<script type="module" src="/assets/main.js"></script>\n', encoding="utf-8")
    (proj / "dist" / "assets" / "main.js").write_text(
        'fetch("/api/level/summary");fetch(`/api/im/chats/${id}/messages`);'
        'const x="/api";\n', encoding="utf-8")
    return app, proj


# ── 源码指纹 ──

def test_fingerprint_stable_and_counts_inputs(bi, tmp_path):
    _app, proj = _make_app(tmp_path)
    fp1, n1, d1 = bi.source_fingerprint(proj)
    fp2, n2, d2 = bi.source_fingerprint(proj)
    assert fp1 == fp2 and n1 == n2 and d1 == d2
    # 输入清单要包含 vite 会原样搬进 dist 的入口与配置，不只是 src/
    assert {"src/a.js", "index.html", "package.json"} <= set(d1)


def test_fingerprint_detects_content_change(bi, tmp_path):
    _app, proj = _make_app(tmp_path)
    fp1, _, _ = bi.source_fingerprint(proj)
    (proj / "index.html").write_text("<!doctype html><!-- 改了标题 -->\n", encoding="utf-8")
    fp2, _, _ = bi.source_fingerprint(proj)
    assert fp1 != fp2, "index.html 改动必须改变指纹（原 mtime 判据正是漏了这类输入）"


def test_changed_sources_reports_add_modify_delete(bi, tmp_path):
    _app, proj = _make_app(tmp_path)
    info = bi.write_build_info(proj)
    (proj / "src" / "a.js").write_text("// a changed\n", encoding="utf-8")
    (proj / "src" / "b.js").write_text("// b\n", encoding="utf-8")
    (proj / "package.json").unlink()
    changed = bi.changed_sources(proj, info)
    assert "修改 src/a.js" in changed
    assert "新增 src/b.js" in changed
    assert "删除 package.json" in changed


def test_fingerprint_ignores_non_build_dirs(bi, tmp_path):
    _app, proj = _make_app(tmp_path)
    fp1, _, _ = bi.source_fingerprint(proj)
    nm = proj / "src" / "node_modules" / "x"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("noise\n", encoding="utf-8")
    fp2, _, _ = bi.source_fingerprint(proj)
    assert fp1 == fp2, "node_modules 不参与构建，不应影响指纹（否则每次 npm ci 都会触发重建）"


# ── needs_build 三态 ──

def test_needs_build_states(bi, tmp_path):
    _app, proj = _make_app(tmp_path)

    need, why = bi.needs_build(proj)
    assert need and "缺少构建信息" in why, "有 dist 但无溯源信息时必须重建一次以收敛"

    bi.write_build_info(proj)
    need, why = bi.needs_build(proj)
    assert not need and "源码未变" in why

    (proj / "src" / "a.js").write_text("// a changed\n", encoding="utf-8")
    need, why = bi.needs_build(proj)
    assert need and "src/a.js" in why, "原因里要能直接看出是哪个源文件变了"


def test_needs_build_without_dist(bi, tmp_path):
    _app, proj = _make_app(tmp_path)
    shutil.rmtree(proj / "dist")
    need, why = bi.needs_build(proj)
    assert need and "尚无构建产物" in why


def test_build_info_roundtrip_and_corrupt(bi, tmp_path):
    _app, proj = _make_app(tmp_path)
    info = bi.write_build_info(proj, note="unit")
    assert info["schema"] == bi.SCHEMA and info["note"] == "unit"
    assert bi.read_build_info(proj)["source_hash"] == info["source_hash"]
    bi.build_info_path(proj).write_text("{ 坏 JSON", encoding="utf-8")
    assert bi.read_build_info(proj) is None, "损坏的溯源信息按“无信息”处理，不能让部署链路抛异常"


# ── 产物扫描与路径匹配 ──

def test_scan_api_paths(bi, tmp_path):
    _app, proj = _make_app(tmp_path)
    paths = bi.scan_api_paths(proj / "dist")
    assert "/api/level/summary" in paths
    # 模板串被截断成静态前缀，交给前缀匹配（见 route_exists）
    assert "/api/im/chats/" in paths
    assert "/api" not in paths, "无信息量的候选要被过滤"


@pytest.mark.parametrize("front,expected", [
    ("/api/level/summary", True),                       # 精确
    ("/api/level/summary/", True),                      # 尾斜杠
    ("/api/novel/12/read", True),                       # 前端写死 id vs /api/novel/{novel_id}/read
    ("/api/im/chats/", True),                           # 模板串截断 → 前缀
    ("/api/im/chats/7/messages", True),                 # 参数段通配
    ("/api/level/summary-v2", False),                   # 接口改名后前端没跟上
    ("/api/legacy/gone", False),
])
def test_route_exists(bi, front, expected):
    # 注：裸 "/api" 走前缀匹配会命中任何路由，故在 api_paths_missing 里按 API_TRIVIAL 过滤
    # （见 test_api_paths_missing_only_reports_absent）
    routes = {"/api/level/summary", "/api/novel/{novel_id}/read",
              "/api/im/chats/{chat_id}/messages"}
    assert bi.route_exists(front, routes) is expected


def test_api_paths_missing_only_reports_absent(bi):
    routes = {"/api/level/summary"}
    missing = bi.api_paths_missing(
        ["/api/level/summary", "/api/level/summary-removed", "/api"], routes)
    assert missing == ["/api/level/summary-removed"]


def test_dump_api_paths_failure_is_graceful(bi, tmp_path):
    _app, proj = _make_app(tmp_path)
    routes, note = bi.dump_api_paths(str(tmp_path / "no-such-python"), _app)
    assert routes == set() and "无法执行" in note, "导不出路由表必须降级而不是抛异常（否则会拦住部署）"


# ── preflight 接入 ──

def _names(findings, level=None):
    return [f.name for f in findings if level is None or f.level == level]


def test_contract_missing_build_info_warns(pf, tmp_path):
    app, _proj = _make_app(tmp_path)
    out = pf.check_frontend_contract(app, sys.executable, routes={"/api/x"})
    assert "主站前端构建溯源缺失" in _names(out, "warn")


def test_contract_ok_when_fresh_and_matched(pf, tmp_path):
    app, proj = _make_app(tmp_path)
    spec = importlib.util.spec_from_file_location("bi_side", app / "tools" / "build_info.py")
    bi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bi)
    bi.write_build_info(proj)
    out = pf.check_frontend_contract(app, sys.executable,
                                     routes={"/api/level/summary", "/api/im/chats/{chat_id}/messages"})
    assert not _names(out, "warn"), f"不该有告警：{_names(out, 'warn')}"
    assert "前后端契约" in _names(out, "ok")


def test_contract_detects_stale_dist_and_skips_contract(pf, tmp_path):
    app, proj = _make_app(tmp_path)
    spec = importlib.util.spec_from_file_location("bi_side2", app / "tools" / "build_info.py")
    bi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bi)
    bi.write_build_info(proj)
    (proj / "src" / "a.js").write_text("// changed after build\n", encoding="utf-8")
    out = pf.check_frontend_contract(app, sys.executable, routes={"/api/level/summary"})
    warns = _names(out, "warn")
    assert "主站前端产物过期" in warns
    assert not any("契约" in n for n in warns), "过期产物跳过契约比对，避免用旧产物误导"


def test_contract_detects_mismatch(pf, tmp_path):
    app, proj = _make_app(tmp_path)
    spec = importlib.util.spec_from_file_location("bi_side3", app / "tools" / "build_info.py")
    bi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bi)
    info = bi.write_build_info(proj)
    info["api_paths"] = ["/api/level/summary", "/api/study/plan-removed"]
    bi.build_info_path(proj).write_text(__import__("json").dumps(info), encoding="utf-8")
    out = pf.check_frontend_contract(app, sys.executable, routes={"/api/level/summary"})
    bad = [f for f in out if f.name == "前后端契约错位"]
    assert bad and "/api/study/plan-removed" in bad[0].detail
    assert bad[0].level == "warn", "契约错位不影响服务启动，按 WARN 处理（闸门只拦会致挂的项）"


def test_run_stage_gating(pf, tmp_path):
    app, _proj = _make_app(tmp_path)
    early = _names(pf.run(app, sys.executable, stage="early", routes={"/api/x"}))
    assert not any("前端" in n for n in early), "early 阶段（构建前）不该做产线检查"
    full = _names(pf.run(app, sys.executable, stage="full", routes={"/api/x"}))
    assert any("前端" in n for n in full) and any("资源" in n for n in full)


# ── 入口资源完整性（白屏防线）──

def test_dist_assets_detects_missing_file(pf, tmp_path):
    app, proj = _make_app(tmp_path)
    (proj / "dist" / "assets" / "main.js").unlink()
    out = pf.check_dist_assets(app)
    bad = [f for f in out if f.level == "warn"]
    assert bad and "不存在" in bad[0].detail


def test_dist_assets_handles_admin_prefix(pf, tmp_path):
    app, proj = _make_app(tmp_path, project="admin")
    (proj / "dist" / "index.html").write_text(
        '<script src="/admin/assets/index-abc.js"></script>\n', encoding="utf-8")
    (proj / "dist" / "assets" / "index-abc.js").write_text("// ok\n", encoding="utf-8")
    out = pf.check_dist_assets(app)
    assert "管理后台资源完整" in _names(out, "ok"), f"admin 产物用 /admin/assets 前缀：{out}"


def test_dist_assets_warns_on_no_reference(pf, tmp_path):
    app, proj = _make_app(tmp_path)
    (proj / "dist" / "index.html").write_text("<html><body>没有脚本</body></html>\n",
                                              encoding="utf-8")
    assert "主站前端资源引用" in _names(pf.check_dist_assets(app), "warn")


# ── 部署脚本结构：闸门必须在重启之前 ──

def test_deploy_gates_precede_restart():
    text = DEPLOY.read_text(encoding="utf-8")
    restart = text.index("systemctl restart ${APP_NAME}")
    assert text.count("preflight.py") >= 2
    early = text.index('--stage early')
    full = text.index('--stage full')
    assert early < restart and full < restart, "前置自检必须在 restart 之前跑（2026-09-24 事故的根因）"
    assert early < full


def test_deploy_uses_fingerprint_judgement_and_records_info():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "needs-build" in text, "构建判据要改用源码指纹"
    assert text.count('build_info.py" write --dir') == 2, "web/admin 构建后都要记录溯源信息"
    assert "mtime 判据" in text, "必须保留兜底路径（工具缺失时不能让部署链断掉）"
