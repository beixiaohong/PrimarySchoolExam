# 同步学、搜题智能解答与语文/英语能力增强（项目会讨论稿）

> 版本：v1.0（已决议）｜日期：2026-08-12｜状态：待批准实施（决议见第 11 节）
> 本文档用于项目会讨论，含现状盘点、方案选型对比、详细设计、排期估算与决议记录（第 11 节）。

---

## 1. 背景与目标

智学学堂已完成小学三科 + 初中九科的出题骨架、学期解锁、课堂同步雏形（仅英语）与多套 AI 能力（错题讲解/十万个为什么/AI 助手）。当前三个短板：

1. **同步学不成体系**：教学进度只有英语词册单元，缺少面向孩子的「跟课堂走」的学习入口；
2. **题目讲解被题库边界卡死**：AI 讲解只覆盖本系统题库内的错题，孩子课内作业、试卷上的题无法获得解答；
3. **语文/英语评测偏弱**：以客观题为主，缺作文/主观题评测、缺阅读专项、小学以上学段的课内同步素材不足。

**本期目标**（按用户确认的范围）：
- 落地「同步学」独立模块（年级-学期-单元三级导航，知识要点 + 同步练习 + 单元小测）；
- 落地「搜题智能解答」（本期只做文字录入；拍照 OCR 依 D2 决议延期至下期，本期预留流程与入口）；
- 语文/英语三线增强：题库与素材扩充、AI 主观题判分（作文/阅读简答）、阅读理解专项（全部要）。

**约束（延续既定决策）**：
- 生产 MySQL；新迁移仅写 MySQL 路径，runner 在 MySQL 下顺序执行（测试建表靠 create_all）；
- AI 种子数据标注「种子版，需人工校对」，不追求一步到位的内容准确性；
- AI 功能全部走钻石计费 + 限频，沿用现有体系；
- 语文课内课文全文不收录（版权），同步素材以古诗文 + 字词为主。

---

## 2. 现状盘点

### 2.1 可直接复用的资产

| 资产 | 位置 | 复用点 |
|---|---|---|
| 多供应商 AI 服务 | `app/services/ai.py` | zhipu（glm-4.7 付费优先 + flash 免费降级）/ relay 兜底 / deepseek（VIP）；`chat_with`、`rate_limit`、用量日志 |
| AI 问答缓存表 ai_qa | `app/models/ai_usage.py` | 全局缓存（同题不再请求 AI）、历史回看；q_type 已区分 qa/explain，可扩展 search |
| 错题讲解三段式 | `app/routers/ai.py` | 讲解 prompt 结构、explain-mark 一键错题、钻石扣费 `_deduct_diamonds` |
| 十万个为什么 | `app/routers/qa.py` | 多轮会话、缓存命中、限频 5 次/分、降级模板 |
| 教学进度 | teaching_progress 表（030）+ `/api/study/progress*` | 每用户每科一条 book_id+chapter，家长密码守卫 |
| 课堂同步过滤 | vocab.py `_sync_unit_filter` | sync_mode 按当前 unit 过滤新词，额度不足回退全量 |
| 九科题库 | middle_questions（033）+ middle_generator | 初中六科选择题已可出卷判分 |
| 语文/英语生成器 | chinese_generator / english_generator | 各 10 题型，静态模板可离线判分 |
| 学期服务 | `app/services/semester.py` | 当前/下学期判断，9-1 月=上、2-8 月=下 |
| 章节列 | problem_types.textbook_chapter（031） | 列已建、映射数据空缺 |

### 2.2 能力缺口（本期要补）

| 缺口 | 影响 |
|---|---|
| 无任意题目录入解答入口 | 课内作业题、外校试卷题无法讲解 |
| 无视觉模型接入 | 拍照搜题本期延期（D2 决议），仅保留文字录入与流程预留 |
| 同步学无孩子端入口 | 教学进度只是家长配置项，孩子感知不到「跟课堂」 |
| 数学章节映射数据空 | 数学无法按课堂章节出题 |
| 无作文/主观题判分 | 语文英语只能测客观题，评测价值受限 |
| 无阅读理解结构化题库 | 阅读仅 english_generator 的零散模板 |
| 初中语文题库空 | 033 六科种子不含语文（当时标注后续补充） |

