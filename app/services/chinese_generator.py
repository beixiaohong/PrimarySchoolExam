"""语文试卷生成器

题型：
  - pinyin_write: 看拼音写汉字
  - idiom_fill: 成语填空
  - poetry_fill: 古诗默写
  - typo_correct: 改错字
  - sentence_rewrite: 句式变换
  - word_classify: 词语归类
"""
import random
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

# ═══════════════════════════════════════════════════════════
# 题型注册
# ═══════════════════════════════════════════════════════════

ALL_EXERCISE_TYPES = [
    "pinyin_write",
    "idiom_fill",
    "poetry_fill",
    "typo_correct",
    "sentence_rewrite",
    "word_classify",
]

TYPE_NAMES = {
    "pinyin_write": "看拼音写词语",
    "idiom_fill": "成语填空",
    "poetry_fill": "古诗默写",
    "typo_correct": "改错字",
    "sentence_rewrite": "句式变换",
    "word_classify": "词语归类",
}


# ═══════════════════════════════════════════════════════════
# 内置数据（后续迁移到DB）
# ═══════════════════════════════════════════════════════════

# 看拼音写词语：(拼音, 汉字词语, 年级)
PINYIN_WORDS = [
    ("pú táo", "葡萄", 3), ("yǎn jing", "眼睛", 3), ("zhī shi", "知识", 3),
    ("hǎi yáng", "海洋", 3), ("péng you", "朋友", 3), ("xué xiào", "学校", 3),
    ("kuài lè", "快乐", 3), ("yǒng gǎn", "勇敢", 3), ("zǔ guó", "祖国", 3),
    ("chūn tiān", "春天", 3), ("huā duǒ", "花朵", 3), ("yīn yuè", "音乐", 3),
    ("jìng ài", "敬爱", 4), ("wēi wǔ", "威武", 4), ("càn làn", "灿烂", 4),
    ("jǔ sàng", "沮丧", 4), ("yōu lǜ", "忧虑", 4), ("zī rùn", "滋润", 4),
    ("chōng jǐng", "憧憬", 4), ("wǔ rǔ", "侮辱", 4), ("jǐn shèn", "谨慎", 4),
    ("pái huái", "徘徊", 4), ("jīng yíng", "晶莹", 4), ("yùn niàng", "酝酿", 4),
    ("kāng kǎi", "慷慨", 5), ("jǐn liáng", "锦囊", 5), ("dǐ yù", "抵御", 5),
    ("xiāo sǎ", "潇洒", 5), ("jǐ liáng", "脊梁", 5), ("zhēn zhì", "真挚", 5),
    ("miǎo máng", "渺茫", 5), ("jì mò", "寂寞", 5), ("chú chuāng", "橱窗", 5),
    ("duàn liàn", "锻炼", 5), ("biàn lùn", "辩论", 5), ("jǐn náng", "锦囊", 5),
    ("líng lì", "伶俐", 6), ("wǔ mèi", "妩媚", 6), ("jīng zhàn", "精湛", 6),
    ("yōu yǎ", "优雅", 6), ("yì lì", "屹立", 6), ("kuí wú", "魁梧", 6),
    ("zhuó yuè", "卓越", 6), ("yǐn bì", "隐蔽", 6), ("jìng mì", "静谧", 6),
    ("qīn pèi", "钦佩", 6), ("yōu yù", "忧郁", 6), ("wǎn zhuǎn", "婉转", 6),
]

# 成语填空：(完整成语, 挖空位置列表, 年级)
IDIOMS = [
    ("画龙点睛", [0, 2], 4), ("守株待兔", [1, 3], 3), ("亡羊补牢", [0, 2], 3),
    ("掩耳盗铃", [1, 3], 4), ("刻舟求剑", [0, 2], 4), ("叶公好龙", [1, 3], 4),
    ("对牛弹琴", [0, 2], 3), ("杯弓蛇影", [1, 3], 5), ("狐假虎威", [0, 2], 3),
    ("鹤立鸡群", [1, 3], 5), ("胸有成竹", [0, 2], 4), ("望梅止渴", [1, 3], 5),
    ("破釜沉舟", [0, 2], 6), ("卧薪尝胆", [1, 3], 6), ("纸上谈兵", [0, 2], 5),
    ("完璧归赵", [1, 3], 6), ("负荆请罪", [0, 2], 5), ("闻鸡起舞", [1, 3], 5),
    ("悬梁刺股", [0, 2], 6), ("程门立雪", [1, 3], 6), ("一鸣惊人", [0, 2], 4),
    ("四面楚歌", [1, 3], 6), ("草木皆兵", [0, 2], 5), ("风声鹤唳", [1, 3], 6),
    ("精忠报国", [0, 2], 4), ("刮目相看", [1, 3], 5), ("指鹿为马", [0, 2], 5),
    ("入木三分", [1, 3], 5), ("东施效颦", [0, 2], 6), ("买椟还珠", [1, 3], 6),
]

