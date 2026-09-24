#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线运维资产体检：定时任务配置 / 脚本依赖 / 运行时文件（静态为主，无副作用）

为什么需要它
------------
调度任务（`tools/scheduler.py`，线上 cron 每 15 分钟触发）是**静默执行**的：
输出只进 `/var/log/scheduler.log`，没有任何告警通道。于是下面这些故障**没有症状**，
只会安静积累成业务数据错误（订单不关单、会员不降级、红包不退回、周期账单不生成）：

1. **任务配置笔误** —— `kind` 拼错、`at` 写 "25:99"、`enabled` 写成字符串 `"False"`
   （`job.get("enabled") is False` 判定不成立 → 停用失效，任务照跑）；
2. **command 指向的脚本被改名 / 删除 / 新增后忘记 `git add`** —— 线上 `git pull`
   拿不到文件，任务每天安静地 `fail` 一次；
3. **脚本硬导入 requirements.txt 未声明的包** —— 与 2026-09-24 全站 502 同源，
   只是从「应用启动崩」变成「定时任务崩」；
4. **运行时文件未纳入 .gitignore** —— `.scheduler_state.json` / `.scheduler.lock`
   会把线上运行状态污染进 git（一旦 `git add -A` 就提交了线上 last_run）。

本脚本把这几类问题在**提交 / 部署前**一次列清。纯静态检查 + 可选的状态文件读取，
**不写任何文件、不跑任何任务**。

用法
----
    python tools/ops_check.py                                        # 静态体检（退出码 0=通过）
    python tools/ops_check.py --state tools/.scheduler_state.json     # 追加线上调度状态体检
    python tools/ops_check.py --json                                 # 机器可读输出

被 `tools/regression_check.py`（提交前自检）与 `tools/preflight.py`（部署闸门）复用。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 运行时生成的文件（线上由调度器创建），必须被 .gitignore 覆盖
RUNTIME_FILES = ("tools/.scheduler_state.json", "tools/.scheduler.lock")

# daily 任务超过该时长未成功执行 -> 判定为「静默停摆」
STALE_AFTER = timedelta(hours=26)

BAD_STATUSES = ("fail", "config_error", "judge_error")


