"""047 - 教材版本表 + 用户版本选择 + word_books 关联版本

背景（需求：每个科目增加教材版本选择，后台配置，每年级每科目单独配置，
默认选 id 靠前的版本）：
- textbook_versions：后台配置的教材版本（学科+年级+版本名+排序+启用）
- user_textbook_prefs：用户每学科选择的版本（未配置回退默认版本）
- word_books.textbook_id：词书归属版本；迁移时按现有 (publisher, grade) 自动
  创建版本并回填，保证旧词库直接可用、无需手工迁移

幂等：全部 information_schema/checkfirst 检测，MySQL-only。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    # ── 1) textbook_versions 表 ──
    from sqlalchemy import MetaData, Table, Column, Integer, String, Boolean, DateTime
    meta = MetaData()
    Table(
        "textbook_versions",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("subject", String(20), nullable=False, index=True),
        Column("grade", Integer, nullable=False, index=True),
        Column("name", String(50), nullable=False),
        Column("sort_order", Integer, nullable=False, default=0),
        Column("enabled", Boolean, nullable=False, default=True),
        Column("remark", String(200), nullable=False, default=""),
        Column("created_at", DateTime, nullable=False),
    ).create(bind=bind, checkfirst=True)

    # ── 2) user_textbook_prefs 表 ──
    Table(
        "user_textbook_prefs",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(50), nullable=False, index=True),
        Column("subject", String(20), nullable=False),
        Column("textbook_id", Integer, nullable=False),
        Column("updated_at", DateTime, nullable=False),
    ).create(bind=bind, checkfirst=True)

    # ── 3) word_books.textbook_id 列 ──
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'word_books' "
        "AND COLUMN_NAME = 'textbook_id'"
    ))
    if result.scalar() == 0:
        db.execute(text(
            "ALTER TABLE word_books ADD COLUMN textbook_id INT NULL "
            "COMMENT '教材版本 id（textbook_versions.id，047 迁移）'"
        ))
        logger.info("047: 已为 word_books 添加 textbook_id 列")
    else:
        logger.info("047: word_books.textbook_id 已存在，跳过")

    # ── 4) 按现有 (publisher, grade) 自动建版本并回填 ──
    rows = db.execute(text(
        "SELECT DISTINCT publisher, grade FROM word_books "
        "WHERE publisher IS NOT NULL AND publisher <> ''"
    )).fetchall()
    made = 0
    for publisher, grade in rows:
        publisher = str(publisher).strip()[:50]
        if not publisher or not grade:
            continue
        exist = db.execute(text(
            "SELECT id FROM textbook_versions "
            "WHERE subject='英语' AND grade=:g AND name=:n LIMIT 1"
        ), {"g": grade, "n": publisher}).scalar()
        if not exist:
            exist = db.execute(text(
                "INSERT INTO textbook_versions (subject, grade, name, sort_order, enabled, remark, created_at) "
                "VALUES ('英语', :g, :n, 0, 1, '', NOW())"
            ), {"g": grade, "n": publisher}).lastrowid
            made += 1
        db.execute(text(
            "UPDATE word_books SET textbook_id = :t "
            "WHERE publisher = :p AND grade = :g AND textbook_id IS NULL"
        ), {"t": exist, "p": publisher, "g": grade})
    db.commit()
    logger.info("047: 教材版本/用户选择表就绪，按词书 publisher 自动建版本 %d 个并回填", made)
