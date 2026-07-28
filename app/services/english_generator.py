"""
英语练习生成器
从数据库词库中抽取单词，生成多种题型
"""
import random
from typing import List, Optional, Dict

from sqlalchemy.orm import Session

from ..models.word import Word, WordBook


def generate_english_exercises(
    grade: int = 6,
    book_ids: Optional[List[int]] = None,
    word_count: int = 50,
    exercise_types: Optional[List[str]] = None,
    db: Session = None,
) -> Dict[str, list]:
    """
    生成英语练习题
    返回: {
        "dictation": [...],       # 听写（给中文写英文）
        "choice": [...],          # 选择题
        "translation": [...],     # 翻译（英译中/中译英）
        "unscramble": [...],      # 词组句
    }
    """
    if exercise_types is None:
        exercise_types = ["dictation", "choice", "translation"]

    # 从DB获取单词
    words = _get_words(db, grade, book_ids, word_count * 2)
    if len(words) < 10:
        # fallback: 使用内置基础词
        words = _fallback_words()

    random.shuffle(words)
    words = words[:word_count]

    result = {}

    if "dictation" in exercise_types:
        result["dictation"] = _gen_dictation(words)

    if "choice" in exercise_types:
        result["choice"] = _gen_choice(words)

    if "translation" in exercise_types:
        result["translation"] = _gen_translation(words)

    if "unscramble" in exercise_types:
        result["unscramble"] = _gen_unscramble(words)

    return result


def _get_words(db, grade, book_ids, limit):
    """从数据库获取单词"""
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
            {
                "word": w.word,
                "phonetic": w.phonetic,
                "pos": w.pos,
                "meaning": w.meaning,
            }
            for w in words
        ]
    except Exception:
        return []


def _fallback_words():
    """内置基础词库（当DB无数据时使用）"""
    base = [
        ("apple", "/ˈæpl/", "n.", "苹果"),
        ("book", "/bʊk/", "n.", "书"),
        ("cat", "/kæt/", "n.", "猫"),
        ("dog", "/dɒɡ/", "n.", "狗"),
        ("egg", "/eɡ/", "n.", "鸡蛋"),
        ("fish", "/fɪʃ/", "n.", "鱼"),
        ("girl", "/ɡɜːl/", "n.", "女孩"),
        ("happy", "/ˈhæpi/", "adj.", "快乐的"),
        ("ice", "/aɪs/", "n.", "冰"),
        ("jump", "/dʒʌmp/", "v.", "跳"),
        ("kite", "/kaɪt/", "n.", "风筝"),
        ("lion", "/ˈlaɪən/", "n.", "狮子"),
        ("milk", "/mɪlk/", "n.", "牛奶"),
        ("nose", "/nəʊz/", "n.", "鼻子"),
        ("orange", "/ˈɒrɪndʒ/", "n.", "橙子"),
        ("pen", "/pen/", "n.", "钢笔"),
        ("queen", "/kwiːn/", "n.", "女王"),
        ("rain", "/reɪn/", "n./v.", "雨/下雨"),
        ("sun", "/sʌn/", "n.", "太阳"),
        ("tree", "/triː/", "n.", "树"),
        ("umbrella", "/ʌmˈbrelə/", "n.", "雨伞"),
        ("vegetable", "/ˈvedʒtəbl/", "n.", "蔬菜"),
        ("water", "/ˈwɔːtə/", "n.", "水"),
        ("yellow", "/ˈjeləʊ/", "adj.", "黄色的"),
        ("zoo", "/zuː/", "n.", "动物园"),
        ("school", "/skuːl/", "n.", "学校"),
        ("teacher", "/ˈtiːtʃə/", "n.", "老师"),
        ("friend", "/frend/", "n.", "朋友"),
        ("family", "/ˈfæməli/", "n.", "家庭"),
        ("beautiful", "/ˈbjuːtɪfl/", "adj.", "美丽的"),
        ("run", "/rʌn/", "v.", "跑"),
        ("swim", "/swɪm/", "v.", "游泳"),
        ("read", "/riːd/", "v.", "阅读"),
        ("write", "/raɪt/", "v.", "写"),
        ("sing", "/sɪŋ/", "v.", "唱歌"),
        ("dance", "/dɑːns/", "v.", "跳舞"),
        ("eat", "/iːt/", "v.", "吃"),
        ("drink", "/drɪŋk/", "v.", "喝"),
        ("sleep", "/sliːp/", "v.", "睡觉"),
        ("play", "/pleɪ/", "v.", "玩"),
        ("morning", "/ˈmɔːnɪŋ/", "n.", "早晨"),
        ("afternoon", "/ˌɑːftəˈnuːn/", "n.", "下午"),
        ("evening", "/ˈiːvnɪŋ/", "n.", "晚上"),
        ("Monday", "/ˈmʌndeɪ/", "n.", "星期一"),
        ("spring", "/sprɪŋ/", "n.", "春天"),
        ("summer", "/ˈsʌmə/", "n.", "夏天"),
        ("autumn", "/ˈɔːtəm/", "n.", "秋天"),
        ("winter", "/ˈwɪntə/", "n.", "冬天"),
        ("big", "/bɪɡ/", "adj.", "大的"),
        ("small", "/smɔːl/", "adj.", "小的"),
    ]
    return [{"word": w, "phonetic": p, "pos": pos, "meaning": m} for w, p, pos, m in base]


def _gen_dictation(words: List[dict]) -> List[dict]:
    """听写题：给中文和音标，写英文"""
    items = []
    for i, w in enumerate(words[:30], 1):
        items.append({
            "id": i,
            "prompt": f"{w['meaning']}  {w['phonetic']}",
            "answer": w["word"],
        })
    return items


def _gen_choice(words: List[dict]) -> List[dict]:
    """选择题：给英文选中文（或反向）"""
    items = []
    for i, w in enumerate(words[:20], 1):
        # 生成3个干扰项
        others = [x for x in words if x["word"] != w["word"]]
        random.shuffle(others)
        distractors = others[:3]

        if random.random() > 0.5:
            # 英→中
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
            # 中→英
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


def _gen_translation(words: List[dict]) -> List[dict]:
    """翻译题"""
    items = []
    for i, w in enumerate(words[:20], 1):
        if random.random() > 0.5:
            items.append({
                "id": i,
                "question": f"英译中：{w['word']}",
                "answer": w["meaning"],
            })
        else:
            items.append({
                "id": i,
                "question": f"中译英：{w['meaning']}（{w['pos']}）",
                "answer": w["word"],
            })
    return items


def _gen_unscramble(words: List[dict]) -> List[dict]:
    """词组句（打乱字母顺序）"""
    items = []
    suitable = [w for w in words if len(w["word"]) >= 3][:15]
    for i, w in enumerate(suitable, 1):
        letters = list(w["word"])
        scrambled = letters[:]
        # 确保打乱后不同
        attempts = 0
        while scrambled == letters and attempts < 10:
            random.shuffle(scrambled)
            attempts += 1
        items.append({
            "id": i,
            "question": f"重新排列字母组成单词：{''.join(scrambled)}（提示：{w['meaning']}）",
            "answer": w["word"],
        })
    return items