def _load_module(name: str, path: Path):
    """按路径加载 tools/ 下的模块

    注意：**必须注册进 sys.modules** —— 否则模块内若用了 dataclass 或
    `from __future__ import annotations`，解析注解时会抛 AttributeError
    （2026-09-24 在 preflight.py 上踩过，见项目记忆）。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SCHED = _load_module("ops_scheduler", ROOT / "tools" / "scheduler.py")
AUDIT = _load_module("ops_dep_audit", ROOT / "tools" / "dep_audit.py")


# ── 结果条目 ──
# 用普通 dict + 工厂函数而非 dataclass：本模块会被按路径加载，保持零依赖最稳。

def item(level: str, title: str, detail: str = "", hint: str = "") -> dict:
    return {"level": level, "title": title, "detail": detail, "hint": hint}


# ── git 辅助 ──

def _git(args: list, cwd: Path) -> tuple:
    """执行 git 子命令 -> (returncode, stdout)；git 不可用时返回 (-1, "")"""
    if not shutil.which("git"):
        return -1, ""
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
        return r.returncode, (r.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return -1, ""


def git_available(cwd: Path = ROOT) -> bool:
    code, _ = _git(["rev-parse", "--git-dir"], cwd)
    return code == 0


def is_tracked(rel_path: str, cwd: Path = ROOT) -> bool:
    """该路径是否已被 git 跟踪（线上 `git pull` 能否拿到）"""
    code, _ = _git(["ls-files", "--error-unmatch", rel_path], cwd)
    return code == 0


def is_ignored(rel_path: str, cwd: Path = ROOT) -> bool:
    """该路径是否被 .gitignore 忽略（用 git check-ignore，最准）"""
    code, _ = _git(["check-ignore", "-q", rel_path], cwd)
    return code == 0


# ── 各项检查 ──

def check_config(jobs) -> list:
    """[1] 任务定义配置校验（复用 scheduler.validate_jobs，规则单一真相源）

    启用任务的配置错误 = error（线上会静默跳过它）；
    停用任务的配置错误 = warn（哪天恢复启用就会踩）。
    """
    out = []
    disabled = {j.get("name") for j in jobs
                if isinstance(j, dict) and j.get("enabled") is False}
    for name, errs in SCHED.validate_jobs(jobs).items():
        level = "warn" if name in disabled else "error"
        for e in errs:
            out.append(item(level, f"任务配置有误：{name}", e,
                            "修复 tools/scheduler.py 中该任务的字段；"
                            "配置有误的任务会被调度器跳过（不再拖垮其它任务）"))
    return out


def check_scripts(jobs, repo_root: Path = ROOT, use_git: bool = True,
                  requirements: Path | None = None) -> list:
    """[2] 任务脚本：存在性 / 依赖声明 / git 跟踪"""
    out = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = job.get("name", "?")
        enabled = job.get("enabled") is not False
        level = "error" if enabled else "warn"
        cmd = job.get("command")
        if not isinstance(cmd, (list, tuple)) or not cmd or not isinstance(cmd[0], str):
            continue                       # 结构问题由 check_config 报出
        rel = cmd[0]
        script = repo_root / rel

        if not script.exists():
            out.append(item(level, f"任务脚本不存在：{name}", f"{rel}（相对仓库根）",
                            "脚本被改名/删除？调度器只会安静地 fail，不会告警"))
            continue
        if not script.is_file():
            out.append(item(level, f"任务脚本不是文件：{name}", rel))
            continue

        # 依赖：脚本的模块级硬导入必须都在 requirements.txt 声明
        result = AUDIT.audit([script], root=repo_root, requirements=requirements)
        for e in result["errors"]:
            files = ", ".join(e["files"][:3])
            out.append(item(level, f"任务脚本依赖未声明：{name}",
                            f"{e['module']}（发行包 {e['dist']}）-> {files}",
                            "与 2026-09-24 全站 502 同源：本地装了、线上没装。"
                            "补进 requirements.txt 并重新部署"))
        for w in result["warnings"]:
            out.append(item("warn", f"任务脚本依赖归属未知：{name}",
                            f"{w['module']} -> {', '.join(w['files'][:2])}",
                            "本地也未安装，请人工确认是否为可选依赖/是否需声明"))

        # git 跟踪：线上 git pull 拿不到的文件，任务必然失败
        if use_git and not is_tracked(rel, repo_root):
            out.append(item(level, f"任务脚本未被 git 跟踪：{name}", rel,
                            "线上 git pull 拿不到这个文件 -> 任务必然失败。"
                            "执行 git add 并提交后再部署"))
    return out


def check_runtime_files(repo_root: Path = ROOT, use_git: bool = True) -> list:
    """[3] 调度器运行时文件必须被 .gitignore 覆盖（防止污染仓库）"""
    out = []
    for rel in RUNTIME_FILES:
        if use_git:
            if is_ignored(rel, repo_root):
                continue
            out.append(item("warn", f"运行时文件未忽略：{rel}",
                            "线上调度器会生成它；未忽略则 `git status` 变脏，"
                            "一旦 `git add -A` 就把线上运行状态提交进仓库",
                            "在 .gitignore 里加 tools/.scheduler_state.json 与 tools/.scheduler.lock"))
        else:
            gi = repo_root / ".gitignore"
            text = gi.read_text(encoding="utf-8", errors="ignore") if gi.exists() else ""
            if not any(rel.split("/")[-1] in line or rel in line
                       for line in text.splitlines()):
                out.append(item("warn", f"运行时文件未忽略（按文本判断）：{rel}",
                                "未找到 git，仅做文本匹配；建议直接确认 .gitignore"))
    return out


def check_state(state_path: Path, jobs, now: datetime | None = None) -> list:
    """[4] 线上调度状态体检（--state 传入；不传则跳过）

    这是唯一能发现「任务已连续多日失败」的地方 —— 调度器本身没有告警通道。
    """
    now = now or datetime.now()
    out = []
    if not state_path.exists():
        return [item("warn", "未找到调度状态文件", str(state_path),
                     "线上还没跑过调度器？若线上已有 crontab 却仍无此文件，"
                     "说明 cron 未生效或工作目录不对")]

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [item("error", "调度状态文件无法解析", f"{type(e).__name__}: {e}",
                     "文件可能被写入中断；删除后调度器会按空状态重建"
                     "（当日 daily 任务可能重复执行一次，任务多为幂等）")]

    names = [j.get("name") for j in jobs if isinstance(j, dict)]
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = job.get("name")
        if not name or job.get("enabled") is False:
            continue
        st = state.get(name)
        if not st:
            out.append(item("warn", f"任务无运行记录：{name}",
                            "调度状态里没有它 -> 线上从未成功触发（cron 未装？"
                            "或任务刚新增尚未到 at 时刻）"))
            continue

        status = st.get("last_status")
        if status in BAD_STATUSES:
            detail = f"last_status={status}"
            for key in ("last_error", "last_output"):
                if st.get(key):
                    detail += f"；{key}={str(st[key])[:180]}"
            out.append(item("warn", f"任务上次执行失败：{name}", detail,
                            "查看线上日志：journalctl/grep scheduler.log；"
                            "修复后下一个 tick 会自动重试"))

        last_run = st.get("last_run")
        if job.get("kind", "daily") == "daily" and last_run:
            try:
                delta = now - datetime.fromisoformat(last_run)
            except ValueError:
                delta = None
            if delta and delta > STALE_AFTER:
                out.append(item("warn", f"任务已超过 {STALE_AFTER.total_seconds() // 3600:.0f} 小时未成功执行：{name}",
                                f"last_run={last_run}（距今 {delta.days} 天 {delta.seconds // 3600} 小时）",
                                "检查 crontab 是否还在、服务器时间是否正确、"
                                "或该任务是否已被 valid_until/max_runs 静默停掉"))

        vu = job.get("valid_until")
        if vu:
            try:
                if now.date() > datetime.fromisoformat(str(vu)).date():
                    out.append(item("warn", f"任务已过有效期：{name}",
                                    f"valid_until={vu} -> 不会再执行",
                                    "确需继续运行就更新/删掉 valid_until，"
                                    "否则建议直接删掉该任务定义（避免僵尸配置）"))
            except ValueError:
                pass

        mr = job.get("max_runs")
        if mr is not None and st.get("run_count", 0) >= mr:
            out.append(item("warn", f"任务已达次数上限：{name}",
                            f"run_count={st.get('run_count')} >= max_runs={mr} -> 不会再执行",
                            "确需继续运行就调大 max_runs，否则建议清理该任务定义"))

    for stale in sorted(set(state) - set(n for n in names if n)):
        out.append(item("warn", f"残留调度状态：{stale}",
                        "状态里有、但 JOBS 中已无同名任务",
                        "任务已删除/改名；可手动从 .scheduler_state.json 里清掉"))
    return out


def check_cron_consistency(repo_root: Path = ROOT) -> list:
    """crontab 安装命令在 scheduler.py 与 DEPLOY.md 中必须逐字一致

    真实踩过：scheduler.py 的 docstring 写的是 `/opt/venv/bin/python`，而线上实际是
    `<部署目录>/venv/bin/python`。运维照抄这条 crontab 会让 cron 指向**不存在的解释器**
    —— 任务完全不跑，且 cron 的错误输出只投递给 root 邮箱，等于静默失效。

    提取规则：含 scheduler.py>>/var/log/scheduler.log 的行（strip 后比对）。
    任一处没写就跳过（不误报）。
    """
    def _lines(path: Path) -> set:
        if not path.exists():
            return set()
        text = path.read_text(encoding="utf-8", errors="ignore")
        return {l.strip() for l in text.splitlines() if "scheduler.py >> /var/log/scheduler.log" in l}

    doc_lines = _lines(repo_root / "tools" / "scheduler.py")
    deploy_lines = _lines(repo_root / "DEPLOY.md")
    if not doc_lines or not deploy_lines:
        return []

    out = []
    if doc_lines != deploy_lines:
        out.append(item("warn", "crontab 安装命令在两处不一致",
                        f"scheduler.py：{sorted(doc_lines)}；DEPLOY.md：{sorted(deploy_lines)}",
                        "保持逐字一致，避免运维照抄到过时的解释器路径"))
    suspicious = sorted(l for l in (doc_lines | deploy_lines) if "/opt/venv" in l or "/opt/" in l)
    if suspicious:
        out.append(item("warn", "crontab 使用了可疑的解释器路径",
                        "；".join(suspicious),
                        "线上解释器是 <部署目录>/venv/bin/python（见 deploy.sh 的 $APP_DIR）"))
    return out


def run(jobs=None, repo_root: Path = ROOT, state_path: Path | None = None,
        now: datetime | None = None, requirements: Path | None = None) -> dict:
    """执行全部检查 -> {"items": [...], "errors": n, "warns": n, "jobs": {...}}"""
    jobs = SCHED.JOBS if jobs is None else jobs
    use_git = git_available(repo_root)

    items: list = []
    if not use_git:
        items.append(item("warn", "未找到可用的 git", "已跳过 git 跟踪与 .gitignore 检查",
                          "在仓库内运行本脚本即可恢复这两项检查"))

    items += check_config(jobs)
    items += check_scripts(jobs, repo_root, use_git, requirements)
    items += check_runtime_files(repo_root, use_git)
    items += check_cron_consistency(repo_root)
    if state_path is not None:
        items += check_state(state_path, jobs, now)

    enabled = [j for j in jobs if isinstance(j, dict) and j.get("enabled") is not False]
    return {
        "items": items,
        "errors": sum(1 for i in items if i["level"] == "error"),
        "warns": sum(1 for i in items if i["level"] == "warn"),
        "jobs": {"total": len(jobs), "enabled": len(enabled), "disabled": len(jobs) - len(enabled)},
    }


def format_report(result: dict, state_checked: bool = False) -> str:
    lines: list[str] = []
    j = result["jobs"]
    lines.append("=" * 68)
    lines.append("上线运维资产体检（定时任务配置 / 脚本依赖 / 运行时文件）")
    lines.append("=" * 68)
    lines.append(f"任务共 {j['total']} 个（启用 {j['enabled']} / 停用 {j['disabled']}）"
                 f"；调度状态体检：{'已开启' if state_checked else '未开启（--state 可开启）'}")
    lines.append("")

    marks = {"error": "✗", "warn": "!"}
    if not result["items"]:
        lines.append("  ✓ 全部通过：任务配置合法、脚本存在且已声明依赖、运行时文件已忽略")
    else:
        for it in result["items"]:
            lines.append(f"  {marks.get(it['level'], '?')} [{it['level'].upper()}] {it['title']}")
            if it["detail"]:
                lines.append(f"      {it['detail']}")
            if it["hint"]:
                lines.append(f"      → {it['hint']}")

    lines.append("")
    lines.append("-" * 68)
    if result["errors"]:
        lines.append(f"结论：不通过（{result['errors']} 个错误 / {result['warns']} 个警告）")
        lines.append("  错误项会导致线上定时任务静默失效，请修复后再部署。")
    else:
        lines.append(f"结论：通过（0 个错误 / {result['warns']} 个警告）")
    lines.append("-" * 68)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="上线运维资产体检（调度任务 / 依赖 / 运行时文件）")
    p.add_argument("--state", default="", help="调度状态文件路径（线上为 tools/.scheduler_state.json）")
    p.add_argument("--requirements", default="", help="依赖清单路径（默认 仓库根/requirements.txt）")
    p.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = p.parse_args(argv)

    state_path = Path(args.state) if args.state else None
    requirements = Path(args.requirements).resolve() if args.requirements else None
    result = run(state_path=state_path, requirements=requirements)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result, state_checked=state_path is not None))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