# 古诗默写：(上句, 下句, 作者, 题目, 年级)
POEMS = [
    ("床前明月光", "疑是地上霜", "李白", "静夜思", 3),
    ("春眠不觉晓", "处处闻啼鸟", "孟浩然", "春晓", 3),
    ("锄禾日当午", "汗滴禾下土", "李绅", "悯农", 3),
    ("白日依山尽", "黄河入海流", "王之涣", "登鹳雀楼", 3),
    ("离离原上草", "一岁一枯荣", "白居易", "草", 3),
    ("两个黄鹂鸣翠柳", "一行白鹭上青天", "杜甫", "绝句", 4),
    ("停车坐爱枫林晚", "霜叶红于二月花", "杜牧", "山行", 4),
    ("飞流直下三千尺", "疑是银河落九天", "李白", "望庐山瀑布", 4),
    ("独在异乡为异客", "每逢佳节倍思亲", "王维", "九月九日忆山东兄弟", 4),
    ("欲穷千里目", "更上一层楼", "王之涣", "登鹳雀楼", 4),
    ("大漠孤烟直", "长河落日圆", "王维", "使至塞上", 5),
    ("海内存知己", "天涯若比邻", "王勃", "送杜少府之任蜀州", 5),
    ("会当凌绝顶", "一览众山小", "杜甫", "望岳", 5),
    ("春蚕到死丝方尽", "蜡炬成灰泪始干", "李商隐", "无题", 5),
    ("接天莲叶无穷碧", "映日荷花别样红", "杨万里", "晓出净慈寺送林子方", 5),
    ("不识庐山真面目", "只缘身在此山中", "苏轼", "题西林壁", 5),
    ("人生自古谁无死", "留取丹心照汗青", "文天祥", "过零丁洋", 6),
    ("落红不是无情物", "化作春泥更护花", "龚自珍", "己亥杂诗", 6),
    ("粉骨碎身浑不怕", "要留清白在人间", "于谦", "石灰吟", 6),
    ("千磨万击还坚劲", "任尔东西南北风", "郑燮", "竹石", 6),
    ("少壮不努力", "老大徒伤悲", "汉乐府", "长歌行", 6),
    ("问渠那得清如许", "为有源头活水来", "朱熹", "观书有感", 6),
    ("等闲识得东风面", "万紫千红总是春", "朱熹", "春日", 6),
    ("谁言寸草心", "报得三春晖", "孟郊", "游子吟", 6),
]

# 改错字：(正确词语, 错误写法, 年级)
TYPOS = [
    ("迫不及待", "迫不急待", 4), ("再接再厉", "再接再励", 5),
    ("川流不息", "穿流不息", 5), ("一筹莫展", "一愁莫展", 5),
    ("天翻地覆", "天翻地复", 5), ("言简意赅", "言简意该", 6),
    ("走投无路", "走头无路", 5), ("鬼鬼祟祟", "鬼鬼崇崇", 6),
    ("金榜题名", "金榜提名", 6), ("世外桃源", "世外桃园", 5),
    ("滥竽充数", "烂竽充数", 4), ("墨守成规", "默守成规", 6),
    ("呕心沥血", "沤心沥血", 6), ("悬梁刺股", "悬梁刺骨", 5),
    ("鼎力相助", "鼎立相助", 6), ("黄粱美梦", "黄梁美梦", 6),
    ("蛛丝马迹", "蛛丝蚂迹", 5), ("萎靡不振", "萎糜不振", 6),
    ("出其不意", "出奇不意", 5), ("谈笑风生", "谈笑风声", 5),
    ("人情世故", "人情事故", 6), ("有恃无恐", "有持无恐", 6),
    ("矫揉造作", "娇揉造作", 6), ("一鼓作气", "一股作气", 5),
]

