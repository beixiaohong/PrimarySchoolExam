"""浙江初中（初一/7年级）九科内容与题库采集录入管线

用途：按浙江教材章节大纲，用 DeepSeek 批量生成初一(7年级)九科的「知识点 + 选择题题库」，
幂等去重后录入系统；英语单词书与语文古诗文用权威硬编码内容保证准确。

学科范围（系统既有九科拆分：语数英 + 物化生 + 政史地）：
- 数学（浙教版七上）、物理/化学（浙教版科学中的理化基础）、生物（浙教版科学）、
  地理（人教版七上）、道德与法治（统编七上）、历史（统编七上）、
  语文（统编七上古诗文 + 知识点）、英语（人教版七上单词书 + 语法点）。

数据库：直连 .env 配置的主库（与线上一致），脚本幂等（按自然键去重），支持 --dry-run。

用法：
  python tools/seed_junior_grade7.py                 # 全量生成并入库
  python tools/seed_junior_grade7.py --dry-run       # 只生成不写库（预览）
  python tools/seed_junior_grade7.py --subjects 数学 物理   # 只跑指定学科
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402
from app.database import SessionLocal, Base  # noqa: E402
from app.models import (TextbookVersion, MiddleQuestion, KnowledgePoint,  # noqa: E402
                        WordBook, Word, ClassicalText, GrammarPoint, GrammarExercise)

GRADE = 7

# ── DeepSeek 配置（复用 .env 的 DEEPSEEK_API_KEY）──
DEEPSEEK_KEY = ""
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DEEPSEEK_API_KEY="):
            DEEPSEEK_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")

SUBJECTS = ["数学", "物理", "化学", "生物", "地理", "道德与法治", "历史", "语文", "英语"]

# 浙江初一(7年级) 教材版本配置（name=版本，remark=说明）
EDITIONS = {
    "数学": ("浙教版", "浙江教育出版社 七年级上册"),
    "物理": ("浙教版科学", "科学(七上)中的物理基础：测量/密度/物态变化/力与运动"),
    "化学": ("浙教版科学", "科学(七上)中的物质科学基础：变化分类/构成/空气/水"),
    "生物": ("浙教版科学", "科学(七上)中的生命科学：观察生物/多样/绿色植物/人体"),
    "地理": ("人教版", "七年级上册 地球·地图·气候·居民"),
    "道德与法治": ("统编版", "义务教育教科书 七年级上册"),
    "历史": ("统编版", "中国历史 七年级上册"),
    "语文": ("统编版", "义务教育教科书 语文 七年级上册"),
    "英语": ("人教版", "Go for it! 七年级上册"),
}

# 各学科的「单元章节」大纲（用于逐单元生成知识点+题库）
UNIT_OUTLINE = {
    # ── 数学（浙教版七上，按章→节拆细）──
    "数学": ["七上·1.1 正数与负数", "七上·1.2 数轴", "七上·1.3 相反数与绝对值",
            "七上·2.1 有理数的加法与减法", "七上·2.2 有理数的乘法与除法",
            "七上·2.3 有理数的乘方与科学记数法", "七上·3.1 平方根", "七上·3.2 立方根",
            "七上·3.3 实数及其运算", "七上·4.1 代数式与列代数式",
            "七上·4.2 整式（单项式与多项式）", "七上·4.3 合并同类项与去括号",
            "七上·5.1 一元一次方程及其解法", "七上·5.2 方程应用：和差倍分与配套",
            "七上·5.3 方程应用：行程与工程", "七上·6.1 几何图形初步",
            "七上·6.2 直线、射线与线段", "七上·6.3 角与角的度量"],
    # ── 物理（浙教版科学七上·物理部分）──
    "物理": ["七上·测量：长度与体积", "七上·测量：温度", "七上·质量及其测量",
            "七上·密度及其测量", "七上·物态变化：熔化与凝固", "七上·物态变化：汽化与液化",
            "七上·物态变化：升华与凝华", "七上·力的初步认识", "七上·重力与弹力",
            "七上·速度与机械运动"],
    # ── 化学（浙教版科学七上·化学部分）──
    "化学": ["七上·物理变化与化学变化", "七上·物质的性质",
            "七上·物质的构成：分子", "七上·物质的构成：原子与元素",
            "七上·空气的成分与用途", "七上·氧气及其性质", "七上·水与溶液初步",
            "七上·溶质质量分数"],
    # ── 生物（浙教版科学七上·生物部分）──
    "生物": ["七上·观察生物：显微镜", "七上·细胞的结构与功能",
            "七上·生物多样性", "七上·绿色植物的光合作用",
            "七上·绿色植物的呼吸作用", "七上·人体的营养",
            "七上·人体的呼吸与循环", "七上·生命活动的调节"],
    # ── 地理（人教版七上）──
    "地理": ["七上·地球的形状与大小", "七上·地球仪与经纬网",
            "七上·地球的运动：自转", "七上·地球的运动：公转与五带",
            "七上·地图三要素", "七上·大洲与大洋", "七上·海陆的变迁",
            "七上·天气与气温", "七上·降水与气候", "七上·居民与聚落"],
    # ── 道德与法治（统编七上）──
    "道德与法治": ["七上·中学时代", "七上·学习新天地", "七上·发现自己",
            "七上·友谊与成长同行", "七上·网上交友新时空", "七上·师生之间",
            "七上·亲情之爱", "七上·生命的思考"],
    # ── 历史（统编七上）──
    "历史": ["七上·中国境内早期人类的代表", "七上·原始农耕生活",
            "七上·远古的传说", "七上·夏商周的更替", "七上·动荡的春秋与战国",
            "七上·秦统一中国", "七上·秦末农民起义与汉初统治",
            "七上·汉武帝巩固大一统", "七上·三国鼎立", "七上·两晋南北朝与民族交融"],
    # ── 语文（统编七上，古诗文由 seed_chinese 硬编码，此处补现代文/名著/写作/语法知识点）──
    "语文": ["七上·古代诗歌四首", "七上·文言文：世说新语与论语",
            "七上·现代文：写景散文（春/济南的冬天）", "七上·现代文：叙事散文（散步/秋天的怀念）",
            "七上·现代文：从百草园到三味书屋", "七上·名著导读：朝花夕拾与西游记",
            "七上·写作：写人记事要具体", "七上·语法与修辞：比喻拟人/病句/标点"],
}


def call_deepseek(system: str, user: str, max_tokens: int = 3000) -> str:
    """调用 DeepSeek，返回文本内容；失败/空响应自动重试（最多 2 次退避），仍失败返回空串。"""
    if not DEEPSEEK_KEY:
        print("  [warn] 未配置 DEEPSEEK_API_KEY，跳过 AI 生成")
        return ""
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": 0.4,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {DEEPSEEK_KEY}"},
        method="POST",
    )
    last_err = ""
    for attempt in range(4):
        try:
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=40, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = (data["choices"][0]["message"]["content"] or "").strip()
                if content:
                    return content
                last_err = "空响应"
        except Exception as e:
            last_err = f"{type(e).__name__} {str(e)[:120]}"
        if attempt < 3:
            backoff = min(5 * (2 ** attempt), 60)  # 5s / 10s / 20s / 40s 退避，缓解限流
            time.sleep(backoff)
    print(f"  [error] DeepSeek 连续失败（{last_err}）")
    return ""


def gen_unit(subject: str, unit: str) -> dict:
    """为一个单元生成 知识点 + 选择题。返回 {knowledge:[...], questions:[...]}。"""
    system = (
        "你是浙江初中（初一/七年级）的资深学科命题与教研专家，严格依据"
        f"《{EDITIONS.get(subject, ('',''))[0]}》{subject}七年级上册的课程标准与教材内容出题。"
        "只产出符合初中生认知水平、表述严谨、无事实错误的内容。"
    )
    user = (
        f"请为「{subject}」「{unit}」生成教学资源，必须且只能输出一个 JSON 对象，结构如下：\n"
        "{\n"
        '  "knowledge": [ {"title":"知识点标题","summary":"一句话要点","content":"详细讲解(规则/推导/易错点, 80-200字)","examples":"示例每行一个(1-3行)","difficulty":2} ],\n'
        '  "questions": [ {"question":"题干","options":["A","B","C","D"],"answer":"必须是options中某一项的原文","analysis":"解析(40-120字)"} ]\n'
        "}\n"
        "要求：\n"
        "1. knowledge 生成 4-6 个本单元核心知识点；\n"
        "2. questions 生成 10-12 道单选题，每题恰好 4 个选项，answer 必须是 options 中某一选项的【原文字】；\n"
        "3. 题目覆盖本单元主要考点，难度梯度合理，不要出超纲或歧义题；\n"
        "4. 不要输出 JSON 以外的任何文字。\n"
    )
    raw = call_deepseek(system, user)
    if not raw:
        return {"knowledge": [], "questions": []}
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        # 容错：去掉可能的前后缀
        s = raw.find("{")
        e = raw.rfind("}")
        if s >= 0 and e > s:
            try:
                obj = json.loads(raw[s:e + 1])
            except Exception:
                return {"knowledge": [], "questions": []}
        else:
            return {"knowledge": [], "questions": []}
    return obj


def ensure_tables():
    """确保新表存在（幂等；仅建缺失表，不动已有表）。"""
    Base.metadata.create_all(bind=SessionLocal().bind, checkfirst=True)


def seed_editions(dry: bool):
    print("== 教材版本配置 ==")
    if dry:
        for s, (n, r) in EDITIONS.items():
            print(f"  [dry] {s} G{GRADE} -> {n} ({r})")
        return
    db = SessionLocal()
    try:
        for s, (n, r) in EDITIONS.items():
            exists = db.query(TextbookVersion).filter_by(
                subject=s, grade=GRADE, name=n).first()
            if exists:
                print(f"  skip {s} G{GRADE} {n} (已存在)")
                continue
            db.add(TextbookVersion(subject=s, grade=GRADE, name=n,
                                   sort_order=0, enabled=True, remark=r))
            print(f"  add  {s} G{GRADE} {n}")
        db.commit()
    finally:
        db.close()


def _dedup_middle(db, subject, question) -> bool:
    return db.query(MiddleQuestion).filter_by(
        subject=subject, question=question).first() is not None


def _dedup_kp(db, subject, grade, unit, title) -> bool:
    return db.query(KnowledgePoint).filter_by(
        subject=subject, grade=grade, unit=unit, title=title).first() is not None


def seed_subject(subject: str, dry: bool):
    units = UNIT_OUTLINE.get(subject, [])
    if not units:
        print(f"  [skip] {subject} 无大纲（由专属逻辑处理）")
        return
    print(f"== {subject} G{GRADE}（{len(units)} 单元）==")
    total_k = total_q = 0
    for unit in units:
        obj = gen_unit(subject, unit)
        kps = obj.get("knowledge", []) or []
        qs = obj.get("questions", []) or []
        if dry:
            print(f"  [dry] {unit}: 知识点 {len(kps)} / 题 {len(qs)}")
            total_k += len(kps)
            total_q += len(qs)
            time.sleep(0.3)
            continue
        db = SessionLocal()
        try:
            added_k = added_q = 0
            for k in kps:
                title = (k.get("title") or "").strip()
                if not title or _dedup_kp(db, subject, GRADE, unit, title):
                    continue
                db.add(KnowledgePoint(
                    subject=subject, grade=GRADE, unit=unit, title=title,
                    summary=(k.get("summary") or "").strip()[:500],
                    content=(k.get("content") or "").strip(),
                    examples=(k.get("examples") or "").strip(),
                    difficulty=int(k.get("difficulty") or 2),
                    source="seed"))
                added_k += 1
            for q in qs:
                question = (q.get("question") or "").strip()
                options = q.get("options") or []
                answer = (q.get("answer") or "").strip()
                if not question or len(options) != 4 or answer not in options:
                    continue  # 跳过不合格题
                if _dedup_middle(db, subject, question):
                    continue
                db.add(MiddleQuestion(
                    subject=subject, grade=GRADE, type="choice", unit=unit,
                    review_status="approved",
                    question=question[:1000],
                    options_json=json.dumps(options, ensure_ascii=False),
                    answer=answer[:200],
                    analysis=(q.get("analysis") or "").strip()[:1000]))
                added_q += 1
            db.commit()
            total_k += added_k
            total_q += added_q
            print(f"  {unit}: +知识点 {added_k} / +题 {added_q}")
        finally:
            db.close()
        time.sleep(3)  # 节流，降低触发速率限制概率
    print(f"  >> {subject} 累计: 知识点 {total_k} / 题 {total_q}")


# ── 英语：硬编码权威单词书（人教版 Go for it! 七上）──
ENGLISH_BOOK_NAME = "人教版 七年级上 (Go for it!)"
ENGLISH_UNITS = {
    "Starter": [("hello", "/həˈləʊ/", "int.", "你好"), ("good", "/ɡʊd/", "adj.", "好的"),
                ("morning", "/ˈmɔːnɪŋ/", "n.", "早晨"), ("fine", "/faɪn/", "adj.", "健康的；美好的"),
                ("thank", "/θæŋk/", "v.", "感谢"), ("what", "/wɒt/", "pron.&adj.", "什么"),
                ("this", "/ðɪs/", "pron.", "这；这个"), ("map", "/mæp/", "n.", "地图"),
                ("key", "/kiː/", "n.", "钥匙；关键"), ("color", "/ˈkʌlə/", "n.", "颜色")],
    "Unit 1": [("name", "/neɪm/", "n.", "名字；名称"), ("nice", "/naɪs/", "adj.", "令人愉快的"),
               ("to", "/tuː/", "prep.", "常用于原形动词前"), ("meet", "/miːt/", "v.", "遇见；相逢"),
               ("too", "/tuː/", "adv.", "也；又；太"), ("your", "/jɔː/", "pron.", "你的；你们的"),
               ("Ms", "/mɪz/", "n.", "女士"), ("his", "/hɪz/", "pron.", "他的"),
               ("and", "/ænd/", "conj.", "和；又；而"), ("her", "/hɜː/", "pron.", "她的"),
               ("yes", "/jes/", "adv.", "是的；可以"), ("she", "/ʃiː/", "pron.", "她")],
    "Unit 2": [("family", "/ˈfæməli/", "n.", "家；家庭"), ("parent", "/ˈpeərənt/", "n.", "父（母）亲"),
               ("brother", "/ˈbrʌðə/", "n.", "兄；弟"), ("sister", "/ˈsɪstə/", "n.", "姐；妹"),
               ("grandmother", "/ˈɡrænmʌðə/", "n.", "祖母；外祖母"), ("grandfather", "/ˈɡrænfɑːðə/", "n.", "祖父；外祖父"),
               ("these", "/ðiːz/", "pron.", "这些"), ("those", "/ðəʊz/", "pron.", "那些"),
               ("who", "/huː/", "pron.", "谁"), ("daughter", "/ˈdɔːtə/", "n.", "女儿"),
               ("cousin", "/ˈkʌzn/", "n.", "堂（表）兄弟；堂（表）姐妹"), ("aunt", "/ɑːnt/", "n.", "姑母；姨母；伯母")],
    "Unit 3": [("pencil", "/ˈpensl/", "n.", "铅笔"), ("book", "/bʊk/", "n.", "书"),
               ("eraser", "/ɪˈreɪzə/", "n.", "橡皮"), ("box", "/bɒks/", "n.", "箱；盒"),
               ("schoolbag", "/ˈskuːlbæɡ/", "n.", "书包"), ("dictionary", "/ˈdɪkʃənri/", "n.", "词典；字典"),
               ("his", "/hɪz/", "pron.", "他的"), ("hers", "/hɜːz/", "pron.", "她的"),
               ("mine", "/maɪn/", "pron.", "我的"), ("teacher", "/ˈtiːtʃə/", "n.", "老师"),
               ("excuse", "/ɪkˈskjuːz/", "v.", "原谅；宽恕"), ("welcome", "/ˈwelkəm/", "adj.", "受欢迎的")],
    "Unit 4": [("where", "/weə/", "adv.", "在哪里；到哪里"), ("table", "/ˈteɪbl/", "n.", "桌子"),
               ("bed", "/bed/", "n.", "床"), ("sofa", "/ˈsəʊfə/", "n.", "沙发"),
               ("chair", "/tʃeə/", "n.", "椅子"), ("on", "/ɒn/", "prep.", "在……上"),
               ("in", "/ɪn/", "prep.", "在……里"), ("under", "/ˈʌndə/", "prep.", "在……下"),
               ("come", "/kʌm/", "v.", "来；来到"), ("room", "/ruːm/", "n.", "房间"),
               ("their", "/ðeə/", "pron.", "他（她、它）们的"), ("hat", "/hæt/", "n.", "帽子")],
    "Unit 5": [("do", "/duː/", "aux.v.", "用于构成疑问句和否定句"), ("have", "/hæv/", "v.", "有"),
               ("tennis", "/ˈtenɪs/", "n.", "网球"), ("ball", "/bɔːl/", "n.", "球"),
               ("ping-pong", "/ˈpɪŋpɒŋ/", "n.", "乒乓球"), ("soccer", "/ˈsɒkə/", "n.", "足球"),
               ("volleyball", "/ˈvɒlibɔːl/", "n.", "排球"), ("basketball", "/ˈbɑːskɪtbɔːl/", "n.", "篮球"),
               ("let", "/let/", "v.", "允许；让"), ("us", "/ʌs/", "pron.", "我们（宾格）"),
               ("go", "/ɡəʊ/", "v.", "去；走"), ("we", "/wiː/", "pron.", "我们")],
    "Unit 6": [("like", "/laɪk/", "v.", "喜欢；喜爱"), ("banana", "/bəˈnɑːnə/", "n.", "香蕉"),
               ("hamburger", "/ˈhæmbɜːɡə/", "n.", "汉堡包"), ("tomato", "/təˈmɑːtəʊ/", "n.", "西红柿"),
               ("ice-cream", "/ˈaɪskriːm/", "n.", "冰激凌"), ("salad", "/ˈsæləd/", "n.", "沙拉"),
               ("strawberry", "/ˈstrɔːbəri/", "n.", "草莓"), ("pear", "/peə/", "n.", "梨"),
               ("milk", "/mɪlk/", "n.", "牛奶"), ("bread", "/bred/", "n.", "面包"),
               ("egg", "/eɡ/", "n.", "蛋；鸡蛋"), ("rice", "/raɪs/", "n.", "大米；米饭")],
    "Unit 7": [("much", "/mʌtʃ/", "pron.&adj.", "许多；大量"), ("sock", "/sɒk/", "n.", "短袜"),
               ("T-shirt", "/ˈtiːʃɜːt/", "n.", "T恤衫"), ("shorts", "/ʃɔːts/", "n.", "短裤"),
               ("sweater", "/ˈswetə/", "n.", "毛衣"), ("trousers", "/ˈtraʊzəz/", "n.", "裤子"),
               ("shoe", "/ʃuː/", "n.", "鞋"), ("skirt", "/skɜːt/", "n.", "裙子"),
               ("dollar", "/ˈdɒlə/", "n.", "元（美国、加拿大货币单位）"), ("big", "/bɪɡ/", "adj.", "大的；大号的"),
               ("small", "/smɔːl/", "adj.", "小的；小号的"), ("short", "/ʃɔːt/", "adj.", "短的；矮的")],
    "Unit 8": [("when", "/wen/", "adv.", "什么时候"), ("month", "/mʌnθ/", "n.", "月；月份"),
               ("January", "/ˈdʒænjuəri/", "n.", "一月"), ("February", "/ˈfebrʊəri/", "n.", "二月"),
               ("March", "/mɑːtʃ/", "n.", "三月"), ("April", "/ˈeɪprəl/", "n.", "四月"),
               ("May", "/meɪ/", "n.", "五月"), ("June", "/dʒuːn/", "n.", "六月"),
               ("July", "/dʒʊˈlaɪ/", "n.", "七月"), ("August", "/ˈɔːɡəst/", "n.", "八月"),
               ("September", "/sepˈtembə/", "n.", "九月"), ("October", "/ɒkˈtəʊbə/", "n.", "十月")],
    "Unit 9": [("favorite", "/ˈfeɪvərɪt/", "adj.&n.", "特别喜爱的（人或事物）"), ("subject", "/ˈsʌbdʒɪkt/", "n.", "学科；科目"),
               ("science", "/ˈsaɪəns/", "n.", "科学"), ("P.E.", "/ˌpiːˈiː/", "n.", "体育"),
               ("music", "/ˈmjuːzɪk/", "n.", "音乐"), ("math", "/mæθ/", "n.", "数学"),
               ("Chinese", "/ˌtʃaɪˈniːz/", "n.", "语文；汉语"), ("English", "/ˈɪŋɡlɪʃ/", "n.", "英语"),
               ("history", "/ˈhɪstri/", "n.", "历史"), ("why", "/waɪ/", "adv.", "为什么"),
               ("because", "/bɪˈkɒz/", "conj.", "因为"), ("Monday", "/ˈmʌndeɪ/", "n.", "星期一")],
}


def seed_english(dry: bool):
    print("== 英语 G7（单词书 + 语法点）==")
    if dry:
        n = sum(len(v) for v in ENGLISH_UNITS.values())
        print(f"  [dry] 单词书 {ENGLISH_BOOK_NAME}: {len(ENGLISH_UNITS)} 单元 / {n} 词")
        print(f"  [dry] 语法点将由 API 生成")
        return
    db = SessionLocal()
    try:
        book = db.query(WordBook).filter_by(name=ENGLISH_BOOK_NAME, grade=GRADE).first()
        if not book:
            book = WordBook(name=ENGLISH_BOOK_NAME, grade=GRADE, semester="上",
                            publisher="人教版", word_count=0)
            db.add(book)
            db.flush()
            print(f"  add 词书 {ENGLISH_BOOK_NAME} (id={book.id})")
        added = 0
        for unit, words in ENGLISH_UNITS.items():
            for w in words:
                word, ph, pos, mean = w
                if db.query(Word).filter_by(book_id=book.id, word=word).first():
                    continue
                db.add(Word(book_id=book.id, word=word, phonetic=ph,
                           pos=pos, meaning=mean, unit=unit, difficulty=2))
                added += 1
        book.word_count = db.query(Word).filter_by(book_id=book.id).count()
        db.commit()
        print(f"  +单词 {added}（词书共 {book.word_count}）")
    finally:
        db.close()
    # 语法点（API 生成）
    seed_english_grammar(dry=False)


def seed_english_grammar(dry: bool):
    system = "你是初中英语语法专家，依据人教版 Go for it! 七年级上册内容命题。"
    user = (
        "为「人教版七年级上册英语」生成 8 个核心语法点，输出 JSON：\n"
        '{"points":[{"name":"语法点名","code":"唯一英文编码如 t_present","category":"时态/词法/句型","description":"规则说明(60-150字)","examples":"例句每行一个(2-4行)"}]}\n'
        "覆盖：be动词/一般现在时、名词单复数、代词、介词、一般疑问句、数词、冠词、祈使句。"
        "只输出 JSON，不要额外文字。"
    )
    raw = call_deepseek(system, user, max_tokens=2500)
    pts = []
    if raw:
        try:
            pts = json.loads(raw).get("points", []) or []
        except Exception:
            s, e = raw.find("{"), raw.rfind("}")
            if s >= 0 and e > s:
                try:
                    pts = json.loads(raw[s:e + 1]).get("points", []) or []
                except Exception:
                    pts = []
    if dry:
        print(f"  [dry] 语法点 {len(pts)}")
        return
    db = SessionLocal()
    try:
        added = 0
        for p in pts:
            code = (p.get("code") or "").strip()
            name = (p.get("name") or "").strip()
            if not code or not name:
                continue
            if db.query(GrammarPoint).filter_by(code=code).first():
                continue
            gp = GrammarPoint(name=name, code=code, grade=GRADE,
                              category=(p.get("category") or "词法")[:50],
                              description=(p.get("description") or "").strip()[:500],
                              examples=(p.get("examples") or "").strip())
            db.add(gp)
            db.flush()
            # 每个语法点配 2 道选择题
            ex = _gen_grammar_exercises(name, p.get("description", ""))
            for e in ex:
                db.add(GrammarExercise(grammar_point_id=gp.id, grade=GRADE,
                                       exercise_type="choice", question=e["question"],
                                       options=json.dumps(e["options"], ensure_ascii=False),
                                       answer=e["answer"], explanation=e.get("explanation", "")[:500]))
            added += 1
            time.sleep(2)  # 语法练习逐题节流
        db.commit()
        print(f"  +语法点 {added}")
    finally:
        db.close()


def _gen_grammar_exercises(name: str, desc: str) -> list:
    system = "你是初中英语语法命题专家。"
    user = (
        f"基于语法点「{name}」({desc[:80]})，出 2 道单选题，输出 JSON：\n"
        '{"items":[{"question":"题干","options":["A","B","C","D"],"answer":"选项原文","explanation":"解析"}]}\n'
        "只输出 JSON。"
    )
    raw = call_deepseek(system, user, max_tokens=800)
    if not raw:
        return []
    try:
        return json.loads(raw).get("items", []) or []
    except Exception:
        s, e = raw.find("{"), raw.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(raw[s:e + 1]).get("items", []) or []
            except Exception:
                return []
    return []


# ── 语文：硬编码统编七上古诗文（权威，避免 AI 出错）──
CLASSICAL_G7 = [
    ("观沧海", "曹操", "东汉末", "四言古诗",
     "东临碣石，以观沧海。水何澹澹，山岛竦峙。树木丛生，百草丰茂。秋风萧瑟，洪波涌起。日月之行，若出其中；星汉灿烂，若出其里。幸甚至哉，歌以咏志。",
     "借景抒情，展现诗人开阔胸襟与统一天下的抱负。"),
    ("闻王昌龄左迁龙标遥有此寄", "李白", "唐", "七言绝句",
     "杨花落尽子规啼，闻道龙标过五溪。我寄愁心与明月，随君直到夜郎西。",
     "以明月寄愁，表达对友人的深切牵挂。"),
    ("次北固山下", "王湾", "唐", "五言律诗",
     "客路青山外，行舟绿水前。潮平两岸阔，风正一帆悬。海日生残夜，江春入旧年。乡书何处达？归雁洛阳边。",
     "写景壮阔，蕴含新旧交替的哲理与思乡之情。"),
    ("天净沙·秋思", "马致远", "元", "元曲",
     "枯藤老树昏鸦，小桥流水人家，古道西风瘦马。夕阳西下，断肠人在天涯。",
     "以意象叠加写尽羁旅之愁。"),
    ("《论语》十二章", "孔子及弟子", "春秋", "文言文",
     "学而时习之，不亦说乎？有朋自远方来，不亦乐乎？人不知而不愠，不亦君子乎？……（节选：吾日三省吾身；温故而知新；学而不思则罔，思而不学则殆；三人行必有我师焉；逝者如斯夫）",
     "记录孔子及其弟子言行，阐述学习方法与修身之道。"),
    ("诫子书", "诸葛亮", "三国", "文言文",
     "夫君子之行，静以修身，俭以养德。非淡泊无以明志，非宁静无以致远。……淫慢则不能励精，险躁则不能治性。",
     "诸葛亮劝勉儿子修身养德、淡泊宁静。"),
    ("狼", "蒲松龄", "清", "文言文",
     "一屠晚归，担中肉尽，止有剩骨。……（节选：禽兽之变诈几何哉？止增笑耳。）",
     "出自《聊斋志异》，讽喻狼的狡诈终被机智战胜。"),
    ("穿井得一人", "《吕氏春秋》", "战国", "文言文",
     "宋之丁氏，家无井而出溉汲，常一人居外。及其家穿井，告人曰：『吾穿井得一人。』……求闻之若此，不若无闻也。",
     "说明耳听为虚、不可轻信传闻的道理。"),
    ("杞人忧天", "《列子》", "战国", "文言文",
     "杞国有人忧天地崩坠，身亡所寄，废寝食者。……（节选：天果积气，日月星宿，不当坠耶？）",
     "嘲讽不必要的忧虑，后指毫无根据的担心。"),
    ("孙权劝学", "司马光", "宋", "文言文",
     "初，权谓吕蒙曰：『卿今当涂掌事，不可不学！』……卿今者才略，非复吴下阿蒙。……士别三日，即更刮目相待。",
     "出自《资治通鉴》，强调学习使人进步。"),
    ("陋室铭", "刘禹锡", "唐", "铭",
     "山不在高，有仙则名。水不在深，有龙则灵。斯是陋室，惟吾德馨。……孔子云：何陋之有？",
     "托物言志，表达安贫乐道的高洁情操。"),
    ("爱莲说", "周敦颐", "宋", "说",
     "水陆草木之花，可爱者甚蕃。……予独爱莲之出淤泥而不染，濯清涟而不妖。……莲，花之君子者也。",
     "以莲喻君子，表达不慕名利、洁身自好。"),
    ("登幽州台歌", "陈子昂", "唐", "七言古诗",
     "前不见古人，后不见来者。念天地之悠悠，独怆然而涕下！",
     "抒发怀才不遇的孤独悲怆。"),
    ("望岳", "杜甫", "唐", "五言古诗",
     "岱宗夫如何？齐鲁青未了。造化钟神秀，阴阳割昏晓。……会当凌绝顶，一览众山小。",
     "咏泰山，展现青年杜甫的雄心壮志。"),
    ("登飞来峰", "王安石", "宋", "七言绝句",
     "飞来山上千寻塔，闻说鸡鸣见日升。不畏浮云遮望眼，自缘身在最高层。",
     "寓理于景，表达高瞻远瞩的胸襟。"),
    ("游山西村", "陆游", "宋", "七言律诗",
     "莫笑农家腊酒浑，丰年留客足鸡豚。山重水复疑无路，柳暗花明又一村。……",
     "蕴含困境中蕴含希望的哲理。"),
    ("己亥杂诗（其五）", "龚自珍", "清", "七言绝句",
     "浩荡离愁白日斜，吟鞭东指即天涯。落红不是无情物，化作春泥更护花。",
     "以落红自喻，表达奉献精神。"),
    ("河中石兽", "纪昀", "清", "文言文",
     "沧州南一寺临河干，山门圮于河……（节选：然则天下之事，但知其一，不知其二者多矣，可据理臆断欤？）",
     "出自《阅微草堂笔记》，强调实践出真知。"),
]


def seed_chinese(dry: bool):
    print("== 语文 G7（统编七上古诗文）==")
    if dry:
        print(f"  [dry] 古诗文 {len(CLASSICAL_G7)} 篇（硬编码权威内容）")
        return
    db = SessionLocal()
    try:
        added = 0
        for title, author, dynasty, ttype, content, notes in CLASSICAL_G7:
            if db.query(ClassicalText).filter_by(title=title, grade=GRADE,
                                                semester="上").first():
                continue
            db.add(ClassicalText(
                title=title, author=author, dynasty=dynasty, text_type=ttype,
                content=content, grade=GRADE, semester="上"))
            added += 1
        db.commit()
        print(f"  +古诗文 {added}")
    finally:
        db.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--subjects", nargs="*", default=None,
                    help="限定学科，如 数学 物理")
    ap.add_argument("--grammar-only", action="store_true",
                    help="只生成 G7 英语语法点（含配套练习），用于补数")
    args = ap.parse_args()
    dry = args.dry_run
    subjects = args.subjects or SUBJECTS

    if args.grammar_only:
        print("浙江初中初一(7年级) 英语语法点补数 | dry={dry}")
        ensure_tables()
        seed_english_grammar(dry)
        print("完成（仅英语语法点）。")
        return

    print(f"浙江初中初一(7年级)九科内容采集 | dry={dry}")
    ensure_tables()
    seed_editions(dry)

    for s in subjects:
        if s == "英语":
            seed_english(dry)
            seed_english_grammar(dry)  # 英语语法点（G7），幂等按 code 去重
        elif s == "语文":
            seed_chinese(dry)
            seed_subject("语文", dry)  # 语文知识点（现代文/写作等）
        elif s in UNIT_OUTLINE:
            seed_subject(s, dry)
        else:
            print(f"  [skip] 未知学科 {s}")
    print("完成。")


if __name__ == "__main__":
    main()