---

## 3. 方向一：搜题智能解答

### 3.1 方案选型

| 方案 | 描述 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A. 纯文字搜题 | 粘贴/录入题干 → 本地题库匹配 → AI 讲解 | 零新增依赖、成本低、复用 ai_qa 缓存 | 孩子抄题麻烦 | 采用，先行 |
| B. 拍照搜题 | 图片 → 视觉模型识别题干 → 转文字流程 | 体验好、真实场景主流入口 | 需多模态端点（glm-4v 系）、识别错误需人工修正 | 延期（D2 决议），保留设计 |
| C. 接入第三方搜题 API | 买现成题库接口 | 命中率高 | 成本不可控、数据不自主、与现有错题体系割裂 | 否决 |

**推荐**：A 先行打通完整链路（含缓存/计费/错题本联动）；拍照搜题依 D2 决议延期至下期，本期预留前端入口与题干处理流程，届时只需补「识图 → 文本」前置一步。

### 3.2 处理流程（文字版）

```
孩子录入题干（可选学科）
  → 题干规范化（去空白/全半角/题号前缀）
  → 本地题库匹配（questions + middle_questions）
      相似度算法：规范化后双向字符 bigram 重合率，阈值 >= 0.6 视为命中
      命中 → 返回题目 + 参考答案 + 解析（有则展示）+「AI 讲解」按钮（走现有 explain 链路）
  → 未命中 → AI 讲解（provider 走免费链，与 qa 一致）
      system：按用户年级设定口吻；三段式【思路】【解答】【举一反三】，≤500 字，
             理科给步骤、文科给要点，禁止直接只给答案（先讲思路）
  → 成功解答写 ai_qa(q_type='search')，规范化题干作全局缓存 key
      相同题任意用户再搜 → cached=true 秒回
  → 解答页提供「加入错题本」→ 写 study/errors(source_type='search')
```

### 3.3 API 设计

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/search/ask` | POST | body：user_id, question_text(≤500 字), subject(可选)。返回：hit(是否命中题库), question, answer, explanation, ai_text, cached, diamond_cost |
| `/api/search/to-wrong` | POST | body：user_id, question, answer, subject。把搜到的题写入错题本（去重：同题干不重复入库） |
| `/api/search/history` | GET | query：user_id。返回本人搜题历史（ai_qa q_type=search 倒序，前 50 条） |
| `/api/search/image` | POST | 延期（下期）。body：user_id, image_base64(≤2MB), subject。视觉模型识题 → 内部转 ask 流程；返回同 ask + ocr_text。本期仅定义接口契约不实现 |

限频：ask 5 次/分钟/用户（复用 `ai_svc.rate_limit`）；image（下期）3 次/分钟。计费（D1 已决议）：命中缓存直接免费返回；仅 AI 实时解答走钻石扣费（diamond.check_and_deduct），扣费失败不阻断（与现状一致）。

### 3.4 拍照搜题预留设计（D2 决议延期，本期不实现）

- ai.py 新增 `chat_with_vision(user_id, system, text, image_b64)`：OpenAI 兼容 messages 携带 image_url(base64 data URI)；zhipu 侧用 glm-4v 系模型（.env 增加 `AI_VISION_MODEL` 配置，缺省关闭）；
- prompt：「识别图中题目文字，输出题干 + 选项，公式用文字描述」，识别结果回显可编辑，孩子确认后再走文字流程（缓存 key = 确认后的文本）；
- 视觉端点不可用（未配置/请求失败）时返回 503 + 明确文案「拍照搜题暂未开通，请先文字录入」。

### 3.5 前端

新增 nav「搜题」页：题干输入框（多行）+ 学科下拉（默认当前学科）+ 拍照按钮（本期置灰占位，点击提示「敬请期待」，下期点亮：input file + FileReader 转 base64，前端压缩至 ≤2MB）→ 解答卡片（命中题库/AI 解答两种样式区分）→「加入错题本」按钮 → 下方「我的搜题历史」列表（点击可回看解答）。

---

## 4. 方向二：同步学模块

### 4.1 方案选型

| 方案 | 描述 | 结论 |
|---|---|---|
| A. 独立同步学模块 | 新页面：年级-学期-单元导航，单元=要点+同步练习+单元小测 | **采用**（用户已确认） |
| B. 仅深化现有课堂同步 | 不加页面，只把章节过滤推广到出卷 | 否决（无孩子端感知） |

### 4.2 信息架构

```
同步学页
├─ 学科 tab（语文 / 数学 / 英语；grade>=7 时出九科）
├─ 当前教学进度条（来自 teaching_progress，家长面板维护）
└─ 单元卡片列表（当前年级 + 当前学期，semesters 复用 semester.py）
    ├─ 单元状态：未开始 / 进行中（做过练习）/ 已过关（小测 ≥80 分）
    ├─ 单元详情：
    │   ├─ 本单元要点（英语=单元词表+语法点；语文=篇目+字词；数学=题型清单）
    │   ├─ 同步练习（10 题以内，随做随判）
    │   └─ 单元小测（10 题，整卷判分，成绩进统计，错题进错题本）
