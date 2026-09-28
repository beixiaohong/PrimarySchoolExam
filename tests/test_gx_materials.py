"""软考高项备考资料：分类与解析工具链测试（tools/gx_parse.py + gx_pack.py + 导入映射）

为什么单独一个文件
------------------
`tools/` 下的解析工具是**资料入库的唯一入口**，但它踩过的坑全是「静默失败」型，
不写测试根本发现不了：

① 考纲归一取不到 → 知识域全空（7383 条），前端筛选/进度统计一起失效；
② 选项分隔符漏了全角句点 `．` → 「带解析」资料整份丢弃（75 题变 6 题）；
③ 案例解析把答案段当题干续写 → 题干里塞满答案；
④ 横幅标签直接写进 chapter → 章节筛选变成一堆噪声；
⑤ 「无解析/有解析」判据带了扩展名 → 规则永不生效，重复题照进题库。

所以这里对每条规则各钉一个用例，纯函数为主（不连库），最后补一个落库幂等用例。
"""
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gx_parse as gx            # noqa: E402
import gx_pack as gxpack         # noqa: E402
import import_gx_materials as gximp   # noqa: E402


# ── ① 分类 ──

@pytest.mark.parametrize("rel,cat,sub", [
    ("03. 题目电子版（每日一练+章节练习+仿真模拟）/每日一练/软考高项2605每日一练（2026.1.24-1）--第12章--项目质量管理（下）.pdf",
     gx.CAT_CHOICE, gx.SK_DAILY),
    ("03. 题目电子版（每日一练+章节练习+仿真模拟）/章节练习/第1次章节练习.pdf",
     gx.CAT_CHOICE, gx.SK_CHAPTER),
    ("03. 题目电子版（每日一练+章节练习+仿真模拟）/仿真模拟/仿真模拟（三）选择题--带解析.pdf",
     gx.CAT_CHOICE, gx.SK_MOCK),
    ("03. 题目电子版（每日一练+章节练习+仿真模拟）/仿真模拟/仿真模拟（三、四）案例题--带解析.pdf",
     gx.CAT_CASE, gx.SK_MOCK),
    ("08.考前冲刺相关资料/选择题相关/冲刺选择题汇总.pdf", gx.CAT_CHOICE, gx.SK_DIGEST),
    ("04. 课前练习（计算+案例+论文）/计算专题课练习/第34课--计算题综合（一）----有解析.pdf",
     gx.CAT_CHOICE, gx.SK_CALC),
    ("04. 课前练习（计算+案例+论文）/文字案例专题课练习/第39课--案例分析综合（二）----有解析.pdf",
     gx.CAT_CASE, "案例专题"),
    ("04. 课前练习（计算+案例+论文）/第10章--项目进度管理（上）回家作业2题.pdf",
     gx.CAT_CASE, "回家作业"),
    ("04. 课前练习（计算+案例+论文）/论文专题课练习/2605班论文练习题（一）----范围管理.pdf",
     gx.CAT_ESSAY, "论文练习"),
    ("09.音频/第1课.m4a", gx.CAT_OTHER, "音频"),
    ("05. 项目管理实战模板/项目章程模板.docx", gx.CAT_OTHER, "实战模板"),
])
def test_classify(rel, cat, sub):
    info = gx.classify(rel)
    assert info["category"] == cat
    assert info["sub"] == sub


def test_classify_reference_doc_becomes_knowledge():
    """案例/论文目录里的「背诵型汇总」不是题目，必须改判知识点（否则白跑一轮解析出 0 条）"""
    info = gx.classify("08.考前冲刺相关资料/案例题相关/案例分析常见问题汇总.pdf")
    assert info["category"] == gx.CAT_KNOWLEDGE
    assert info["sub"] == gx.KN_REF


def test_classify_unknown_falls_to_other():
    info = gx.classify("某个没见过的目录/文件.pdf")
    assert info["category"] == gx.CAT_OTHER


def test_knowledge_kind_not_fooled_by_top_dir_name():
    """02 顶层目录名本身含「思维导图」，直接 find 会把该目录下所有文件判成导图"""
    list_file = gx.classify("02. 课程主要知识点清单+思维导图+填空辅助记忆清单/知识点清单/第8章清单.pdf")
    mind = gx.classify("02. 课程主要知识点清单+思维导图+填空辅助记忆清单/思维导图/第8章导图.pdf")
    assert list_file["sub"] == gx.KN_LIST
    assert mind["sub"] == gx.KN_MINDMAP


