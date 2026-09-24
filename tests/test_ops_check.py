"""上线运维资产体检（tools/ops_check.py）与调度器容错的回归测试

背景：调度任务由线上 cron 每 15 分钟**静默执行**，没有告警通道。所以
「任务配置写错」「command 指向的脚本不存在 / 忘了 git add」「脚本依赖未声明」
这些问题的症状就是「什么都不发生」，可安静积累成业务数据错误（订单不关单、
会员不降级、红包不退回、周期账单不生成）。

本文件覆盖两件事：
1. **检测器真能抓到问题**（不能是永远通过的摆设）—— 每条检查都用注入的坏数据验证；
2. **检测器不误报** —— 停用任务的配置错误只算 warn、真实 JOBS 必须零错误；
3. **调度器容错** —— 一个任务配置写错时，只跳过它自己，**不拖垮整轮调度**
   （历史行为：非法 at 抛 ValueError 冒泡出 run_due_jobs，排在它之后的任务永久停摆）。
"""
import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


OPS = _load("t_ops_check", "tools/ops_check.py")
SCHED = OPS.SCHED


def _job(name, **kw):
    """构造一条任务定义（默认是合法的最小配置）"""
    base = {"name": name, "kind": "daily", "at": "01:00",
            "command": ["tools/close_expired_orders.py"]}
    base.update(kw)
    return base


def _titles(result, level):
    return [i["title"] for i in result["items"] if i["level"] == level]


# ── 1. 真实 JOBS 必须零错误（当前配置是健康的）──

def test_real_jobs_pass():
    result = OPS.run()
    assert result["errors"] == 0, (
        f"真实 JOBS 出现错误项：{[(i['title'], i['detail']) for i in result['items'] if i['level'] == 'error']}")
    assert result["jobs"]["total"] == len(SCHED.JOBS)


# ── 2. 检测能力：脚本不存在 ──

def test_missing_script_detected():
    jobs = [_job("ghost", command=["tools/definitely_not_a_real_script_xyz.py"])]
    result = OPS.run(jobs=jobs)
    assert result["errors"] >= 1, "脚本不存在却未报错 —— 检测器失效"
    assert any("脚本不存在" in t for t in _titles(result, "error"))


# ── 3. 检测能力：脚本未被 git 跟踪（线上 pull 不到）──
# 用 data/ 目录（已在 .gitignore 中）放置临时脚本，避免污染工作区

def test_untracked_script_detected():
    tmp_dir = ROOT / "data"
    tmp_dir.mkdir(exist_ok=True)
    rel = "data/_ops_check_tmp_script.py"
    f = ROOT / rel
    f.write_text("# 临时文件：未被 git 跟踪\n", encoding="utf-8")
    try:
        # 前置条件：确认它确实未被跟踪（否则本用例无意义）
        assert not OPS.is_tracked(rel), f"{rel} 竟然被跟踪了，用例前提不成立"
        result = OPS.run(jobs=[_job("untracked", command=[rel])])
        assert any("未被 git 跟踪" in t for t in _titles(result, "error")), (
            f"未跟踪脚本未报错：{result['items']}")
    finally:
        f.unlink(missing_ok=True)


# ── 4. 检测能力：脚本依赖未在 requirements.txt 声明（与全站 502 同源）──

def test_undeclared_dependency_detected():
    tmp_dir = ROOT / "data"
    tmp_dir.mkdir(exist_ok=True)
    script = ROOT / "data/_ops_check_tmp_dep.py"
    script.write_text("import httpx  # 模块级硬导入\n", encoding="utf-8")
    # 注入一份「删掉 httpx」的清单：模拟 2026-09-24 线上事故前的状态
    req = ROOT / "data/_ops_check_tmp_req.txt"
    full = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    req.write_text("\n".join(l for l in full.splitlines() if not l.startswith("httpx==")),
                   encoding="utf-8")
    try:
        result = OPS.run(jobs=[_job("depmiss", command=["data/_ops_check_tmp_dep.py"])],
                         requirements=req)
        errs = [i for i in result["items"] if i["level"] == "error"]
        assert any("依赖未声明" in i["title"] and "httpx" in i["detail"] for i in errs), (
            f"未声明依赖未报错：{result['items']}")
        # 反向确认：用真实清单时不应报错（说明检测不是无脑报错）
        ok = OPS.run(jobs=[_job("depmiss", command=["data/_ops_check_tmp_dep.py"])])
        assert not any("依赖未声明" in t for t in _titles(ok, "error")), (
            "httpx 已在 requirements.txt 声明，不该报错")
    finally:
        script.unlink(missing_ok=True)
        req.unlink(missing_ok=True)


