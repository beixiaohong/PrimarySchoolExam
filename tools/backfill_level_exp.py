"""等级经验回填工具（新功能 C 上线配套）

背景
----
等级体系（`add_exp`）是「行为发生时增量累加」的，从上线那一刻起才开始计经验。
上线前已有大量学习历史的用户如果 exp=0，级别会全部停在 Lv1（"学了半年还是 1 级"），
体验突兀。本脚本按**历史行为计数 × EXP_RULES** 一次性补齐经验。

用法（在**线上服务器**执行——写生产库的任务不得在本地跑，见项目铁律）
--------------------------------------------------------------------
    # 1) 先看会发生什么（默认就是 dry-run，不写库）
    .venv/bin/python tools/backfill_level_exp.py

    # 2) 确认无误后真正写库
    .venv/bin/python tools/backfill_level_exp.py --apply

    # 3) 如需把「升级奖励钻石」也补发（默认不发，见下）
    .venv/bin/python tools/backfill_level_exp.py --apply --grant-reward

设计说明
--------
- **默认 dry-run**：必须显式 `--apply` 才写库（误操作成本高）。
- **默认不发升级钻石**：`add_exp` 的升级钻石是「升级那一刻的即时激励」，历史用户并未经历
  升级过程；一次性补发会在短时间内注入大量钻石（通胀）。确需补偿时显式 `--grant-reward`，
  且走 `commerce.contracts.DiamondService.grant`（不直连 services）。
- **只补未回填过的用户**（`--only-zero`，默认开启）：以 `exp == 0 或 NULL` 为判据，
  避免对已在正常使用等级的活跃用户重复翻倍（脚本可安全重跑）。
- **分批提交**：每批 `--batch`（默认 200）个用户提交一次，避免长事务锁表。
- 经验规则与等级阈值都**从代码里 import**（`EXP_RULES` / `level_for_exp`），不在本脚本里
  重写一份，防止与线上逻辑漂移。
"""
import argparse
import sys
from pathlib import Path

# 从项目根导入 app 包：直接 `python tools/xxx.py` 时 sys.path 只含 tools/（与其它 tools 脚本一致）
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import func  # noqa: E402

from app.database import SessionLocal  # noqa: E402


def _count_events(db, uid: str) -> dict:
    """统计某用户的历史行为次数（返回 event -> 次数）。

    口径与埋点一一对应：交卷 / 错题掌握 / 任务完成 / 签到 / 心情打卡 / 专注。
    专注额外按分钟数贡献（与 focus.py 埋点的 `extra_exp=minutes // 10` 一致）。
    """
    from app.models.daily_task import DailyTask
    from app.models.exam import ExamAttempt, WrongRecord
    from app.models.focus import FocusSession
    from app.models.mood import MoodCheckin

    def _cnt(q):
        return int(q.scalar() or 0)

    return {
        "exam_done": _cnt(db.query(func.count()).select_from(ExamAttempt)
                          .filter(ExamAttempt.user_id == uid)),
        "wrong_mastered": _cnt(db.query(func.count()).select_from(WrongRecord)
                               .filter(WrongRecord.user_id == uid,
                                       WrongRecord.is_mastered.is_(True))),
        # 每日任务完成（排除签到行——签到单独计，否则重复计数）
        "task_done": _cnt(db.query(func.count()).select_from(DailyTask)
                          .filter(DailyTask.user_id == uid,
                                  DailyTask.status == "done",
                                  DailyTask.task_code != "checkin")),
        "checkin": _cnt(db.query(func.count()).select_from(DailyTask)
                        .filter(DailyTask.user_id == uid,
                                DailyTask.status == "done",
                                DailyTask.task_code == "checkin")),
        "mood_done": _cnt(db.query(func.count()).select_from(MoodCheckin)
                          .filter(MoodCheckin.user_id == uid)),
        "focus_done": _cnt(db.query(func.count()).select_from(FocusSession)
                           .filter(FocusSession.user_id == uid)),
        # 专注分钟数（用于 extra_exp），在 compute_exp 里按 //10 追加
        "_focus_minutes": int(db.query(func.coalesce(func.sum(FocusSession.minutes), 0))
                              .filter(FocusSession.user_id == uid).scalar() or 0),
    }


