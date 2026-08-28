#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代码内置轻量定时器（部署到线上服务器，由 crontab 周期调用）。

为什么放在代码里：
    本定时器随代码提交、随 deploy 上线，在线上服务器运行，直接读写线上库
    （依赖服务器 .env 的 DB_HOST/DB_NAME），不依赖任何外部调度平台。

线上服务器 crontab 安装（只需一次）：
    */15 * * * * cd /home/PrimarySchoolExam && /opt/venv/bin/python tools/scheduler.py >> /var/log/scheduler.log 2>&1

能力：
- 任务类型：once（一次性）/ daily（每日）/ weekly（每周）
- 限制次数：max_runs（None=不限）；有效期：valid_from / valid_until（日期，到期自动停）
- 幂等：用 tools/.scheduler_state.json 记录每个任务的 last_run 与 run_count，
  cron 高频触发（每 15 分钟）也不会重复执行；若某天服务器在指定时刻宕机，
  下一个 tick 会自动补跑（自愈）。
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
        "name": "seed_junior_grade7",
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
        "name": "backfill_paper_answers",
        "kind": "daily",
        "at": "01:00",
        "valid_from": "2026-08-27",
        "valid_until": "2026-09-15",   # 每晚限量补，多晚补完（幂等：只补缺答案的）
        "max_runs": 15,
        "weekday": None,
        "command": ["tools/backfill_paper_answers.py"],
        "timeout": 10800,              # 每晚最多约 3000 题（智谱 ~2s/题）
    },
]


def _load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _parse_hm(s):
    h, m = str(s).split(":")
    return dtime(int(h), int(m))


def _job_due(job, now, st):
    vf = job.get("valid_from")
    vu = job.get("valid_until")
    if vf and now.date() < date.fromisoformat(vf):
        return False, "未到 valid_from"
    if vu and now.date() > date.fromisoformat(vu):
        return False, "已过 valid_until"
    mr = job.get("max_runs")
    if mr is not None and st.get("run_count", 0) >= mr:
        return False, "已达 max_runs"
    at = _parse_hm(job.get("at", "01:00"))
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
    return False, "未知 kind"


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


def run_due_jobs():
    now = datetime.now()
    if not _acquire_lock():
        return
    try:
        state = _load_state()
        for job in JOBS:
            name = job["name"]
            st = state.get(name, {})
            due, reason = _job_due(job, now, st)
            if not due:
                print(f"[{now.isoformat()}] 跳过 {name}: {reason}", flush=True)
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