# ── ② 章节/知识域归一 ──

@pytest.mark.parametrize("text,expected", [
    ("第12章--项目质量管理（下）.pdf", "第12章 质量管理"),
    ("第1、6~8章 章节练习", "第1章 信息化发展"),
    ("软考高项教程第四版P373：控制质量过程的主要作用", ""),
    ("第6.4.1节--项目管理12原则", "第6章 项目管理概论"),   # 无章号 → 域反查
])
def test_chapter_of(text, expected):
    assert gx.chapter_of(text) == expected


def test_normalize_chapter_keeps_domain_and_chapter_consistent():
    """章节必须与知识域自洽，否则「按章节筛选」和「按域统计」会互相打架"""
    from app.domains.assessment.services.gaoxiang import (normalize_chapter,
                                                          normalize_domain)
    assert normalize_domain("第13章 项目资源管理") == "资源管理"
    assert normalize_chapter("资源管理") == "第13章 资源管理"


def test_taxonomy_check_passes_in_project_env():
    """考纲归一可用性自检：不可用时打包脚本会直接中止（而不是产出空域数据）"""
    assert gx.taxonomy_check() == ""


# ── ③ 选择题解析 ──

DECK_CHOICE = [
    "-----【仿真模拟（三）----高项2025 年5 月班----选择题】题目-------",
    "1、新型基础设施建设是以新发展理念为引领，以（）为驱动？",
    "A、技术创新；", "B、人工智能；", "C、区块链；", "D、工业互联网；",
    "2、两化融合主要在技术、产品、（）四个方面进行融合。",
    "A、业务", "B、软件", "C、网络", "D、硬件",
]


def test_parse_choice_basic():
    out = gx.parse_choice_lines(list(DECK_CHOICE),
                                {"source_file": "仿真模拟（三）----打印版.pdf",
                                 "sub": gx.SK_MOCK, "deck": gx.deck_of("仿真模拟（三）----打印版.pdf")})
    assert len(out["items"]) == 2
    it = out["items"][0]
    assert it["question"].startswith("新型基础设施建设")
    assert it["options"] == ["A. 技术创新；", "B. 人工智能；",
                             "C. 区块链；", "D. 工业互联网；"]
    assert it["answer"] == ""            # 打印版无答案 → 由上层提示「无参考答案」
    assert it["deck"] == "仿真模拟（三）"


def test_parse_choice_fullwidth_dot_options():
    """回归：`A．xxx`（全角句点）曾不被识别 → 带解析的整份资料被丢弃"""
    lines = [
        "⚫第1题",
        "新型基础设施建设以（）为驱动？",
        "A．技术创新；", "B．人工智能；", "C．区块链；", "D．工业互联网；",
        "仿真模拟（三）",
        "答案：A",
        "⚫题意解析",
    ]
    out = gx.parse_choice_lines(lines, {"source_file": "仿真模拟（三）选择题--带解析.pdf",
                                        "sub": gx.SK_MOCK})
    assert len(out["items"]) == 1
    assert out["items"][0]["answer"] == "A"
    assert len(out["items"][0]["options"]) == 4


def test_parse_choice_multi_option_line_and_analysis_answer():
    """一行挤多个选项 + 无【参考答案】时从解析正文兜底抽答案（计算专题排版）"""
    lines = [
        "⚫决策树和预期货币价值分析（风险管理）",
        "决策树分析法通常用决策树图表进行分析，图中机会节点的预期收益EMV分别是90和（）？",
        "A、160；      B、150；      C、140；      D、100；",
        "解题思路：",
        "◆已知升级方案的EMV为90；",
        "◆开发方案的EMV=200*75%+（-40*25%）=140；",
        "◆所以选择C。",
        "⚫决策树和预期货币价值分析（风险管理）",
        "第二题题干？",
        "A、1；      B、2；      C、3；      D、4；",
    ]
    out = gx.parse_choice_lines(lines, {"source_file": "第34课--计算题综合（一）----有解析.pdf",
                                        "sub": gx.SK_CALC})
    assert len(out["items"]) == 2          # 「◆要点」不能各自另起一题
    it = out["items"][0]
    assert len(it["options"]) == 4
    assert it["answer"] == "C"
    assert it.get("answer_from_analysis") is True
    assert "所以选择C" in it["analysis"]


