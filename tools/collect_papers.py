"""试卷采集命令行入口（主项目统一入口）

用法：
  python tools/collect_papers.py                 # 持续采集（按 REQUEST_INTERVAL 循环）
  python tools/collect_papers.py --once          # 跑一轮即退出
  python tools/collect_papers.py --migrate-demo  # 把 demo/learning.db 已采集试卷迁入主库
  python tools/collect_papers.py --stats         # 打印题库统计

说明：
- 采集结果入库到主库 primary_school.db 的 papers / paper_questions 表；
- 按 source_url 去重，已采集过的试卷不会重复采集；
- 试卷以 HTML 富文本（图片 base64 内联）保存，不保存 doc 原件。
"""
import argparse
import sys
from pathlib import Path

# 让脚本可直接从项目根目录运行
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.paper_crawler import run_collection, migrate_demo_papers, print_stats  # noqa: E402
from app.services.answer_generator import fill_missing_answers, count_missing_answers  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="试卷采集与入库（第一试卷网）")
    parser.add_argument("--once", action="store_true", help="只跑一轮采集即退出")
    parser.add_argument("--migrate-demo", action="store_true",
                        help="将 demo/learning.db 中已采集的试卷迁入主库")
    parser.add_argument("--stats", action="store_true", help="打印题库统计后退出")
    parser.add_argument("--demo-db", default=None, help="指定 demo 数据库路径（覆盖默认）")
    parser.add_argument("--fill-answers", action="store_true",
                        help="为缺失答案的采集题目调用 AI 补全（保留自带答案）")
    parser.add_argument("--count-missing", action="store_true",
                        help="仅统计仍缺失答案的题目数后退出")
    parser.add_argument("--limit", type=int, default=None,
                        help="--fill-answers 时最多处理多少题（控成本/时长）")
    parser.add_argument("--grade", default=None, help="限定年级（如 一年级）")
    parser.add_argument("--subject", default=None, help="限定学科（如 数学）")
    parser.add_argument("--dry-run", action="store_true",
                        help="--fill-answers 仅预览不写库")
    args = parser.parse_args()

    if args.count_missing:
        n = count_missing_answers(grade=args.grade, subject=args.subject)
        print(f"缺失答案的题目数：{n}")
        return

    if args.fill_answers:
        p, ok, skip = fill_missing_answers(
            limit=args.limit, grade=args.grade, subject=args.subject, dry_run=args.dry_run)
        print(f"答案补全：处理 {p}，成功 {ok}，跳过 {skip}")
        return

    if args.stats:
        print_stats()
        return

    if args.migrate_demo:
        migrate_demo_papers(args.demo_db)
        print_stats()
        return

    run_collection(once=args.once)
    print_stats()


if __name__ == "__main__":
    main()