```

### 4.3 各学科单元数据来源（关键设计决策）

| 学科 | 单元划分 | 数据源 | 本期数据工作 |
|---|---|---|---|
| 英语 | 词册 Unit | WordBook + Word.unit（已有） | 无新数据，直接可用 |
| 语文 | 学期篇目组 | classical_texts 按 grade+semester 分组为一「单元」；每单元附该年级字词素材 | classical_texts.unit 列 + 标注（037） |
| 小学数学 | 教材章节 | problem_types.textbook_chapter（031 列已有） | 034 补人教版 3-6 年级章节映射种子（每册 6-8 章） |
| 初中数学 | 知识点分组 | mid_* 题型标签（已有） | 无新数据，按知识点组织单元 |
| 初中六科（物理/化学/生物/道德与法治/历史/地理） | 教材章节 | middle_questions.unit 列（037 新增） | 各科题库按 7-9 年级章节标注（每年级 4-6 章），题库每科 20 → 30+ 题 |

D4 已决议覆盖九科：grade>=7 时同步学页展示全部九科单元。

### 4.4 API 设计

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/sync/overview` | GET | query：user_id, subject, grade。返回单元列表 [{unit, status, quiz_best, practice_done}]，学期过滤 + include_next 预习 |
| `/api/sync/unit-points` | GET | 单元要点（词表/篇目/题型清单） |
| `/api/sync/unit-practice` | GET | 单元同步练习：英语=该 unit 词汇选择/默写；语文=篇目默写翻译（复用 classical session-quiz）；数学=按 textbook_chapter 过滤出题 |
| `/api/sync/unit-quiz` | POST | 单元小测：整卷 10 题，判分走现有 answer_check，错题自动入错题本；成绩记录（034 迁移内建 sync_quiz_log 表） |

### 4.5 联动机制

- 单元小测自动联动每日任务（D3 已决议）：提交 unit-quiz 后自动计完成对应科目的 *_sync 任务（chi_sync/math_sync/eng_sync），不再需要家长手动确认；初中六科的小测计入该科目刷题类任务（如存在）；
- sync_mode 出题过滤推广：刷题中心出卷时若教学进度有数学 chapter，按章节过滤（开关同 sync_mode，不加新开关）。

### 4.6 前端

新增 nav「同步学」页 + 家长面板「教学进度」选择器扩展学科：英语=词册→单元（现状），语文=学期篇目组只读展示，小学数学=章节下拉（034 种子驱动），初中六科=章节下拉（037 标注驱动）。

---

## 5. 方向三：语文/英语能力增强

### 5.1 三线并进

#### 线 1 · 题库与素材扩充（离线可判分打底）

| 项 | 内容 | 迁移 | 规模（种子起步） |
|---|---|---|---|
| 初中语文题库 | middle_questions 补语文：字音字形/文学常识/古诗理解 | 037 | ≥30 题，grade 7-9 |
| 英语初中短语句子 | phrases/sentences 表补 grade 7-9 数据 | 037 | 短语 ≥80、句子 ≥60 |
| 语文单元标注 | classical_texts 加 unit 列 + 按课内单元标注 | 037 | 现有 48 篇标注 |
| 数学章节映射 | problem_types.textbook_chapter 人教版种子 | 034 | 3-6 年级每册 6-8 章 |
| 六科题库扩充与章节标注 | middle_questions 加 unit 列，各科题库扩至 30+ 题并按 7-9 年级章节标注（支撑 D4 九科同步学单元） | 037 | 六科 × 30+ 题 |

