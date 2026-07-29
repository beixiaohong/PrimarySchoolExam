"""
英语试卷生成器
支持题型：
  - word_translation   单词翻译（英译中/中译英）
  - phrase_translation 词组翻译
  - sentence_translation 句子翻译
  - phonetics          语音辨析（找不同发音）
  - grammar_choice     语法选择
  - situational        情景交际（补全对话）
  - unscramble_sentence 连词成句
  - cloze              选词填空
  - dictation          听写（给中文写英文）
  - choice             单词选择
"""
import random
from typing import List, Optional, Dict

from sqlalchemy.orm import Session

from ..models.word import Word, WordBook
from ..models.phrase import Phrase, Sentence


# ─── 数据获取（从数据库） ─────────────────────────────────────

def _get_phrases(db, grade: int) -> List[dict]:
    """从数据库获取词组"""
    if db is None:
        return []
    try:
        rows = db.query(Phrase).filter(Phrase.grade <= grade).all()
        return [
            {"grade": r.grade, "phrase": r.phrase, "meaning": r.meaning, "type": r.type}
            for r in rows
        ]
    except Exception:
        return []


def _get_sentences(db, grade: int) -> List[dict]:
    """从数据库获取句子"""
    if db is None:
        return []
    try:
        rows = db.query(Sentence).filter(Sentence.grade <= grade).all()
        return [
            {"grade": r.grade, "en": r.sentence_en, "cn": r.sentence_cn,
             "type": r.type, "grammar": r.grammar_point}
            for r in rows
        ]
    except Exception:
        return []


# ─── 主入口 ─────────────────────────────────────────────────

# 所有支持的题型
ALL_EXERCISE_TYPES = [
    "word_translation", "phrase_translation", "sentence_translation",
    "phonetics", "grammar_choice", "situational",
    "unscramble_sentence", "cloze", "dictation", "choice",
]

# 题型中文名（用于试卷排版）
TYPE_NAMES = {
    "word_translation": "单词翻译",
    "phrase_translation": "词组翻译",
    "sentence_translation": "句子翻译",
    "phonetics": "语音辨析",
    "grammar_choice": "语法选择",
    "situational": "情景交际",
    "unscramble_sentence": "连词成句",
    "cloze": "选词填空",
    "dictation": "单词听写",
    "choice": "单词选择",
}


def generate_english_exam(
    grade: int = 6,
    book_ids: Optional[List[int]] = None,
    count_per_type: int = 10,
    exercise_types: Optional[List[str]] = None,
    db: Session = None,
) -> Dict[str, list]:
    """
    生成英语试卷题目。
    返回: { "word_translation": [...], "phrase_translation": [...], ... }
    每个列表元素: {"id": int, "question": str, "answer": str, "options": list|None}
    """
    if exercise_types is None:
        exercise_types = ALL_EXERCISE_TYPES[:]

    # 从DB获取单词
    words = _get_words(db, grade, book_ids, count_per_type * 5)
    if len(words) < 10:
        words = _fallback_words()

    phrases = _get_phrases(db, grade)
    sentences = _get_sentences(db, grade)

    result = {}
    generators = {
        "word_translation": lambda: _gen_word_translation(words, count_per_type),
        "phrase_translation": lambda: _gen_phrase_translation(phrases, count_per_type),
        "sentence_translation": lambda: _gen_sentence_translation(sentences, count_per_type),
        "phonetics": lambda: _gen_phonetics(words, count_per_type),
        "grammar_choice": lambda: _gen_grammar_choice(sentences, count_per_type),
        "situational": lambda: _gen_situational(grade, count_per_type),
        "unscramble_sentence": lambda: _gen_unscramble_sentence(sentences, count_per_type),
        "cloze": lambda: _gen_cloze(sentences, words, count_per_type),
        "dictation": lambda: _gen_dictation(words, count_per_type),
        "choice": lambda: _gen_choice(words, count_per_type),
    }

    for etype in exercise_types:
        if etype in generators:
            result[etype] = generators[etype]()

    return result


