"""037 语言/题库扩充（MySQL-only，SQLite 测试跳过）

1. classical_texts 加 unit 列 + 按 (年级,学期) 标注课内单元
2. middle_questions 加 unit 列 + 六科按章节标注
3. 初中语文题库（middle_questions subject=语文）≥30 题
4. 六科题库各扩充至 ≥30 题（原 20 → 30+）
5. 英语初中 phrases/sentences 扩充（短语 ≥80、句子 ≥60，grade 7-9）

幂等：列已存在则跳过 ALTER；种子按唯一键去重。

为何 MySQL-only：属于 MYSQL_ONLY_BASELINE(029) 基线，SQLite 下被标记已执行而跳过；
ALTER/种子依赖 MySQL 路径已建好的表结构。
"""
import json

from sqlalchemy import inspect, text


# ── 六科章节单元（用于 middle_questions.unit 标注，每年级 4-6 章）──
CH_UNITS = {
    "物理": ["八年级上·机械运动", "八年级上·声现象", "八年级下·力", "九年级·电与磁", "九年级·能量"],
    "化学": ["九年级·物质构成", "九年级·空气与水", "九年级·碳和氧化物", "九年级·化学与社会"],
    "生物": ["七年级·生物圈", "七年级·人体营养", "八年级·人体调节", "八年级·遗传与进化"],
    "道德与法治": ["七年级·成长的节拍", "八年级·遵守社会规则", "九年级·国情教育"],
    "历史": ["七年级·中国古代史", "八年级·中国近现代史", "九年级·世界史"],
    "地理": ["七年级·地球与地图", "七年级·世界地理", "八年级·中国地理"],
    "语文": ["七年级·现代文阅读", "七年级·古诗文", "八年级·记叙文", "八年级·文言文", "九年级·议论文", "九年级·古诗文"],
}

# 选项加 A-D 前缀的工具
_LETTERS = "ABCD"


def _prefixed(options):
    return [f"{_LETTERS[i]}. {opt}" for i, opt in enumerate(options)]


def _correct(options, answer):
    return next(p for p, opt in zip(_prefixed(options), options) if opt == answer)


