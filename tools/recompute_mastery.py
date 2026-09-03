"""离线掌握度全量重算 + 快照脚本（S3-M5 / 07 §5.1.1 步骤4/5，C8）

用途：
- 冷启动 / 每日 01:00 全量重算活跃用户（近 N 天有作答）掌握度；
- 每日 01:30 对活跃用户生成 mastery_snapshots（趋势曲线 + 提升量指标）。

设计（持连铁律）：
- 每个用户自开短会话，纯 DB 计算（recompute_user_mastery 无外部调用）；
- 分批处理，避免长事务与连接长时间占用；
- 幂等可重跑：UPSERT mastery_records / mastery_snapshots。

用法：
  python tools/recompute_mastery.py                 # 重算活跃用户(7天) + 快照
  python tools/recompute_mastery.py --days 30       # 活跃窗口改为 30 天
  python tools/recompute_mastery.py --user 小明      # 仅重算单个用户
  python tools/recompute_mastery.py --dry-run       # 只读统计活跃用户数，不写库

注意：写线上库的任务只能在线上服务器运行（沙箱禁连克隆库写）。本脚本可重跑，
建议由线上 crontab 每日调度（先 01:00 重算，再 01:30 快照）。
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)
# 强制 MySQL 驱动（与线上一致）
import os
os.environ["DB_DRIVER"] = "mysql"

from sqlalchemy import func

from app.database import SessionLocal
from app.domains.engine.services.mastery_store import (
    generate_snapshots,
    recompute_user_mastery,
)
from app.models.exam import AttemptAnswer, ExamAttempt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("recompute_mastery")


def _active_users(db, days: int):
    """近 days 天有作答的用户（去重）。"""
    cutoff = datetime.now() - timedelta(days=days)
    rows = (
        db.query(func.distinct(ExamAttempt.user_id))
        .join(AttemptAnswer, AttemptAnswer.attempt_id == ExamAttempt.id)
        .filter(AttemptAnswer.created_at >= cutoff)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def main():
    parser = argparse.ArgumentParser(description="掌握度全量重算 + 快照")
    parser.add_argument("--days", type=int, default=7, help="活跃窗口（天）")
    parser.add_argument("--batch", type=int, default=100, help="每批处理用户数")
    parser.add_argument("--user", type=str, default=None, help="仅重算单个用户")
    parser.add_argument("--dry-run", action="store_true", help="只读统计，不写库")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.user:
            active = [args.user]
        else:
            active = _active_users(db, args.days)
    finally:
        db.close()

    if args.dry_run:
        logger.info("[dry-run] active_users=%d (近 %d 天有作答)", len(active), args.days)
        return

    total_kps = 0
    for i in range(0, len(active), args.batch):
        batch = active[i:i + args.batch]
        for uid in batch:
            udb = SessionLocal()
            try:
                total_kps += recompute_user_mastery(udb, uid)
            except Exception:
                logger.exception("重算失败 user=%s", uid)
            finally:
                udb.close()
        logger.info("[progress] 已处理 %d/%d 用户", min(i + args.batch, len(active)), len(active))

    # 快照（每日 01:30）
    sdb = SessionLocal()
    try:
        snap_n = generate_snapshots(sdb, user_ids=active if not args.user else None)
    finally:
        sdb.close()

    logger.info("完成：users=%d recomputed_kps=%d snapshots=%d",
                len(active), total_kps, snap_n)


if __name__ == "__main__":
    main()