# 句式变换：(原句, 变换类型, 答案, 年级)
SENTENCE_REWRITES = [
    ("小明把作业写完了。", "改为被字句", "作业被小明写完了。", 4),
    ("风吹倒了小树。", "改为被字句", "小树被风吹倒了。", 4),
    ("妈妈洗干净了衣服。", "改为被字句", "衣服被妈妈洗干净了。", 4),
    ("老师表扬了同学们。", "改为被字句", "同学们被老师表扬了。", 4),
    ("雨水淋湿了大地。", "改为被字句", "大地被雨水淋湿了。", 4),
    ("这道题很难。", "改为反问句", "这道题难道不难吗？", 5),
    ("我们应该保护环境。", "改为反问句", "我们难道不应该保护环境吗？", 5),
    ("没有人不喜欢春天。", "改为陈述句", "所有人都喜欢春天。", 5),
    ("难道我们不应该努力学习吗？", "改为陈述句", "我们应该努力学习。", 5),
    ("他跑得很快。", "改为夸张句", "他跑得像风一样快。", 5),
    ("教室里很安静。", "改为夸张句", "教室里安静得连一根针掉在地上都能听见。", 5),
    ("太阳升起来了。", "改为拟人句", "太阳公公露出了笑脸。", 4),
    ("小鸟在枝头叫。", "改为拟人句", "小鸟在枝头唱歌。", 4),
    ("弯弯的月亮挂在天上。", "改为比喻句", "弯弯的月亮像小船一样挂在天上。", 4),
    ("红红的枫叶飘落下来。", "改为比喻句", "红红的枫叶像蝴蝶一样飘落下来。", 4),
]

# 词语归类：(类别名, 词语列表, 年级)
WORD_GROUPS = [
    ("表示高兴的词语", ["兴高采烈", "喜出望外", "欢天喜地", "心花怒放", "眉开眼笑", "手舞足蹈"], 4),
    ("表示悲伤的词语", ["悲痛欲绝", "泪流满面", "伤心欲绝", "痛不欲生", "泣不成声", "肝肠寸断"], 5),
    ("描写春天的词语", ["春暖花开", "万物复苏", "春意盎然", "莺歌燕舞", "草长莺飞", "春色满园"], 4),
    ("描写冬天的词语", ["冰天雪地", "寒风刺骨", "白雪皑皑", "银装素裹", "天寒地冻", "滴水成冰"], 4),
    ("含有动物名的成语", ["狐假虎威", "鹤立鸡群", "对牛弹琴", "画龙点睛", "守株待兔", "鸡飞蛋打"], 4),
    ("含有数字的成语", ["一心一意", "三心二意", "五光十色", "七上八下", "九牛一毛", "百发百中"], 3),
    ("描写人物品质的词语", ["舍己为人", "大公无私", "见义勇为", "助人为乐", "拾金不昧", "鞠躬尽瘁"], 5),
    ("描写学习认真的词语", ["专心致志", "聚精会神", "一丝不苟", "废寝忘食", "孜孜不倦", "全神贯注"], 5),
]


# ═══════════════════════════════════════════════════════════
# 生成器
# ═══════════════════════════════════════════════════════════

def _gen_pinyin_write(count: int, grade: int) -> List[dict]:
    """看拼音写词语"""
    pool = [w for w in PINYIN_WORDS if w[2] <= grade]
    if len(pool) < count:
        pool = PINYIN_WORDS[:]
    selected = random.sample(pool, min(count, len(pool)))
    items = []
    for pinyin, word, g in selected:
        items.append({
            "id": 0,
            "question": f"看拼音写词语：{pinyin} → (    )",
            "answer": word,
            "options": None,
        })
    return items