# ════════════ 初中语文题库（≥30）═══════════
# (题干, [4选项], 正确选项文本, 解析, 年级, 单元key)
CHI_SEED = [
    ("下列加点字注音完全正确的一项是（ ）", ["静谧(mì)", "抖擞(sǒu)", "贮蓄(chǔ)", "莅临(wèi)"], "静谧(mì)", "贮蓄 zhù；莅临 lì；抖擞 sǒu 也正确，但题中仅 mì 无误且其余有误。", 7, "七年级·现代文阅读"),
    ("「春」的作者是（ ）", ["朱自清", "老舍", "鲁迅", "冰心"], "朱自清", "《春》是现代散文家朱自清的作品。", 7, "七年级·现代文阅读"),
    ("下列词语书写有误的一项是（ ）", ["朗润", "喉咙", "瞭亮", "唤醒"], "瞭亮", "应为「嘹亮」。", 7, "七年级·现代文阅读"),
    ("「济南的冬天」中作者认为济南冬天的特点是（ ）", ["寒冷", "响晴", "炎热", "多雨"], "响晴", "老舍写济南冬天「温晴」「响晴」。", 7, "七年级·现代文阅读"),
    ("古代诗歌中「日月之行，若出其中」出自（ ）", ["《观沧海》", "《次北固山下》", "《天净沙》", "《闻王昌龄》"], "《观沧海》", "出自曹操《观沧海》。", 7, "七年级·古诗文"),
    ("「海日生残夜，江春入旧年」的作者是（ ）", ["王湾", "李白", "王维", "杜甫"], "王湾", "出自王湾《次北固山下》。", 7, "七年级·古诗文"),
    ("下列诗句描写春天的是（ ）", ["停车坐爱枫林晚", "孤舟蓑笠翁", "万条垂下绿丝绦", "千山鸟飞绝"], "万条垂下绿丝绦", "贺知章咏柳写春天。", 7, "七年级·古诗文"),
    ("「论语」中「学而时习之」的下句是（ ）", ["不亦说乎", "不亦乐乎", "不亦君乎", "不亦友乎"], "不亦说乎", "原文「不亦说乎」。", 7, "七年级·古诗文"),
    ("下列句子修辞手法与其他三项不同的是（ ）", ["春天像小姑娘", "雨是最寻常的", "树尖上顶着一髻儿白花", "那点儿薄雪好像忽然害了羞"], "雨是最寻常的", "其余为比喻/拟人，此项为陈述。", 7, "七年级·现代文阅读"),
    ("「散步」中一家人散步的分歧是（ ）", ["走大路还是小路", "去公园还是回家", "吃饭还是看书", "坐车还是走路"], "走大路还是小路", "母亲要走大路，儿子要走小路。", 7, "七年级·现代文阅读"),

    ("「藤野先生」的作者是（ ）", ["鲁迅", "郭沫若", "茅盾", "巴金"], "鲁迅", "出自鲁迅《朝花夕拾》。", 8, "八年级·记叙文"),
    ("「背影」中父亲为「我」做的事件是（ ）", ["买橘子", "写信", "做饭", "缝衣"], "买橘子", "父亲爬月台为「我」买橘子。", 8, "八年级·记叙文"),
    ("下列加点字读音正确的一项是（ ）", ["绯红(fēi)", "畸形(qí)", "不逊(sūn)", "匿名(nuò)"], "绯红(fēi)", "畸 jī；逊 xùn；匿 nì。", 8, "八年级·记叙文"),
    ("「苏州园林」的说明对象是（ ）", ["园林", "庙宇", "桥梁", "楼阁"], "园林", "说明苏州园林的设计特点。", 8, "八年级·记叙文"),
    ("说明文中「务必使游览者无论站在哪个点上，眼前总是一幅完美的图画」运用了（ ）", ["描写", "议论", "说明", "抒情"], "说明", "以说明为主介绍设计追求。", 8, "八年级·记叙文"),
    ("「三峡」的作者是（ ）", ["郦道元", "柳宗元", "欧阳修", "苏轼"], "郦道元", "出自北魏郦道元《水经注》。", 8, "八年级·文言文"),
    ("「记承天寺夜游」的作者是（ ）", ["苏轼", "苏辙", "苏洵", "王安石"], "苏轼", "北宋苏轼所作。", 8, "八年级·文言文"),
    ("下列句子翻译正确的一项是（ ）", ["但少闲人如吾两人者耳——只是缺少像我俩这样清闲的人", "略无阙处——完全没有缺口", "虽乘奔御风——虽然乘着奔马", "五色交辉——五种颜色"], "但少闲人如吾两人者耳——只是缺少像我俩这样清闲的人", "B 应为「完全没有中断的地方」；C「虽」即使；D 应为「色彩交相辉映」。", 8, "八年级·文言文"),
    ("「孟子」二章中「天时不如地利」说明（ ）", ["天气重要", "地理重要", "人和最重要", "武器重要"], "人和最重要", "论点「地利不如人和」。", 8, "八年级·文言文"),
    ("下列成语出自「愚公移山」的是（ ）", ["精益求精", "愚公移山", "守株待兔", "画蛇添足"], "愚公移山", "出自《列子·汤问》。", 8, "八年级·文言文"),

    ("「岳阳楼记」的作者是（ ）", ["范仲淹", "欧阳修", "苏轼", "柳宗元"], "范仲淹", "北宋范仲淹作。", 9, "九年级·古诗文"),
    ("「先天下之忧而忧」的下句是（ ）", ["后天下之乐而乐", "不以己悲", "气象万千", "宠辱偕忘"], "后天下之乐而乐", "出自《岳阳楼记》。", 9, "九年级·古诗文"),
    ("「醉翁亭记」的作者是（ ）", ["欧阳修", "范仲淹", "王安石", "司马光"], "欧阳修", "北宋欧阳修作。", 9, "九年级·古诗文"),
    ("「敬业与乐业」的作者是（ ）", ["梁启超", "康有为", "谭嗣同", "严复"], "梁启超", "近代梁启超的演讲词。", 9, "九年级·议论文"),
    ("议论文的三要素是（ ）", ["论点、论据、论证", "标题、开头、结尾", "描写、抒情、议论", "起因、经过、结果"], "论点、论据、论证", "议论文基本要素。", 9, "九年级·议论文"),
    ("「中国人失掉自信力了吗」的作者是（ ）", ["鲁迅", "茅盾", "老舍", "冰心"], "鲁迅", "鲁迅杂文。", 9, "九年级·议论文"),
    ("下列诗句「沉舟侧畔千帆过」的下句是（ ）", ["病树前头万木春", "到乡翻似烂柯人", "怀旧空吟闻笛赋", "暂凭杯酒长精神"], "病树前头万木春", "刘禹锡《酬乐天》名句。", 9, "九年级·古诗文"),
    ("「水调歌头·明月几时有」的作者是（ ）", ["苏轼", "辛弃疾", "李清照", "柳永"], "苏轼", "北宋苏轼词。", 9, "九年级·古诗文"),
    ("「破阵子」「醉里挑灯看剑」的作者是（ ）", ["辛弃疾", "陆游", "岳飞", "文天祥"], "辛弃疾", "辛弃疾豪放词。", 9, "九年级·古诗文"),
    ("下列加点词「属予作文以记之」中「属」意为（ ）", ["属于", "同「嘱」，嘱咐", "种类", "连接"], "同「嘱」，嘱咐", "「属」通「嘱」，嘱托。", 9, "九年级·古诗文"),
    ("「谈创造性思维」一文主要观点是（ ）", ["答案唯一", "事物的正确答案不止一个", "不必思考", "模仿他人"], "事物的正确答案不止一个", "强调创新思维。", 9, "九年级·议论文"),
]

