"""002 古诗文种子数据（部编版 1-6 年级必背篇目，教材同步）

将古诗文初始化数据从 init_data.py 迁入迁移脚本管理。
幂等：classical_texts 表已有数据则跳过。
"""
import json
import logging

from ...models.classical import ClassicalText

logger = logging.getLogger("migrations")


CLASSICAL_SEED_DATA = [
    # ── 一年级 ──
    {"title": "咏鹅", "author": "骆宾王", "dynasty": "唐", "grade": 1, "tags": "五言绝句,咏物",
     "content": "鹅，鹅，鹅，\n曲项向天歌。\n白毛浮绿水，\n红掌拨清波。"},
    {"title": "江南", "author": "汉乐府", "dynasty": "汉", "grade": 1, "tags": "乐府,写景",
     "content": "江南可采莲，\n莲叶何田田。\n鱼戏莲叶间。\n鱼戏莲叶东，\n鱼戏莲叶西，\n鱼戏莲叶南，\n鱼戏莲叶北。"},
    {"title": "画", "author": "王维", "dynasty": "唐", "grade": 1, "tags": "五言绝句,写景",
     "content": "远看山有色，\n近听水无声。\n春去花还在，\n人来鸟不惊。"},
    {"title": "悯农（其二）", "author": "李绅", "dynasty": "唐", "grade": 1, "tags": "五言绝句,悯农",
     "content": "锄禾日当午，\n汗滴禾下土。\n谁知盘中餐，\n粒粒皆辛苦。"},
    {"title": "古朗月行（节选）", "author": "李白", "dynasty": "唐", "grade": 1, "tags": "五言古诗,咏月",
     "content": "小时不识月，\n呼作白玉盘。\n又疑瑶台镜，\n飞在青云端。"},
    {"title": "风", "author": "李峤", "dynasty": "唐", "grade": 1, "tags": "五言绝句,咏物",
     "content": "解落三秋叶，\n能开二月花。\n过江千尺浪，\n入竹万竿斜。"},
    {"title": "春晓", "author": "孟浩然", "dynasty": "唐", "grade": 1, "tags": "五言绝句,惜春",
     "content": "春眠不觉晓，\n处处闻啼鸟。\n夜来风雨声，\n花落知多少。"},
    {"title": "赠汪伦", "author": "李白", "dynasty": "唐", "grade": 1, "tags": "七言绝句,友情",
     "content": "李白乘舟将欲行，\n忽闻岸上踏歌声。\n桃花潭水深千尺，\n不及汪伦送我情。"},
    {"title": "静夜思", "author": "李白", "dynasty": "唐", "grade": 1, "tags": "五言绝句,思乡",
     "content": "床前明月光，\n疑是地上霜。\n举头望明月，\n低头思故乡。"},
    {"title": "池上", "author": "白居易", "dynasty": "唐", "grade": 1, "tags": "五言绝句,童趣",
     "content": "小娃撑小艇，\n偷采白莲回。\n不解藏踪迹，\n浮萍一道开。"},
    {"title": "小池", "author": "杨万里", "dynasty": "宋", "grade": 1, "tags": "七言绝句,写景",
     "content": "泉眼无声惜细流，\n树阴照水爱晴柔。\n小荷才露尖尖角，\n早有蜻蜓立上头。"},
    {"title": "寻隐者不遇", "author": "贾岛", "dynasty": "唐", "grade": 1, "tags": "五言绝句,问答",
     "content": "松下问童子，\n言师采药去。\n只在此山中，\n云深不知处。"},
    # ── 二年级 ──
    {"title": "登鹳雀楼", "author": "王之涣", "dynasty": "唐", "grade": 2, "tags": "五言绝句,哲理",
     "content": "白日依山尽，\n黄河入海流。\n欲穷千里目，\n更上一层楼。"},
    {"title": "望庐山瀑布", "author": "李白", "dynasty": "唐", "grade": 2, "tags": "七言绝句,写景",
     "content": "日照香炉生紫烟，\n遥看瀑布挂前川。\n飞流直下三千尺，\n疑是银河落九天。"},
    {"title": "江雪", "author": "柳宗元", "dynasty": "唐", "grade": 2, "tags": "五言绝句,写景",
     "content": "千山鸟飞绝，\n万径人踪灭。\n孤舟蓑笠翁，\n独钓寒江雪。"},
    {"title": "夜宿山寺", "author": "李白", "dynasty": "唐", "grade": 2, "tags": "五言绝句,夸张",
     "content": "危楼高百尺，\n手可摘星辰。\n不敢高声语，\n恐惊天上人。"},
    {"title": "敕勒歌", "author": "北朝民歌", "dynasty": "南北朝", "grade": 2, "tags": "乐府,草原",
     "content": "敕勒川，\n阴山下。\n天似穹庐，\n笼盖四野。\n天苍苍，\n野茫茫，\n风吹草低见牛羊。"},
    {"title": "村居", "author": "高鼎", "dynasty": "清", "grade": 2, "tags": "七言绝句,写景",
     "content": "草长莺飞二月天，\n拂堤杨柳醉春烟。\n儿童散学归来早，\n忙趁东风放纸鸢。"},
    {"title": "咏柳", "author": "贺知章", "dynasty": "唐", "grade": 2, "tags": "七言绝句,咏物",
     "content": "碧玉妆成一树高，\n万条垂下绿丝绦。\n不知细叶谁裁出，\n二月春风似剪刀。"},
    {"title": "赋得古原草送别（节选）", "author": "白居易", "dynasty": "唐", "grade": 2, "tags": "五言古诗,咏物",
     "content": "离离原上草，\n一岁一枯荣。\n野火烧不尽，\n春风吹又生。"},
    {"title": "晓出净慈寺送林子方", "author": "杨万里", "dynasty": "宋", "grade": 2, "tags": "七言绝句,写景",
     "content": "毕竟西湖六月中，\n风光不与四时同。\n接天莲叶无穷碧，\n映日荷花别样红。"},
    {"title": "绝句", "author": "杜甫", "dynasty": "唐", "grade": 2, "tags": "七言绝句,写景",
     "content": "两个黄鹂鸣翠柳，\n一行白鹭上青天。\n窗含西岭千秋雪，\n门泊东吴万里船。"},
    {"title": "舟夜书所见", "author": "查慎行", "dynasty": "清", "grade": 2, "tags": "五言绝句,写景",
     "content": "月黑见渔灯，\n孤光一点萤。\n微微风簇浪，\n散作满河星。"},
    # ── 三年级 ──
    {"title": "所见", "author": "袁枚", "dynasty": "清", "grade": 3, "tags": "五言绝句,童趣",
     "content": "牧童骑黄牛，\n歌声振林樾。\n意欲捕鸣蝉，\n忽然闭口立。"},
    {"title": "早发白帝城", "author": "李白", "dynasty": "唐", "grade": 3, "tags": "七言绝句,写景",
     "content": "朝辞白帝彩云间，\n千里江陵一日还。\n两岸猿声啼不住，\n轻舟已过万重山。"},
    {"title": "望天门山", "author": "李白", "dynasty": "唐", "grade": 3, "tags": "七言绝句,写景",
     "content": "天门中断楚江开，\n碧水东流至此回。\n两岸青山相对出，\n孤帆一片日边来。"},
    {"title": "饮湖上初晴后雨", "author": "苏轼", "dynasty": "宋", "grade": 3, "tags": "七言绝句,写景",
     "content": "水光潋滟晴方好，\n山色空蒙雨亦奇。\n欲把西湖比西子，\n淡妆浓抹总相宜。"},
    {"title": "夜书所见", "author": "叶绍翁", "dynasty": "宋", "grade": 3, "tags": "七言绝句,思乡",
     "content": "萧萧梧叶送寒声，\n江上秋风动客情。\n知有儿童挑促织，\n夜深篱落一灯明。"},
    {"title": "九月九日忆山东兄弟", "author": "王维", "dynasty": "唐", "grade": 3, "tags": "七言绝句,思乡",
     "content": "独在异乡为异客，\n每逢佳节倍思亲。\n遥知兄弟登高处，\n遍插茱萸少一人。"},
    {"title": "望洞庭", "author": "刘禹锡", "dynasty": "唐", "grade": 3, "tags": "七言绝句,写景",
     "content": "湖光秋月两相和，\n潭面无风镜未磨。\n遥望洞庭山水翠，\n白银盘里一青螺。"},
    {"title": "采莲曲", "author": "王昌龄", "dynasty": "唐", "grade": 3, "tags": "七言绝句,写景",
     "content": "荷叶罗裙一色裁，\n芙蓉向脸两边开。\n乱入池中看不见，\n闻歌始觉有人来。"},
    {"title": "司马光", "author": "《宋史》", "dynasty": "宋", "grade": 3, "text_type": "prose", "tags": "文言文,勤学",
     "content": "群儿戏于庭，\n一儿登瓮，足跌没水中。\n众皆弃去，\n光持石击瓮破之，\n水迸，儿得活。"},
    {"title": "守株待兔", "author": "韩非子", "dynasty": "战国", "grade": 3, "text_type": "prose", "tags": "文言文,寓言",
     "content": "宋人有耕者。\n田中有株。\n兔走触株，折颈而死。\n因释其耒而守株，冀复得兔。\n兔不可复得，\n而身为宋国笑。"},
    # ── 四年级 ──
    {"title": "题西林壁", "author": "苏轼", "dynasty": "宋", "grade": 4, "tags": "七言绝句,哲理",
     "content": "横看成岭侧成峰，\n远近高低各不同。\n不识庐山真面目，\n只缘身在此山中。"},
    {"title": "暮江吟", "author": "白居易", "dynasty": "唐", "grade": 4, "tags": "七言绝句,写景",
     "content": "一道残阳铺水中，\n半江瑟瑟半江红。\n可怜九月初三夜，\n露似真珠月似弓。"},
    {"title": "雪梅", "author": "卢钺", "dynasty": "宋", "grade": 4, "tags": "七言绝句,咏物",
     "content": "梅雪争春未肯降，\n骚人阁笔费评章。\n梅须逊雪三分白，\n雪却输梅一段香。"},
    {"title": "出塞", "author": "王昌龄", "dynasty": "唐", "grade": 4, "tags": "七言绝句,边塞",
     "content": "秦时明月汉时关，\n万里长征人未还。\n但使龙城飞将在，\n不教胡马度阴山。"},
    {"title": "凉州词", "author": "王翰", "dynasty": "唐", "grade": 4, "tags": "七言绝句,边塞",
     "content": "葡萄美酒夜光杯，\n欲饮琵琶马上催。\n醉卧沙场君莫笑，\n古来征战几人回。"},
    {"title": "夏日绝句", "author": "李清照", "dynasty": "宋", "grade": 4, "tags": "五言绝句,咏史",
     "content": "生当作人杰，\n死亦为鬼雄。\n至今思项羽，\n不肯过江东。"},
    {"title": "别董大", "author": "高适", "dynasty": "唐", "grade": 4, "tags": "七言绝句,送别",
     "content": "千里黄云白日曛，\n北风吹雁雪纷纷。\n莫愁前路无知己，\n天下谁人不识君。"},
    {"title": "精卫填海", "author": "《山海经》", "dynasty": "先秦", "grade": 4, "text_type": "prose", "tags": "文言文,神话",
     "content": "炎帝之少女，名曰女娃。\n女娃游于东海，溺而不返，故为精卫，\n常衔西山之木石，以堙于东海。"},
    {"title": "王戎不取道旁李", "author": "刘义庆", "dynasty": "南朝", "grade": 4, "text_type": "prose", "tags": "文言文,哲理",
     "content": "王戎七岁，尝与诸小儿游。\n看道边李树多子折枝，\n诸儿竞走取之，\n唯戎不动。\n人问之，答曰：\n树在道边而多子，此必苦李。\n取之，信然。"},
    # ── 五年级 ──
    {"title": "示儿", "author": "陆游", "dynasty": "宋", "grade": 5, "tags": "七言绝句,爱国",
     "content": "死去元知万事空，\n但悲不见九州同。\n王师北定中原日，\n家祭无忘告乃翁。"},
    {"title": "题临安邸", "author": "林升", "dynasty": "宋", "grade": 5, "tags": "七言绝句,爱国",
     "content": "山外青山楼外楼，\n西湖歌舞几时休。\n暖风熏得游人醉，\n直把杭州作汴州。"},
    {"title": "己亥杂诗", "author": "龚自珍", "dynasty": "清", "grade": 5, "tags": "七言绝句,爱国",
     "content": "九州生气恃风雷，\n万马齐喑究可哀。\n我劝天公重抖擞，\n不拘一格降人材。"},
    {"title": "山居秋暝", "author": "王维", "dynasty": "唐", "grade": 5, "tags": "五言律诗,写景",
     "content": "空山新雨后，\n天气晚来秋。\n明月松间照，\n清泉石上流。\n竹喧归浣女，\n莲动下渔舟。\n随意春芳歇，\n王孙自可留。"},
    {"title": "枫桥夜泊", "author": "张继", "dynasty": "唐", "grade": 5, "tags": "七言绝句,羁旅",
     "content": "月落乌啼霜满天，\n江枫渔火对愁眠。\n姑苏城外寒山寺，\n夜半钟声到客船。"},
    {"title": "渔歌子", "author": "张志和", "dynasty": "唐", "grade": 5, "tags": "词,写景",
     "content": "西塞山前白鹭飞，\n桃花流水鳜鱼肥。\n青箬笠，绿蓑衣，\n斜风细雨不须归。"},
    {"title": "观书有感（其一）", "author": "朱熹", "dynasty": "宋", "grade": 5, "tags": "七言绝句,哲理",
     "content": "半亩方塘一鉴开，\n天光云影共徘徊。\n问渠那得清如许？\n为有源头活水来。"},
    {"title": "四时田园杂兴（其三十一）", "author": "范成大", "dynasty": "宋", "grade": 5, "tags": "七言绝句,田园",
     "content": "昼出耘田夜绩麻，\n村庄儿女各当家。\n童孙未解供耕织，\n也傍桑阴学种瓜。"},
    {"title": "自相矛盾", "author": "韩非子", "dynasty": "战国", "grade": 5, "text_type": "prose", "tags": "文言文,寓言",
     "content": "楚人有鬻盾与矛者，\n誉之曰：吾盾之坚，物莫能陷也。\n又誉其矛曰：吾矛之利，于物无不陷也。\n或曰：以子之矛，陷子之盾，何如？\n其人弗能应也。\n夫不可陷之盾与无不陷之矛，不可同世而立。"},
    {"title": "杨氏之子", "author": "刘义庆", "dynasty": "南朝", "grade": 5, "text_type": "prose", "tags": "文言文,机智",
     "content": "梁国杨氏子九岁，甚聪惠。\n孔君平诣其父，父不在，乃呼儿出。\n为设果，果有杨梅。\n孔指以示儿曰：此是君家果。\n儿应声答曰：未闻孔雀是夫子家禽。"},
    # ── 六年级 ──
    {"title": "马诗", "author": "李贺", "dynasty": "唐", "grade": 6, "tags": "五言绝句,咏物",
     "content": "大漠沙如雪，\n燕山月似钩。\n何当金络脑，\n快走踏清秋。"},
    {"title": "竹石", "author": "郑燮", "dynasty": "清", "grade": 6, "tags": "七言绝句,咏物",
     "content": "咬定青山不放松，\n立根原在破岩中。\n千磨万击还坚劲，\n任尔东西南北风。"},
    {"title": "石灰吟", "author": "于谦", "dynasty": "明", "grade": 6, "tags": "七言绝句,咏物",
     "content": "千锤万凿出深山，\n烈火焚烧若等闲。\n粉骨碎身浑不怕，\n要留清白在人间。"},
    {"title": "墨梅", "author": "王冕", "dynasty": "元", "grade": 6, "tags": "七言绝句,咏物",
     "content": "我家洗砚池头树，\n朵朵花开淡墨痕。\n不要人夸好颜色，\n只留清气满乾坤。"},
    {"title": "春夜喜雨", "author": "杜甫", "dynasty": "唐", "grade": 6, "tags": "五言律诗,写景",
     "content": "好雨知时节，\n当春乃发生。\n随风潜入夜，\n润物细无声。\n野径云俱黑，\n江船火独明。\n晓看红湿处，\n花重锦官城。"},
    {"title": "泊船瓜洲", "author": "王安石", "dynasty": "宋", "grade": 6, "tags": "七言绝句,思乡",
     "content": "京口瓜洲一水间，\n钟山只隔数重山。\n春风又绿江南岸，\n明月何时照我还。"},
    {"title": "游园不值", "author": "叶绍翁", "dynasty": "宋", "grade": 6, "tags": "七言绝句,哲理",
     "content": "应怜屐齿印苍苔，\n小扣柴扉久不开。\n春色满园关不住，\n一枝红杏出墙来。"},
    {"title": "书湖阴先生壁", "author": "王安石", "dynasty": "宋", "grade": 6, "tags": "七言绝句,写景",
     "content": "茅檐长扫净无苔，\n花木成畦手自栽。\n一水护田将绿绕，\n两山排闼送青来。"},
    {"title": "六月二十七日望湖楼醉书", "author": "苏轼", "dynasty": "宋", "grade": 6, "tags": "七言绝句,写景",
     "content": "黑云翻墨未遮山，\n白雨跳珠乱入船。\n卷地风来忽吹散，\n望湖楼下水如天。"},
    {"title": "江上渔者", "author": "范仲淹", "dynasty": "宋", "grade": 6, "tags": "五言绝句,悯农",
     "content": "江上往来人，\n但爱鲈鱼美。\n君看一叶舟，\n出没风波里。"},
    {"title": "学弈", "author": "《孟子》", "dynasty": "战国", "grade": 6, "text_type": "prose", "tags": "文言文,勤学",
     "content": "弈秋，通国之善弈者也。\n使弈秋诲二人弈，\n其一人专心致志，惟弈秋之为听；\n一人虽听之，一心以为有鸿鹄将至，思援弓缴而射之。\n虽与之俱学，弗若之矣。\n为是其智弗若与？曰：非然也。"},
    {"title": "两小儿辩日", "author": "《列子》", "dynasty": "战国", "grade": 6, "text_type": "prose", "tags": "文言文,哲理",
     "content": "孔子东游，见两小儿辩斗，问其故。\n一儿曰：我以日始出时去人近，而日中时远也。\n一儿以日初出远，而日中时近也。\n一儿曰：日初出大如车盖，及日中则如盘盂，此不为远者小而近者大乎？\n一儿曰：日初出沧沧凉凉，及其日中如探汤，此不为近者热而远者凉乎？\n孔子不能决也。\n两小儿笑曰：孰为汝多知乎？"},
]


def upgrade(db):
    count = db.query(ClassicalText).count()
    if count > 0:
        logger.info("classical_texts 已有 %s 条数据，跳过种子", count)
        return
    for item in CLASSICAL_SEED_DATA:
        lines = [l.strip() for l in item["content"].split("\n") if l.strip()]
        db.add(ClassicalText(
            title=item["title"],
            author=item["author"],
            dynasty=item["dynasty"],
            text_type=item.get("text_type", "poem"),
            grade=item["grade"],
            content=item["content"],
            lines_json=json.dumps(lines, ensure_ascii=False),
            tags=item["tags"],
        ))
    db.commit()
    logger.info("古诗文种子数据已写入 %s 篇", len(CLASSICAL_SEED_DATA))
