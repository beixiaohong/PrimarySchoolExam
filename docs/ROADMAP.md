# 智学学堂 · 产品优化落地路线

> 最后更新：2026-08-11 · 对应代码版本：main @ 4ca23b5
>
> 三个核心方向：
> 1. 如何跟随孩子的年级提升增加新知识（内容成长体系）
> 2. 如何同步学习课堂知识（教材进度同步）
> 3. 初中的学科如何处理（小升初衔接与初中扩展）

---

## 现状盘点（已核实的技术地基）

| 能力 | 现状 | 代码位置 |
|---|---|---|
| 年级体系 | 支持 1-12 年级；每年 9 月 1 日自动升年级 | app/routers/user.py `_auto_upgrade_grade` |
| 出卷年级 | 已支持 1-9 年级（`grade: ge=1, le=9`） | app/schemas/exam.py `ExamCreateRequest` |
| 数学题型 | ProblemType 带 grade_min/grade_max，出卷按年级过滤；**已播种 5 个初中题型**（mid_quadratic_eq/mid_linear_func/mid_pythagorean/mid_inequality/mid_probability，7-9 年级） | app/services/math_generator.py、app/services/init_data.py |
| 英语词库 | WordBook 已有 版本/年级/学期 三维，Word 已有 unit 字段；现有数据为人教版 PEP 3-6 年级（1969 词） | app/models/word.py、app/data/words_primary_school.csv |
| 古诗文 | ClassicalText.grade 支持 1-9，种子数据覆盖 1-6 年级 | app/models/classical.py、迁移 002_classical_seed.py |
| 内容检索 | vocab 新学只取当前年级词书，古诗文 /today 按 `grade <= 当前年级`，内容随年级自然解锁，但无学期区分 | app/routers/vocab.py、classical.py |
| 已知缺口 | 无学期维度解锁；无「当前教学进度（单元）」概念；无初中英语词汇与语文篇目数据；试卷标题硬编码「小学」 | docx_service.py L49/L139 等 |

---

## 阶段 A：低成本快赢（约 2-3 天）

### A1 初中数学打通（半天）

初中题型生成器与种子数据已就绪，只差入口与文案。

- 数据：无需迁移。服务器核对：
  ```sql
  SELECT code, name, grade_min, grade_max FROM problem_types WHERE code LIKE 'mid_%';
  -- 预期 5 行，grade 范围 7-9
  ```
- 后端：
  - `app/services/docx_service.py` L49/L139：标题「小学{grade}年级」改为
    `("小学" if grade <= 6 else "初中") + f"{grade}年级..."`（L110/L207 文件名同理）
- 前端：
  - `web/src/App.vue` 年级选择器选项从 1-6 扩到 1-9（出卷弹窗、登录注册页年级选项排查）
- 测试：
  - tests/test_exam.py 新增用例：grade=8 生成数学卷，断言题目中可出现 mid_* 题型、Word 标题含「初中」
- 验收：八年级用户生成试卷自动包含一元二次方程/一次函数等题型

### A2 学期维度内容解锁（1 天）

现状问题：升级后一次性解锁该年级上下学期全部内容，与课堂节奏不符。

- 后端（无表结构变更，仅查询条件）：
  - `app/routers/vocab.py` `_get_grade_books`（现只取当前年级全部词书）：改为按当前日期定学期
    （9 月-次年 1 月 = 上，2-8 月 = 下），返回「当前年级当前学期词书」，
    低年级已学词由复习队列（VocabProgress）自然覆盖，新学入口只管当前学期
  - 家长设置 JSON 增 `include_next` 布尔开关（沿用 parent_task_settings.settings_json，无需迁移）：
    开启后额外返回「当前年级下学期」词书，支持假期预习
- 古诗文：
  - 迁移 **029_classical_semester.py**（方言兼容）：classical_texts 增
    `semester VARCHAR(10) DEFAULT '全'`；存量数据不动（'全' 表示两学期均可背）
  - `classical.py` /today 检索加同规则学期过滤（semester in ['全', 当前学期]）
- 前端：家长面板加「允许提前学下学期内容」开关
- 测试：用 monkeypatch/mock 模拟 3 月（下学期）与 10 月（上学期），断言词书范围；include_next 开启后含下学期
- 验收：六年级上学期用户只看到六上词书；2 月开学自动切换到六下

### A3 升年级引导（半天）

- 后端：`user.py` 登录接口在 `_auto_upgrade_grade` 前后对比年级，
  响应体增 `"promoted": true, "new_grade": N`（仅升级当天首次登录返回）
- 前端：收到 promoted 弹「恭喜升入 X 年级！已为你解锁新年级的学习内容」
- 测试：mock date 为 9 月 1 日，构造六年级用户，断言登录响应 promoted 标志

---

## 阶段 B：教材进度同步（约 3-5 天）

目标：新学内容跟随课堂进度（当前单元），而不是按词库顺序自学。

### B1 教学进度模型（1 天）

- 迁移 **030_teaching_progress.py**（方言兼容，SQLite/MySQL 都建表）：
  ```sql
  CREATE TABLE teaching_progress (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    user_id VARCHAR(64) NOT NULL,
    subject VARCHAR(20) NOT NULL,        -- 数学/语文/英语
    book_id INTEGER NULL,                -- 英语词书 ID（语文/数学可空）
    chapter VARCHAR(100) DEFAULT '',     -- 当前章节/单元（如 "Unit 3"）
    updated_at DATETIME,
    UNIQUE KEY uq_user_subject (user_id, subject)
  );
  ```
