"""080 - 等级 / 成长体系（新功能 C，2026Q4）

三件事，均幂等可重复执行：
1. `users` 表补 `level` / `exp` 两列（走 `database._ensure_column`，跨 dialect 安全；
   两列均可空，存量行由 DEFAULT 填充，展示等级由 exp 反算故不受影响）；
2. 新建 `level_config` 表（模型单一真相源见 `app/models/level.py`）；
3. seed 默认 20 级阶梯（复用服务层 `ensure_level_config`，**按 lv 增量补齐**——
   这样后续扩等级时新级会自动补进表，且不会覆盖后台已调过的旧等级数值）。

执行顺序不敏感：补列忽略「列已存在」，建表用 checkfirst，seed 按 lv 增量。
seed 失败不阻断迁移：服务层保留 `LEVEL_FALLBACK` 常量兜底，等级页不会因空表而异常。
"""


def upgrade(db):
    # 1) users 补 level / exp（幂等：列已存在时 _ensure_column 内部吞异常）
    from app.database import _ensure_column
    _ensure_column("users", "level", "INT DEFAULT 1")
    _ensure_column("users", "exp", "INT DEFAULT 0")

    # 2) 建等级配置表
    from app.models.level import LevelConfig
    LevelConfig.__table__.create(bind=db.get_bind(), checkfirst=True)
    db.commit()

    # 3) seed 默认等级阶梯（按 lv 增量补齐）
    try:
        from app.domains.engagement.services.level import ensure_level_config
        ensure_level_config(db)
    except Exception:
        # 不阻断迁移：服务层有 LEVEL_FALLBACK 兜底，等级功能仍可用；
        # 下次启动/迁移重跑时会再次尝试补齐（幂等）。
        try:
            db.rollback()
        except Exception:
            pass