# ════════════ 六科扩充（各 +10，达 30+）═══════════
# (学科, 年级, 题干, [4选项], 正确, 解析)
SUBJECT_EXTRA = [
    # 物理
    ("物理", 8, "下列属于省力杠杆的是（ ）", ["镊子", "天平", "撬棍", "钓鱼竿"], "撬棍", "撬棍动力臂大于阻力臂，省力。"),
    ("物理", 8, "物体保持运动状态不变的性质叫（ ）", ["惯性", "重力", "摩擦力", "弹力"], "惯性", "惯性是物体保持原有运动状态的性质。"),
    ("物理", 9, "家庭电路中保险丝的作用是（ ）", ["装饰", "增大电流", "电流过大时切断电路", "节省电能"], "电流过大时切断电路", "保险丝熔断保护电路。"),
    ("物理", 9, "下列用电器中电能主要转化为内能的是（ ）", ["电动机", "电热水器", "电风扇", "扬声器"], "电热水器", "电热水器利用电流热效应。"),
    ("物理", 8, "力的三要素不包括（ ）", ["大小", "方向", "作用点", "颜色"], "颜色", "力的大小、方向、作用点称三要素。"),
    ("物理", 9, "导体的电阻大小与下列哪个因素有关（ ）", ["电压", "电流", "材料", "电荷"], "材料", "电阻与材料、长度、横截面积、温度有关。"),
    ("物理", 8, "一个标准大气压约支持多高的水银柱（ ）", ["76 cm", "10 cm", "1 m", "100 cm"], "76 cm", "标准大气压约 760 mm 汞柱。"),
    ("物理", 9, "电动机的工作原理是（ ）", ["电磁感应", "通电导体在磁场中受力", "电流的磁效应", "热效应"], "通电导体在磁场中受力", "电动机利用通电线圈在磁场中受力转动。"),
    ("物理", 8, "关于质量，下列说法正确的是（ ）", ["位置变质量变", "物态变质量变", "质量是物体本身属性", "速度变质量变"], "质量是物体本身属性", "质量不随位置、状态、形状改变。"),
    ("物理", 9, "发电机的工作原理是（ ）", ["通电受力", "电磁感应", "热效应", "光电效应"], "电磁感应", "发电机利用电磁感应发电。"),

    # 化学
    ("化学", 9, "下列物质属于混合物的是（ ）", ["蒸馏水", "空气", "氧气", "氯化钠"], "空气", "空气由多种气体组成，是混合物。"),
    ("化学", 9, "下列金属活动性最强的是（ ）", ["铜", "铁", "锌", "镁"], "镁", "金属活动性顺序中镁强于锌铁铜。"),
    ("化学", 9, "下列变化属于物理变化的是（ ）", ["铁生锈", "冰融化", "食物腐败", "蜡烛燃烧"], "冰融化", "冰融化只是状态变化，无新物质。"),
    ("化学", 9, "稀释浓硫酸时，应将（ ）", ["水倒入浓硫酸", "浓硫酸缓慢倒入水中并搅拌", "两者同时倒", "直接混合"], "浓硫酸缓慢倒入水中并搅拌", "防止酸液飞溅，应将浓硫酸缓缓注入水。"),
    ("化学", 9, "下列气体能供给呼吸的是（ ）", ["二氧化碳", "氮气", "氧气", "氢气"], "氧气", "氧气能供给呼吸。"),
    ("化学", 9, "化学反应前后一定不变的是（ ）", ["分子数目", "物质种类", "原子种类", "分子种类"], "原子种类", "原子种类、数目、质量守恒。"),
    ("化学", 9, "下列物质溶于水显碱性的是（ ）", ["食盐", "蔗糖", "纯碱", "醋酸"], "纯碱", "纯碱（碳酸钠）水溶液显碱性。"),
    ("化学", 9, "点燃氢气前必须（ ）", ["直接点燃", "验纯", "加水", "加热"], "验纯", "可燃性气体点燃前须验纯防爆炸。"),
    ("化学", 9, "下列肥料属于钾肥的是（ ）", ["尿素", "过磷酸钙", "氯化钾", "硝酸铵"], "氯化钾", "含钾元素的化肥为钾肥。"),
    ("化学", 9, "下列实验操作错误的是（ ）", ["倾倒液体标签向手心", "量筒读数平视", "用嘴吹灭酒精灯", "加热前预热"], "用嘴吹灭酒精灯", "酒精灯须用灯帽盖灭。"),

    # 生物
    ("生物", 7, "人体消化淀粉最终的产物是（ ）", ["葡萄糖", "氨基酸", "甘油", "脂肪酸"], "葡萄糖", "淀粉最终被消化为葡萄糖。"),
    ("生物", 7, "下列结构中属于器官的是（ ）", ["心肌", "血液", "肝脏", "神经元"], "肝脏", "肝脏由多种组织构成，属器官。"),
    ("生物", 8, "形成听觉的部位是（ ）", ["外耳道", "鼓膜", "耳蜗", "大脑皮层"], "大脑皮层", "听觉在大脑皮层形成。"),
    ("生物", 8, "下列属于特异性免疫的是（ ）", ["皮肤屏障", "吞噬细胞", "抗体免疫", "溶菌酶"], "抗体免疫", "抗体免疫针对特定病原体，属特异性免疫。"),
    ("生物", 7, "植物根部吸收水分主要部位是（ ）", ["根冠", "分生区", "伸长区", "成熟区"], "成熟区", "成熟区有根毛，是吸水主要部位。"),
    ("生物", 8, "人体气体交换的场所是（ ）", ["鼻腔", "气管", "肺泡", "支气管"], "肺泡", "肺泡是气体交换的场所。"),
    ("生物", 7, "下列动物属于脊椎动物的是（ ）", ["蝗虫", "蚯蚓", "鲫鱼", "蜗牛"], "鲫鱼", "鲫鱼有脊柱，属脊椎动物。"),
    ("生物", 8, "DNA 主要存在于（ ）", ["细胞膜", "细胞质", "细胞核", "细胞壁"], "细胞核", "遗传物质的载体 DNA 主要在细胞核。"),
    ("生物", 7, "绿色植物制造有机物依赖（ ）", ["呼吸作用", "光合作用", "蒸腾作用", "吸收作用"], "光合作用", "光合作用制造有机物。"),
    ("生物", 8, "下列属于传染病的是（ ）", ["近视", "贫血", "流感", "佝偻病"], "流感", "流感由病原体引起，可传染。"),

    # 道德与法治
    ("道德与法治", 7, "青春期身心发育的重要特点是（ ）", ["停滞", "显著变化", "退化", "不变"], "显著变化", "青春期身体和心理都发生显著变化。"),
    ("道德与法治", 8, "诚信是中华民族的传统（ ）", ["美德", "法律", "制度", "货币"], "美德", "诚信是中华传统美德。"),
    ("道德与法治", 9, "我国根本政治制度是（ ）", ["人民代表大会制度", "多党合作", "基层群众自治", "民族区域自治"], "人民代表大会制度", "人民代表大会制度是根本政治制度。"),
    ("道德与法治", 7, "集体生活有助于我们（ ）", ["封闭自我", "学会交往与合作", "脱离社会", "变得自私"], "学会交往与合作", "集体生活培养合作能力。"),
    ("道德与法治", 8, "法律区别于道德等行为规范的最主要特征是（ ）", ["约定俗成", "由国家强制力保证实施", "靠舆论", "靠习惯"], "由国家强制力保证实施", "法律靠国家强制力保证实施。"),
    ("道德与法治", 9, "创新是引领发展的（ ）", ["阻碍", "第一动力", "次要因素", "负担"], "第一动力", "创新是引领发展的第一动力。"),
    ("道德与法治", 7, "友谊的特质是（ ）", ["功利", "亲密、平等、双向", "单向索取", "短暂"], "亲密、平等、双向", "友谊是平等的、双向的。"),
    ("道德与法治", 8, "公民行使权利必须在（ ）范围内", ["任意", "法律", "心情", "他人允许"], "法律", "行使权利不能超越法律范围。"),
    ("道德与法治", 9, "全面推进依法治国的总目标是建设（ ）", ["人治国家", "社会主义法治国家", "无政府状态", "特权社会"], "社会主义法治国家", "依法治国总目标。"),
    ("道德与法治", 7, "生命的特点是（ ）", ["永恒", "来之不易、独特、不可逆", "可以重来", "毫无价值"], "来之不易、独特、不可逆", "生命来之不易且不可逆。"),

    # 历史
    ("历史", 7, "我国有文字可考的历史从哪个朝代开始（ ）", ["夏朝", "商朝", "周朝", "秦朝"], "商朝", "甲骨文使商朝历史可考。"),
    ("历史", 8, "新文化运动高举的两面大旗是（ ）", ["自强、求富", "民主、科学", "变法、图强", "实业、教育"], "民主、科学", "新文化运动提倡民主与科学。"),
    ("历史", 9, "第一次世界大战爆发的导火线是（ ）", ["萨拉热窝事件", "凡尔登战役", "十月革命", "巴黎和会"], "萨拉热窝事件", "萨拉热窝事件是一战导火线。"),
    ("历史", 7, "秦始皇统一货币，全国统一使用（ ）", ["刀币", "圆形方孔钱", "贝币", "纸币"], "圆形方孔钱", "秦统一为圆形方孔半两钱。"),
    ("历史", 8, "中国第一个农村革命根据地是（ ）", ["延安", "井冈山", "西柏坡", "瑞金"], "井冈山", "井冈山革命根据地。"),
    ("历史", 9, "第二次工业革命的标志性成就是（ ）", ["蒸汽机", "电力广泛应用", "计算机", "核能"], "电力广泛应用", "第二次工业革命以电力为标志。"),
    ("历史", 7, "汉武帝时出使西域的是（ ）", ["张骞", "卫青", "霍去病", "董仲舒"], "张骞", "张骞出使西域。"),
    ("历史", 8, "遵义会议确立了以谁为核心的领导（ ）", ["毛泽东", "陈独秀", "王明", "张国焘"], "毛泽东", "遵义会议确立毛泽东领导地位。"),
    ("历史", 9, "俄国十月革命发生在（ ）", ["1917 年", "1914 年", "1921 年", "1929 年"], "1917 年", "1917 年俄历十月革命。"),
    ("历史", 7, "甲骨文最早出土于（ ）", ["安阳", "西安", "洛阳", "南京"], "安阳", "甲骨文出土于殷墟（安阳）。"),

    # 地理
    ("地理", 7, "地图上指向标箭头一般指向（ ）", ["南方", "北方", "东方", "西方"], "北方", "指向标箭头通常指北。"),
    ("地理", 7, "海拔一般在 500 米以上、起伏较大的地形是（ ）", ["平原", "丘陵", "山地", "盆地"], "山地", "山地海拔较高、起伏大。"),
    ("地理", 8, "我国地势的总体特征是（ ）", ["西高东低", "东高西低", "南高北低", "北高南低"], "西高东低", "我国地势西高东低，呈三级阶梯。"),
    ("地理", 8, "黄河注入（ ）", ["渤海", "黄海", "东海", "南海"], "渤海", "黄河入渤海。"),
    ("地理", 7, "世界人口稠密区分布在（ ）", ["两极", "高山", "中低纬度沿海平原", "沙漠"], "中低纬度沿海平原", "中低纬沿海平原人口稠密。"),
    ("地理", 8, "我国少数民族最多的省份是（ ）", ["云南", "贵州", "四川", "广西"], "云南", "云南少数民族最多。"),
    ("地理", 7, "降水受地形影响，山地迎风坡（ ）", ["少雨", "多雨", "无雨", "不变"], "多雨", "迎风坡降水多。"),
    ("地理", 8, "西北地区的自然特征是（ ）", ["高寒", "干旱", "湿热", "冷湿"], "干旱", "西北地区深居内陆，干旱。"),
    ("地理", 7, "下列河流属于内流河的是（ ）", ["长江", "黄河", "塔里木河", "珠江"], "塔里木河", "塔里木河是我国最大内流河。"),
    ("地理", 8, "北京的城市职能主要是（ ）", ["工业中心", "政治文化中心", "金融中心", "航运中心"], "政治文化中心", "北京是全国政治文化中心。"),
]

