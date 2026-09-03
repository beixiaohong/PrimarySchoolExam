"""S2-A3 标注工作量统计（只读克隆库，绝不写库）

读取 192.168.2.158 克隆库（.env 默认指向）三张题目表：
    questions / paper_questions / middle_questions
统计：
    1) 各表总题量 + 按学科（subject）分布
    2) 已被标注的题量（question_kp_map，若该表已建）
    3) 标注覆盖率 + 待标注余量
    4) 粗略人力估算（按每题 1.5 分钟标注，供教研排期）

输出：打印摘要 + 写入 docs/enterprise/S2-标注工作量统计.md
注意：本脚本只发 SELECT，不改动任何数据（克隆库铁律）。
"""
from datetime import datetime

from sqlalchemy import func, distinct

from app.database import engine
from app.models.exam import Question
from app.models.paper import PaperQuestion
from app.models.middle import MiddleQuestion
from app.models.kp_map import QuestionKpMap

TABLES = {
    "questions": Question,
    "paper_questions": PaperQuestion,
    "middle_questions": MiddleQuestion,
}
# 每张题标注耗时估算（分钟），供排期参考
MIN_PER_Q = 1.5


def _group_by_subject(conn, mdl):
    """返回 {subject: count}，未知学科记 '<空>'。"""
    from sqlalchemy import select
    stmt = select(mdl.subject, func.count(mdl.id)).group_by(mdl.subject)
    out = {}
    for subj, cnt in conn.execute(stmt).all():
        out[subj or "<空>"] = cnt
    return out


def _annotated_by_source(conn):
    """返回 {source_table: 已标注题数}；表不存在返回 {}。"""
    try:
        from sqlalchemy import select
        stmt = select(QuestionKpMap.source_table,
                      func.count(distinct(QuestionKpMap.question_id))).group_by(
            QuestionKpMap.source_table)
        return {st: c for st, c in conn.execute(stmt).all()}
    except Exception as e:  # 表未建（迁移 053 尚未上线）
        print(f"[warn] question_kp_map 不可读（{e}），标注覆盖率按 0 计")
        return {}


def main():
    with engine.connect() as conn:
        annotated = _annotated_by_source(conn)
        report_lines = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        report_lines.append(f"# S2 标注工作量统计报告\n")
        report_lines.append(f"- 生成时间：{now}")
        report_lines.append(f"- 数据源：克隆库 `192.168.2.158`（只读快照，不写库）")
        report_lines.append(f"- 说明：覆盖 `questions`/`paper_questions`/`middle_questions` 三张题目表；标注余量 = 总题量 − 已标注题量。\n")

        # 总览表
        report_lines.append("## 一、总览\n")
        report_lines.append("| 题目表 | 总题量 | 已标注 | 覆盖率 | 待标注余量 | 估算人力(人时) |")
        report_lines.append("|---|---|---|---|---|---|")
        grand_total = grand_remaining = 0
        per_table = {}
        for name, mdl in TABLES.items():
            total = conn.execute(func.count(mdl.id)).scalar() or 0
            ann = annotated.get(name, 0)
            cov = (ann / total * 100) if total else 0
            remaining = max(0, total - ann)
            hours = round(remaining * MIN_PER_Q / 60, 1)
            grand_total += total
            grand_remaining += remaining
            per_table[name] = (total, ann, cov, remaining, hours)
            report_lines.append(
                f"| {name} | {total:,} | {ann:,} | {cov:.1f}% | {remaining:,} | {hours:,} |")
        grand_hours = round(grand_remaining * MIN_PER_Q / 60, 1)
        report_lines.append(
            f"| **合计** | **{grand_total:,}** | — | — | **{grand_remaining:,}** | **{grand_hours:,}** |\n")

        # 学科分布
        report_lines.append("## 二、各学科题量分布\n")
        for name, mdl in TABLES.items():
            total, ann, cov, remaining, hours = per_table[name]
            report_lines.append(f"### {name}（总 {total:,}，待标注 {remaining:,}）\n")
            by_subj = _group_by_subject(conn, mdl)
            if not by_subj:
                report_lines.append("（无 subject 分布数据）\n")
                continue
            report_lines.append("| 学科 | 题量 | 占比 |")
            report_lines.append("|---|---|---|")
            for subj, cnt in sorted(by_subj.items(), key=lambda x: -x[1]):
                pct = (cnt / total * 100) if total else 0
                report_lines.append(f"| {subj} | {cnt:,} | {pct:.1f}% |")
            report_lines.append("")

        # 排期建议
        report_lines.append("## 三、排期建议\n")
        report_lines.append(
            f"- 待标注总量约 **{grand_remaining:,}** 题，按每题 {MIN_PER_Q} 分钟估算约 "
            f"**{grand_hours:,} 人时**（单人约 {round(grand_hours/8,1)} 个工作日，8h/日）。")
        report_lines.append(
            "- `questions` 为在线做题主表，优先标注；`paper_questions` 体量最大，建议按学科/"
            "年级分批、结合 AI 预标注（/content/annotation/ai-predict）降人工量。")
        report_lines.append(
            "- 标注前需先建知识点树（/content/kp/tree）并录入知识点，否则 AI 预标注无目录可映射。")
        report_lines.append(
            "- 本统计基于克隆库快照；生产标注进度以后台 /content/annotation/stats 实时为准。\n")

        md = "\n".join(report_lines)
        out_path = "docs/enterprise/S2-标注工作量统计.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)

        # 终端摘要
        print("=" * 50)
        print(f"题目存量统计（克隆库只读）@ {now}")
        print(f"  总题量   : {grand_total:,}")
        print(f"  待标注余量: {grand_remaining:,}  (估算 {grand_hours:,} 人时)")
        for name, (total, ann, cov, remaining, hours) in per_table.items():
            print(f"  - {name:16s} 总 {total:>7,}  已标 {ann:>6,}  余 {remaining:>7,}  {hours:>7,} 人时")
        print(f"报告已写入: {out_path}")
        print("=" * 50)


if __name__ == "__main__":
    main()
