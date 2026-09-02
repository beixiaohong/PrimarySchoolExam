"""种子数据 · 英语语法知识点与配套练习（GrammarPoint / GrammarExercise）

幂等：表内已有数据则直接跳过（`count() > 0` 即 return），可随每次启动安全重跑，
由 `init_data/core.py` 的 `ensure_initial_data()` 统一调用。
"""
import csv
import os
from pathlib import Path

from app.database import SessionLocal
from app.models.word import Word, WordBook
from app.models.phrase import Phrase, Sentence
from app.models.problem_type import ProblemType, ProblemCategory
from app.models.grammar import GrammarPoint, GrammarExercise
from app.config import WORD_CSV_PATH, MIDDLE_WORD_CSV_PATH, DATA_DIR

def _seed_grammar(db):
    """初始化英语语法练习数据"""
    if db.query(GrammarPoint).count() > 0:
        return

    
    grammar_data = [
        {
            "name": "一般现在时", "code": "simple_present", "grade": 3, "category": "时态",
            "description": "表示经常性、习惯性的动作或状态。主语第三人称单数时动词加s/es。",
            "examples": "I go to school every day.\nShe likes apples.\nThey play football after school.",
            "exercises": [
                ("choice", 3, 1, "He ______ to school every day.", '[ "go", "goes", "going", "went" ]', "B", "主语He是第三人称单数，动词go要加es变成goes。"),
                ("choice", 3, 1, "She ______ milk very much.", '[ "like", "likes", "liking", "liked" ]', "B", "主语She是第三人称单数，like要加s。"),
                ("fill", 3, 1, "I ______ (read) books every evening.", "", "read", "主语I是第一人称，动词用原形read。"),
                ("fill", 4, 2, "My mother ______ (cook) dinner at six every day.", "", "cooks", "My mother是第三人称单数，cook加s。"),
                ("fill", 4, 2, "The sun ______ (rise) in the east.", "", "rises", "The sun是第三人称单数，rise加s。"),
                ("choice", 4, 2, "______ your father ______ a car?", '[ "Do, drive", "Does, drive", "Does, drives", "Do, drives" ]', "B", "一般现在时的疑问句，主语your father用Does引导，动词用原形。"),
                ("fill", 4, 2, "Tom ______ (not, like) swimming.", "", "doesn't like", "否定句用doesn't + 动词原形。"),
                ("choice", 5, 3, "Water ______ at 100 degrees.", '[ "boil", "boils", "boiling", "is boil" ]', "B", "Water是第三人称单数，表示客观事实用一般现在时。"),
                ("transform", 5, 3, "She goes to bed at nine. (改为否定句)", "", "She doesn't go to bed at nine.", "第三人称否定用doesn't + 动词原形。"),
                ("fill", 5, 3, "______ he ______ (speak) English?", "", "Does; speak", "一般现在时疑问句：Does + 主语 + 动词原形。"),
            ],
        },
        {
            "name": "现在进行时", "code": "present_continuous", "grade": 4, "category": "时态",
            "description": "表示正在进行的动作。构成：be(am/is/are) + 动词ing。",
            "examples": "I am reading a book.\nShe is singing a song.\nThey are playing games.",
            "exercises": [
                ("choice", 4, 1, "Look! The children ______ in the park.", '[ "play", "plays", "are playing", "is playing" ]', "C", "Look!提示正在发生，children是复数用are playing。"),
                ("choice", 4, 1, "— What are you doing? — I ______ a letter.", '[ "write", "writes", "am writing", "is writing" ]', "C", "I搭配am，write去e加ing。"),
                ("fill", 4, 1, "She ______ (dance) in the room now.", "", "is dancing", "She搭配is，dance去e加ing。"),
                ("fill", 4, 2, "Listen! Someone ______ (sing) upstairs.", "", "is singing", "Listen!提示正在进行，sing直接加ing。"),
                ("choice", 5, 2, "We ______ an English lesson at the moment.", '[ "have", "has", "are having", "is having" ]', "C", "at the moment提示进行时，We用are having。"),
                ("fill", 5, 2, "The dog ______ (run) after the cat now.", "", "is running", "run双写n加ing。"),
                ("transform", 5, 3, "He is watching TV. (改为一般疑问句)", "", "Is he watching TV?", "将be动词is提到主语前面。"),
                ("choice", 5, 3, "______ they ______ football now?", '[ "Are, playing", "Are, play", "Do, playing", "Is, playing" ]', "A", "now提示进行时，they用Are，动词加ing。"),
                ("fill", 3, 1, "I ______ (do) my homework now.", "", "am doing", "I搭配am，do直接加ing。"),
                ("fill", 5, 3, "The baby ______ (sleep). Don't be noisy.", "", "is sleeping", "表示正在进行用is + sleeping。"),
            ],
        },
        {
            "name": "一般过去时", "code": "simple_past", "grade": 5, "category": "时态",
            "description": "表示过去发生的动作或状态。规则动词加ed，不规则动词需记忆过去式。",
            "examples": "I visited my grandma yesterday.\nShe went to the park last Sunday.\nThey watched TV last night.",
            "exercises": [
                ("choice", 5, 1, "I ______ my homework last night.", '[ "do", "does", "did", "doing" ]', "C", "last night提示过去时，do的过去式是did。"),
                ("choice", 5, 1, "She ______ to the zoo yesterday.", '[ "go", "goes", "went", "going" ]', "C", "yesterday提示过去时，go的过去式是went。"),
                ("fill", 5, 1, "We ______ (visit) the museum last week.", "", "visited", "last week提示过去时，visit加ed。"),
                ("fill", 5, 2, "He ______ (buy) a new book yesterday.", "", "bought", "buy的过去式是bought（不规则变化）。"),
                ("choice", 5, 2, "They ______ a good time last weekend.", '[ "have", "has", "had", "having" ]', "C", "last weekend提示过去时，have的过去式是had。"),
                ("fill", 5, 2, "My mother ______ (make) a cake last Sunday.", "", "made", "make的过去式是made。"),
                ("choice", 6, 3, "______ you ______ the film last night?", '[ "Do, see", "Does, see", "Did, see", "Did, saw" ]', "C", "过去时疑问句用Did + 主语 + 动词原形。"),
                ("transform", 6, 3, "She cleaned her room yesterday. (改为否定句)", "", "She didn't clean her room yesterday.", "过去时否定用didn't + 动词原形。"),
                ("fill", 6, 3, "The children ______ (not, go) to school last Monday.", "", "didn't go", "过去时否定用didn't + 动词原形。"),
                ("choice", 6, 3, "He ______ his keys on the bus yesterday.", '[ "leave", "leaves", "left", "leaving" ]', "C", "leave的过去式是left。"),
            ],
        },
        {
            "name": "一般将来时", "code": "simple_future", "grade": 5, "category": "时态",
            "description": "表示将要发生的动作。构成：will + 动词原形 或 be going to + 动词原形。",
            "examples": "I will go to Beijing tomorrow.\nShe is going to be a teacher.\nWe will have a party next week.",
            "exercises": [
                ("choice", 5, 1, "I ______ visit my grandparents next weekend.", '[ "will", "am", "did", "do" ]', "A", "next weekend提示将来时，用will + 动词原形。"),
                ("choice", 5, 1, "She ______ going to buy a new dress.", '[ "will", "is", "was", "does" ]', "B", "be going to结构，She搭配is。"),
                ("fill", 5, 2, "We ______ (have) a picnic tomorrow if it's fine.", "", "will have", "tomorrow提示将来时，用will + 动词原形。"),
                ("fill", 5, 2, "They ______ (not, come) to the party next Friday.", "", "won't come", "将来时否定：will not(won't) + 动词原形。"),
                ("choice", 6, 2, "— There's no milk left.\n— Really? I ______ go and buy some.", '[ "will", "am going to", "am", "do" ]', "A", "临时决定用will。"),
                ("choice", 6, 3, "Look at those clouds! It ______ rain.", '[ "will", "is going to", "is", "does" ]', "B", "根据迹象判断将要发生的事用be going to。"),
                ("transform", 6, 3, "He will finish the work tomorrow. (改为否定句)", "", "He won't finish the work tomorrow.", "will的否定：will not = won't。"),
                ("fill", 6, 3, "______ you ______ (help) me with this box?", "", "Will; help", "将来时疑问句：Will + 主语 + 动词原形。"),
            ],
        },
        {
            "name": "名词单复数", "code": "noun_plural", "grade": 3, "category": "词法",
            "description": "名词变复数的规则：一般加s；以s/x/sh/ch结尾加es；辅音+y变y为i加es；以f/fe结尾变f/fe为v加es。",
            "examples": "book → books\nbox → boxes\nbaby → babies\nknife → knives",
            "exercises": [
                ("fill", 3, 1, "one book — two ______", "", "books", "一般名词加s。"),
                ("fill", 3, 1, "one box — three ______", "", "boxes", "以x结尾加es。"),
                ("fill", 3, 1, "one baby — four ______", "", "babies", "辅音字母+y，变y为i加es。"),
                ("fill", 4, 2, "one knife — two ______", "", "knives", "以fe结尾，变fe为v加es。"),
                ("fill", 4, 2, "one bus — five ______", "", "buses", "以s结尾加es。"),
                ("choice", 4, 2, "There are many ______ on the farm.", '[ "sheep", "sheeps", "sheepes", "a sheep" ]', "A", "sheep单复数同形。"),
                ("choice", 4, 2, "I can see three ______ in the sky.", '[ "child", "childs", "children", "childrens" ]', "C", "child的复数是不规则变化children。"),
                ("fill", 5, 3, "one foot — two ______", "", "feet", "foot的复数是feet（不规则变化）。"),
                ("fill", 5, 3, "one man — ten ______", "", "men", "man的复数是men。"),
                ("choice", 5, 3, "We need some ______ for the salad.", '[ "tomato", "tomatos", "tomatoes", "a tomato" ]', "C", "tomato以o结尾加es。some后接复数。"),
            ],
        },
        {
            "name": "形容词比较级与最高级", "code": "comparative", "grade": 4, "category": "词法",
            "description": "比较级：短形容词加er/ier，长形容词前加more。最高级：短形容词加est/iest，长形容词前加most。",
            "examples": "tall → taller → the tallest\nbeautiful → more beautiful → the most beautiful\nbig → bigger → the biggest",
            "exercises": [
                ("fill", 4, 1, "Tom is ______ (tall) than Jerry.", "", "taller", "tall加er构成比较级。"),
                ("fill", 4, 1, "This book is ______ (interesting) than that one.", "", "more interesting", "interesting是多音节词，比较级前加more。"),
                ("choice", 4, 2, "She is the ______ girl in our class.", '[ "tall", "taller", "tallest", "more tall" ]', "C", "the后面用最高级，tall加est。"),
                ("fill", 5, 2, "Running is ______ (fast) than walking.", "", "faster", "fast加er构成比较级。"),
                ("choice", 5, 2, "Which season do you like ______?", '[ "good", "better", "best", "well" ]', "B", "两者之间比较用比较级better。"),
                ("fill", 5, 3, "This is the ______ (beautiful) park I've ever seen.", "", "most beautiful", "beautiful是多音节词，最高级前加most。"),
                ("fill", 4, 2, "My bag is ______ (heavy) than yours.", "", "heavier", "辅音+y结尾，变y为i加er。"),
                ("choice", 6, 3, "He is the ______ student in the school.", '[ "good", "better", "best", "well" ]', "C", "good的最高级是best。"),
                ("fill", 5, 3, "Today is ______ (hot) than yesterday.", "", "hotter", "hot双写t加er。"),
            ],
        },
        {
            "name": "There be 句型", "code": "there_be", "grade": 3, "category": "句型",
            "description": "表示'某处有某物'。be的形式由后面最近的名词决定：单数/不可数用is，复数用are。",
            "examples": "There is a book on the desk.\nThere are some birds in the tree.\nThere isn't any water in the bottle.",
            "exercises": [
                ("choice", 3, 1, "There ______ a cat under the chair.", '[ "is", "are", "am", "be" ]', "A", "a cat是单数，用is。"),
                ("choice", 3, 1, "There ______ some milk in the glass.", '[ "is", "are", "am", "be" ]', "A", "milk是不可数名词，用is。"),
                ("fill", 3, 1, "There ______ (be) three books on the desk.", "", "are", "three books是复数，用are。"),
                ("choice", 4, 2, "There ______ any pencils in the box?", '[ "is", "are", "Are there", "Is there" ]', "C", "pencils是复数，疑问句用Are there。"),
                ("fill", 4, 2, "There ______ (not, be) any water in the bottle.", "", "isn't", "water不可数，否定用isn't。"),
                ("choice", 5, 2, "There ______ a pen and two books on the desk.", '[ "is", "are", "am", "be" ]', "A", "就近原则：a pen是单数，用is。"),
                ("fill", 5, 3, "There ______ (be) going to be a meeting tomorrow.", "", "is", "there be的将来时：there is/are going to be。meeting单数用is。"),
                ("choice", 5, 3, "There ______ some bread and eggs on the plate.", '[ "is", "are", "am", "have" ]', "A", "就近原则：bread不可数，用is。"),
            ],
        },
        {
            "name": "情态动词", "code": "modal_verbs", "grade": 4, "category": "词法",
            "description": "情态动词(can/could/may/must/should)后接动词原形，表示能力、许可、义务、建议等。",
            "examples": "I can swim.\nYou must finish your homework.\nShould I open the window?",
            "exercises": [
                ("choice", 4, 1, "I ______ swim very well.", '[ "can", "am", "do", "have" ]', "A", "can表示能力，后接动词原形。"),
                ("choice", 4, 1, "You ______ wash your hands before meals.", '[ "can", "must", "may", "would" ]', "B", "must表示必须，饭前洗手是必须的。"),
                ("fill", 4, 2, "______ I use your pen? (表示请求)", "", "May", "May I...? 表示礼貌地请求许可。"),
                ("fill", 5, 2, "You ______ (not, run) in the classroom. It's dangerous.", "", "mustn't", "mustn't表示禁止，教室里不能跑。"),
                ("choice", 5, 2, "She ______ speak three languages.", '[ "can", "must", "should", "may" ]', "A", "can表示能力，会说三种语言。"),
                ("choice", 5, 3, "You look tired. You ______ go to bed early.", '[ "can", "must", "should", "may" ]', "C", "should表示建议，你看起来累了应该早睡。"),
                ("fill", 6, 3, "______ you help me, please? (请求)", "", "Could", "Could you...? 比Can更礼貌地请求。"),
                ("choice", 6, 3, "He ______ be at home. His car is in the garage.", '[ "can", "must", "should", "may" ]', "B", "must表示肯定的推测，车在车库所以他一定在家。"),
            ],
        },
        {
            "name": "疑问句", "code": "question_forms", "grade": 3, "category": "句型",
            "description": "特殊疑问句用疑问词(what/where/when/who/why/how)开头，一般疑问句用do/does/is/are/can开头。",
            "examples": "What is your name?\nWhere do you live?\nCan you help me?\nHow old are you?",
            "exercises": [
                ("choice", 3, 1, "— ______ is your name? — My name is Tom.", '[ "What", "Where", "Who", "How" ]', "A", "问名字用What。"),
                ("choice", 3, 1, "— ______ do you live? — In Beijing.", '[ "What", "Where", "Who", "How" ]', "B", "问地点用Where。"),
                ("fill", 3, 1, "— ______ old are you? — I'm ten.", "", "How", "问年龄用How old。"),
                ("choice", 4, 2, "— ______ does she go to school? — By bus.", '[ "What", "Where", "How", "Who" ]', "C", "问交通方式用How。"),
                ("fill", 4, 2, "— ______ is the weather like today? — It's sunny.", "", "What", "What is ... like? 询问……怎么样。"),
                ("choice", 4, 2, "— ______ are you crying? — Because I lost my toy.", '[ "What", "Where", "Why", "How" ]', "C", "问原因用Why，回答用Because。"),
                ("fill", 5, 3, "— ______ many apples are there? — There are five.", "", "How", "How many + 复数名词，问数量。"),
                ("choice", 5, 3, "— ______ is your birthday? — It's on May 1st.", '[ "What", "When", "Where", "How" ]', "B", "问日期/时间用When。"),
                ("fill", 6, 3, "— ______ much is this shirt? — It's 50 yuan.", "", "How", "How much问价格。"),
            ],
        },
        {
            "name": "介词", "code": "prepositions", "grade": 3, "category": "词法",
            "description": "常用介词：in(在…里面), on(在…上面), under(在…下面), behind(在…后面), next to(在…旁边), between(在…之间)。",
            "examples": "The cat is under the table.\nThe book is on the desk.\nShe sits between Tom and Jerry.",
            "exercises": [
                ("choice", 3, 1, "The ball is ______ the box.", '[ "in", "on", "at", "to" ]', "A", "球在盒子里面用in。"),
                ("choice", 3, 1, "There is a picture ______ the wall.", '[ "in", "on", "at", "under" ]', "B", "画挂在墙上用on。"),
                ("fill", 3, 1, "The cat is hiding ______ the table.", "", "under", "猫躲在桌子下面用under。"),
                ("choice", 4, 2, "I sit ______ Lily ______ Lucy.", '[ "between, and", "between, or", "in, and", "next, and" ]', "A", "between...and... 在…和…之间。"),
                ("fill", 4, 2, "The school is next ______ the park.", "", "to", "next to 在…旁边。"),
                ("choice", 4, 2, "We usually have lunch ______ noon.", '[ "in", "on", "at", "by" ]', "C", "at noon 在中午。"),
                ("fill", 5, 3, "My birthday is ______ May.", "", "in", "月份前用介词in。"),
                ("choice", 5, 3, "He was born ______ July 4th.", '[ "in", "on", "at", "by" ]', "B", "具体日期前用on。"),
                ("fill", 5, 3, "I get up ______ 7 o'clock.", "", "at", "具体时间点前用at。"),
                ("choice", 6, 3, "We often play basketball ______ the afternoon.", '[ "in", "on", "at", "by" ]', "A", "in the afternoon/morning/evening。"),
            ],
        },
        {
            "name": "冠词", "code": "articles", "grade": 3, "category": "词法",
            "description": "a用于辅音开头的词前，an用于元音开头的词前，the用于特指或上文提到过的事物。",
            "examples": "a book, a dog\nan apple, an egg\nthe sun, the moon",
            "exercises": [
                ("choice", 3, 1, "I have ______ apple.", '[ "a", "an", "the", "/" ]', "B", "apple以元音音素开头，用an。"),
                ("choice", 3, 1, "She is ______ honest girl.", '[ "a", "an", "the", "/" ]', "B", "honest的h不发音，以元音音素开头，用an。"),
                ("fill", 3, 1, "There is ______ bird in the tree.", "", "a", "bird以辅音开头，用a。"),
                ("choice", 4, 2, "______ sun rises in the east.", '[ "A", "An", "The", "/" ]', "C", "太阳是独一无二的事物，用the。"),
                ("fill", 4, 2, "He wants to be ______ engineer.", "", "an", "engineer以元音音素开头，用an。"),
                ("choice", 4, 2, "I saw ______ interesting film yesterday.", '[ "a", "an", "the", "/" ]', "B", "interesting以元音音素开头，用an。"),
                ("fill", 5, 3, "Please close ______ door behind you.", "", "the", "特指你身后的那扇门，用the。"),
                ("choice", 5, 3, "He plays ______ piano every day.", '[ "a", "an", "the", "/" ]', "C", "乐器前用the：play the piano/guitar/violin。"),
                ("fill", 5, 3, "She goes to ______ school by bike.", "", "/", "go to school是固定搭配，school前不加冠词。"),
            ],
        },
        {
            "name": "代词", "code": "pronouns", "grade": 4, "category": "词法",
            "description": "人称代词：I/you/he/she/it/we/they；物主代词：my/your/his/her/its/our/their；名词性物主代词：mine/yours/his/hers/ours/theirs。",
            "examples": "I am a student. My name is Tom.\nThis is her book. That book is hers.\nThey are my friends.",
            "exercises": [
                ("choice", 4, 1, "This is ______ book. (我)", '[ "I", "me", "my", "mine" ]', "C", "修饰名词book用形容词性物主代词my。"),
                ("choice", 4, 1, "______ are good friends. (我们)", '[ "Our", "Us", "We", "Ours" ]', "C", "作主语用主格代词We。"),
                ("fill", 4, 2, "Is this ______ pen? (你的)", "", "your", "修饰名词pen用形容词性物主代词your。"),
                ("choice", 5, 2, "The red bag is ______. (她的)", '[ "she", "her", "hers", "herself" ]', "C", "后面没有名词，用名词性物主代词hers。"),
                ("fill", 5, 2, "______ dog is very cute. (他们的)", "", "Their", "修饰名词dog用形容词性物主代词Their。"),
                ("choice", 5, 3, "Give ______ some water, please. (他)", '[ "he", "him", "his", "himself" ]', "B", "作宾语用宾格代词him。"),
                ("fill", 6, 3, "The cat is licking ______ paws. (它)", "", "its", "修饰名词paws用形容词性物主代词its（注意不加'）。"),
                ("choice", 6, 3, "This dictionary is ______. (我的)", '[ "I", "me", "my", "mine" ]', "D", "后面没有名词，用名词性物主代词mine。"),
            ],
        },
    ]

    for gp_data in grammar_data:
        point = GrammarPoint(
            name=gp_data["name"],
            code=gp_data["code"],
            grade=gp_data["grade"],
            category=gp_data["category"],
            description=gp_data["description"],
            examples=gp_data["examples"],
        )
        db.add(point)
        db.flush()

        for ex_type, grade, diff, question, options, answer, explanation in gp_data["exercises"]:
            exercise = GrammarExercise(
                grammar_point_id=point.id,
                grade=grade,
                exercise_type=ex_type,
                question=question,
                options=options,
                answer=answer,
                explanation=explanation,
                difficulty=diff,
            )
            db.add(exercise)

    db.commit()