# ── 5. 分级：启用任务的配置错误 = error；停用任务 = warn（不误报为阻断）──

def test_config_error_level_follows_enabled():
    jobs = [
        _job("live_bad", kind="dailly"),                    # 启用 + kind 拼错
        _job("offline_bad", kind="dailly", enabled=False),  # 停用 + kind 拼错
    ]
    result = OPS.run(jobs=jobs)
    assert any("live_bad" in t for t in _titles(result, "error")), \
        "启用任务的配置错误必须是 error（线上会静默跳过它）"
    assert any("offline_bad" in t for t in _titles(result, "warn")), \
        "停用任务的配置错误应为 warn（恢复启用时才会踩，不该阻断当前流程）"
    assert not any("offline_bad" in t for t in _titles(result, "error"))


# ── 6. 运行时文件必须留在 .gitignore 里（防止这份清单被删掉）──

def test_runtime_files_stay_gitignored():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for rel in OPS.RUNTIME_FILES:
        assert rel in text, (
            f"{rel} 必须留在 .gitignore 中：否则线上调度器生成它后工作区变脏，"
            f"一旦 git add -A 就把线上运行状态提交进仓库")
        assert OPS.is_ignored(rel), f"{rel} 未被 git 忽略"


# ── 7. 状态体检：失败 / 静默停摆 / 过期 / 残留 都要报出来 ──

def test_state_health_warnings(tmp_path):
    now = datetime(2026, 9, 24, 12, 0, 0)
    state = {
        "a_failed": {"last_run": (now - timedelta(hours=2)).isoformat(),
                     "run_count": 3, "last_status": "fail",
                     "last_output": "Traceback: boom"},
        "b_stale": {"last_run": (now - timedelta(days=4)).isoformat(),
                    "run_count": 9, "last_status": "ok"},
        "c_expired": {"last_run": (now - timedelta(hours=3)).isoformat(),
                      "run_count": 1, "last_status": "ok"},
        "d_capped": {"last_run": (now - timedelta(hours=3)).isoformat(),
                     "run_count": 30, "last_status": "ok"},
        "z_removed": {"last_run": now.isoformat(), "run_count": 1, "last_status": "ok"},
    }
    p = tmp_path / "state.json"
    p.write_text(json.dumps(state), encoding="utf-8")

    jobs = [
        _job("a_failed"),
        _job("b_stale"),
        _job("c_expired", valid_until="2026-09-01"),
        _job("d_capped", max_runs=30),
        _job("e_never_run"),                 # 状态里没有 -> 从未成功触发
    ]
    items = OPS.check_state(p, jobs, now=now)
    titles = [i["title"] for i in items]
    joined = " | ".join(titles)

    assert any("a_failed" in t and "失败" in t for t in titles), joined
    assert any("b_stale" in t and "未成功执行" in t for t in titles), joined
    assert any("c_expired" in t and "有效期" in t for t in titles), joined
    assert any("d_capped" in t and "上限" in t for t in titles), joined
    assert any("e_never_run" in t for t in titles), joined
    assert any("残留调度状态" in t and "z_removed" in t for t in titles), joined
    assert all(i["level"] == "warn" for i in items), "状态体检的问题都应是 warn 级"


def test_state_missing_and_corrupt(tmp_path):
    missing = OPS.check_state(tmp_path / "nope.json", [_job("x")])
    assert missing and missing[0]["level"] == "warn"

    bad = tmp_path / "broken.json"
    bad.write_text("{ not json", encoding="utf-8")
    items = OPS.check_state(bad, [_job("x")])
    assert items and items[0]["level"] == "error", "状态文件损坏应报 error（会导致任务重复执行）"


# ── 8. 调度器容错：非法配置返回「配置错误」而不是抛异常 ──

def test_job_due_tolerates_bad_config():
    now = datetime.now()
    for bad in ({"name": "x", "kind": "daily", "at": "25:99", "command": ["tools/x.py"]},
                {"name": "x", "kind": "daily", "at": "0100", "command": ["tools/x.py"]},
                {"name": "x", "kind": "daily", "at": "01:00",
                 "valid_from": "2026-13-45", "command": ["tools/x.py"]},
                {"name": "x", "kind": "dailly", "at": "01:00", "command": ["tools/x.py"]}):
        due, reason = SCHED._job_due(bad, now, {})   # 不允许抛异常
        assert due is False and "配置错误" in reason, (bad, due, reason)