def test_parse_choice_does_not_take_analysis_as_option():
    """答案出现后的 `A．xxx` 引用不得再当选项（否则题干被解析正文污染）"""
    lines = [
        "1、关于项目价值的描述，不正确的是（）。",
        "A、甲", "B、乙", "C、丙", "D、丁",
        "【参考答案】B",
        "【试题解析】A．这是解析里引用的选项文本，不应进选项。",
    ]
    out = gx.parse_choice_lines(lines, {"source_file": "x.pdf", "sub": gx.SK_DAILY})
    assert len(out["items"]) == 1
    assert len(out["items"][0]["options"]) == 4
    assert out["items"][0]["answer"] == "B"


def test_choice_fingerprint_same_for_print_and_annotated():
    """打印版与带解析版必须同指纹，否则同一道题在题库里存两份"""
    base = ["1、题干内容相同（）？", "A、一", "B、二", "C、三", "D、四"]
    a = gx.parse_choice_lines(list(base) + ["答案：C"],
                              {"source_file": "a.pdf", "sub": gx.SK_MOCK})["items"][0]
    b = gx.parse_choice_lines(["1、题干内容相同（）？", "A．一", "B．二", "C．三", "D．四"],
                              {"source_file": "b.pdf", "sub": gx.SK_MOCK})["items"][0]
    assert a["fingerprint"] == b["fingerprint"]
    assert a["answer"] == "C" and b["answer"] == ""


# ── ④ 案例题解析 ──

CASE_LINES = [
    "仿真模拟（一）",
    "为实现空气质量的精细化治理，某市规划了智慧环保项目。该项目涉及网格化监测、应急管理等多个子系统。"
    "李经理任项目经理，识别出项目干系人为客户和供应商后开始了项目建设工作。",
    "⚫试题一",
    "仿真模拟（一）",
    "【问题一】（12分）：结合案例，请指出李经理在资源管理方面存在的问题",
    "【问题二】（5分）：请写出项目资源管理包含的过程",
    "⚫试题一",
    "【问题一】（12分）：结合案例，请指出李经理在资源管理方面存在的问题",
    "资源管理方面：1、没有制订完善的资源管理计划；2、未针对实物资源延期采取措施；",
    "⚫试题一",
    "【问题二】（5分）：请写出项目资源管理包含的过程",
    "1、规划资源管理；2、估算活动资源；3、获取资源；4、建设团队；",
]


def test_parse_case_separates_answer_from_question():
    """回归：答案段把问题重抄一遍，曾被当成题干续写 → 题干里灌满答案"""
    out = gx.parse_case_lines(list(CASE_LINES),
                              {"source_file": "仿真模拟（一、二）案例题---带解析.pdf",
                               "sub": gx.SK_MOCK})
    assert len(out["items"]) == 1
    it = out["items"][0]
    assert it["title"] == "仿真模拟（一） 试题一"
    assert it["deck"] == "仿真模拟（一）"
    subs = {s["q"][:6]: s for s in it["sub_questions"]}
    q1 = [s for s in it["sub_questions"] if "问题一" in s["q"] or "12分" in s["q"]][0]
    assert "没有制订完善的资源管理计划" not in q1["q"]      # 答案没进题干
    assert "没有制订完善的资源管理计划" in q1["answer"]     # 答案在答案里
    assert q1["points"] == 12
    q2 = [s for s in it["sub_questions"] if s["points"] == 5][0]
    assert "规划资源管理" in q2["answer"]


def test_parse_case_shared_store_merges_answer_file():
    """题目与答案分两个 PDF：共用块存储，答案文件把答案灌进题目已经建好的块"""
    q_lines = ["第10章 项目进度管理 回家作业",
               "⚫回家作业1",
               "某项目包含 A~K 共 11 项活动，活动之间的依赖关系如下表所示，项目工期需要计算。",
               "【问题一】请画出单代号网络图并计算关键路径。",
               "【问题二】请计算该项目的总工期。"]
    a_lines = ["⚫回家作业1",
               "【问题一】请画出单代号网络图并计算关键路径。",
               "关键路径为 A→C→F→K，工期 17 天。",
               "【问题二】请计算该项目的总工期。",
               "总工期为 17 天。"]
    meta_q = {"source_file": "q.pdf", "sub": gx.SK_DAILY, "domain": "", "chapter": ""}
    out = gx.parse_case_lines(list(q_lines), dict(meta_q), None)
    store = out["store"]
    out = gx.parse_case_lines(list(a_lines),
                              dict(meta_q, source_file="a.pdf", is_answer_file=True),
                              store)
    assert len(out["items"]) == 1
    it = out["items"][0]
    assert it["source_file"] == "q.pdf"                # 条目归属题目文件
    assert sum(1 for s in it["sub_questions"] if s["answer"]) == 2


