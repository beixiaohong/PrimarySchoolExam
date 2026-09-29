"""tools/gx_apply_content_patch.py 的回填计划测试

核心是 `_plan` 的冲突检测 —— 这里吃过一次亏：原先逐条查库判断「新指纹是否已被
占用」，但**本批里另一条还没写入、指纹仍是旧值**，于是干跑报告「冲突 0」，真正
`--apply` 却撞唯一索引 1062（`Duplicate entry ... ux_gx_knowledge_fingerprint`）。

所以预检必须一次性把所有相关指纹捞出来，在内存里连同「本批内部互相冲突」一起判。
下面用内存 SQLite 把这条钉死：`fingerprint` 列带 unique 约束，一旦漏判，写入时
真的会抛 IntegrityError —— 而不是靠断言猜。
"""
import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load(name):
    here = ROOT / "tools"
    spec = importlib.util.spec_from_file_location("_gx_" + name, str(here / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ap = _load("gx_apply_content_patch")

Base = declarative_base()


class _K(Base):
    """只保留回填要用到的列；`unique` 用来模拟线上的唯一索引"""
    __tablename__ = "gx_knowledge"
    id = Column(Integer, primary_key=True)
    fingerprint = Column(String(32), unique=True)
    summary = Column(String(600))
    content = Column(String)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _row(db, fp, content="旧正文"):
    r = _K(fingerprint=fp, content=content, summary=content[:10])
    db.add(r)
    db.flush()
    return r


def _ent(old, new, src="a.pdf", title="章节"):
    return {"old_fingerprint": old, "new_fingerprint": new, "source_file": src,
            "title": title, "content": "新正文", "summary": "新摘要"}


# ── 内部冲突（本次线上事故的回归用例） ──────────────────────────────────

def test_plan_flags_collision_inside_the_patch(db):
    """⚠️ 回归：两条针对不同行、却算出同一新指纹 —— 逐条查库查不出来，必须集合预检"""
    _row(db, "OLD1")
    _row(db, "OLD2")
    plan, stats, _miss, _conf = ap._plan(
        db, _K, [_ent("OLD1", "NEW"), _ent("OLD2", "NEW")])
    assert stats["conflict"] == 1
    assert stats["inner"] == 1, "必须识别出这是补丁内部冲突，而不是库里别行占用"
    assert stats["update"] == 1
    # 真按计划写库不能撞唯一索引
    for rid, e in plan:
        r = db.get(_K, rid)
        r.content, r.fingerprint = e["content"], e["new_fingerprint"]
    db.flush()


def test_plan_flags_collision_with_a_row_outside_the_patch(db):
    """新指纹被本批之外的行占用：同样要跳过，不能把别人的行改坏"""
    _row(db, "OLD1")
    _row(db, "OTHER")            # 不参与本次回填，却已经占了 NEW
    r = db.query(_K).filter(_K.fingerprint == "OTHER").one()
    r.fingerprint = "NEW"
    db.flush()
    plan, stats, _miss, conf = ap._plan(db, _K, [_ent("OLD1", "NEW")])
    assert stats["conflict"] == 1
    assert stats["update"] == 0
    assert conf and conf[0][1] == 1 and conf[0][2] is False


# ── 幂等 / 去重 / 未命中 ────────────────────────────────────────────────

def test_plan_skips_already_applied_entries(db):
    """已回填：old 查不到、但新指纹在库里 → 幂等跳过"""
    _row(db, "NEW1")
    plan, stats, _miss, _conf = ap._plan(db, _K, [_ent("OLD1", "NEW1")])
    assert stats["already"] == 1
    assert stats["update"] == 0
    assert plan == []


def test_plan_updates_one_row_once_when_patch_has_twice(db):
    """补丁里两条指向同一行（去重前的形态）：只更新一次，不重复写"""
    _row(db, "OLD1")
    plan, stats, _miss, _conf = ap._plan(
        db, _K, [_ent("OLD1", "NEW1", src="a.pdf"), _ent("OLD1", "NEW1", src="b.pdf")])
    assert stats["update"] == 1
    assert stats["already"] == 1
    assert len(plan) == 1


def test_plan_reports_miss_when_neither_fingerprint_exists(db):
    plan, stats, miss, _conf = ap._plan(db, _K, [_ent("OLD1", "NEW1")])
    assert stats["miss"] == 1
    assert stats["update"] == 0
    assert len(miss) == 1


def test_plan_counts_entries_without_fingerprint(db):
    plan, stats, _miss, _conf = ap._plan(
        db, _K, [_ent("", "NEW1"), _ent("OLD1", "")])
    assert stats["empty_fp"] == 2
    assert plan == []


def test_plan_empty_patch_is_noop(db):
    plan, stats, _miss, _conf = ap._plan(db, _K, [])
    assert plan == []
    assert stats["update"] == 0


# ── 补丁自检：拦住旧版补丁 ──────────────────────────────────────────────

def test_selfcheck_passes_on_clean_patch():
    ents = [_ent("OLD%d" % i, "NEW%d" % i) for i in range(4)]
    assert ap.selfcheck(ents) == []


def test_selfcheck_catches_duplicate_new_fingerprints():
    """旧版补丁（未做碰撞消解）必须被拦在写库之前"""
    dups = ap.selfcheck([_ent("OLD1", "NEW", src="a.pdf"), _ent("OLD2", "NEW", src="b.pdf")])
    assert len(dups) == 1
    assert dups[0][0]["source_file"] == "b.pdf"
    assert dups[0][1]["source_file"] == "a.pdf"


def test_selfcheck_ignores_missing_fingerprint():
    """缺指纹由 _plan 的 empty_fp 统计处理，自检不重复报错"""
    assert ap.selfcheck([_ent("", "NEW1"), _ent("OLD1", "")]) == []


_PATCH = ROOT / "data" / "gx_content_patch.json"


@pytest.mark.skipif(not _PATCH.exists(), reason="补丁未生成（需在存放资料的机器上跑 gx_rebuild_list）")
def test_real_patch_applies_with_zero_conflict():
    """端到端回归：真实补丁 + 一行不差的模拟库 → 零冲突、零未命中、全部可更新。

    这一条是整条回填链路的最终把关：它证明「本地算出来的新指纹」在写库时不会互相
    撞车。线上那次 1062 就是缺了这一步验证。
    """
    import json
    entries = json.loads(_PATCH.read_text(encoding="utf-8"))["entries"]
    assert entries
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for e in entries:
            _row(db, e["old_fingerprint"])
        plan, stats, miss, conf = ap._plan(db, _K, entries)
        assert stats["conflict"] == 0, conf[:3]
        assert stats["miss"] == 0, miss[:3]
        assert stats["update"] == len(entries)
        # 真按计划写库（unique 约束会拦住任何漏网之鱼）
        for rid, e in plan:
            r = db.get(_K, rid)
            r.content, r.fingerprint = e["content"], e["new_fingerprint"]
            db.flush()
        db.commit()


# ── 写库不违反唯一索引（集成） ──────────────────────────────────────────

def test_applying_a_clean_plan_never_raises(db):
    """干净补丁（新指纹两两不同）按计划写入，必须整批成功"""
    for i in range(5):
        _row(db, "OLD%d" % i)
    ents = [_ent("OLD%d" % i, "NEW%d" % i) for i in range(5)]
    plan, stats, _miss, _conf = ap._plan(db, _K, ents)
    assert stats["update"] == 5
    for rid, e in plan:
        r = db.get(_K, rid)
        r.content, r.fingerprint = e["content"], e["new_fingerprint"]
        db.flush()
    db.commit()
    assert sorted(r.fingerprint for r in db.query(_K).all()) == \
        ["NEW%d" % i for i in range(5)]


def test_unique_index_would_really_catch_a_bad_plan(db):
    """反证：如果预检放行了两行同指纹，写库确实会炸 —— 说明上面的断言不是空转"""
    _row(db, "A")
    _row(db, "B")
    db.query(_K).filter(_K.fingerprint == "B").one().fingerprint = "SAME"
    db.flush()
    db.query(_K).filter(_K.fingerprint == "A").one().fingerprint = "SAME"
    with pytest.raises(IntegrityError):
        db.flush()