def test_validate_job_catches_silent_traps():
    cases = {
        "kind 拼错": _job("x", kind="dailly"),
        "at 非法": _job("x", at="25:99"),
        "日期非法": _job("x", valid_from="2026-13-45"),
        "enabled 写成字符串": _job("x", enabled="False"),
        "weekday 用在 daily": _job("x", weekday=3),
        "weekday 越界": _job("x", kind="weekly", weekday=9),
        "command 为空": _job("x", command=[]),
        "command 绝对路径": _job("x", command=["/home/PrimarySchoolExam/tools/a.py"]),
        "timeout 非正": _job("x", timeout=0),
        "max_runs 非正": _job("x", max_runs=-1),
        "有效期倒置": _job("x", valid_from="2026-09-10", valid_until="2026-09-01"),
    }
    for label, job in cases.items():
        assert SCHED.validate_job(job), f"未能抓到：{label}"
    # 合法任务不得误报
    assert SCHED.validate_job(_job("ok")) == []
    # 重名必须报出（state 会互相覆盖）
    bad = SCHED.validate_jobs([_job("dup"), _job("dup")])
    assert "dup" in bad and any("重复" in e for e in bad["dup"])


# ── 9. 端到端：一个任务配置写错，不得拖垮其它任务 ──

def test_bad_job_does_not_block_others(tmp_path, monkeypatch):
    ran = []

    def fake_run_job(job, now):
        ran.append(job["name"])
        return True, "fake ok"

    monkeypatch.setattr(SCHED, "_run_job", fake_run_job)
    monkeypatch.setattr(SCHED, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(SCHED, "LOCK_FILE", str(tmp_path / "sched.lock"))
    monkeypatch.setattr(SCHED, "JOBS", [
        # 排在最前的坏任务：历史上会让整轮调度在这里崩掉
        {"name": "bad_first", "kind": "dailly", "at": "25:99",
         "command": ["tools/close_expired_orders.py"]},
        # 排在后面的好任务：必须照常执行
        {"name": "good_after", "kind": "daily", "at": "00:00",
         "command": ["tools/close_expired_orders.py"]},
    ])

    SCHED.run_due_jobs()

    assert ran == ["good_after"], f"坏任务阻断了好任务：实际执行 {ran}"
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["bad_first"]["last_status"] == "config_error", state
    assert "last_run" not in state["bad_first"], "配置错误的任务不应写入 last_run（它没真正执行）"
    assert state["good_after"]["last_status"] == "ok", state


# ── 10. crontab 安装命令在文档与代码中必须一致 ──

def test_cron_lines_consistent_in_repo():
    """真实仓库里 scheduler.py 与 DEPLOY.md 的 crontab 行必须一致

    踩过：scheduler.py 写的是 /opt/venv/bin/python（线上并不存在该解释器），
    运维照抄会让 cron 指向不存在的解释器 —— 任务完全不跑且只往 root 邮箱发错误。
    """
    items = OPS.check_cron_consistency(ROOT)
    assert items == [], f"仓库内 crontab 命令不一致或路径可疑：{items}"


def test_cron_inconsistency_detected(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "scheduler.py").write_text(
        "    */15 * * * * cd /home/PrimarySchoolExam && /opt/venv/bin/python "
        "tools/scheduler.py >> /var/log/scheduler.log 2>&1\n", encoding="utf-8")
    (tmp_path / "DEPLOY.md").write_text(
        "*/15 * * * * cd /home/PrimarySchoolExam && /home/PrimarySchoolExam/venv/bin/python "
        "tools/scheduler.py >> /var/log/scheduler.log 2>&1\n", encoding="utf-8")

    titles = [i["title"] for i in OPS.check_cron_consistency(tmp_path)]
    assert any("不一致" in t for t in titles), titles
    assert any("可疑的解释器路径" in t for t in titles), titles

    # 两处都没写时静默跳过，不得误报
    empty = tmp_path / "empty"
    empty.mkdir()
    assert OPS.check_cron_consistency(empty) == []


# ── 11. CLI 出口：JSON 输出可解析、退出码正确 ──

def test_cli_json_and_exit_code(capsys):
    code = OPS.main(["--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "items" in data and "jobs" in data
    assert code == (1 if data["errors"] else 0)