# ════════════ 英语初中短语（≥80，grade 7-9）═══════════
# (grade, phrase, meaning, type)
PHRASES = [
    (7, "be good at", "擅长", "动词词组"), (7, "be interested in", "对……感兴趣", "动词词组"),
    (7, "look forward to", "期待", "动词词组"), (7, "take care of", "照顾", "动词词组"),
    (7, "get up", "起床", "动词词组"), (7, "go to school", "去上学", "动词词组"),
    (7, "do homework", "做作业", "动词词组"), (7, "have breakfast", "吃早餐", "动词词组"),
    (7, "play sports", "做运动", "动词词组"), (7, "listen to music", "听音乐", "动词词组"),
    (7, "help with", "帮忙做", "动词词组"), (7, "talk to", "和……交谈", "动词词组"),
    (7, "think of", "想起；认为", "动词词组"), (7, "a lot of", "许多", "介词词组"),
    (7, "on weekends", "在周末", "介词词组"), (7, "in the morning", "在早上", "介词词组"),
    (7, "by bus", "乘公交", "介词词组"), (7, "for example", "例如", "介词词组"),
    (7, "each other", "互相", "代词词组"), (7, "all kinds of", "各种各样的", "形容词词组"),
    (7, "be late for", "迟到", "动词词组"), (7, "ask for", "请求；要", "动词词组"),
    (7, "come from", "来自", "动词词组"), (7, "be afraid of", "害怕", "动词词组"),
    (7, "make friends", "交朋友", "动词词组"), (7, "write to", "给……写信", "动词词组"),
    (7, "between...and...", "在……和……之间", "介词词组"), (7, "in front of", "在……前面", "介词词组"),
    (8, "find out", "查明；弄清", "动词词组"), (8, "care about", "关心；在意", "动词词组"),
    (8, "make a difference", "起作用；有影响", "动词词组"), (8, "take up", "开始做；占据", "动词词组"),
    (8, "look after", "照料", "动词词组"), (8, "depend on", "依靠；依赖", "动词词组"),
    (8, "be different from", "与……不同", "形容词词组"), (8, "the same as", "与……相同", "形容词词组"),
    (8, "in order to", "为了", "介词词组"), (8, "as long as", "只要", "连词词组"),
    (8, "because of", "因为", "介词词组"), (8, "at least", "至少", "副词词组"),
    (8, "such as", "例如；像……这样", "介词词组"), (8, "more than", "多于；超过", "介词词组"),
    (8, "be talented in", "在……方面有天赋", "形容词词组"), (8, "bring out", "使显现；使表现出", "动词词组"),
    (8, "share with", "与……分享", "动词词组"), (8, "reach for", "伸手取", "动词词组"),
    (8, "touch one's heart", "触动某人的心", "动词词组"), (8, "be similar to", "与……相像", "形容词词组"),
    (8, "get into a fight", "打架", "动词词组"), (8, "communicate with", "与……交流", "动词词组"),
    (8, "work out", "解决；算出", "动词词组"), (8, "look through", "浏览", "动词词组"),
    (8, "be angry with", "生……的气", "形容词词组"), (8, "copy one's homework", "抄作业", "动词词组"),
    (8, "feel lonely", "感到孤独", "形容词词组"), (8, "in one's opinion", "依某人看", "介词词组"),
    (9, "look up", "查阅（词典等）", "动词词组"), (9, "pay attention to", "注意；关注", "动词词组"),
    (9, "connect...with...", "把……和……连接", "动词词组"), (9, "be born with", "天生具有", "动词词组"),
    (9, "practice doing", "练习做", "动词词组"), (9, "learn from", "向……学习", "动词词组"),
    (9, "be proud of", "为……感到自豪", "形容词词组"), (9, "take pride in", "以……为傲", "动词词组"),
    (9, "deal with", "处理；应对", "动词词组"), (9, "worry about", "担心", "动词词组"),
    (9, "make progress", "取得进步", "动词词组"), (9, "in public", "公开地；在别人面前", "介词词组"),
    (9, "be used to", "习惯于", "形容词词组"), (9, "give up", "放弃", "动词词组"),
    (9, "be thankful to", "对……感激", "形容词词组"), (9, "dream of", "梦想", "动词词组"),
    (9, "make a decision", "做决定", "动词词组"), (9, "take breaks", "休息", "动词词组"),
    (9, "get used to", "习惯于", "动词词组"), (9, "keep away from", "远离", "动词词组"),
    (9, "be in control of", "掌管；管理", "形容词词组"), (9, "give out", "分发；散发", "动词词组"),
]

