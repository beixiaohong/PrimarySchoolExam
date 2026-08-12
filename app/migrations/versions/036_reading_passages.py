"""036 阅读理解专项：reading_passages 表 + 阅读种子（MySQL-only，SQLite 测试跳过）

种子规模（种子版，需人工校对）：
- 英语：7/8/9 年级各 5 篇，每篇 4 道选择题
- 语文：小学高段（5/6 年级）5 篇 + 初中 6 篇，每篇 3 道选择 + 1 道主观简答

questions_json 每题结构：
{type:choice|short, question, options:[...], answer, points:[...], score}

为何 MySQL-only：reading_passages 建表用 INT AUTO_INCREMENT / ENGINE=InnoDB /
内联 COMMENT 等 MySQL 专属 DDL，SQLite 不支持。
"""
import json

from sqlalchemy import inspect, text

# 阅读篇目种子（subject, grade, semester, title, passage, questions_list）
# 说明：语文篇目为自编/改编短文本，不收录课内课文全文（版权约束）
READING_SEED = [
    # ════════════ 英语 · 七年级 ════════════
    ("英语", 7, "全", "My New School",
     "I am Li Hua. I am a student in Grade 7. My new school is big and beautiful. There are many trees and flowers. I have a good friend, Tom. He is from England. We read books in the library after class.",
     [
         {"type": "choice", "question": "What grade is Li Hua in?", "options": ["Grade 6", "Grade 7", "Grade 8", "Grade 9"], "answer": "Grade 7", "points": [], "score": 5},
         {"type": "choice", "question": "Where is Tom from?", "options": ["China", "England", "America", "Japan"], "answer": "England", "points": [], "score": 5},
         {"type": "choice", "question": "What do they do after class?", "options": ["Play football", "Read books", "Watch TV", "Swim"], "answer": "Read books", "points": [], "score": 5},
         {"type": "choice", "question": "How is Li Hua's new school?", "options": ["Small", "Old", "Big and beautiful", "Noisy"], "answer": "Big and beautiful", "points": [], "score": 5},
     ]),
    ("英语", 7, "全", "A Happy Family",
     "There are four people in my family: my father, my mother, my sister and I. My father is a teacher. My mother is a doctor. My sister and I are students. We often have dinner together and talk about our day.",
     [
         {"type": "choice", "question": "How many people are in the family?", "options": ["Three", "Four", "Five", "Six"], "answer": "Four", "points": [], "score": 5},
         {"type": "choice", "question": "What is the father's job?", "options": ["Doctor", "Teacher", "Driver", "Farmer"], "answer": "Teacher", "points": [], "score": 5},
         {"type": "choice", "question": "What is the mother?", "options": ["A doctor", "A teacher", "A student", "A worker"], "answer": "A doctor", "points": [], "score": 5},
         {"type": "choice", "question": "What do they often do together?", "options": ["Go to the park", "Have dinner and talk", "Watch films", "Play games"], "answer": "Have dinner and talk", "points": [], "score": 5},
     ]),
    ("英语", 7, "全", "My Favorite Animal",
     "My favorite animal is the panda. Pandas are black and white. They live in China. They like eating bamboo. They are very cute but they are in danger, so we should protect them.",
     [
         {"type": "choice", "question": "What is the writer's favorite animal?", "options": ["The tiger", "The panda", "The dog", "The cat"], "answer": "The panda", "points": [], "score": 5},
         {"type": "choice", "question": "What color are pandas?", "options": ["Black and white", "Brown", "Yellow", "Red"], "answer": "Black and white", "points": [], "score": 5},
         {"type": "choice", "question": "What do pandas like eating?", "options": ["Meat", "Bamboo", "Fish", "Grass"], "answer": "Bamboo", "points": [], "score": 5},
         {"type": "choice", "question": "Why should we protect pandas?", "options": ["They are big", "They are in danger", "They are fast", "They are cheap"], "answer": "They are in danger", "points": [], "score": 5},
     ]),
    ("英语", 7, "全", "A Busy Sunday",
     "On Sunday morning, I do my homework. Then I help my mother clean the room. In the afternoon, I play basketball with my friends. In the evening, I read a storybook. I have a busy but happy Sunday.",
     [
         {"type": "choice", "question": "What does the writer do on Sunday morning?", "options": ["Play basketball", "Do homework", "Clean the room", "Read a book"], "answer": "Do homework", "points": [], "score": 5},
         {"type": "choice", "question": "Who does the writer play basketball with?", "options": ["His mother", "His friends", "His teacher", "His brother"], "answer": "His friends", "points": [], "score": 5},
         {"type": "choice", "question": "When does he read a storybook?", "options": ["In the morning", "In the afternoon", "In the evening", "At noon"], "answer": "In the evening", "points": [], "score": 5},
         {"type": "choice", "question": "How is his Sunday?", "options": ["Sad", "Busy but happy", "Boring", "Tired"], "answer": "Busy but happy", "points": [], "score": 5},
     ]),
    ("英语", 7, "全", "Healthy Food",
     "We should eat healthy food. Apples, bananas and oranges are good fruit. Milk and eggs help us grow. We should not eat too much candy or drink too much cola. Water is the best drink.",
     [
         {"type": "choice", "question": "Which is good fruit?", "options": ["Candy", "Apples", "Cola", "Chips"], "answer": "Apples", "points": [], "score": 5},
         {"type": "choice", "question": "What helps us grow?", "options": ["Milk and eggs", "Cola", "Candy", "Ice cream"], "answer": "Milk and eggs", "points": [], "score": 5},
         {"type": "choice", "question": "What is the best drink?", "options": ["Cola", "Juice", "Water", "Coffee"], "answer": "Water", "points": [], "score": 5},
         {"type": "choice", "question": "We should NOT eat too much of...?", "options": ["Fruit", "Vegetables", "Candy", "Eggs"], "answer": "Candy", "points": [], "score": 5},
     ]),

    # ════════════ 英语 · 八年级 ════════════
    ("英语", 8, "全", "The Internet",
     "The Internet is an important part of our life. We can study, shop and talk with friends online. But we must be careful. We should not tell strangers our personal information, and we should not spend too much time online.",
     [
         {"type": "choice", "question": "What can we do on the Internet?", "options": ["Only study", "Study, shop and talk", "Nothing useful", "Only play"], "answer": "Study, shop and talk", "points": [], "score": 5},
         {"type": "choice", "question": "What should we NOT do online?", "options": ["Learn English", "Tell strangers personal info", "Send emails", "Watch news"], "answer": "Tell strangers personal info", "points": [], "score": 5},
         {"type": "choice", "question": "Why must we be careful online?", "options": ["It is slow", "There are risks", "It is expensive", "It is boring"], "answer": "There are risks", "points": [], "score": 5},
         {"type": "choice", "question": "What does the writer advise about time?", "options": ["Spend all day online", "Not too much time", "No time online", "Only at night"], "answer": "Not too much time", "points": [], "score": 5},
     ]),
    ("英语", 8, "全", "A Trip to the Mountains",
     "Last weekend, my class went to the mountains. The weather was fine. We climbed the hill and saw beautiful flowers. At noon we had a picnic by the lake. Everyone was tired but happy.",
     [
         {"type": "choice", "question": "Where did the class go last weekend?", "options": ["The park", "The mountains", "The zoo", "The museum"], "answer": "The mountains", "points": [], "score": 5},
         {"type": "choice", "question": "What was the weather like?", "options": ["Rainy", "Windy", "Fine", "Snowy"], "answer": "Fine", "points": [], "score": 5},
         {"type": "choice", "question": "What did they do at noon?", "options": ["Went swimming", "Had a picnic", "Climbed again", "Went home"], "answer": "Had a picnic", "points": [], "score": 5},
         {"type": "choice", "question": "How did everyone feel?", "options": ["Tired but happy", "Angry", "Afraid", "Bored"], "answer": "Tired but happy", "points": [], "score": 5},
     ]),
    ("英语", 8, "全", "My Dream Job",
     "I want to be a scientist when I grow up. I like asking questions and doing experiments. Science helps us understand the world. I will study hard and never give up my dream.",
     [
         {"type": "choice", "question": "What does the writer want to be?", "options": ["A teacher", "A scientist", "A doctor", "A driver"], "answer": "A scientist", "points": [], "score": 5},
         {"type": "choice", "question": "What does the writer like doing?", "options": ["Watching TV", "Asking questions and experiments", "Sleeping", "Eating"], "answer": "Asking questions and experiments", "points": [], "score": 5},
         {"type": "choice", "question": "What will the writer do for the dream?", "options": ["Give up", "Study hard", "Play more", "Do nothing"], "answer": "Study hard", "points": [], "score": 5},
         {"type": "choice", "question": "What does science help us do?", "options": ["Earn money", "Understand the world", "Travel", "Sleep"], "answer": "Understand the world", "points": [], "score": 5},
     ]),
    ("英语", 8, "全", "Saving Water",
     "Water is very important. People can live without food for some days, but not without water. We should save water every day. Turn off the tap when brushing teeth. Reuse water to clean the floor.",
     [
         {"type": "choice", "question": "Why is water important?", "options": ["It is cheap", "We cannot live without it", "It is blue", "It is cold"], "answer": "We cannot live without it", "points": [], "score": 5},
         {"type": "choice", "question": "What should we do when brushing teeth?", "options": ["Keep tap on", "Turn off the tap", "Use hot water", "Sing"], "answer": "Turn off the tap", "points": [], "score": 5},
         {"type": "choice", "question": "How can we reuse water?", "options": ["Pour it away", "Clean the floor", "Drink it again", "Throw it"], "answer": "Clean the floor", "points": [], "score": 5},
         {"type": "choice", "question": "The writer asks us to save water...?", "options": ["Every day", "Only in summer", "Never", "Once a year"], "answer": "Every day", "points": [], "score": 5},
     ]),
    ("英语", 8, "全", "Friendship",
     "A good friend is like a mirror. He tells you the truth. When you are sad, he stays with you. When you succeed, he is happy for you. True friends are not easy to find, so we should treasure them.",
     [
         {"type": "choice", "question": "What is a good friend like according to the text?", "options": ["A book", "A mirror", "A teacher", "A tree"], "answer": "A mirror", "points": [], "score": 5},
         {"type": "choice", "question": "What does a good friend do when you are sad?", "options": ["Leaves you", "Stays with you", "Laughs", "Calls you lazy"], "answer": "Stays with you", "points": [], "score": 5},
         {"type": "choice", "question": "When you succeed, a true friend...?", "options": ["Is jealous", "Is happy for you", "Leaves", "Is quiet"], "answer": "Is happy for you", "points": [], "score": 5},
         {"type": "choice", "question": "What should we do with true friends?", "options": ["Forget them", "Treasure them", "Ignore them", "Change them"], "answer": "Treasure them", "points": [], "score": 5},
     ]),

    # ════════════ 英语 · 九年级 ════════════
    ("英语", 9, "全", "The Value of Time",
     "Time is money, but time is more precious than money because when money is spent, we can earn it back; when time is gone, it never returns. We should make good use of time and never put off what we can do today until tomorrow.",
     [
         {"type": "choice", "question": "Why is time more precious than money?", "options": ["It is cheaper", "It cannot come back", "It is easier to use", "It is heavier"], "answer": "It cannot come back", "points": [], "score": 5},
         {"type": "choice", "question": "What should we do with time?", "options": ["Waste it", "Make good use of it", "Forget it", "Sell it"], "answer": "Make good use of it", "points": [], "score": 5},
         {"type": "choice", "question": "What does 'put off' mean here?", "options": ["Finish", "Delay", "Start", "Enjoy"], "answer": "Delay", "points": [], "score": 5},
         {"type": "choice", "question": "What should we NOT do?", "options": ["Work hard", "Use time well", "Leave today's work for tomorrow", "Study"], "answer": "Leave today's work for tomorrow", "points": [], "score": 5},
     ]),
    ("英语", 9, "全", "Protecting the Environment",
     "Our earth is in trouble. Air and water are polluted. To protect the environment, we should take public transport, plant more trees, and reduce waste. Small actions by everyone can make a big difference.",
     [
         {"type": "choice", "question": "What problem does the earth have?", "options": ["Too much rain", "Pollution", "Too many people", "No trees"], "answer": "Pollution", "points": [], "score": 5},
         {"type": "choice", "question": "Which is a way to protect the environment?", "options": ["Drive alone", "Take public transport", "Burn trash", "Cut trees"], "answer": "Take public transport", "points": [], "score": 5},
         {"type": "choice", "question": "What can small actions do?", "options": ["Nothing", "Make a big difference", "Harm the earth", "Cost money"], "answer": "Make a big difference", "points": [], "score": 5},
         {"type": "choice", "question": "The writer thinks everyone should...?", "options": ["Do nothing", "Act", "Wait for others", "Leave"], "answer": "Act", "points": [], "score": 5},
     ]),
    ("英语", 9, "全", "Learning from Failure",
     "Failure is not the end. Many great people failed many times before they succeeded. Thomas Edison tried thousands of times before he made the light bulb. We should learn from failure and keep trying.",
     [
         {"type": "choice", "question": "What is failure according to the text?", "options": ["The end", "A lesson", "A shame", "A mistake"], "answer": "A lesson", "points": [], "score": 5},
         {"type": "choice", "question": "Who is mentioned as an example?", "options": ["Newton", "Edison", "Einstein", "Darwin"], "answer": "Edison", "points": [], "score": 5},
         {"type": "choice", "question": "What should we do after failure?", "options": ["Give up", "Learn and keep trying", "Cry", "Hide"], "answer": "Learn and keep trying", "points": [], "score": 5},
         {"type": "choice", "question": "How many times did Edison try?", "options": ["Ten", "Thousands", "One", "Hundred"], "answer": "Thousands", "points": [], "score": 5},
     ]),
    ("英语", 9, "全", "The Power of Reading",
     "Reading opens a door to the world. Through books we can travel to far places, meet great minds and learn about the past. A good book is a good friend. The more we read, the more we know.",
     [
         {"type": "choice", "question": "What does reading open?", "options": ["A window", "A door to the world", "A box", "A bottle"], "answer": "A door to the world", "points": [], "score": 5},
         {"type": "choice", "question": "Through books we can...?", "options": ["Only sleep", "Travel and learn", "Eat", "Sing"], "answer": "Travel and learn", "points": [], "score": 5},
         {"type": "choice", "question": "What is a good book compared to?", "options": ["A friend", "A meal", "A car", "A bed"], "answer": "A friend", "points": [], "score": 5},
         {"type": "choice", "question": "What happens the more we read?", "options": ["The less we know", "The more we know", "The tired we are", "The poorer we are"], "answer": "The more we know", "points": [], "score": 5},
     ]),
    ("英语", 9, "全", "Healthy Habits",
     "Good habits make a healthy life. We should go to bed early and get up early. Doing sports every day keeps us strong. A balanced diet with vegetables and fruit is better than junk food. Smiling often makes us happy.",
     [
         {"type": "choice", "question": "When should we go to bed?", "options": ["Late", "Early", "At noon", "Never"], "answer": "Early", "points": [], "score": 5},
         {"type": "choice", "question": "What keeps us strong?", "options": ["Watching TV", "Doing sports", "Eating candy", "Sleeping all day"], "answer": "Doing sports", "points": [], "score": 5},
         {"type": "choice", "question": "What is better than junk food?", "options": ["A balanced diet", "More candy", "Cola", "Chips"], "answer": "A balanced diet", "points": [], "score": 5},
         {"type": "choice", "question": "What makes us happy?", "options": ["Crying", "Smiling often", "Anger", "Worry"], "answer": "Smiling often", "points": [], "score": 5},
     ]),

    # ════════════ 语文 · 小学高段（5/6 年级）══════════
    ("语文", 6, "全", "守株待兔（改编）",
     "从前，宋国有个农夫。有一天，他正在田里干活，忽然一只兔子撞死在树桩上。农夫白捡了一只兔子，非常高兴。从此，他放下农具，天天守在树桩旁，希望再捡到兔子。可是，他再也没有等到兔子，地里的庄稼却荒芜了。",
     [
         {"type": "choice", "question": "兔子是怎么死的？", "options": ["被农夫打死", "撞死在树桩上", "被猎人抓走", "生病死了"], "answer": "撞死在树桩上", "points": [], "score": 5},
         {"type": "choice", "question": "农夫后来每天都在做什么？", "options": ["认真种地", "守在树桩旁等兔子", "去集市卖菜", "读书写字"], "answer": "守在树桩旁等兔子", "points": [], "score": 5},
         {"type": "choice", "question": "这个故事告诉我们什么？", "options": ["兔子很多", "不能存侥幸心理，要勤劳", "树桩很有用", "庄稼不重要"], "answer": "不能存侥幸心理，要勤劳", "points": [], "score": 5},
         {"type": "short", "question": "说说「守株待兔」现在常用来比喻什么样的人或事？", "options": [],
          "answer": "比喻不主动努力，而存万一的侥幸心理，希望得到意外收获的人；也指死守狭隘经验不知变通。",
          "points": ["不主动努力/存侥幸心理", "希望意外收获", "死守经验不知变通"], "score": 10},
     ]),
    ("语文", 6, "全", "小溪流的歌（改编）",
     "一条小溪流，唱着歌往前跑。他遇到枯树桩和枯草，他们劝他歇一歇。小溪流说：「我不能停留！」他不停地奔流，变成了小河、大江，最后奔向大海。他永远唱着快乐的歌。",
     [
         {"type": "choice", "question": "小溪流遇到谁劝他休息？", "options": ["小鱼", "枯树桩和枯草", "小鸟", "老牛"], "answer": "枯树桩和枯草", "points": [], "score": 5},
         {"type": "choice", "question": "小溪流最后变成了什么？", "options": ["池塘", "大海", "水井", "湖泊"], "answer": "大海", "points": [], "score": 5},
         {"type": "choice", "question": "小溪流的精神是？", "options": ["懒惰", "不停奔流、永远向前", "害怕困难", "喜欢停下"], "answer": "不停奔流、永远向前", "points": [], "score": 5},
         {"type": "short", "question": "从「小溪流」变成「大海」的过程，你体会到了什么？", "options": [],
          "answer": "体会到只要不怕困难、坚持不懈地努力，就能不断成长、由小变大，最终实现目标。",
          "points": ["不怕困难/坚持不懈", "不断成长进步", "实现目标"], "score": 10},
     ]),
    ("语文", 5, "全", "画蛇添足（改编）",
     "几个人比赛画蛇，先画完的人可以喝酒。有个人先画完了，见别人还没画好，就左手拿酒壶，右手给蛇添上脚。这时另一个人画完了，说：「蛇本来没有脚，你画的不是蛇。」于是夺过酒喝了。",
     [
         {"type": "choice", "question": "比赛画蛇的奖品是什么？", "options": ["钱", "酒", "肉", "画"], "answer": "酒", "points": [], "score": 5},
         {"type": "choice", "question": "先画完的人为什么没喝到酒？", "options": ["他画得慢", "他给蛇添了脚，画的不是蛇", "酒被打翻", "他让给了别人"], "answer": "他给蛇添了脚，画的不是蛇", "points": [], "score": 5},
         {"type": "choice", "question": "「画蛇添足」比喻什么？", "options": ["做事认真", "多此一举，反而坏事", "画得好", "跑得快"], "answer": "多此一举，反而坏事", "points": [], "score": 5},
         {"type": "short", "question": "生活中有没有「画蛇添足」的事？举一例说明。", "options": [],
          "answer": "例如写作文时本来已经写清楚了，又啰嗦地重复解释，反而让文章不简洁；或把简单的事复杂化。",
          "points": ["能举出生活例子", "说明「多此一举反而坏事」", "表达清楚"], "score": 10},
     ]),
    ("语文", 6, "全", "蜜蜂（改编）",
     "蜜蜂是一种勤劳的昆虫。它们每天在花丛中飞来飞去，采集花蜜，酿成香甜的蜂蜜。蜜蜂分工明确：工蜂采蜜，蜂王产卵。它们团结协作，把巢筑得又整齐又牢固。",
     [
         {"type": "choice", "question": "蜜蜂采集什么酿蜜？", "options": ["树叶", "花蜜", "雨水", "泥土"], "answer": "花蜜", "points": [], "score": 5},
         {"type": "choice", "question": "负责产卵的是？", "options": ["工蜂", "蜂王", "雄蜂", "幼蜂"], "answer": "蜂王", "points": [], "score": 5},
         {"type": "choice", "question": "蜜蜂的特点是什么？", "options": ["懒惰", "勤劳、团结协作", "凶猛", "孤独"], "answer": "勤劳、团结协作", "points": [], "score": 5},
         {"type": "short", "question": "从蜜蜂身上，我们可以学到哪些品质？", "options": [],
          "answer": "可以学到勤劳肯干、团结协作、各司其职、为集体做贡献的品质。",
          "points": ["勤劳", "团结协作", "各司其职/为集体"], "score": 10},
     ]),
    ("语文", 5, "全", "夏夜（改编）",
     "夏天的夜晚真美。青蛙在池塘里呱呱地唱，萤火虫提着小灯笼在草丛间飞来飞去。星星眨着眼睛，月亮弯弯像一只小船。晚风轻轻吹过，带来阵阵花香。孩子们躺在凉席上，听奶奶讲古老的故事。",
     [
         {"type": "choice", "question": "谁提着小灯笼飞来飞去？", "options": ["青蛙", "萤火虫", "星星", "月亮"], "answer": "萤火虫", "points": [], "score": 5},
         {"type": "choice", "question": "月亮被比作什么？", "options": ["一面镜子", "一只小船", "一个圆盘", "一盏灯"], "answer": "一只小船", "points": [], "score": 5},
         {"type": "choice", "question": "孩子们夏夜在做什么？", "options": ["写作业", "听奶奶讲故事", "看电视", "捉鱼"], "answer": "听奶奶讲故事", "points": [], "score": 5},
         {"type": "short", "question": "这段话表达了作者怎样的感情？", "options": [],
          "answer": "表达了对夏夜美景的喜爱，以及对温馨、宁静乡村生活的热爱与赞美。",
          "points": ["喜爱夏夜美景", "赞美宁静温馨的生活"], "score": 10},
     ]),

    # ════════════ 语文 · 初中 ═══════════
    ("语文", 7, "全", "春（节选改编）",
     "盼望着，盼望着，东风来了，春天的脚步近了。一切都像刚睡醒的样子，欣欣然张开了眼。山朗润起来了，水涨起来了，太阳的脸红起来了。小草偷偷地从土里钻出来，嫩嫩的，绿绿的。",
     [
         {"type": "choice", "question": "这段话描写的是哪个季节？", "options": ["春", "夏", "秋", "冬"], "answer": "春", "points": [], "score": 5},
         {"type": "choice", "question": "「小草偷偷地从土里钻出来」用了什么修辞？", "options": ["比喻", "拟人", "夸张", "排比"], "answer": "拟人", "points": [], "score": 5},
         {"type": "choice", "question": "「欣欣然张开了眼」写的是？", "options": ["动物醒来", "万物复苏", "太阳升起", "风吹过"], "answer": "万物复苏", "points": [], "score": 5},
         {"type": "short", "question": "这段景物描写好在哪里？请结合词句说说。", "options": [],
          "answer": "好在运用拟人（如「欣欣然张开了眼」「偷偷地钻」）把春天写得充满生机，用词准确生动（朗润、涨、钻），画面感强，表达了喜悦之情。",
          "points": ["运用拟人等修辞", "用词生动准确", "写出生机/表达喜悦"], "score": 10},
     ]),
    ("语文", 8, "全", "背影（节选改编）",
     "我看见他戴着黑布小帽，穿着黑布大马褂，深青布棉袍，蹒跚地走到铁道边，慢慢探身下去，尚不大难。可是他穿过铁道，要爬上那边月台，就不容易了。他用两手攀着上面，两脚再向上缩。",
     [
         {"type": "choice", "question": "这段话主要写什么？", "options": ["父亲买橘子的背影", "天气很冷", "车站很乱", "作者读书"], "answer": "父亲买橘子的背影", "points": [], "score": 5},
         {"type": "choice", "question": "父亲的衣着是什么颜色为主？", "options": ["红", "黑、深青", "白", "黄"], "answer": "黑、深青", "points": [], "score": 5},
         {"type": "choice", "question": "「攀」「缩」等动词突出了什么？", "options": ["父亲轻松", "父亲动作艰难、爱子情深", "父亲高兴", "父亲生气"], "answer": "父亲动作艰难、爱子情深", "points": [], "score": 5},
         {"type": "short", "question": "作者为什么反复描写父亲的「背影」？", "options": [],
          "answer": "因为背影是作者观察父亲的独特角度，凝聚了父亲艰难谋生却仍关爱儿子的深情，表达了作者对父爱的感动与怀念。",
          "points": ["观察角度独特", "凝聚父爱", "表达感动与怀念"], "score": 10},
     ]),
    ("语文", 9, "全", "岳阳楼记（节选改编）",
     "予观夫巴陵胜状，在洞庭一湖。衔远山，吞长江，浩浩汤汤，横无际涯；朝晖夕阴，气象万千。此则岳阳楼之大观也。然则北通巫峡，南极潇湘，迁客骚人，多会于此，览物之情，得无异乎？",
     [
         {"type": "choice", "question": "这段文字写的是哪里的景色？", "options": ["西湖", "洞庭湖/岳阳楼", "太湖", "鄱阳湖"], "answer": "洞庭湖/岳阳楼", "points": [], "score": 5},
         {"type": "choice", "question": "「衔远山，吞长江」用了什么修辞？", "options": ["比喻", "对偶兼拟人", "夸张", "反问"], "answer": "对偶兼拟人", "points": [], "score": 5},
         {"type": "choice", "question": "「浩浩汤汤，横无际涯」形容什么？", "options": ["湖水广阔", "山很高", "楼很大", "风很大"], "answer": "湖水广阔", "points": [], "score": 5},
         {"type": "short", "question": "「览物之情，得无异乎」在文中有什么作用？", "options": [],
          "answer": "承上启下（过渡），由写景转入写「迁客骚人」因景而异的悲喜之情，引出下文两种情境的描写。",
          "points": ["承上启下/过渡", "由景入情", "引出下文"], "score": 10},
     ]),
    ("语文", 7, "全", "散步（节选改编）",
     "我们在田野上散步：我，我的母亲，我的妻子和儿子。母亲要走大路，大路平顺；我的儿子要走小路，小路有意思。不过，一切都取决于我。我的母亲老了，她早已习惯听从她强壮的儿子。",
     [
         {"type": "choice", "question": "一家人散步出现了什么分歧？", "options": ["走大路还是小路", "去公园还是回家", "吃饭还是看书", "坐车还是走路"], "answer": "走大路还是小路", "points": [], "score": 5},
         {"type": "choice", "question": "母亲为什么习惯听从儿子？", "options": ["儿子聪明", "她老了，儿子强壮", "儿子有钱", "儿子生气"], "answer": "她老了，儿子强壮", "points": [], "score": 5},
         {"type": "choice", "question": "这段写了哪些人？", "options": ["我和朋友", "我、母亲、妻子、儿子", "只有我", "老师和同学"], "answer": "我、母亲、妻子、儿子", "points": [], "score": 5},
         {"type": "short", "question": "从这段「分歧」的描写中，你感受到怎样的亲情？", "options": [],
          "answer": "感受到一家人相互体谅、尊老爱幼的温馨亲情；母亲老了依赖儿子，儿子承担责任，体现了中年人的担当。",
          "points": ["相互体谅/尊老爱幼", "温馨亲情", "中年人的担当"], "score": 10},
     ]),
    ("语文", 8, "全", "苏州园林（节选改编）",
     "苏州园林据说有一百多处，我到过的不过十多处。设计者和匠师们一致追求的是：务必使游览者无论站在哪个点上，眼前总是一幅完美的图画。他们讲究亭台轩榭的布局，讲究假山池沼的配合。",
     [
         {"type": "choice", "question": "苏州园林设计的核心追求是？", "options": ["高大", "处处如画", "华丽", "对称"], "answer": "处处如画", "points": [], "score": 5},
         {"type": "choice", "question": "设计者讲究什么？", "options": ["只种树", "亭台布局与假山池沼配合", "只修路", "只建高楼"], "answer": "亭台布局与假山池沼配合", "points": [], "score": 5},
         {"type": "choice", "question": "「完美的图画」指什么？", "options": ["真的一幅画", "园林处处美观如画", "照片", "地图"], "answer": "园林处处美观如画", "points": [], "score": 5},
         {"type": "short", "question": "「务必使游览者无论站在哪个点上，眼前总是一幅完美的图画」体现了苏州园林怎样的特点？", "options": [],
          "answer": "体现了苏州园林讲究整体构图、不拘一格却处处精致的特点，追求自然与人工的和谐统一，不讲究对称而重画意。",
          "points": ["整体构图/处处精致", "自然与人工和谐", "不重对称重画意"], "score": 10},
     ]),
    ("语文", 9, "全", "敬业与乐业（节选改编）",
     "我这题目，是把《礼记》里头「敬业乐群」和《老子》里头「安其居，乐其业」那两句话，断章取义造出来的。我所说的是敬字为古圣贤教人做人最简易、直捷的法门。业有什么可敬呢？",
     [
         {"type": "choice", "question": "「敬业乐群」出自哪部书？", "options": ["《论语》", "《礼记》", "《孟子》", "《大学》"], "answer": "《礼记》", "points": [], "score": 5},
         {"type": "choice", "question": "作者认为「敬」是什么？", "options": ["好玩", "做人最简易直捷的法门", "赚钱", "休息"], "answer": "做人最简易直捷的法门", "points": [], "score": 5},
         {"type": "choice", "question": "「断章取义」在文中是？", "options": ["贬义批评", "作者自谦的说法", "指责别人", "无意义"], "answer": "作者自谦的说法", "points": [], "score": 5},
         {"type": "short", "question": "结合文段，说说作者提出「敬业」是为了说明什么道理。", "options": [],
          "answer": "说明做人做事要把「敬」作为根本态度，即对所做的事专心、认真负责；无论什么职业都值得敬重，应踏实做好本职。",
          "points": ["敬是做人做事的根本态度", "专心负责", "职业无贵贱都应敬重"], "score": 10},
     ]),
]


