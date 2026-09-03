#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""线上库缺答案采集题 → 智谱 AI 补全（每晚限量，幂等）。

- 由 tools/scheduler.py 的 backfill_paper_answers 任务在每日 01:00 调用（线上服务器）。
- 只处理 correct_answer 为空的 paper_questions；[AI生成] 前缀存储，不覆盖已有答案。
- AI 走 app.domains.platform.services.ai 的多提供商路由：智谱 GLM（用户指定）优先，余额耗尽回退免费版，
  relay/DeepSeek 兜底；自带全局节流与「连续失败即停止」保护。
- 每晚默认最多 3000 题（BACKFILL_PER_RUN 可覆盖），多晚跑完，幂等可重入。

用法：
  python tools/backfill_paper_answers.py                # 默认补 3000 题
  BACKFILL_PER_RUN=5000 python tools/backfill_paper_answers.py
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(ROOT, ".env"), override=False)

PER_RUN = int(os.environ.get("BACKFILL_PER_RUN", "3000"))


def _load_import_module():
    """动态加载 tools/import_local_papers.py（复用其 online_conn 与 AI 补答案逻辑）。"""
    path = os.path.join(ROOT, "tools", "import_local_papers.py")
    spec = importlib.util.spec_from_file_location("import_local_papers", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    mod = _load_import_module()

    # 统计当前缺答案（直连 .env 指向的库 = 线上）
    try:
        conn = mod.online_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM paper_questions "
                            "WHERE correct_answer IS NULL OR correct_answer=''")
                missing = cur.fetchone()[0]
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        print(f"[backfill] 统计缺答案失败: {e}", flush=True)
        sys.exit(1)

    print(f"[backfill] 当前缺答案题目: {missing}；本次上限 {PER_RUN}", flush=True)
    if missing <= 0:
        print("[backfill] 无缺答案，退出", flush=True)
        sys.exit(0)

    done = mod.fill_missing_answers_online(limit=PER_RUN)
    remain = max(0, missing - done)
    print(f"[backfill] 本次成功补全 {done} 题，剩余约 {remain}（明晚继续）", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