# ── ⑤ 论文题解析 ──

ESSAY_LINES = [
    "题目----论信息系统项目的范围管理",
    "实施项目范围管理的目的是确保项目做且只做所需的全部工作，关注为项目界定清楚工作边界。",
    "请以“论信息系统项目的范围管理”为题，分别从以下三个方面进行论述：",
    "1、概要叙述你参与管理过的信息系统项目，并说明你在其中承担的工作。",
    "2、结合项目，围绕以下要点论述你对范围管理的认识：",
    "（1）写出你制定的范围管理计划的主要内容；",
    "（2）写出WBS的创建过程。",
]


def test_parse_essay():
    out = gx.parse_essay_lines(list(ESSAY_LINES),
                               {"source_file": "2605班论文练习题（一）----范围管理.pdf",
                                "sub": "论文练习"})
    assert len(out["items"]) == 1
    it = out["items"][0]
    assert it["title"] == "论信息系统项目的范围管理"
    assert it["domain"] == "范围管理"
    assert it["chapter"] == "第9章 范围管理"
    assert len(it["requirements"]) == 2
    assert "WBS的创建过程" in it["requirements"][1]


# ── ⑥ 打包：配对 / 跳过 / 去重 ──

def test_pair_key_strips_answer_suffix():
    assert gxpack._pair_key("d/xxx.pdf")[0] == gxpack._pair_key("d/xxx（答案）.pdf")[0]
    assert gxpack._pair_key("d/xxx（答案）.pdf")[1] == "ans"


CALC_DIR = "04. 课前练习（计算+案例+论文）/计算专题课练习/"
DAILY_DIR = "03. 题目电子版（每日一练+章节练习+仿真模拟）/每日一练/"
HW_DIR = "04. 课前练习（计算+案例+论文）/"


def test_plan_skips_noanswer_variant():
    """`----无解析` 在同名 `----有解析` 存在时必须跳过（判据必须落在 stem 上）"""
    paths = [CALC_DIR + "第34课--计算题综合（一）----无解析.pdf",
             CALC_DIR + "第34课--计算题综合（一）----有解析.pdf"]
    p = gxpack.plan(paths)
    kept = [g[0][0] for g in p["groups"]]
    assert kept == [paths[1]]
    assert paths[0] in p["skip"]


def test_plan_pairs_question_and_answer_files():
    paths = [HW_DIR + "第10章--项目进度管理（上）回家作业2题----提前滞后量、单代号和双代号图.pdf",
             HW_DIR + "第10章--项目进度管理（上）回家作业2题----提前滞后量、单代号和双代号图（答案）.pdf"]
    p = gxpack.plan(paths)
    assert len(p["groups"]) == 1
    assert p["groups"][0][0][1] is False      # 题目在前
    assert p["groups"][0][1][1] is True       # 答案在后


def test_plan_skips_non_pdf_and_other_category():
    p = gxpack.plan(["09.音频/第1课.m4a", "01. 直播课程课件/第1课.pdf"])
    assert "09.音频/第1课.m4a" in p["skip"]
    assert [g[0][0] for g in p["groups"]] == ["01. 直播课程课件/第1课.pdf"]


def test_dedupe_keeps_richest_and_records_sources():
    """同题多出处：留信息最全的那份（有答案 > 无答案），并把出处合并记录"""
    items = [
        {"question": "题干", "options": ["A. 一"], "answer": "", "analysis": "",
         "source_file": "print.pdf"},
        {"question": "题干", "options": ["A. 一"], "answer": "A",
         "analysis": "详解", "source_file": "annotated.pdf"},
    ]
    kept, st = gxpack.dedupe(gx.CAT_CHOICE, items)
    assert len(kept) == 1
    assert kept[0]["answer"] == "A"
    assert kept[0]["sources"] == ["annotated.pdf", "print.pdf"]
    assert st == {"in": 2, "out": 1, "dups": 1}


def test_clean_case_drops_choice_fallback_without_answer():
    """纯图形作业的表格碎片会被选择题兜底解析器切成假题，必须丢掉"""
    items = [
        {"sub_questions": [{"q": "x"}], "answer": ""},          # 真案例题
        {"answer": "D"},                                        # 有答案的兜底选择题
        {"question": "FS-2 FF-2 SS-2", "options": ["A. 5天"], "answer": ""},  # 假题
    ]
    out = gxpack._clean_case(items)
    assert len(out) == 2