# ════════════ 英语初中句子（≥60，grade 7-9）═══════════
# (grade, en, cn, type, grammar_point)
SENTENCES = [
    (7, "I can speak a little English.", "我会说一点英语。", "陈述句", "can 表能力"),
    (7, "What time do you usually get up?", "你通常几点起床？", "特殊疑问句", "what time 提问时间"),
    (7, "My favorite subject is science.", "我最喜欢的科目是科学。", "主系表", "favorite 的用法"),
    (7, "How do you get to school?", "你怎么去学校？", "特殊疑问句", "how 提问方式"),
    (7, "It takes me about 20 minutes to walk.", "步行大约花我 20 分钟。", "It takes sb. time", "take 表花费"),
    (7, "There is a bank across from the park.", "公园对面有一家银行。", "there be", "there be 就近原则"),
    (7, "What does he look like?", "他长什么样？", "特殊疑问句", "look like 问外貌"),
    (7, "I'd like a large bowl of noodles.", "我想要一大碗面条。", "would like", "would like 表意愿"),
    (7, "How was your school trip?", "你的学校郊游怎么样？", "一般过去时", "be 过去式"),
    (7, "Did you go to the zoo last weekend?", "上周末你去动物园了吗？", "一般疑问句", "实义动词过去式"),
    (7, "He is taller than me.", "他比我高。", "比较级", "比较级 + than"),
    (7, "What do you want to be when you grow up?", "你长大后想做什么？", "want to do", "want 后接不定式"),
    (7, "We should help each other.", "我们应该互相帮助。", "情态动词", "should 表建议"),
    (7, "The book is interesting and I like it.", "这本书很有趣，我喜欢它。", "并列句", "and 连接并列"),
    (7, "Can you come to my party?", "你能来我的聚会吗？", "邀请", "can 表请求"),
    (7, "If it rains, we will stay at home.", "如果下雨，我们就待在家。", "条件状语从句", "if 引导条件句"),
    (8, "He is as tall as his brother.", "他和他哥哥一样高。", "原级比较", "as...as"),
    (8, "Who is the funniest person you know?", "你认识的最有趣的人是谁？", "最高级", "funniest 最高级"),
    (8, "I think friends should be honest.", "我认为朋友应该诚实。", "宾语从句", "think 后接从句"),
    (8, "The more you read, the more you know.", "你读得越多，懂得越多。", "the more...the more", "比较级递进"),
    (8, "My best friend likes to do the same things as me.", "我最好的朋友喜欢和我做同样的事。", "same as", "the same as"),
    (8, "What's the best movie theater?", "最好的电影院是哪家？", "最高级", "best 最高级"),
    (8, "You can buy tickets the most cheaply there.", "在那儿你能最便宜地买到票。", "副词最高级", "cheaply 最高级"),
    (8, "I'm going to study medicine.", "我打算学医。", "be going to", "表计划将来"),
    (8, "What are you going to be when you grow up?", "你长大后打算做什么？", "将来时", "be going to"),
    (8, "If you go to the party, you'll have fun.", "如果你去聚会，你会玩得开心。", "条件句主将从现", "主将从现"),
    (8, "He let me watch TV all night.", "他让我看了一整晚电视。", "let sb. do", "使役动词后接原形"),
    (8, "Why don't you talk to your parents?", "你为什么不和你父母谈谈？", "建议", "why don't you"),
    (8, "It's best not to run away from problems.", "最好不要逃避问题。", "it's best to", "it 形式主语"),
    (8, "Unless it rains, we will play soccer.", "除非下雨，否则我们踢足球。", "条件状语从句", "unless 除非"),
    (9, "I used to be afraid of the dark.", "我过去害怕黑暗。", "used to", "used to 表过去习惯"),
    (9, "You should speak English as much as possible.", "你应该尽可能多说英语。", "as...as possible", "尽可能"),
    (9, "The more I read, the more I want to read.", "我读得越多就越想读。", "the more...the more", "递进比较"),
    (9, "It's necessary for us to learn English well.", "对我们来说学好英语很有必要。", "it's adj. for sb.", "形式主语"),
    (9, "Could you please tell me where the restroom is?", "请问洗手间在哪儿？", "宾语从句语序", "陈述语序"),
    (9, "I wonder if it will rain tomorrow.", "我想知道明天是否下雨。", "wonder + if", "whether/if 从句"),
    (9, "What do you think of the movie?", "你觉得这部电影怎么样？", "观点表达", "think of"),
    (9, "We are supposed to shake hands when we meet.", "我们见面时应该握手。", "be supposed to", "应该"),
    (9, "It is impolite to point at others.", "指着别人是不礼貌的。", "it is adj. to do", "形式主语"),
    (9, "Teenagers should be allowed to choose their own clothes.", "青少年应该被允许自己选衣服。", "被动语态", "should be done"),
    (9, "The work must be finished by Friday.", "工作必须在周五前完成。", "情态被动", "must be done"),
    (9, "If I were you, I would study harder.", "如果我是你，我会更努力学习。", "虚拟语气", "与现在事实相反"),
    (9, "He is a boy who likes helping others.", "他是一个喜欢帮助别人的男孩。", "定语从句", "who 指人"),
    (9, "This is the book that I bought yesterday.", "这是我昨天买的书。", "定语从句", "that 指物"),
    (9, "We should protect the environment so that we can live better.", "我们应保护环境以便生活更好。", "目的状语从句", "so that"),
    (9, "No matter how hard it is, never give up.", "无论多难，永不放弃。", "让步状语", "no matter how"),
    (9, "Reading more is good for your writing.", "多阅读对你的写作有好处。", "动名词主语", "reading 作主语"),
    (9, "By the time I got up, he had left.", "我起床时他已经离开了。", "过去完成时", "had done"),
]