MIDDLE_GRAMMAR_DATA = [
    {
        "name": "现在完成时", "code": "present_perfect", "grade": 8, "category": "时态",
        "description": "表示过去发生的动作对现在造成的影响，或从过去持续到现在的状态。构成：have/has + 过去分词。常与 already/yet/just/ever/never/for/since 连用。",
        "examples": "I have finished my homework.\nShe has lived here since 2015.\nHave you ever been to Beijing?",
        "exercises": [
            ("choice", 8, 1, "I ______ my homework already.", '[ "finish", "finished", "have finished", "am finishing" ]', "C", "already提示现在完成时，用have + 过去分词。"),
            ("choice", 8, 1, "She ______ in this city since 2018.", '[ "lives", "lived", "has lived", "is living" ]', "C", "since + 时间点用现在完成时，She用has lived。"),
            ("fill", 8, 2, "He ______ just ______ (leave) the office.", "", "has; left", "just提示现在完成时，He用has + left。"),
            ("choice", 8, 2, "______ you ever ______ sushi?", '[ "Do, eat", "Have, eaten", "Did, eat", "Are, eating" ]', "B", "ever用于现在完成时疑问句：Have + 主语 + 过去分词。"),
            ("fill", 9, 3, "They ______ (not, see) the film yet.", "", "haven't seen", "yet用于否定句，现在完成时：haven't + 过去分词。"),
            ("choice", 9, 3, "He has been a teacher ______ ten years.", '[ "since", "for", "in", "at" ]', "B", "for + 时间段，since + 时间点。"),
        ],
    },
    {
        "name": "过去进行时", "code": "past_continuous", "grade": 8, "category": "时态",
        "description": "表示过去某一时刻正在进行的动作。构成：was/were + 动词ing。常与 at that time/when/while 连用。",
        "examples": "I was reading at eight last night.\nWhile she was cooking, the phone rang.",
        "exercises": [
            ("choice", 8, 1, "I ______ TV at eight last night.", '[ "watch", "watched", "was watching", "am watching" ]', "C", "at eight last night指过去某一时刻，用过去进行时。"),
            ("choice", 8, 1, "While my mother ______ dinner, I was doing homework.", '[ "cooks", "cooked", "was cooking", "is cooking" ]', "C", "while引导的从句用进行时，过去背景用was cooking。"),
            ("fill", 8, 2, "They ______ (play) basketball when it began to rain.", "", "were playing", "雨开始下时他们正在打球，were + playing。"),
            ("fill", 8, 2, "What ______ you ______ (do) at this time yesterday?", "", "were; doing", "过去进行时疑问句：were + 主语 + doing。"),
            ("transform", 9, 3, "She was singing at that time. (改为一般疑问句)", "", "Was she singing at that time?", "把was提到主语前面。"),
        ],
    },
    {
        "name": "过去完成时", "code": "past_perfect", "grade": 9, "category": "时态",
        "description": "表示在过去某一时间或动作之前已经完成的动作，即“过去的过去”。构成：had + 过去分词。",
        "examples": "When I arrived, the train had left.\nShe had finished the book before dinner.",
        "exercises": [
            ("choice", 9, 2, "When I got to the station, the train ______.", '[ "left", "has left", "had left", "leaves" ]', "C", "火车离开在到达之前，用过去完成时had left。"),
            ("choice", 9, 2, "She ______ the work before her boss came back.", '[ "finishes", "finished", "had finished", "has finished" ]', "C", "before came back之前的动作用had + 过去分词。"),
            ("fill", 9, 3, "By the end of last term, we ______ (learn) 20 units.", "", "had learned", "by + 过去时间点用过去完成时。"),
            ("fill", 9, 3, "He realized he ______ (lose) his key.", "", "had lost", "钥匙丢失发生在realize之前，用had lost。"),
        ],
    },
    {
        "name": "被动语态", "code": "passive_voice", "grade": 8, "category": "语态",
        "description": "主语是动作的承受者时用被动语态。构成：be + 过去分词。不同时态中be动词变化：一般现在时am/is/are，一般过去时was/were，含情态动词can/must/should be。",
        "examples": "The room is cleaned every day.\nThe bridge was built in 1990.\nHomework must be finished first.",
        "exercises": [
            ("choice", 8, 1, "English ______ in many countries.", '[ "speaks", "is spoken", "spoke", "is speaking" ]', "B", "English被说，一般现在时被动：is + spoken。"),
            ("choice", 8, 2, "The bridge ______ in 1990.", '[ "builds", "built", "was built", "is built" ]', "C", "1990年是过去，用一般过去时被动was built。"),
            ("fill", 8, 2, "The windows ______ (clean) by Tom yesterday.", "", "were cleaned", "windows是复数，过去时被动were cleaned。"),
            ("choice", 9, 2, "The homework must ______ before Friday.", '[ "finish", "be finished", "finished", "finishing" ]', "B", "情态动词被动：must be + 过去分词。"),
            ("transform", 9, 3, "People grow rice in the south. (改为被动语态)", "", "Rice is grown in the south.", "rice作主语，一般现在时被动is grown。"),
            ("fill", 9, 3, "Many trees ______ (plant) every spring.", "", "are planted", "every spring用一般现在时，trees复数用are planted。"),
        ],
    },
    {
        "name": "宾语从句", "code": "object_clause", "grade": 9, "category": "从句",
        "description": "在句中作宾语的从句。陈述句用that引导，一般疑问句用if/whether，特殊疑问句用疑问词。从句用陈述语序；主句过去时，从句时态相应后退。",
        "examples": "I think (that) he is right.\nDo you know if it will rain?\nCan you tell me where the bank is?",
        "exercises": [
            ("choice", 9, 1, "I don't know ______ he will come tomorrow.", '[ "that", "if", "what", "which" ]', "B", "“是否”用if/whether引导宾语从句。"),
            ("choice", 9, 2, "Can you tell me ______?", '[ "where is the bank", "where the bank is", "the bank is where", "is where the bank" ]', "B", "宾语从句用陈述语序：疑问词 + 主语 + 谓语。"),
            ("choice", 9, 2, "He said that he ______ ill.", '[ "is", "was", "be", "being" ]', "B", "主句是过去时said，从句时态后退用was。"),
            ("fill", 9, 3, "Do you know ______ (does, he, live)? (连词成句作宾语从句)", "", "where he lives", "特殊疑问词引导，从句用陈述语序：where he lives。"),
            ("choice", 9, 3, "The teacher told us that the earth ______ around the sun.", '[ "moved", "moves", "move", "is moved" ]', "B", "客观真理在宾语从句中始终用一般现在时。"),
        ],
    },
    {
        "name": "定语从句", "code": "attributive_clause", "grade": 9, "category": "从句",
        "description": "修饰名词的从句。指人用who/that，指物用which/that，所属关系用whose。关系代词在从句中作主语或宾语。",
        "examples": "The man who is standing there is my uncle.\nThis is the book that I bought yesterday.",
        "exercises": [
            ("choice", 9, 1, "The girl ______ won the prize is my sister.", '[ "which", "who", "whose", "whom" ]', "B", "指人且作主语用who。"),
            ("choice", 9, 1, "This is the movie ______ I like best.", '[ "who", "which", "whose", "whom" ]', "B", "指物用which/that。"),
            ("choice", 9, 2, "I know the boy ______ father is a doctor.", '[ "who", "which", "whose", "that" ]', "C", "表示“他的父亲”用whose。"),
            ("choice", 9, 3, "She is one of the students ______ good at math.", '[ "who is", "who are", "which is", "that is" ]', "B", "先行词是复数students，从句谓语用are。"),
            ("fill", 9, 3, "The book ______ he bought yesterday is interesting. (用which或that)", "", "which/that", "指物作宾语，用which或that。"),
        ],
    },
    {
        "name": "状语从句", "code": "adverbial_clause", "grade": 8, "category": "从句",
        "description": "表示时间(when/while/as soon as)、条件(if/unless)、原因(because)、让步(although)的从句。注意：主将从现——主句将来时，条件/时间从句用一般现在时。",
        "examples": "I will call you when I arrive.\nIf it rains, we will stay at home.",
        "exercises": [
            ("choice", 8, 2, "I will tell him the news as soon as he ______ back.", '[ "will come", "comes", "came", "is coming" ]', "B", "主将从现：as soon as从句用一般现在时。"),
            ("choice", 8, 2, "If it ______ tomorrow, we will go hiking.", "[ \"won't rain\", \"doesn't rain\", \"didn't rain\", \"isn't raining\" ]", "B", "if条件从句主将从现，否定用doesn't rain。"),
            ("choice", 8, 1, "______ he was tired, he kept working.", '[ "Because", "Although", "If", "Unless" ]', "B", "“虽然累但继续工作”是让步关系，用Although。"),
            ("choice", 9, 3, "You will fail the exam ______ you study hard.", '[ "if", "unless", "because", "when" ]', "B", "unless = if not，除非努力学习否则考砸。"),
            ("fill", 9, 3, "He ______ (phone) me when he arrives.", "", "will phone", "主句用将来时，when从句用现在时。"),
        ],
    },
    {
        "name": "不定式与动名词", "code": "infinitive_gerund", "grade": 8, "category": "词法",
        "description": "to + 动词原形为不定式，动词ing为动名词。有些动词后只能接不定式(want/decide/hope/plan)，有些只能接动名词(enjoy/finish/keep/mind)，有些两者均可但意义不同(remember/stop/forget)。",
        "examples": "I want to be a doctor.\nShe enjoys reading.\nRemember to close the door. (记得去关)\nI remember closing the door. (记得关过)",
        "exercises": [
            ("choice", 8, 1, "He decided ______ a new bike.", '[ "buy", "buying", "to buy", "bought" ]', "C", "decide后接不定式to buy。"),
            ("choice", 8, 1, "I enjoy ______ English songs.", '[ "listen to", "to listen to", "listening to", "listened to" ]', "C", "enjoy后接动名词listening to。"),
            ("choice", 8, 2, "Don't forget ______ the lights when you leave.", '[ "turn off", "turning off", "to turn off", "turned off" ]', "C", "remember/forget to do表示记得/忘记要去做。"),
            ("choice", 9, 3, "Stop ______! The teacher is coming. (别说话了)", '[ "talk", "to talk", "talking", "talked" ]', "C", "stop doing表示停止正在做的事。"),
            ("fill", 9, 3, "She hopes ______ (become) a doctor.", "", "to become", "hope后接不定式to become。"),
        ],
    },
    {
        "name": "感叹句", "code": "exclamatory", "grade": 7, "category": "句型",
        "description": "What引导的感叹句修饰名词：What (a/an) + 形容词 + 名词 + 主谓！How引导的感叹句修饰形容词/副词：How + 形容词/副词 + 主谓！",
        "examples": "What a beautiful flower it is!\nHow fast he runs!",
        "exercises": [
            ("choice", 7, 1, "______ lovely weather it is!", '[ "What", "What a", "How", "How a" ]', "A", "weather不可数，用What + 形容词 + 不可数名词。"),
            ("choice", 7, 1, "______ interesting the story is!", '[ "What", "What an", "How", "How an" ]', "C", "修饰形容词interesting用How。"),
            ("choice", 8, 2, "______ great fun we had at the party!", '[ "What", "What a", "How", "How a" ]', "A", "fun不可数，用What。"),
            ("transform", 8, 3, "The boy is very clever. (改为感叹句)", "", "How clever the boy is!", "How + 形容词 + 主语 + 谓语。"),
            ("fill", 9, 3, "______ (What/How) a hard-working student she is!", "", "What", "修饰名词短语a hard-working student用What。"),
        ],
    },
    {
        "name": "情态动词表推测", "code": "modal_speculation", "grade": 9, "category": "词法",
        "description": "must表示肯定推测（一定），can't/couldn't表示否定推测（不可能），may/might/could表示可能。对现在的推测后接动词原形，对正在进行的推测接be doing。",
        "examples": "He must be at home. (他一定在家)\nIt can't be true. (这不可能是真的)\nShe may come tomorrow. (她可能来)",
        "exercises": [
            ("choice", 9, 2, "The lights are on. He ______ be at home.", "[ \"can't\", \"must\", \"may\", \"should\" ]", "B", "灯亮着是强证据，肯定推测用must。"),
            ("choice", 9, 2, "It ______ be Tom. He is in Shanghai now.", "[ \"mustn't\", \"can't\", \"needn't\", \"may not\" ]", "B", "他在上海，不可能在这，否定推测用can't。"),
            ("choice", 9, 3, "She ______ be reading in the library. I saw her there just now.", "[ \"must\", \"can't\", \"may\", \"should\" ]", "A", "刚看到她在图书馆，肯定推测正在进行用must be doing。"),
            ("fill", 9, 3, "It ______ (may) rain tomorrow. Take an umbrella. (用may/might填空)", "", "may/might", "可能性较弱的推测用may/might。"),
        ],
    },
]

def _migrate_middle_grammar(db):
    """为已有数据库增量补充初中语法知识点（按 code 去重）"""
    added = 0
    for gp_data in MIDDLE_GRAMMAR_DATA:
        existing = db.query(GrammarPoint).filter(GrammarPoint.code == gp_data["code"]).first()
        if existing:
            continue
        point = GrammarPoint(
            name=gp_data["name"],
            code=gp_data["code"],
            grade=gp_data["grade"],
            category=gp_data["category"],
            description=gp_data["description"],
            examples=gp_data["examples"],
        )
        db.add(point)
        db.flush()
        for ex_type, grade, diff, question, options, answer, explanation in gp_data["exercises"]:
            db.add(GrammarExercise(
                grammar_point_id=point.id,
                grade=grade,
                exercise_type=ex_type,
                question=question,
                options=options,
                answer=answer,
                explanation=explanation,
                difficulty=diff,
            ))
        added += 1
    if added:
        db.commit()

__all__ = [
    "MIDDLE_GRAMMAR_DATA",
    "_migrate_middle_grammar",
    "_seed_grammar",
]
