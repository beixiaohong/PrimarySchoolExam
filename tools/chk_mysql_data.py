"""检查 MySQL（.env 配置）与本地 SQLite 的关键表行数，验证数据迁移完整性。"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from app import config  # noqa: E402

TABLES = [
    "users", "exam_records", "wrong_problems", "vocab_progress", "vocab_daily_logs",
    "classical_progress", "classical_daily_logs", "daily_tasks", "rewards", "wishes",
    "pet_profiles", "pet_ledger", "diamond_ledger", "badges_user", "auth_codes",
    "admins", "admin_operation_logs", "system_config", "focus_sessions", "qa_sessions",
]

def main():
    print(f"driver={config.DB_DRIVER}")
    eng = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    sq = sqlite3.connect(str(ROOT / "primary_school.db"))

    print(f"{'table':<24}{'sqlite':>10}{'mysql':>10}{'diff':>8}")
    bad = 0
    with eng.connect() as conn:
        for t in TABLES:
            try:
                my = conn.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
            except Exception as e:
                my = f"ERR:{type(e).__name__}"
            try:
                sl = sq.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:
                sl = "-"
            diff = "" if not isinstance(my, int) or sl == "-" else (str(my - sl) if my - sl else "ok")
            if isinstance(my, str) or (isinstance(my, int) and sl != "-" and my != sl):
                bad += 1
            print(f"{t:<24}{str(sl):>10}{str(my):>10}{diff:>8}")
        mig = conn.execute(text(
            "SELECT version FROM schema_migrations ORDER BY version")).scalars().all()
        print("\napplied migrations:", ", ".join(mig))
    print(f"\nmismatch/error tables: {bad}")

if __name__ == "__main__":
    main()
