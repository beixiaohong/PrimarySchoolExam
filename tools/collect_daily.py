"""每日试卷采集入口（第一试卷网 → 本地每日 SQLite 文件）

与 collect_papers.py 的区别：
- 数据落「当日独立」SQLite 文件：data/collected_YYYY-MM-DD.sqlite（每日一个文件）；
- 跨日去重由 paper_crawler 的持久化注册表（data/scrape_registry.sqlite）保证，
  因此「之前没抓过的」跨天生效，不会每天重复抓；
- 学段优先级 初中→小学→高中、每学科均衡、仅最近 10 年 等策略沿用 collect_papers。

抓取流程（paper_crawler.run_collection）：
- 优先初中、再小学、最后高中；九大学科在每日配额切片内均衡覆盖；
- 仅抓取标题含明确年份且 >= (今年-10) 的试卷；无年份者视为近期，不过滤；
- 按 source_url / 注册表去重，已抓过的跳过；
- 抓取后调用 AI（智谱 GLM / 中转站 / DeepSeek 多链路）为缺失答案的题目补全。

用法（建议由定时器 / 自动化 每日凌晨调用一次）：
  python tools/collect_daily.py                       # 采 ~200 份 + AI 补全答案
  python tools/collect_daily.py --daily-limit 50 --answer-cap 600
  python tools/collect_daily.py --no-fill             # 仅采集入库，不调 AI 补答案
  python tools/collect_daily.py --dry                 # 仅打印策略与路径，不实际抓取
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ⚠️ 必须在 import app.* 之前设置 STAGING_DB_URL，让 app.database 用「当日」SQLite 文件，
# 而不是 .env 里写死的单文件 staging。load_dotenv(override=False) 不会回盖已存在的环境变量。
TODAY = datetime.now().strftime("%Y-%m-%d")
DAILY_DB = ROOT / "data" / f"collected_{TODAY}.sqlite"
os.environ["STAGING_DB_URL"] = f"sqlite:///{DAILY_DB}"

from app.domains.content.services.paper_crawler import run_collection, print_stats, seed_registry_from_staging  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="每日试卷采集（第一试卷网 → 当日 SQLite）")
    parser.add_argument("--daily-limit", type=int, default=200,
                        help="本日采集新卷上限（默认 200，约 200 份/天）")
    parser.add_argument("--answer-cap", type=int, default=0,
                        help="本日 AI 补全答案的题数上限（0=不限制，补全当日全部新卷答案；默认 0）")
    parser.add_argument("--no-fill", action="store_true",
                        help="采集后不调用 AI 补全答案（仅入库）")
    parser.add_argument("--dry", action="store_true",
                        help="仅打印当日策略与文件路径，不实际抓取")
    args = parser.parse_args()

    print(f"🗓 每日采集：{TODAY}")
    print(f"📁 当日数据文件：{DAILY_DB}")
    if args.dry:
        print("🔍 dry 模式：不实际抓取。")
        return

    # 跨日去重注册表：从既有 staging 库导入历史已抓记录（仅首次，避免重复抓历史卷）
    seed_registry_from_staging()

    new_ids = run_collection(
        once=True,
        daily_limit=args.daily_limit,
        fill_answers_after=not args.no_fill,
        answer_cap=args.answer_cap,
    )
    print(f"\n🆕 本次新采集试卷 {len(new_ids)} 份")
    print_stats()


if __name__ == "__main__":
    main()