#### 线 2 · AI 主观题判分（钻石计费，补评测空白）

**作文批改**：
- POST `/api/ai/grade-essay`：user_id, subject(语文/英语), topic, content(≤800 字)；
- 输出评分卡：总分（分学段评分制，D5 已决议：小学语文 30 分制、初中语文 50 分制；小学英语 15 分制、初中英语 20 分制）+ 四维分项（内容/结构/语言/卷面）+ 亮点 2 条 + 改进建议 2 条 + 升格示例片段（1 段）；system prompt 按小学/初中两套评分标准拆分；
- 限频 3 次/分；035 迁移建 essay_grades 表（user_id, subject, topic, content, score_json, created_at），前端可回看历次批改对比。

**阅读简答判分**：
- POST `/api/ai/grade-short-answer`：user_id, question, reference_points（参考答案要点）, user_answer；
- AI 按要点分档（0/1/2）给分 + 一句话评语；服务于阅读理解专项的主观题，也开放给搜题追问场景。

#### 线 3 · 阅读理解专项

- 036 迁移建 reading_passages 表：subject, grade, semester, title, passage, questions_json（每题：type=choice/short, question, options, answer, points 要点, score 分值）；
- 种子规模：英语 7-9 年级各 5 篇（每篇 4-5 选择题）；语文小学高段 5 篇 + 初中 6 篇（客观选择 + 1-2 道主观简答）；
- english_generator 新增 `reading_choice` 题型接入出卷分发；
- 刷题中心新增「阅读专项」入口：按年级抽篇 → 逐题作答 → 客观即时判分、主观走 AI 判分 → 结束展示逐题解析与得分。

### 5.4 多 AI 联合校对机制（D6 决议，数据质量闸门）

种子/扩充数据不再依赖单点人工校对，改为「机器先行、人工兼底」：

```
新种子数据写入（题库/阅读篇目/词句素材）→ 生成校对任务
  → 多 AI 独立审阅：至少 2 个独立供应商（免费链 zhipu + VIP 链 deepseek/relay）
     各自审：题干正确性、答案正确性、干扰项有效性、年级/难度标注匹配
     输出 verdict(pass/fail) + 理由
  → 汇总规则：全部 pass → review_status=approved，可参与出题
             存在 fail 或意见不一 → review_status=conflict → 进管理后台人工审核队列
  → 人工裁决：采纳(approved) / 驳回(rejected，剔除出出题池) / 修改后重新送审
```

落地要点：
- 038 迁移：content_reviews 表（content_type, content_id, provider, model, verdict, comment, created_at）；middle_questions / reading_passages 加 review_status 列（默认 pending，approved 才进出题池）；
- admin.py 扩展：POST /api/admin/reviews/run（批量触发多 AI 校对）、GET /api/admin/reviews（按 status=conflict 过滤队列）、POST /api/admin/reviews/resolve（人工裁决）；
- 管理后台新增「内容校对」队列页：意见分歧项列表，并排展示各 AI 的意见与理由，一键裁决。

---

## 6. 数据模型与迁移清单（MySQL-only）

| 迁移 | 内容 | 类型 |
|---|---|---|
| 034_sync_chapters | problem_types 数学章节映射种子 + sync_quiz_log 表（user_id, subject, unit, score, total, created_at） | 建表+种子 |
| 035_essay_grades | essay_grades 表 | 建表 |
| 036_reading_passages | reading_passages 表 + 阅读种子 | 建表+种子 |
| 037_lang_seed | 初中语文题库 + 英语初中短语句子 + classical_texts.unit 标注 + middle_questions.unit 列与六科章节标注、题库扩充 | 加列+种子 |
| 038_content_review | content_reviews 多 AI 校对记录表 + middle_questions/reading_passages 加 review_status 列 | 建表+加列 |

配套 ORM 模型（app/models/）：EssayGrade、ReadingPassage、SyncQuizLog、ContentReview，供 create_all 在测试库建表。ai_qa 无需加列（q_type='search' 复用）。

## 7. API 总览（新增 15 个）