def compute_exp(counts: dict) -> int:
    """按行为次数与 EXP_RULES 计算应得经验（与线上加经验口径一致）。"""
    from app.domains.engagement.services.events import EXP_RULES

    total = 0
    for event, n in counts.items():
        if event.startswith("_"):
            continue
        total += int(EXP_RULES.get(event, 0)) * int(n)
    # 专注的按分钟数追加贡献（与 focus.py 埋点 extra_exp=minutes // 10 一致）
    total += int(counts.get("_focus_minutes", 0)) // 10
    return total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="等级经验回填（新功能 C 上线配套）")
    parser.add_argument("--apply", action="store_true",
                        help="真正写库；默认只做 dry-run 打印统计")
    parser.add_argument("--grant-reward", action="store_true",
                        help="同时补发升级奖励钻石（默认不发，避免一次性钻石通胀）")
    parser.add_argument("--only-zero", action="store_true", default=True,
                        help="只回填 exp 为 0/NULL 的用户（默认开启，保证可安全重跑）")
    parser.add_argument("--all", dest="only_zero", action="store_false",
                        help="覆盖所有用户（会重算并覆盖现有 exp，慎用）")
    parser.add_argument("--batch", type=int, default=200, help="每批提交用户数（默认 200）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个用户（0=不限，用于抽查）")
    args = parser.parse_args(argv)

    from app.domains.engagement.services.level import ensure_level_config, level_for_exp
    from app.models.user import User

    db = SessionLocal()
    try:
        # 等级阶梯先补齐（幂等），否则等级反算会走 FALLBACK 常量
        if args.apply:
            added = ensure_level_config(db)
            if added:
                print(f"[等级配置] 补齐 {added} 级")

        q = db.query(User).order_by(User.id)
        if args.only_zero:
            q = q.filter((User.exp.is_(None)) | (User.exp == 0))
        if args.limit:
            q = q.limit(args.limit)
        users = q.all()

        print(f"[目标] 待处理用户 {len(users)} 个"
              f"（{'仅 exp=0/NULL' if args.only_zero else '全部用户，将覆盖现有 exp'}）")
        print(f"[模式] {'APPLY 写库' if args.apply else 'DRY-RUN 只读'}"
              f"{'（同时补发升级钻石）' if args.grant_reward else '（不发升级钻石）'}")

        changed = 0
        total_exp = 0
        total_reward = 0
        for idx, u in enumerate(users, 1):
            counts = _count_events(db, u.user_id)
            exp = compute_exp(counts)
            if exp <= 0:
                continue
            old_level = level_for_exp(int(u.exp or 0))
            new_level = level_for_exp(exp)
            reward = 0
            if args.grant_reward and new_level > old_level:
                from app.domains.engagement.services.level import LEVEL_FALLBACK
                reward = sum(int(c["reward_diamond"]) for c in LEVEL_FALLBACK
                             if old_level < int(c["lv"]) <= new_level)

            if idx <= 20 or new_level > 1:
                print(f"  {u.user_id}: exp 0 -> {exp}, Lv{old_level} -> Lv{new_level}"
                      f"{f', 钻石 +{reward}' if reward else ''}  {counts}")

            changed += 1
            total_exp += exp
            total_reward += reward

            if args.apply:
                u.exp = exp
                u.level = new_level
                if idx % max(1, args.batch) == 0:
                    db.commit()
                    print(f"  …已提交 {idx} 个用户")

        if args.apply:
            db.commit()
            # 补发钻石放在 exp 全部落库之后，逐人发放（DiamondService 内部自带行锁与提交）
            if args.grant_reward:
                from app.domains.commerce.contracts import DiamondService
                granted = 0
                for u in users:
                    counts = _count_events(db, u.user_id)
                    exp = compute_exp(counts)
                    if exp <= 0:
                        continue
                    lv = level_for_exp(exp)
                    from app.domains.engagement.services.level import LEVEL_FALLBACK
                    amt = sum(int(c["reward_diamond"]) for c in LEVEL_FALLBACK if int(c["lv"]) <= lv)
                    if amt > 0:
                        DiamondService.grant(db, u.user_id, float(amt), biz="level_backfill")
                        granted += 1
                print(f"[钻石] 已补发 {granted} 人")

        print(f"[结果] {'已写库' if args.apply else 'DRY-RUN'}：{changed} 个用户，"
              f"经验合计 {total_exp}，升级钻石合计 {total_reward}")
        if not args.apply and changed:
            print("[提示] 确认无误后加 --apply 执行写入。")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