- API（新增于 app/routers/study.py）：
  - `GET /api/study/progress?user_id=&subject=` 读当前进度
  - `PUT /api/study/progress` 写进度（家长密码守卫 X-Parent-Pwd，沿用现有守卫模式）
  - `GET /api/study/progress/options?subject=&book_id=` 返回单元列表
    （英语：`SELECT DISTINCT unit FROM words WHERE book_id=? ORDER BY unit`；
    数学/语文：返回 ProblemType 章节或古诗文篇目分组，B3 前可先返回空）
- 前端：背诵中心与刷题中心顶部加「当前进度」选择器（词书 → 单元两级下拉），家长可改

### B2 背诵/听写同步模式（1-2 天）

- 家长设置 JSON 增 `sync_mode` 布尔开关（默认开）
- `vocab.py` /today 新词抽取：sync_mode 开启且存在英语教学进度时，
  候选词限定「当前 book_id 且 unit <= 当前 unit」（unit 按自然排序），
  不足额度时回退全量未学词（避免卡死）
- `dictation.py` 听写词源同样按当前 unit 过滤
- session-quiz / dictate 无需改动（它们只处理传入的 word_ids）
- 测试：设置进度为 Unit 2，断言 /today 新词均来自 Unit 1-2；关掉 sync_mode 恢复全量

### B3 数学章节同步（2 天，可选后置）

- 迁移 **031_problem_type_chapter.py**：problem_types 增
  `textbook_chapter VARCHAR(100) DEFAULT ''`（如「五年级上·第3单元·小数除法」）
- init_data 补现有题型的章节映射（人工整理，按人教版目录）
- `exam.py` generate_exam 增 `sync=true` 参数：数学卷优先从用户当前章节对应的题型抽取，
  无映射题型仍进随机池保底
- 验收：进度设为「分数除法」时，出卷集中出现该章节题型

---

## 阶段 C：初中内容扩充（约 4-6 天 + 数据制作，随孩子学段推进）

### C1 初中英语（2 天）

- 新增 `app/data/words_middle_school.csv`，**列结构与小学完全一致**：
  ```csv
  grade,semester,unit,word,phonetic,pos,meaning,difficulty,tags
  7,上,Starter Unit 1,hello,/həˈləʊ/,int.,你好,1,问候
  ```
  init_data.py 现有导入逻辑按「人教版PEP{grade}年级{semester}」建册，
  初中建议扩展命名（如「人教版Go for it 七年级上」）：
  init_data 增 publisher 列或按 grade>=7 切换教材名（约 20 行改动）
- 语法点：grammar_points 种子补初中内容（现在完成时/定语从句/宾语从句等，沿用现有格式）
- 词量验收标准（依据课标）：七年级约 500 词、八年级约 450 词、九年级约 400 词

### C2 初中语文（1 天）

- 迁移 **032_classical_middle_seed.py**：沿用 002_classical_seed.py 数据格式，
  插入初中必背古诗文（grade=7-9，约 60-80 篇，依据课标推荐篇目：
  《观沧海》《次北固山下》《岳阳楼记》《出师表》等）
- /today 的 `ClassicalText.grade <= grade` 检索天然包含初中篇目，无需改逻辑
- chinese_generator 静态题库（拼音/成语/阅读）暂不扩展，文档标注为后续人工补充项

### C3 小升初衔接模式（1 天）

- 家长设置 JSON 增 `xsc_bridge` 开关：六年级用户开启后，
  vocab/classical /today 的新学批次按 7:3 混合「六年级内容 + 七年级预习内容」
- 前端：家长面板「小升初衔接模式」开关 + 说明文案（仅六年级可见）

### C4 数据制作（与开发并行）

- 初中词汇 CSV：可从教材官方词表整理，注意音标与词性规范
- 古诗文篇目：以《义务教育语文课程标准》附录「优秀诗文背诵推荐篇目」为准
- 迁移脚本内数据必须含 UTF-8 全角标点校对，插入前按 title 唯一约束去重

---

## 优先级与排期建议

| 阶段 | 内容 | 工时 | 排期建议 |
|---|---|---|---|
| A1 | 初中数学打通 | 0.5 天 | 立即（几乎零成本） |
| A2 | 学期维度解锁 | 1 天 | 立即（课堂节奏刚需） |
| A3 | 升年级引导 | 0.5 天 | 随 A2 一并交付 |
| B1+B2 | 教学进度 + 背诵同步 | 2-3 天 | 第二批（家长核心诉求） |
| B3 | 数学章节同步 | 2 天 | 视 B2 反馈决定 |
| C1-C3 | 初中内容扩充与衔接 | 4-6 天 | 六年级下学期启动，数据制作提前并行 |

## 风险与注意事项

1. **迁移脚本**：029-032 均为新增脚本，必须方言兼容（SQLite/MySQL 双驱动真实执行），
   遵循 026_user_auth 的幂等写法（inspector 检查列/表存在性）
2. **学期判断边界**：2 月寒假与 8 月暑假的学期归属需与家长确认（当前方案：2-8 月为下学期，
   7-8 月实际是暑假，可通过 include_next 预习开关覆盖）
3. **unit 排序**：词库 unit 字段为字符串（如 "Unit 10"），自然排序需处理数字部分，
   建议新增 unit_order 数值列或用解析函数
4. **内容版权**：初中词汇与古诗文为课标公开内容，教材原文引用注意版权边界（古诗词无版权问题）