搜题：ask / to-wrong / history / image（延期，仅定义契约）
同步学：overview / unit-points / unit-practice / unit-quiz
AI 判分：grade-essay / grade-short-answer
阅读：passages(抽篇) / submit(交卷判分)
管理后台校对：reviews/run / reviews / reviews/resolve

## 8. 里程碑与工作量估算

| 里程碑 | 内容 | 估算 | 验收要点 |
|---|---|---|---|
| M1（P0） | 文字搜题全链路 + 同步学骨架（英语/语文单元可用）+ 034 | 4-5 人日 | 搜题命中缓存与 AI 降级可用；同步学页英语单元练习+小测闭环 |
| M2（P1） | 作文批改 + 阅读简答判分 + 同步学扩数学（章节出题）+ 035 | 3-4 人日 | 作文评分卡落库可回看；数学按章节出小测卷 |
| M3（P2） | 阅读专项 + 题库扩充与九科章节标注 + 多 AI 校对机制与管理后台审核队列 + 036/037/038 + 文档 | 6-7 人日 | 阅读专项逐题解析；校对机制双供应商跑通、分歧项进后台队列；同步学九科单元可导航 |

每个里程碑内部：后端→测试→前端→build→pytest 全绿→推送。合计约 13-16 人日；拍照搜题依 D2 延期至下期，不计入本期。

## 9. 测试与验收

- 新增测试文件：test_search.py（缓存命中/降级/限频 400/一键错题本去重）、test_sync_study.py（学期过滤、三科单元结构、小测判分与成绩落库）、test_essay.py（评分卡结构、历史回看；mock ai_svc）、test_reading.py（按年级抽篇、客观判分、主观题走 AI mock）；
- 全量 pytest 保持绿（当前 58 用例基线）+ `npm run build` 通过；
- AI 用例一律 mock 外部调用，不依赖真实 API key；
- M3 结束后浏览器端到端抽验搜题与同步学主链路。

## 10. 风险与依赖

| 风险 | 等级 | 缓解 |
|---|---|---|
| AI 讲解质量不稳（超纲/错误） | 中 | prompt 约束年级口吻 + 三段式；缓存命中题优先展示题库解析；家长端可关闭 AI 功能（现状已有） |
| 视觉模型无可用端点 | 低 | 拍照搜题本期延期（D2），仅预留接口与入口，风险本期不存在 |
| 种子数据准确性 | 中 | 多 AI 联合校对（5.4）：机器先行批量审、意见分歧进管理后台人工裁决，驳回内容剔出出题池；结构正确可判分为验收线 |
| 数学章节映射量大 | 低 | 先覆盖 3-6 年级人教版主干章节；初中章节后续补 |
| 阅读/作文 AI 判分成本 | 低 | 钻石计费 + 限频；作文限 800 字、简答要点判分 token 小 |
| 本地题库命中率低 | 低 | 搜题定位是「AI 解答入口」而非「题库检索」，未命中即走 AI，体验不断链 |

## 11. 决议记录（2026-08-12 项目会）

| 编号 | 事项 | 结论 | 对方案的影响 |
|---|---|---|---|
| D1 | 搜题计费 | 命中缓存免费；AI 实时解答才扣钻石 | 3.3 计费规则已固化 |
| D2 | 拍照搜题供应商 | 待定，延期；本期只做文字搜题 | 拍照移出 M3，降为预留设计（3.4） |
| D3 | 单元小测与 *_sync 任务 | 自动联动，不再需家长手动确认 | 4.5 已固化 |
| D4 | 同步学覆盖学科 | 九科全覆盖 | 4.3 新增初中六科单元数据源（middle_questions.unit，037） |
| D5 | 作文批改学段 | 小学 + 初中 | 5.1 分学段评分制（语文 30/50、英语 15/20） |
| D6 | 数据校对责任人 | 多 AI 联合校对，意见不一时管理后台人工审核 | 新增 5.4 机制 + 038 迁移 + admin 审核队列 |

---

## 附：与既有 ROADMAP 的关系

- 完成遗留项 B3（数学章节映射）：并入本方案 034；
- 完成遗留项「初中语文静态题库」：并入本方案 037；
- 种子数据人工校对遗留项：转为 D6 决议事项，不再阻塞开发。
