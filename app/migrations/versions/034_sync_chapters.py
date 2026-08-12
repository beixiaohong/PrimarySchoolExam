"""034 同步学支撑：problem_types 人教版章节映射种子 + sync_quiz_log 表

MySQL-only（SQLite 测试环境靠 ORM create_all 建表，不执行本迁移）。
幂等：sync_quiz_log 已存在则跳过；章节映射按年级回填到已有 problem_types 行。

为何 MySQL-only：sync_quiz_log 用 INT AUTO_INCREMENT / ENGINE=InnoDB 等 MySQL 专属 DDL，
SQLite 不支持，故测试环境跳过。
"""
from sqlalchemy import inspect, text


# 人教版小学数学 3-6 年级主干章节（每册 6-8 章，种子版，需人工校对扩充）
CHAPTER_MAP = {
    3: [
        "三年级上·第1单元·时、分、秒",
        "三年级上·第2单元·万以内的加法和减法",
        "三年级上·第3单元·测量",
        "三年级上·第4单元·倍的认识",
        "三年级上·第5单元·多位数乘一位数",
        "三年级上·第6单元·长方形和正方形",
        "三年级上·第7单元·分数的初步认识",
        "三年级下·第1单元·位置与方向",
        "三年级下·第2单元·除数是一位数的除法",
        "三年级下·第3单元·复式统计表",
        "三年级下·第4单元·两位数乘两位数",
        "三年级下·第5单元·面积",
        "三年级下·第6单元·年、月、日",
        "三年级下·第7单元·小数的初步认识",
    ],
    4: [
        "四年级上·第1单元·大数的认识",
        "四年级上·第2单元·公顷和平方千米",
        "四年级上·第3单元·角的度量",
        "四年级上·第4单元·三位数乘两位数",
        "四年级上·第5单元·平行四边形和梯形",
        "四年级上·第6单元·除数是两位数的除法",
        "四年级上·第7单元·条形统计图",
        "四年级上·第8单元·数学广角（优化）",
        "四年级下·第1单元·四则运算",
        "四年级下·第2单元·观察物体",
        "四年级下·第3单元·运算定律",
        "四年级下·第4单元·小数的意义和性质",
        "四年级下·第5单元·三角形",
        "四年级下·第6单元·小数的加法和减法",
        "四年级下·第7单元·图形的运动",
        "四年级下·第8单元·平均数与条形统计图",
    ],
    5: [
        "五年级上·第1单元·小数乘法",
        "五年级上·第2单元·位置",
        "五年级上·第3单元·小数除法",
        "五年级上·第4单元·可能性",
        "五年级上·第5单元·简易方程",
        "五年级上·第6单元·多边形的面积",
        "五年级上·第7单元·数学广角（植树问题）",
        "五年级下·第1单元·观察物体",
        "五年级下·第2单元·因数与倍数",
        "五年级下·第3单元·长方体和正方体",
        "五年级下·第4单元·分数的意义和性质",
        "五年级下·第5单元·图形的运动（旋转）",
        "五年级下·第6单元·分数的加法和减法",
        "五年级下·第7单元·折线统计图",
    ],
    6: [
        "六年级上·第1单元·分数乘法",
        "六年级上·第2单元·位置与方向",
        "六年级上·第3单元·分数除法",
        "六年级上·第4单元·比",
        "六年级上·第5单元·圆",
        "六年级上·第6单元·百分数",
        "六年级上·第7单元·扇形统计图",
        "六年级上·第8单元·数学广角（数与形）",
        "六年级下·第1单元·负数",
        "六年级下·第2单元·百分数（折扣成数）",
        "六年级下·第3单元·圆柱与圆锥",
        "六年级下·第4单元·比例",
        "六年级下·第5单元·鸽巢问题",
        "六年级下·第6单元·整理与复习",
    ],
}


def upgrade(db):
    insp = inspect(db.bind)
    tables = set(insp.get_table_names())

    # ── 1. 建 sync_quiz_log 表（AUTO_INCREMENT/InnoDB 为 MySQL 专属）──
    if "sync_quiz_log" not in tables:
        db.execute(text(
            """
            CREATE TABLE sync_quiz_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                subject VARCHAR(20) NOT NULL,
                grade INT NOT NULL DEFAULT 0,
                unit VARCHAR(120) NOT NULL DEFAULT '',
                score FLOAT NOT NULL DEFAULT 0,
                total INT NOT NULL DEFAULT 10,
                correct INT NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX (user_id),
                INDEX (subject)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同步学单元小测成绩'
            """
        ))

    # ── 2. 人教版章节映射种子：回填到已有 problem_types 行 ──
    try:
        from ..models.problem_type import ProblemType
    except Exception:
        return
    for grade, chapters in CHAPTER_MAP.items():
        rows = db.query(ProblemType).filter(
            ProblemType.grade_min <= grade,
            ProblemType.grade_max >= grade,
        ).order_by(ProblemType.id).all()
        if not rows:
            continue
        # 把该年级的章节循环分配给题型（章节数 >= 题型数时一一对应，否则循环复用）
        for i, pt in enumerate(rows):
            if pt.textbook_chapter:
                continue  # 已标注则保留人工值
            pt.textbook_chapter = chapters[i % len(chapters)]
        db.flush()