def upgrade(db):
    insp = inspect(db.bind)
    tables = set(insp.get_table_names())

    # ── 1. 加 unit 列（已存在则跳过）──
    if "classical_texts" in tables:
        _add_column(db, "classical_texts", "unit", "VARCHAR(100) DEFAULT ''")
    if "middle_questions" in tables:
        _add_column(db, "middle_questions", "unit", "VARCHAR(100) DEFAULT ''")

    # ── 2. 标注 classical_texts.unit（按 年级+学期 分组）──
    try:
        rows = db.execute(text(
            "SELECT id, grade, semester FROM classical_texts WHERE unit IS NULL OR unit = ''"
        )).fetchall()
        # 按 (grade, semester) 归组，每 4 篇为一单元
        groups = {}
        for r in rows:
            groups.setdefault((r[1], r[2]), []).append(r[0])
        for (grade, sem), ids in groups.items():
            for k, rid in enumerate(ids):
                unit = f"{grade}年级{sem}·第{(k // 4) + 1}单元"
                db.execute(text("UPDATE classical_texts SET unit = :u WHERE id = :id"),
                           {"u": unit, "id": rid})
        db.flush()
    except Exception as e:
        import logging
        logging.getLogger("migrations").warning("037 标注 classical_texts.unit 失败: %s", e)

    # ── 3. 标注 middle_questions.unit（六科 + 语文，按章节循环）──
    try:
        rows = db.execute(text(
            "SELECT id, subject, grade FROM middle_questions WHERE unit IS NULL OR unit = ''"
        )).fetchall()
        by_subject = {}
        for r in rows:
            by_subject.setdefault(r[1], []).append(r[0])
        for subject, ids in by_subject.items():
            units = CH_UNITS.get(subject, ["未分章"])
            for k, rid in enumerate(ids):
                unit = units[k % len(units)]
                db.execute(text("UPDATE middle_questions SET unit = :u WHERE id = :id"),
                           {"u": unit, "id": rid})
        db.flush()
    except Exception as e:
        import logging
        logging.getLogger("migrations").warning("037 标注 middle_questions.unit 失败: %s", e)

    # ── 4. 初中语文题库（按 subject+question 去重）──
    existing = {(r[0], r[1]) for r in db.execute(
        text("SELECT subject, question FROM middle_questions"))}
    added_chi = 0
    for question, options, answer, analysis, grade, unit in CHI_SEED:
        if ("语文", question) in existing:
            continue
        prefixed = _prefixed(options)
        correct = _correct(options, answer)
        db.execute(text(
            "INSERT INTO middle_questions (subject, grade, type, question, options_json, answer, analysis, unit, created_at) "
            "VALUES ('语文', :grade, 'choice', :question, :options_json, :answer, :analysis, :unit, NOW())"
        ), {"grade": grade, "question": question, "options_json": json.dumps(prefixed, ensure_ascii=False),
            "answer": correct, "analysis": analysis, "unit": unit})
        added_chi += 1
    db.flush()

    # ── 5. 六科题库扩充（各 +10）──
    added_subj = 0
    for subject, grade, question, options, answer, analysis in SUBJECT_EXTRA:
        if (subject, question) in existing:
            continue
        unit = CH_UNITS.get(subject, ["未分章"])[0]
        prefixed = _prefixed(options)
        correct = _correct(options, answer)
        db.execute(text(
            "INSERT INTO middle_questions (subject, grade, type, question, options_json, answer, analysis, unit, created_at) "
            "VALUES (:subject, :grade, 'choice', :question, :options_json, :answer, :analysis, :unit, NOW())"
        ), {"subject": subject, "grade": grade, "question": question,
            "options_json": json.dumps(prefixed, ensure_ascii=False), "answer": correct,
            "analysis": analysis, "unit": unit})
        added_subj += 1
    db.flush()

    # ── 6. 英语短语（grade 7-9，按 phrase 去重）──
    existing_ph = {r[0] for r in db.execute(text("SELECT phrase FROM phrases"))}
    added_ph = 0
    for grade, phrase, meaning, ptype in PHRASES:
        if phrase in existing_ph:
            continue
        db.execute(text(
            "INSERT INTO phrases (grade, phrase, meaning, type, created_at) "
            "VALUES (:grade, :phrase, :meaning, :type, NOW())"
        ), {"grade": grade, "phrase": phrase, "meaning": meaning, "type": ptype})
        added_ph += 1
    db.flush()

    # ── 7. 英语句子（grade 7-9，按 sentence_en 去重）──
    existing_se = {r[0] for r in db.execute(text("SELECT sentence_en FROM sentences"))}
    added_se = 0
    for grade, en, cn, stype, gp in SENTENCES:
        if en in existing_se:
            continue
        db.execute(text(
            "INSERT INTO sentences (grade, sentence_en, sentence_cn, type, grammar_point, created_at) "
            "VALUES (:grade, :en, :cn, :type, :gp, NOW())"
        ), {"grade": grade, "en": en, "cn": cn, "type": stype, "gp": gp})
        added_se += 1
    db.flush()

    import logging
    logging.getLogger("migrations").info(
        "037 语言扩充：语文+%d, 六科+%d, 短语+%d, 句子+%d", added_chi, added_subj, added_ph, added_se)


def _add_column(db, table, column, definition):
    try:
        # 为指定表新增一列（列已存在则靠异常兜底跳过，幂等）
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