# 兼容旧接口
def generate_english_exercises(
    grade: int = 6,
    book_ids: Optional[List[int]] = None,
    word_count: int = 50,
    exercise_types: Optional[List[str]] = None,
    db: Session = None,
) -> Dict[str, list]:
    """兼容旧接口"""
    # 旧类型映射
    old_map = {
        "dictation": "dictation",
        "choice": "choice",
        "translation": "word_translation",
        "unscramble": "unscramble_sentence",
    }
    if exercise_types:
        new_types = [old_map.get(t, t) for t in exercise_types]
    else:
        new_types = ALL_EXERCISE_TYPES[:]
    count = max(5, word_count // len(new_types))
    return generate_english_exam(grade, book_ids, count, new_types, db)


# ─── 数据获取 ─────────────────────────────────────────────────

def _get_words(db, grade, book_ids, limit):
    if db is None:
        return []
    try:
        q = db.query(Word)
        if book_ids:
            q = q.filter(Word.book_id.in_(book_ids))
        else:
            q = q.join(WordBook).filter(WordBook.grade <= grade)
        words = q.limit(limit).all()
        return [
            {"word": w.word, "phonetic": w.phonetic, "pos": w.pos, "meaning": w.meaning}
            for w in words
        ]
    except Exception:
        return []


def _fallback_words():
    base = [
        ("apple", "/ˈæpl/", "n.", "苹果"), ("book", "/bʊk/", "n.", "书"),
        ("cat", "/kæt/", "n.", "猫"), ("dog", "/dɒɡ/", "n.", "狗"),
        ("egg", "/eɡ/", "n.", "鸡蛋"), ("fish", "/fɪʃ/", "n.", "鱼"),
        ("girl", "/ɡɜːl/", "n.", "女孩"), ("happy", "/ˈhæpi/", "adj.", "快乐的"),
        ("ice", "/aɪs/", "n.", "冰"), ("jump", "/dʒʌmp/", "v.", "跳"),
        ("kite", "/kaɪt/", "n.", "风筝"), ("lion", "/ˈlaɪən/", "n.", "狮子"),
        ("milk", "/mɪlk/", "n.", "牛奶"), ("nose", "/nəʊz/", "n.", "鼻子"),
        ("orange", "/ˈɒrɪndʒ/", "n.", "橙子"), ("pen", "/pen/", "n.", "钢笔"),
        ("queen", "/kwiːn/", "n.", "女王"), ("rain", "/reɪn/", "n./v.", "雨"),
        ("sun", "/sʌn/", "n.", "太阳"), ("tree", "/triː/", "n.", "树"),
        ("umbrella", "/ʌmˈbrelə/", "n.", "雨伞"), ("water", "/ˈwɔːtə/", "n.", "水"),
        ("yellow", "/ˈjeləʊ/", "adj.", "黄色的"), ("zoo", "/zuː/", "n.", "动物园"),
        ("school", "/skuːl/", "n.", "学校"), ("teacher", "/ˈtiːtʃə/", "n.", "老师"),
        ("friend", "/frend/", "n.", "朋友"), ("family", "/ˈfæməli/", "n.", "家庭"),
        ("beautiful", "/ˈbjuːtɪfl/", "adj.", "美丽的"), ("run", "/rʌn/", "v.", "跑"),
        ("swim", "/swɪm/", "v.", "游泳"), ("read", "/riːd/", "v.", "阅读"),
        ("write", "/raɪt/", "v.", "写"), ("sing", "/sɪŋ/", "v.", "唱歌"),
        ("dance", "/dɑːns/", "v.", "跳舞"), ("eat", "/iːt/", "v.", "吃"),
        ("drink", "/drɪŋk/", "v.", "喝"), ("sleep", "/sliːp/", "v.", "睡觉"),
        ("play", "/pleɪ/", "v.", "玩"), ("big", "/bɪɡ/", "adj.", "大的"),
        ("small", "/smɔːl/", "adj.", "小的"), ("tall", "/tɔːl/", "adj.", "高的"),
        ("short", "/ʃɔːt/", "adj.", "矮的"), ("long", "/lɒŋ/", "adj.", "长的"),
        ("young", "/jʌŋ/", "adj.", "年轻的"), ("old", "/əʊld/", "adj.", "老的"),
        ("hot", "/hɒt/", "adj.", "热的"), ("cold", "/kəʊld/", "adj.", "冷的"),
        ("new", "/njuː/", "adj.", "新的"), ("good", "/ɡʊd/", "adj.", "好的"),
    ]
    return [{"word": w, "phonetic": p, "pos": pos, "meaning": m} for w, p, pos, m in base]


# ─── 题型生成器 ─────────────────────────────────────────────────

def _gen_word_translation(words: List[dict], count: int) -> List[dict]:
    """单词翻译：英译中 + 中译英混合"""
    items = []
    selected = random.sample(words, min(count, len(words)))
    for i, w in enumerate(selected, 1):
        if random.random() > 0.5:
            items.append({
                "id": i,
                "question": f"英译中：{w['word']} ({w['pos']})",
                "answer": w["meaning"],
                "options": None,
            })
        else:
            items.append({
                "id": i,
                "question": f"中译英：{w['meaning']}（{w['pos']}）",
                "answer": w["word"],
                "options": None,
            })
    return items


def _gen_phrase_translation(phrases: List[dict], count: int) -> List[dict]:
    """词组翻译：英译中 + 中译英"""
    items = []
    if not phrases:
        return items
    selected = random.sample(phrases, min(count, len(phrases)))
    for i, p in enumerate(selected, 1):
        if random.random() > 0.5:
            items.append({
                "id": i,
                "question": f"英译中：{p['phrase']}",
                "answer": p["meaning"],
                "options": None,
            })
        else:
            items.append({
                "id": i,
                "question": f"中译英：{p['meaning']}",
                "answer": p["phrase"],
                "options": None,
            })
    return items


def _gen_sentence_translation(sentences: List[dict], count: int) -> List[dict]:
    """句子翻译：英译中 + 中译英"""
    items = []
    if not sentences:
        return items
    selected = random.sample(sentences, min(count, len(sentences)))
    for i, s in enumerate(selected, 1):
        if random.random() > 0.5:
            items.append({
                "id": i,
                "question": f"英译中：{s['en']}",
                "answer": s["cn"],
                "options": None,
            })
        else:
            items.append({
                "id": i,
                "question": f"中译英：{s['cn']}",
                "answer": s["en"],
                "options": None,
            })
    return items


def _gen_phonetics(words: List[dict], count: int) -> List[dict]:
    """语音辨析：找出划线部分发音不同的词"""
    # 按元音字母分组构造题目
    vowel_groups = {
        "a": [("cake", "make", "name", "cat"), ("bag", "map", "hat", "face"),
              ("day", "play", "say", "cat"), ("apple", "hand", "bag", "cake")],
        "e": [("he", "me", "she", "bed"), ("pen", "ten", "red", "these"),
              ("desk", "get", "let", "be"), ("egg", "leg", "bed", "he")],
        "i": [("like", "bike", "kite", "sit"), ("big", "pig", "six", "five"),
              ("fish", "this", "his", "ice"), ("milk", "hill", "him", "time")],
        "o": [("nose", "home", "go", "dog"), ("hot", "not", "lot", "no"),
              ("box", "fox", "dog", "rose"), ("come", "some", "love", "go")],
        "u": [("use", "cute", "mule", "bus"), ("cup", "bus", "sun", "ruler"),
              ("fun", "run", "duck", "music"), ("put", "but", "cut", "use")],
    }
    items = []
    all_questions = []
    for vowel, groups in vowel_groups.items():
        for group in groups:
            # 最后一个通常是不同的
            words_list = list(group)
            answer_idx = len(words_list) - 1  # 默认最后一个不同
            # 打乱位置
            answer_word = words_list[answer_idx]
            random.shuffle(words_list)
            new_idx = words_list.index(answer_word)
            options = [f"{'ABCD'[j]}. {w}" for j, w in enumerate(words_list)]
            all_questions.append({
                "question": f"找出划线字母\"{vowel}\"发音不同的一项：",
                "options": options,
                "answer": "ABCD"[new_idx],
            })
    random.shuffle(all_questions)
    for i, q in enumerate(all_questions[:count], 1):
        items.append({"id": i, **q})
    return items


def _gen_grammar_choice(sentences: List[dict], count: int) -> List[dict]:
    """语法选择题"""
    # 内置语法题库（按语法点分类）
    grammar_bank = [
        {
            "question": "There ___ a book and two pens on the desk.",
            "options": ["A. is", "B. are", "C. am", "D. be"],
            "answer": "A",
            "point": "there be就近原则",
        },
        {
            "question": "She ___ to school by bus every day.",
            "options": ["A. go", "B. goes", "C. going", "D. went"],
            "answer": "B",
            "point": "三单",
        },
        {
            "question": "Look! The children ___ in the park.",
            "options": ["A. play", "B. plays", "C. are playing", "D. played"],
            "answer": "C",
            "point": "现在进行时",
        },
        {
            "question": "He ___ his homework yesterday evening.",
            "options": ["A. do", "B. does", "C. doing", "D. did"],
            "answer": "D",
            "point": "一般过去时",
        },
        {
            "question": "My sister is ___ than me.",
            "options": ["A. tall", "B. taller", "C. tallest", "D. more tall"],
            "answer": "B",
            "point": "比较级",
        },
        {
            "question": "I'm going to ___ a trip next week.",
            "options": ["A. take", "B. takes", "C. taking", "D. took"],
            "answer": "A",
            "point": "be going to + 动词原形",
        },
        {
            "question": "___ you like some tea?",
            "options": ["A. Are", "B. Do", "C. Would", "D. Can"],
            "answer": "C",
            "point": "would like",
        },
        {
            "question": "She can ___ English very well.",
            "options": ["A. speaks", "B. speak", "C. speaking", "D. spoke"],
            "answer": "B",
            "point": "can + 动词原形",
        },
        {
            "question": "There are many ___ on the farm.",
            "options": ["A. sheep", "B. sheeps", "C. sheepes", "D. a sheep"],
            "answer": "A",
            "point": "名词复数(不规则)",
        },
        {
            "question": "He ___ TV at 8:00 last night.",
            "options": ["A. watch", "B. watches", "C. was watching", "D. is watching"],
            "answer": "C",
            "point": "过去进行时",
        },
        {
            "question": "I have ___ apple and ___ banana.",
            "options": ["A. a; a", "B. an; a", "C. a; an", "D. an; an"],
            "answer": "B",
            "point": "冠词a/an",
        },
        {
            "question": "___ is your favourite season?",
            "options": ["A. What", "B. Which", "C. Where", "D. When"],
            "answer": "A",
            "point": "特殊疑问词",
        },
        {
            "question": "The elephant is ___ than the monkey.",
            "options": ["A. heavy", "B. heavier", "C. heaviest", "D. more heavy"],
            "answer": "B",
            "point": "比较级(y变i)",
        },
        {
            "question": "Let's ___ football after school.",
            "options": ["A. play", "B. plays", "C. playing", "D. to play"],
            "answer": "A",
            "point": "let's + 动词原形",
        },
        {
            "question": "She ___ like dancing.",
            "options": ["A. don't", "B. doesn't", "C. isn't", "D. can't"],
            "answer": "B",
            "point": "三单否定",
        },
        {
            "question": "I ___ to Beijing last summer.",
            "options": ["A. go", "B. goes", "C. went", "D. going"],
            "answer": "C",
            "point": "过去式(不规则)",
        },
        {
            "question": "How ___ is the river? It's 100 metres.",
            "options": ["A. long", "B. tall", "C. heavy", "D. old"],
            "answer": "A",
            "point": "how + adj",
        },
        {
            "question": "He is good ___ playing basketball.",
            "options": ["A. in", "B. at", "C. on", "D. for"],
            "answer": "B",
            "point": "介词搭配",
        },
        {
            "question": "We should ___ the environment.",
            "options": ["A. protect", "B. protects", "C. protecting", "D. protected"],
            "answer": "A",
            "point": "should + 动词原形",
        },
        {
            "question": "___ does your mother do? She's a doctor.",
            "options": ["A. How", "B. Where", "C. What", "D. When"],
            "answer": "C",
            "point": "询问职业",
        },
        {
            "question": "I'm 12 years old. He is ___ than me.",
            "options": ["A. young", "B. younger", "C. youngest", "D. more young"],
            "answer": "B",
            "point": "比较级",
        },
        {
            "question": "She often ___ books in the library.",
            "options": ["A. read", "B. reads", "C. reading", "D. is reading"],
            "answer": "B",
            "point": "三单(often)",
        },
        {
            "question": "Don't ___ in the classroom.",
            "options": ["A. run", "B. runs", "C. running", "D. to run"],
            "answer": "A",
            "point": "祈使句否定",
        },
        {
            "question": "I'd like two ___ of water.",
            "options": ["A. glass", "B. glasses", "C. glasss", "D. a glass"],
            "answer": "B",
            "point": "量词复数",
        },
    ]
    items = []
    selected = random.sample(grammar_bank, min(count, len(grammar_bank)))
    for i, q in enumerate(selected, 1):
        items.append({
            "id": i,
            "question": q["question"],
            "options": q["options"],
            "answer": q["answer"],
        })
    return items


def _gen_situational(grade: int, count: int) -> List[dict]:
    """情景交际：选择正确应答"""
    dialogues = [
        {"q": "— How are you?\n— ___", "options": ["A. I'm fine, thank you.", "B. I'm ten.", "C. I'm a student.", "D. I like it."], "answer": "A"},
        {"q": "— What's your name?\n— ___", "options": ["A. I'm fine.", "B. My name is Tom.", "C. I'm nine.", "D. Thank you."], "answer": "B"},
        {"q": "— Nice to meet you.\n— ___", "options": ["A. Goodbye.", "B. Nice to meet you, too.", "C. I'm sorry.", "D. You're welcome."], "answer": "B"},
        {"q": "— Thank you very much.\n— ___", "options": ["A. No thanks.", "B. You're welcome.", "C. Yes please.", "D. I'm fine."], "answer": "B"},
        {"q": "— Can I help you?\n— ___", "options": ["A. Yes, I'd like a skirt.", "B. I'm fine.", "C. Thank you.", "D. You're welcome."], "answer": "A"},
        {"q": "— What would you like for dinner?\n— ___", "options": ["A. I'd like some rice.", "B. I'm ten.", "C. It's Monday.", "D. I can swim."], "answer": "A"},
        {"q": "— Where is the library?\n— ___", "options": ["A. It's on the second floor.", "B. It's a library.", "C. I like it.", "D. Yes it is."], "answer": "A"},
        {"q": "— How do you go to school?\n— ___", "options": ["A. I go by bus.", "B. I'm a student.", "C. It's far.", "D. I like school."], "answer": "A"},
        {"q": "— What does your father do?\n— ___", "options": ["A. He's a teacher.", "B. He's fine.", "C. He's tall.", "D. He likes reading."], "answer": "A"},
        {"q": "— Did you go swimming yesterday?\n— ___", "options": ["A. Yes, I did.", "B. Yes, I do.", "C. Yes, I am.", "D. Yes, I can."], "answer": "A"},
        {"q": "— What's the weather like today?\n— ___", "options": ["A. It's sunny.", "B. It's Monday.", "C. It's a book.", "D. I'm fine."], "answer": "A"},
        {"q": "— How tall are you?\n— ___", "options": ["A. I'm 160 cm.", "B. I'm 12.", "C. I'm fine.", "D. I'm a boy."], "answer": "A"},
        {"q": "— What's your hobby?\n— ___", "options": ["A. I like reading.", "B. I'm reading.", "C. I read a book.", "D. Yes I do."], "answer": "A"},
        {"q": "— When is your birthday?\n— ___", "options": ["A. It's in October.", "B. I'm ten.", "C. It's Monday.", "D. I like cakes."], "answer": "A"},
        {"q": "— Excuse me, where is the hospital?\n— ___", "options": ["A. Turn left and go straight.", "B. I'm a doctor.", "C. It's big.", "D. Thank you."], "answer": "A"},
        {"q": "— What are you going to do this weekend?\n— ___", "options": ["A. I'm going to visit my grandma.", "B. I visited my grandma.", "C. I visit my grandma.", "D. I'm visiting."], "answer": "A"},
    ]
    items = []
    selected = random.sample(dialogues, min(count, len(dialogues)))
    for i, d in enumerate(selected, 1):
        items.append({
            "id": i,
            "question": d["q"],
            "options": d["options"],
            "answer": d["answer"],
        })
    return items


def _gen_unscramble_sentence(sentences: List[dict], count: int) -> List[dict]:
    """连词成句：打乱单词顺序"""
    items = []
    if not sentences:
        return items
    # 选适合打乱的句子（3-10个单词）
    suitable = [s for s in sentences if 3 <= len(s["en"].split()) <= 12]
    selected = random.sample(suitable, min(count, len(suitable)))
    for i, s in enumerate(selected, 1):
        words = s["en"].rstrip(".!?").split()
        scrambled = words[:]
        attempts = 0
        while scrambled == words and attempts < 10:
            random.shuffle(scrambled)
            attempts += 1
        # 首字母小写化（打乱后不提示首字母大写）
        scrambled_display = [w.lower() if w[0].isupper() and not w.isupper() else w for w in scrambled]
        items.append({
            "id": i,
            "question": f"连词成句：{' / '.join(scrambled_display)}（提示：{s['cn']}）",
            "answer": s["en"],
            "options": None,
        })
    return items


def _gen_cloze(sentences: List[dict], words: List[dict], count: int) -> List[dict]:
    """选词填空：从给定词中选正确的填入句子"""
    items = []
    if not sentences:
        return items
    # 选含有明确关键词的句子
    suitable = [s for s in sentences if len(s["en"].split()) >= 4]
    selected = random.sample(suitable, min(count, len(suitable)))

    # 构造干扰词池
    word_pool = [w["word"] for w in words if len(w["word"]) >= 2]

    for i, s in enumerate(selected, 1):
        en_words = s["en"].rstrip(".!?").split()
        if len(en_words) < 3:
            continue
        # 随机挖一个实词（非冠词/介词）
        skip = {"a", "an", "the", "is", "am", "are", "was", "were", "in", "on", "at", "to", "of", "and", "or", "but", "I", "I'm"}
        candidates = [(idx, w) for idx, w in enumerate(en_words) if w.lower() not in skip and len(w) >= 2]
        if not candidates:
            continue
        blank_idx, target_word = random.choice(candidates)

        # 生成干扰项
        distractors = random.sample([w for w in word_pool if w.lower() != target_word.lower()], min(3, len(word_pool)))
        options_list = [target_word] + distractors
        random.shuffle(options_list)
        correct_idx = options_list.index(target_word)

        # 构造填空句
        display_words = en_words[:]
        display_words[blank_idx] = "______"
        sentence_display = " ".join(display_words)

        items.append({
            "id": i,
            "question": f"选词填空：{sentence_display}",
            "options": [f"{'ABCD'[j]}. {opt}" for j, opt in enumerate(options_list)],
            "answer": "ABCD"[correct_idx],
        })
    return items


def _gen_dictation(words: List[dict], count: int) -> List[dict]:
    """听写：给中文和音标写英文"""
    items = []
    selected = random.sample(words, min(count, len(words)))
    for i, w in enumerate(selected, 1):
        items.append({
            "id": i,
            "question": f"{w['meaning']}  {w['phonetic']}",
            "answer": w["word"],
            "options": None,
        })
    return items


def _gen_choice(words: List[dict], count: int) -> List[dict]:
    """选择题：英选中 / 中选英"""
    items = []
    selected = random.sample(words, min(count, len(words)))
    for i, w in enumerate(selected, 1):
        others = [x for x in words if x["word"] != w["word"]]
        random.shuffle(others)
        distractors = others[:3]

        if random.random() > 0.5:
            options = [w["meaning"]] + [d["meaning"] for d in distractors]
            random.shuffle(options)
            correct_idx = options.index(w["meaning"])
            items.append({
                "id": i,
                "question": f"单词 \"{w['word']}\" 的意思是：",
                "options": [f"{'ABCD'[j]}. {opt}" for j, opt in enumerate(options)],
                "answer": "ABCD"[correct_idx],
            })
        else:
            options = [w["word"]] + [d["word"] for d in distractors]
            random.shuffle(options)
            correct_idx = options.index(w["word"])
            items.append({
                "id": i,
                "question": f"\"{w['meaning']}\" 用英语怎么说：",
                "options": [f"{'ABCD'[j]}. {opt}" for j, opt in enumerate(options)],
                "answer": "ABCD"[correct_idx],
            })
    return items
