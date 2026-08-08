"""语文试卷生成器

题型：
  - pinyin_write: 看拼音写汉字
  - idiom_fill: 成语填空
  - poetry_fill: 古诗默写
  - typo_correct: 改错字
  - sentence_rewrite: 句式变换
  - word_classify: 词语归类
  - poetry_translate: 诗词翻译（古译今）
  - idiom_chain: 成语接龙
  - flying_flower: 飞花令
  - reading_comp: 阅读理解
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
    "poetry_translate",
    "idiom_chain",
    "flying_flower",
    "reading_comp",
]

TYPE_NAMES = {
    "pinyin_write": "看拼音写词语",
    "idiom_fill": "成语填空",
    "poetry_fill": "古诗默写",
    "typo_correct": "改错字",
    "sentence_rewrite": "句式变换",
    "word_classify": "词语归类",
    "poetry_translate": "诗词翻译",
    "idiom_chain": "成语接龙",
    "flying_flower": "飞花令",
    "reading_comp": "阅读理解",
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

# 诗词翻译：(原句, 现代文翻译, 作者, 题目, 年级)
POETRY_TRANSLATIONS = [
    ("床前明月光，疑是地上霜", "明亮的月光洒在床前，好像地上泛起了一层白霜", "李白", "静夜思", 3),
    ("春眠不觉晓，处处闻啼鸟", "春天睡醒不觉天已破晓，处处听到鸟儿的啼叫", "孟浩然", "春晓", 3),
    ("白日依山尽，黄河入海流", "太阳沿着山峦渐渐沉落，黄河奔腾着流向大海", "王之涣", "登鹳雀楼", 3),
    ("飞流直下三千尺，疑是银河落九天", "瀑布从高处飞流而下好像有三千尺，让人怀疑是银河从天上落下来", "李白", "望庐山瀑布", 4),
    ("停车坐爱枫林晚，霜叶红于二月花", "停下马车是因为喜爱这傍晚的枫林，被霜打过的枫叶比二月的花还要红", "杜牧", "山行", 4),
    ("独在异乡为异客，每逢佳节倍思亲", "独自在他乡做客，每到节日就加倍思念亲人", "王维", "九月九日忆山东兄弟", 4),
    ("欲穷千里目，更上一层楼", "想要看到更远的风景，就要再登上一层楼", "王之涣", "登鹳雀楼", 4),
    ("大漠孤烟直，长河落日圆", "浩瀚沙漠中孤烟直上，黄河边上落日浑圆", "王维", "使至塞上", 5),
    ("海内存知己，天涯若比邻", "四海之内有知心朋友，即使远在天边也像近邻一样", "王勃", "送杜少府之任蜀州", 5),
    ("会当凌绝顶，一览众山小", "一定要登上泰山的最高峰，那时所有的山都显得矮小了", "杜甫", "望岳", 5),
    ("春蚕到死丝方尽，蜡炬成灰泪始干", "春蚕到死才停止吐丝，蜡烛烧成灰烬才停止流泪", "李商隐", "无题", 5),
    ("不识庐山真面目，只缘身在此山中", "认不清庐山的真实面貌，只因为自己就在这座山中", "苏轼", "题西林壁", 5),
    ("落红不是无情物，化作春泥更护花", "落花不是无情的东西，它化作春泥后更加呵护花朵", "龚自珍", "己亥杂诗", 6),
    ("千磨万击还坚劲，任尔东西南北风", "经历无数磨难和打击依然坚强挺拔，任凭你刮什么风都不怕", "郑燮", "竹石", 6),
    ("谁言寸草心，报得三春晖", "谁说像小草一样的孝心，能报答得了春天阳光般的母爱", "孟郊", "游子吟", 6),
    ("问渠那得清如许，为有源头活水来", "要问池塘里的水为什么这么清澈，是因为有源头的活水不断流进来", "朱熹", "观书有感", 6),
]

# 成语接龙：(起始成语, 接龙序列, 年级)
IDIOM_CHAINS = [
    ("一心一意", ["一心一意", "意气风发", "发扬光大", "大快人心"], 3),
    ("画龙点睛", ["画龙点睛", "睛天霹雳"], 4),
    ("守株待兔", ["守株待兔", "兔死狐悲", "悲欢离合"], 4),
    ("亡羊补牢", ["亡羊补牢", "牢不可破"], 5),
    ("对牛弹琴", ["对牛弹琴", "琴棋书画"], 4),
    ("狐假虎威", ["狐假虎威", "威风凛凛"], 5),
    ("胸有成竹", ["胸有成竹", "竹篮打水"], 5),
    ("一鸣惊人", ["一鸣惊人", "人山人海", "海阔天空"], 4),
    ("破釜沉舟", ["破釜沉舟", "舟车劳顿"], 6),
    ("完璧归赵", ["完璧归赵"], 6),
    ("闻鸡起舞", ["闻鸡起舞", "舞文弄墨"], 5),
    ("精忠报国", ["精忠报国", "国泰民安", "安居乐业"], 5),
    ("指鹿为马", ["指鹿为马", "马到成功", "功成名就"], 6),
    ("入木三分", ["入木三分", "分秒必争"], 6),
    ("四面楚歌", ["四面楚歌", "歌舞升平"], 6),
]

# 飞花令：(令字, 包含该字的诗句列表, 年级)
FLYING_FLOWER = [
    ("月", ["床前明月光——李白《静夜思》", "举头望明月——李白《静夜思》", "明月几时有——苏轼《水调歌头》", "月落乌啼霜满天——张继《枫桥夜泊》"], 4),
    ("花", ["霜叶红于二月花——杜牧《山行》", "花落知多少——孟浩然《春晓》", "花开堪折直须折——杜秋娘《金缕衣》", "花重锦官城——杜甫《春夜喜雨》"], 4),
    ("风", ["春风不度玉门关——王之涣《凉州词》", "大风起兮云飞扬——刘邦《大风歌》", "夜来风雨声——孟浩然《春晓》", "风吹草低见牛羊——北朝民歌"], 4),
    ("春", ["春眠不觉晓——孟浩然《春晓》", "春风又绿江南岸——王安石《泊船瓜洲》", "春色满园关不住——叶绍翁《游园不值》", "春蚕到死丝方尽——李商隐《无题》"], 5),
    ("山", ["会当凌绝顶，一览众山小——杜甫《望岳》", "不识庐山真面目——苏轼《题西林壁》", "两岸青山相对出——李白《望天门山》", "千山鸟飞绝——柳宗元《江雪》"], 5),
    ("水", ["黄河入海流——王之涣《登鹳雀楼》", "飞流直下三千尺——李白《望庐山瀑布》", "黄河之水天上来——李白《将进酒》", "秋水共长天一色——王勃《滕王阁序》"], 5),
    ("雪", ["窗含西岭千秋雪——杜甫《绝句》", "北风卷地白草折，胡天八月即飞雪——岑参《白雪歌》", "梅须逊雪三分白——卢梅坡《雪梅》", "孤舟蓑笠翁，独钓寒江雪——柳宗元《江雪》"], 6),
    ("云", ["远上寒山石径斜，白云生处有人家——杜牧《山行》", "黄河远上白云间——王之涣《凉州词》", "朝辞白帝彩云间——李白《早发白帝城》", "只在此山中，云深不知处——贾岛《寻隐者不遇》"], 5),
    ("日", ["白日依山尽——王之涣《登鹳雀楼》", "日照香炉生紫烟——李白《望庐山瀑布》", "锄禾日当午——李绅《悯农》", "日出江花红胜火——白居易《忆江南》"], 4),
    ("秋", ["春花秋月何时了——李煜《虞美人》", "自古逢秋悲寂寥——刘禹锡《秋词》", "停车坐爱枫林晚——杜牧《山行》", "空山新雨后，天气晚来秋——王维《山居秋暝》"], 6),
]

# 阅读理解：(短文, 题目列表[(问题, 答案)], 年级)
READING_PASSAGES = [
    (
        "小明家的院子里有一棵老槐树。春天，槐树抽出新的枝条，长出嫩绿的叶子。夏天，槐树长得郁郁葱葱，像一把巨大的绿伞，为我们遮挡阳光。秋天，槐树的叶子变黄了，一片片落下来，像一只只金色的蝴蝶在飞舞。冬天，槐树虽然只剩下光秃秃的枝干，但它依然挺立在寒风中。",
        [
            ("春天的槐树是什么样的？", "抽出新的枝条，长出嫩绿的叶子"),
            ("夏天槐树像什么？", "像一把巨大的绿伞"),
            ("秋天的槐树叶像什么？", "像一只只金色的蝴蝶在飞舞"),
            ("冬天槐树有什么特点？", "虽然只剩下光秃秃的枝干，但依然挺立在寒风中"),
        ],
        3,
    ),
    (
        "乌鸦口渴了，到处找水喝。乌鸦看见一个瓶子，瓶子里有水。可是，瓶子里水不多，瓶口又小，乌鸦喝不着水。怎么办呢？乌鸦看见旁边有许多小石子，想出办法来了。乌鸦把小石子一颗一颗地放进瓶子里，瓶子里的水渐渐升高，乌鸦就喝着水了。",
        [
            ("乌鸦遇到了什么困难？", "瓶子里水不多，瓶口又小，喝不着水"),
            ("乌鸦想出了什么办法？", "把小石子一颗一颗地放进瓶子里，让水升高"),
            ("这个故事告诉我们什么道理？", "遇到困难要动脑筋想办法"),
        ],
        3,
    ),
    (
        "赵州桥非常雄伟。桥长五十多米，有九米多宽，中间行马车，两旁走人。这么长的桥，全部用石头砌成，下面没有桥墩，只有一个拱形的大桥洞，横跨在三十七米多宽的河面上。大桥洞顶上的左右两边，还各有两个拱形的小桥洞。这种设计，在建桥史上是一个创举，既减轻了流水对桥身的冲击力，使桥不容易被大水冲毁，又减轻了桥身的重量，节省了石料。",
        [
            ("赵州桥有多长多宽？", "桥长五十多米，有九米多宽"),
            ("赵州桥的设计有什么特点？", "全部用石头砌成，下面没有桥墩，只有一个拱形的大桥洞"),
            ("这种设计的两个好处是什么？", "既减轻了流水对桥身的冲击力，又减轻了桥身的重量节省了石料"),
        ],
        5,
    ),
    (
        "圆明园中，有金碧辉煌的殿堂，也有玲珑剔透的亭台楼阁；有象征着热闹街市的「买卖街」，也有象征着田园风光的山乡村野。园中许多景物都是仿照各地名胜建造的，如海宁的安澜园、苏州的狮子林、杭州西湖的平湖秋月；还有很多景物是根据古代诗人的诗情画意建造的，如蓬岛瑶台、武陵春色。园中不仅有民族建筑，还有西洋景观。漫步园内，有如漫游在天南海北，饱览着中外风景名胜；流连其间，仿佛置身在幻想的境界里。",
        [
            ("圆明园中有哪些类型的建筑？", "有殿堂、亭台楼阁、买卖街、山乡村野等"),
            ("园中的景物是怎么来的？", "有的仿照各地名胜建造，有的根据古代诗人的诗情画意建造，还有西洋景观"),
            ("这段文字表达了作者怎样的感情？", "对圆明园辉煌景观的赞叹和喜爱"),
        ],
        6,
    ),
    (
        "父亲说：「花生的好处很多，有一样最可贵。它的果实埋在地里，不像桃子、石榴、苹果那样，把鲜红嫩绿的果实高高地挂在枝上，使人一见就生爱慕之心。你们看它矮矮地长在地上，等到成熟了，也不能立刻分辨出来它有没有果实，必须挖起来才知道。」我们都说是，母亲也点点头。父亲接下去说：「所以你们要像花生，它虽然不好看，可是很有用。」",
        [
            ("父亲认为花生最可贵的地方是什么？", "果实埋在地里，不像桃子石榴苹果那样把果实高高挂在枝上"),
            ("花生和桃子、苹果有什么不同？", "花生果实埋在地下，矮矮地长在地上；桃子苹果把鲜红嫩绿的果实高高挂在枝上"),
            ("父亲借花生告诉孩子们什么道理？", "要做有用的人，不要做只讲体面而对别人没有好处的人"),
        ],
        5,
    ),
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


def _gen_poetry_translate(count: int, grade: int) -> List[dict]:
    """诗词翻译：给出古诗原句，写出白话文翻译"""
    pool = [w for w in POETRY_TRANSLATIONS if w[4] <= grade]
    if len(pool) < count:
        pool = POETRY_TRANSLATIONS[:]
    selected = random.sample(pool, min(count, len(pool)))
    items = []
    for original, translation, author, title, g in selected:
        question = f"翻译下列诗句（{author}《{title}》）：\n「{original}」"
        items.append({
            "id": 0,
            "question": question,
            "answer": translation,
            "options": None,
        })
    return items


def _gen_idiom_chain(count: int, grade: int) -> List[dict]:
    """成语接龙：给出起始成语，写出接龙序列"""
    pool = [w for w in IDIOM_CHAINS if w[2] <= grade]
    if len(pool) < count:
        pool = IDIOM_CHAINS[:]
    selected = random.sample(pool, min(count, len(pool)))
    items = []
    for start, chain, g in selected:
        # 挖空接龙中的后续成语（保留第一个）
        if len(chain) <= 1:
            continue
        blanks_needed = len(chain) - 1
        display = [chain[0]] + ["(    )"] * blanks_needed
        question = f"成语接龙：{' → '.join(display)}\n（提示：后一个成语的第一个字 = 前一个成语的最后一个字）"
        answer = " → ".join(chain[1:])
        items.append({
            "id": 0,
            "question": question,
            "answer": answer,
            "options": None,
        })
    return items


def _gen_flying_flower(count: int, grade: int) -> List[dict]:
    """飞花令：给出令字，写出包含该字的诗句"""
    pool = [w for w in FLYING_FLOWER if w[2] <= grade]
    if len(pool) < count:
        pool = FLYING_FLOWER[:]
    selected = random.sample(pool, min(count, len(pool)))
    items = []
    for char, poems, g in selected:
        # 展示部分诗句作为示例，要求写出更多
        shown = poems[:2]
        question = f"飞花令——令字「{char}」\n示例：{shown[0]}、{shown[1]}\n请再写出 2 句含有「{char}」字的诗句："
        answer = "、".join(poems[2:]) if len(poems) > 2 else "、".join(poems)
        items.append({
            "id": 0,
            "question": question,
            "answer": answer,
            "options": None,
        })
    return items


def _gen_reading_comp(count: int, grade: int) -> List[dict]:
    """阅读理解：给出短文，回答问题"""
    pool = [w for w in READING_PASSAGES if w[2] <= grade]
    if len(pool) < count:
        pool = READING_PASSAGES[:]
    selected = random.sample(pool, min(count, len(pool)))
    items = []
    for passage, questions, g in selected:
        # 每篇短文取 2-3 个问题
        q_count = min(3, len(questions))
        chosen_qs = random.sample(questions, q_count)
        for qi, (q_text, q_answer) in enumerate(chosen_qs, 1):
            full_q = f"阅读短文，回答问题：\n\n{passage}\n\n第{qi}题：{q_text}"
            items.append({
                "id": 0,
                "question": full_q,
                "answer": q_answer,
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
        "poetry_translate": lambda: _gen_poetry_translate(count_per_type, grade),
        "idiom_chain": lambda: _gen_idiom_chain(count_per_type, grade),
        "flying_flower": lambda: _gen_flying_flower(count_per_type, grade),
        "reading_comp": lambda: _gen_reading_comp(count_per_type, grade),
    }

    result = {}
    for etype in exercise_types:
        if etype in generators:
            result[etype] = generators[etype]()

    return result