def upgrade(db):
    insp = inspect(db.bind)
    tables = set(insp.get_table_names())
    if "reading_passages" not in tables:
        # 新建阅读理解专项表 reading_passages（AUTO_INCREMENT/InnoDB/内联 COMMENT 为 MySQL 专属）
        db.execute(text(
            """
            CREATE TABLE reading_passages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                subject VARCHAR(20) NOT NULL,
                grade INT NOT NULL DEFAULT 0,
                semester VARCHAR(10) DEFAULT '全',
                title VARCHAR(200) DEFAULT '',
                passage TEXT,
                questions_json TEXT NOT NULL DEFAULT '[]',
                review_status VARCHAR(20) DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX (subject),
                INDEX (grade)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='阅读理解专项篇目'
            """
        ))

    # 去重：按 (subject, grade, title) 判定
    existing = {
        (r[0], r[1], r[2]) for r in db.execute(
            text("SELECT subject, grade, title FROM reading_passages")
        )
    }
    added = 0
    for subject, grade, semester, title, passage, questions in READING_SEED:
        if (subject, grade, title) in existing:
            continue
        db.execute(
            text(
                "INSERT INTO reading_passages (subject, grade, semester, title, passage, questions_json, review_status, created_at) "
                "VALUES (:subject, :grade, :semester, :title, :passage, :questions_json, 'pending', NOW())"
            ),
            {
                "subject": subject, "grade": grade, "semester": semester,
                "title": title, "passage": passage,
                "questions_json": json.dumps(questions, ensure_ascii=False),
            },
        )
        added += 1
    db.flush()
    import logging
    logging.getLogger("migrations").info("036 阅读种子：新增 %d 篇（英语/语文）", added)