# ── ⑦ 数据包 → 入库记录映射 ──

def test_question_row_maps_choice():
    it = {"category": gx.CAT_CHOICE, "fingerprint": "fp1", "domain": "质量管理",
          "chapter": "第12章 质量管理", "source_kind": gx.SK_DAILY,
          "source_file": "a.pdf", "deck": "", "seq": 3,
          "question": "题干", "options": ["A. 一"], "answer": "AB", "analysis": "解析"}
    row = gximp.question_row(it, 1)
    assert row["qtype"] == "multi"            # 答案多字母 → 多选
    assert json.loads(row["options_json"]) == ["A. 一"]
    assert row["source"] == "import" and row["seq"] == 3
    assert row["sub_questions"] is None


def test_question_row_maps_case_and_essay():
    case = {"category": gx.CAT_CASE, "fingerprint": "fp2", "domain": "资源管理",
            "background": "背景材料", "title": "试题一",
            "sub_questions": [{"q": "问题一", "answer": "答案一", "points": 12}]}
    row = gximp.question_row(case, 1)
    assert row["qtype"] == "case"
    assert row["question"] == "背景材料"
    assert json.loads(row["sub_questions"])[0]["points"] == 12

    essay = {"category": gx.CAT_ESSAY, "fingerprint": "fp3", "domain": "范围管理",
             "title": "论范围管理", "background": "背景",
             "requirements": ["要求一", "要求二"]}
    row = gximp.question_row(essay, 1)
    assert row["qtype"] == "essay"
    assert row["options_json"] is None
    assert len(json.loads(row["sub_questions"])) == 2


def test_knowledge_row_and_material_rows():
    k = {"fingerprint": "fpk", "domain": "质量管理", "title": "t", "summary": "s",
         "content": "c", "chapter": "第12章 质量管理", "kind": gx.KN_RECITE,
         "source_file": "a.pdf", "seq": 7}
    row = gximp.knowledge_row(k, 1)
    assert row["source"] == "import" and row["seq"] == 7 and row["kind"] == "recite"

    manifest = {"files": [{"rel_path": "d/a.pdf", "category": gx.CAT_CHOICE,
                           "sub_kind": gx.SK_DAILY, "items": 3,
                           "size_bytes": 123, "skipped": "", "error": ""}]}
    rows = gximp.material_rows(manifest)
    assert rows[0]["rel_path"] == "d/a.pdf"
    assert rows[0]["title"] == "a" and rows[0]["ext"] == "pdf"
    assert rows[0]["size_bytes"] == 123


def test_check_pack_rejects_empty_dir(tmp_path):
    with pytest.raises(SystemExit):
        gximp.check_pack(str(tmp_path))


# ── ⑧ 落库幂等（集成，走测试库） ──

def test_import_upsert_is_idempotent():
    """同一指纹导入两次只留一行：这是「重复导入不翻倍」的根基"""
    from app.database import SessionLocal
    from app.models.gaoxiang import GxQuestion
    from sqlalchemy import text as _sql

    uid_fp = "gx_test_fp_idem_0001"
    db = SessionLocal()
    try:
        db.query(GxQuestion).filter(GxQuestion.fingerprint == uid_fp).delete()
        db.commit()
        row = gximp.question_row(
            {"category": gx.CAT_CHOICE, "fingerprint": uid_fp, "domain": "质量管理",
             "question": "幂等测试题干", "options": ["A. 一"], "answer": "A"},
            1)
        ins, upd, skip = gximp._upsert(db, GxQuestion, [row], "测试")
        assert (ins, upd, skip) == (1, 0, 0)
        row2 = dict(row, answer="B")
        ins, upd, skip = gximp._upsert(db, GxQuestion, [row2], "测试")
        assert (ins, upd) == (0, 1)
        rows = db.query(GxQuestion).filter(GxQuestion.fingerprint == uid_fp).all()
        assert len(rows) == 1
        assert rows[0].answer == "B"                  # 更新覆盖
        # 无指纹行不入库（AI 动态题为 NULL，不参与去重）
        _, _, skipped = gximp._upsert(db, GxQuestion, [dict(row, fingerprint="")], "测试")
        assert skipped == 1
    finally:
        db.query(GxQuestion).filter(GxQuestion.fingerprint == uid_fp).delete()
        db.commit()
        db.close()