def _gen_idiom_fill(count: int, grade: int) -> List[dict]:
    """成语填空"""
    pool = [w for w in IDIOMS if w[2] <= grade]
    if len(pool) < count:
        pool = IDIOMS[:]
    selected = random.sample(pool, min(count, len(pool)))
    items = []
    for idiom, blanks, g in selected:
        chars = list(idiom)
        display = []
        answers = []
        for i, ch in enumerate(chars):
            if i in blanks:
                display.append("(  )")
                answers.append(ch)
            else:
                display.append(ch)
        question = f"补充成语：{''.join(display)}"
        answer = "、".join(answers)
        items.append({
            "id": 0,
            "question": question,
            "answer": answer,
            "options": None,
        })
    return items


def _gen_poetry_fill(count: int, grade: int) -> List[dict]:
    """古诗默写"""
    pool = [w for w in POEMS if w[4] <= grade]
    if len(pool) < count:
        pool = POEMS[:]
    selected = random.sample(pool, min(count, len(pool)))
    items = []
    for upper, lower, author, title, g in selected:
        # 随机决定填上句还是下句
        if random.random() < 0.5:
            question = f"默写古诗《{title}》({author})：{upper}，____________。"
            answer = lower
        else:
            question = f"默写古诗《{title}》({author})：____________，{lower}。"
            answer = upper
        items.append({
            "id": 0,
            "question": question,
            "answer": answer,
            "options": None,
        })
    return items


def _gen_typo_correct(count: int, grade: int) -> List[dict]:
    """改错字"""
    pool = [w for w in TYPOS if w[2] <= grade]
    if len(pool) < count:
        pool = TYPOS[:]
    selected = random.sample(pool, min(count, len(pool)))
    items = []
    for correct, wrong, g in selected:
        question = f"找出错别字并改正：「{wrong}」→ (    )"
        items.append({
            "id": 0,
            "question": question,
            "answer": correct,
            "options": None,
        })
    return items


def _gen_sentence_rewrite(count: int, grade: int) -> List[dict]:
    """句式变换"""
    pool = [w for w in SENTENCE_REWRITES if w[3] <= grade]
    if len(pool) < count:
        pool = SENTENCE_REWRITES[:]
    selected = random.sample(pool, min(count, len(pool)))
    items = []
    for original, transform_type, answer, g in selected:
        question = f"句式变换（{transform_type}）：{original}"
        items.append({
            "id": 0,
            "question": question,
            "answer": answer,
            "options": None,
        })
    return items


def _gen_word_classify(count: int, grade: int) -> List[dict]:
    """词语归类"""
    pool = [w for w in WORD_GROUPS if w[2] <= grade]
    if len(pool) < count:
        pool = WORD_GROUPS[:]
    selected = random.sample(pool, min(count, len(pool)))
    items = []
    for category, words, g in selected:
        # 从该类别取3个 + 从其他类别取1个作为干扰
        others = [w for grp in WORD_GROUPS if grp[0] != category for w in grp[1]]
        correct_words = random.sample(words, min(3, len(words)))
        distractor = random.choice(others) if others else ""
        all_words = correct_words + [distractor]
        random.shuffle(all_words)
        question = f"下列词语中，不属于「{category}」的是：{'、'.join(all_words)}"
        items.append({
            "id": 0,
            "question": question,
            "answer": distractor,
            "options": None,
        })
    return items


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def generate_chinese_exam(
    grade: int = 6,
    count_per_type: int = 5,
    exercise_types: Optional[List[str]] = None,
    db: Session = None,
) -> Dict[str, list]:
    """
    生成语文试卷题目。
    返回: { "pinyin_write": [...], "idiom_fill": [...], ... }
    """
    if exercise_types is None:
        exercise_types = ALL_EXERCISE_TYPES[:]

    generators = {
        "pinyin_write": lambda: _gen_pinyin_write(count_per_type, grade),
        "idiom_fill": lambda: _gen_idiom_fill(count_per_type, grade),
        "poetry_fill": lambda: _gen_poetry_fill(count_per_type, grade),
        "typo_correct": lambda: _gen_typo_correct(count_per_type, grade),
        "sentence_rewrite": lambda: _gen_sentence_rewrite(count_per_type, grade),
        "word_classify": lambda: _gen_word_classify(count_per_type, grade),
    }

    result = {}
    for etype in exercise_types:
        if etype in generators:
            result[etype] = generators[etype]()

    return result
