// gaoxiang.js：软考高项备考（面向非学生成人用户）的 data / computed / methods。
// 仅依赖通用 api/goTab/showToast（通用方法保留在主文件）；与其他 logic/* 经展开运算符
// 合并后 this 仍绑定同一实例。后端契约见 app/domains/assessment/routers/gaoxiang.py：
//   GET  /api/gx/domains                    -> {domains, qtypes, chapters, wrong_kinds, pass_score}
//   GET  /api/gx/catalog                    -> {source_kinds:[{value,count}], chapters:[...], qtypes}
//   GET  /api/gx/knowledge?user_id&domain&chapter&kind&q
//                                           -> {items:[{id,domain,code,title,summary,chapter,kind,source_file}]}
//   GET  /api/gx/knowledge/{kid}?user_id    -> {id,...,content}
//   POST /api/gx/knowledge/generate         {user_id,domain} -> {generated,added}
//   POST /api/gx/quiz/generate              {user_id,domain,qtype,count,source_kind,chapter,scope}
//                                           -> {count,ai_added,questions:[{id,qtype,question,options,chapter,source_kind,deck}]}
//   POST /api/gx/quiz/submit                {user_id,answers:[{question_id,answer,duration_ms}]}
//                                           -> {wrong_count, results:[{question_id,judged,is_correct,correct,analysis}]}
//   GET  /api/gx/case/sub/list          ?user_id&domain&limit -> 按小问展开（不新增题目行）
//   POST /api/gx/case/sub/grade         {user_id,question_id,sub_index,user_answer}
//   GET  /api/gx/case/list|/essay/list      ?user_id&domain&chapter&source_kind
//                                           -> {items:[{id,title,domain,chapter,source_kind,sub_count,background}]}
//   GET  /api/gx/case/{qid} | /essay/{qid}  -> {background, sub_questions:[{q,answer,points}], ...}
//   POST /api/gx/case/generate              {user_id,domain} -> {question_id,...}
//   POST /api/gx/case/grade                 {user_id,question_id,user_answer}
//                                           -> {score,feedback,pass_score,in_wrong_book}
//   POST /api/gx/essay/grade                {user_id,question_id,user_answer}
//                                           -> {score,rubric:[{dim,score,comment}],feedback,pass_score,in_wrong_book}
//   GET  /api/gx/wrong?user_id&kind          -> {items:[...],count,by_kind:{choice,case,essay}}
//   POST /api/gx/wrong/analyze              {user_id,question_id|0,limit,force}
//                                           -> {analyzed,items:[{question_id,ok,reason_type,analysis,tips}]}
//   POST /api/gx/wrong/master               {user_id,question_id}
//   GET  /api/gx/progress?user_id           -> {domains:[...], summary:{...}}
//
// 设计约定：
// 1. 判分在服务端（答案不下发前端），前端只做展示与提交；AI 生成均可能慢（数秒），
//    相关按钮一律带 loading 防重复点击。
// 2. **错题闭环**：选择题提交后自动对答错的题（最多 AUTO_ANALYZE_MAX 道）调
//    `/wrong/analyze` 拿错因并就地展示，做到「做完立刻有分析」；分析与缓存都在服务端，
//    再看错题本不再重复扣费。案例/论文批改低于 60 分由服务端自动入错题本，前端同样自动分析。

// 论文四维评分：维度中文名与权重（与后端 ESSAY_GRADE_SYSTEM_PROMPT 保持一致）
const RUBRIC_LABELS = {
  relevance: '切题与完整性',
  structure: '结构与管理过程',
  practice: '项目实践与真实性',
  writing: '文字表达与字数',
};
const RUBRIC_WEIGHTS = { relevance: 35, structure: 25, practice: 25, writing: 15 };

// 一次提交最多自动分析几道错题：每题一次 AI 调用（数秒），限量以免提交后长等待
const AUTO_ANALYZE_MAX = 3;

// 知识点资料类型中文名兜底（正常从后端 catalog.knowledge_kinds 取，这里保证首屏不空白）
const KN_LABELS_FALLBACK = {
  list: '知识点清单', mindmap: '思维导图', recite: '速记清单', must: '必背考点',
  formula: '公式汇总', mnemonic: '记忆口诀', itto: '过程与ITTO', slide: '课堂课件',
  textbook: '教材考纲', ref: '参考汇总', ai: 'AI 生成',
};

// 错题本题型分栏（与后端 WRONG_KINDS 对齐）
const WRONG_TABS = [
  { k: '', label: '全部' },
  { k: 'choice', label: '选择题' },
  { k: 'case', label: '案例' },
  { k: 'essay', label: '论文' },
];

/* ── 正文结构化（展现形式优化）─────────────────────────────────────
 * 后端存的是 PDF/AI 抽取原文。直接平铺 <p> 会把「1.」「（1）」「一、」条目
 * 和小标题糊成一大坨。这里把每行分类成小标题 / 条目 / 段落，连续条目归组为列表。
 *
 * 知识点清单 PDF 常见「----」层级分隔（如「网络存储3种技术----DAS----无需网络…」），
 * 预处理器 _gxKPreprocess 把它展开成 • / ◦ / ▪ 多层列表，避免所有内容糊成一段。
 *
 * 空括号（万一还有遗留数据）渲染为填空线；数据层已把填空清单转成完整知识点，
 * 正常不应再出现空框。
 * 只输出结构（gxKParseBlocks）与输出 HTML（gxKBlocksHtml）分离：结构可单测，
 * HTML 拼装前对每段文本做转义（内容来自自家库的 PDF/AI 抽取，转义是双保险）。
 */
// 小标题：章/节行、中文序号行（短且不成句）、多级编号行（如 1.2 / 2.3.1）。
// 判定保守 —— 长行宁可当段落，误判标题比漏判标题更伤排版。
const GX_K_H_RE = [
  /^第[一二三四五六七八九十百\d]{1,4}[章节讲篇]/,
  /^[一二三四五六七八九十]{1,3}、/,
  /^\d{1,2}(?:\.\d{1,2}){1,2}(?!\d)\s/,
];
// 条目前缀：1. / 1、 / 1． / （1） / (1) / • / ◦ / ▪ 等。`(?!\d)` 防止把多级编号「1.2」
// 吃成条目「1.」+ 正文「2 xxx」（多级编号已先被标题规则接走，这里是双保险）。
// 圆点分三级：•(l1) ◦(l2) ▪(l3)，用于把 PDF 里的「----」层级展开成缩进列表。
const GX_K_LI_RES = [
  [/^（\d{1,3}）\s*/, null, 'p'], [/^\(\d{1,3}\)\s*/, null, 'p'],
  [/^\d{1,3}[、．](?!\d)/, null, 'n'], [/^\d{1,3}\.(?!\d)\s*/, null, 'n'],
  [/^[-–]\s+/, '•', 'b1'],
  [/^[•·●]\s?/, '•', 'b1'], [/^◦\s?/, '◦', 'b2'], [/^▪\s?/, '▪', 'b3'],
];
// 空括号（允许内部空白）→ 填空空框。括号里有内容（如「（如 GB/T）」）不动。
const GX_K_BLANK_RE = /（\s*）|\(\s*\)/g;
// PDF 层级分隔符：「网络存储3种技术----直接附加存储DAS ----无需网络…」
// 一行里出现多个 ---- 时，展开成「主题 / 术语 / 描述」（见 _gxKPreprocess）。
const GX_K_DASH_SEP_RE = /[-—]{2,}/;
// 描述行标记：预处理器给「最后一段（描述）」加的前缀 —— 渲染为缩进段落、不带符号
const GX_K_DESC_RE = /^»\s?/;

function _gxKPreprocess(text) {
  /** 把 PDF 里用 `----` 连接的层级结构展开成「主题 / 术语 / 描述」。

   * PDF 原排版是缩进树（`----` 实为缩进引导线），但 PDF 文本抽取**不保留缩进**
   * （实测 fitz get_text 每行 x0 全为 0），所以只能按 `----` 分段还原：
   * **最后一段是描述，前面各段是主题 / 子术语**——这与原 PDF 一致
   * （如「网络存储3种技术----DAS----无需网络…」里 DAS 是术语、其后是它的描述）。
   *
   * 例：
   *   网络存储3种技术----直接附加存储DAS ----无需网络…；
   * → 网络存储3种技术
   *   • 直接附加存储DAS
   *     无需网络…；            （缩进段落，不带符号，贴近 PDF 观感）
   *
   * 行首以 ---- 开头（上一行的延续）时，第一级不输出，直接从 • 开始。
   * 只处理确实含 `----` 且能拆出 ≥2 个非空片段的行，避免误伤正文里的少量横线。
   */
  return (text || '').split('\n').map(line => {
    if (!GX_K_DASH_SEP_RE.test(line)) return line;
    const parts = line.split(GX_K_DASH_SEP_RE).map(s => s.trim());
    const leading = parts[0] === '';
    if (leading) parts.shift();
    // 去掉两端空串后不足两段，保持原样
    const clean = parts.filter(Boolean);
    if (clean.length < 2) return line;
    const head = leading ? '' : clean.shift() + '\n';
    // 最后一段是描述（缩进段落、不带符号）；中间各段是逐级子术语
    const desc = clean.pop();
    const markers = ['•', '◦', '▪'];
    const body = clean.map((p, i) => {
      const marker = markers[Math.min(i, markers.length - 1)] || '•';
      return marker + ' ' + p;
    });
    body.push('» ' + desc);
    return (head + body.join('\n')).trim();
  }).join('\n');
}

function _gxKLineKind(line) {
  // 描述行（由预处理器从 ---- 末段展开）：缩进段落，不参与列表分组
  if (GX_K_DESC_RE.test(line)) {
    return { kind: 'desc', rest: line.replace(GX_K_DESC_RE, '') };
  }
  if (line.length <= 40 && GX_K_H_RE.some(re => re.test(line))
      && !(line.length > 30 && line.includes('。'))) {
    return { kind: 'h' };
  }
  for (const [re, fixed, cls] of GX_K_LI_RES) {
    const m = re.exec(line);
    if (m) {
      const no = fixed != null ? fixed : m[0].trim();
      return { kind: 'li', no, cls, rest: line.slice(m[0].length).trim() };
    }
  }
  return { kind: 'p' };
}

// 一行 → 文本/空框片段序列（blank=true 的位置渲染为填空线）
function _gxKSegs(line) {
  const segs = [];
  let last = 0, m;
  GX_K_BLANK_RE.lastIndex = 0;
  while ((m = GX_K_BLANK_RE.exec(line))) {
    if (m.index > last) segs.push({ s: line.slice(last, m.index), blank: false });
    segs.push({ s: m[0], blank: true });
    last = m.index + m[0].length;
  }
  if (last < line.length) segs.push({ s: line.slice(last), blank: false });
  return segs.length ? segs : [{ s: line, blank: false }];
}

export function gxKParseBlocks(text) {
  /** 结构化正文。行首缩进即层级（每 2 个空格一级）——
   *  由 `tools/gx_pdf_tree.py` 按 PDF 真实缩进坐标生成，与 PDF 视觉排版一一对应。
   *  旧数据没有缩进（level 恒为 0），此时退回用 •/◦/▪ 符号类别判层级，行为不变。
   */
  const lines = _gxKPreprocess(text).split('\n');
  const blocks = [];
  for (const raw of lines) {
    if (!raw.trim()) continue;
    // 不能用 trim() 丢掉缩进：层级就带在前导空格里
    const lead = (raw.match(/^[ \t]*/) || [''])[0];
    const level = Math.floor(lead.replace(/\t/g, '  ').length / 2);
    const line = raw.trim();
    const k = _gxKLineKind(line);
    if (k.kind === 'h') {
      blocks.push({ type: 'h', text: line, level });
    } else if (k.kind === 'desc') {
      blocks.push({ type: 'desc', segs: _gxKSegs(k.rest), level });
    } else if (k.kind === 'li') {
      const segs = _gxKSegs(k.rest);
      const last = blocks[blocks.length - 1];
      // 层级不同不归为同一组，否则不同级条目会被并成一个列表
      if (last && last.type === 'ul' && last.cls === k.cls && last.level === level) {
        last.items.push({ no: k.no, segs });
      } else {
        blocks.push({ type: 'ul', cls: k.cls, level, items: [{ no: k.no, segs }] });
      }
    } else {
      blocks.push({ type: 'p', segs: _gxKSegs(line), level });
    }
  }
  return blocks;
}

function _gxKEsc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _gxKLv(b) {
  /** 层级：行首缩进优先（PDF 重解析数据）；没有缩进时退回用符号类别判（旧数据） */
  if (b.level > 0) return b.level;
  if (b.cls === 'b3') return 3;
  if (b.cls === 'b2') return 2;
  if (b.cls === 'b1') return 1;
  return 0;
}

export function gxKBlocksHtml(text) {
  const segsHtml = segs => segs.map(sg =>
    sg.blank ? '<span class="gx-k-blank"></span>' : _gxKEsc(sg.s)).join('');
  // 层级 → class（最多 5 级），交给 CSS 决定缩进量
  const lvCls = lv => (lv > 0 ? 'gx-k-lv' + Math.min(lv, 5) : '');
  return gxKParseBlocks(text).map(b => {
    if (b.type === 'h') {
      return '<div class="gx-k-h ' + lvCls(_gxKLv(b)) + '">' + _gxKEsc(b.text) + '</div>';
    }
    if (b.type === 'ul') {
      const lv = lvCls(_gxKLv(b));
      return '<div class="gx-k-ul ' + lv + '">' + b.items.map(li =>
        '<div class="gx-k-li">'
        + (li.no ? '<span class="gx-k-li-no">' + _gxKEsc(li.no) + '</span>' : '')
        + '<span class="gx-k-li-tx">' + segsHtml(li.segs) + '</span></div>').join('')
        + '</div>';
    }
    if (b.type === 'desc') {
      // 描述已有 .gx-k-desc 的固定缩进，再叠加层级缩进
      return '<p class="gx-k-desc ' + lvCls(_gxKLv(b)) + '">' + segsHtml(b.segs) + '</p>';
    }
    return '<p class="' + lvCls(_gxKLv(b)) + '">' + segsHtml(b.segs) + '</p>';
  }).join('');
}

export function gaoxiangData() {
  return {
    // ── 通用 ──
    gxSub: 'quiz',          // 子页签：quiz / knowledge / case / essay / wrong / progress
    gxDomains: [],          // 考纲 24 章（章名即知识域名）
    gxChapters: [],         // [{no,name,label}] 供章节下拉兜底
    gxPassScore: 60,        // 主观题及格线（低于它自动进错题本）
    gxLoading: false,       // 首次进入总开关
    gxCatalog: null,        // {source_kinds, chapters} 只含库里有条目的筛选项
    gxSecretTaps: 0,        // 隐藏入口计数：设置页「关于」行连点 5 次跳转高项页（不对外展示导航）
    // ── 知识点 ──
    gxKDomain: '',          // '' = 不限知识域
    gxKChapter: '',
    gxKKind: '',            // 资料类型（list/mindmap/recite/slide/textbook…），'' = 全部按类型分节
    gxKQ: '',               // 关键词（标题/正文模糊匹配）
    gxKList: [],            // 列表（无正文）
    gxKLoading: false,
    gxKDetail: null,        // 当前阅读的知识点（含 content）
    gxKGenning: false,      // AI 生成中
    // ── 刷题 ──
    gxQDomain: '',          // '' = 不限（配合资料筛选刷整套）
    gxQType: 'single',      // single / multi
    gxQCount: 5,
    gxUseAi: false,         // 勾选后才允许 AI 补题（source='all'）；默认只用已导入的真题库（source='import'），不产生 AI 费用
    gxQSourceKind: '',      // 资料子类：每日一练 / 章节练习 / 仿真模拟…
    gxQChapter: '',         // 规范章节名
    gxQScope: '',           // ''=常规刷题；'wrong'=错题重练
    gxQuestions: [],        // [{id,qtype,question,options,chapter,source_kind}]
    gxAnswers: {},          // qid → 'A'/'ABD'
    gxQResult: null,        // {wrong_count, results:[{question_id,judged,is_correct,correct,analysis}]}
    gxQLoading: false,
    gxQSubmitting: false,
    gxQStartAt: 0,          // 本组题开始时间（算用时）
    gxQAiAdded: 0,          // 本组题里 AI 现场补了几道
    // 错因分析：{question_id: 分析文本}，就地展示避免整表重载
    gxReasonMap: {},
    gxAnalyzing: null,      // {total,done} 自动分析进度；null=不在分析
    // ── 案例分析 ──
    gxCaseDomain: '',
    gxCaseList: [],         // 资料案例题列表
    gxCaseListLoading: false,
    gxCaseDetail: null,     // {id,title,background,sub_questions:[{q,answer,points}],analysis}
    gxCaseExtra: null,      // AI 现场出的题（未落库则无 id，走 question_text 批改）
    gxC_answer: '',         // 作答全文
    gxC_result: null,       // {score,feedback,pass_score,in_wrong_book}
    gxCaseGrading: false,
    gxCaseGenning: false,
    gxCaseShowAnswer: false,// 是否展开参考答案要点（批改后才建议看）
    // ── 案例「按小问刷」：展示层把一道大题的 3~4 个小问展开成一问一练 ──
    // 后端不新增题目行（`key = 题目id#小问下标` 只用于前端定位），批改时只把该小问
    // 交给 AI —— prompt 短、反馈聚焦、单次消耗低；错题本仍按整道大题归集。
    gxCaseModes: [          // 案例页两种练习方式
      { k: 'whole', label: '整卷练习' },
      { k: 'sub', label: '按小问刷' },
    ],
    gxCaseMode: 'whole',    // 'whole' | 'sub'
    gxSubList: [],          // [{key,question_id,sub_index,title,domain,chapter,points,q,has_answer}]
    gxSubLoading: false,
    gxSubIdx: 0,            // 当前小问在列表里的下标（不是小问序号，序号是 sub_index）
    gxSubDetail: null,      // 当前小问所属大题详情（背景与参考答案要点）
    gxS_answer: '',
    gxSubGrading: false,
    gxSubResult: null,      // {score,earned,points,feedback,pass_score,in_wrong_book}
    gxSubAnswers: {},       // key -> 上次作答（来回切不丢草稿）
    gxSubScores: {},        // key -> 历史得分（localStorage 持久化，刷新后仍在）
    gxSubShowBg: true,      // 案例背景默认展开（小问依赖情境，必须先读背景）
    gxSubShowAnswer: false,
    // ── 论文练习 ──
    gxEssayDomain: '',
    gxEssayList: [],
    gxEssayLoading: false,
    gxEssayDetail: null,    // {id,title,background,sub_questions（论述要求）,...}
    gxE_answer: '',
    gxE_result: null,       // {score,rubric,feedback,pass_score,in_wrong_book}
    gxEssayGrading: false,
    gxEssayShowReq: true,   // 是否展开论述要求
    // ── 错题本 ──
    gxWrong: [],
    gxWrongKind: '',        // '' / choice / case / essay
    gxWrongByKind: { choice: 0, case: 0, essay: 0 },
    gxWrongLoading: false,
    gxWrongAnalyzing: 0,    // 正在分析哪道题（question_id），0=无
    gxWrongBatchAnalyzing: false,
    // ── 进度 ──
    gxProgress: null,
  };
}

export const gaoxiangComputed = {
  // 刷题结果按 qid 索引，模板取用方便
  gxResultMap() {
    const m = {};
    ((this.gxQResult && this.gxQResult.results) || []).forEach(r => { m[r.question_id] = r; });
    return m;
  },
  // 本组题是否全部作答（未答完禁用提交）
  gxAllAnswered() {
    return this.gxQuestions.length > 0 &&
      this.gxQuestions.every(q => (this.gxAnswers[q.id] || '').trim());
  },
  // 本组题对了几道（提交后顶部的结算条）
  gxCorrectCount() {
    return ((this.gxQResult && this.gxQResult.results) || [])
      .filter(r => r.is_correct === true).length;
  },
  // 未判分的题数（资料里没抓到的题：无参考答案，不计错、不入错题本）
  gxUngradedCount() {
    return ((this.gxQResult && this.gxQResult.results) || [])
      .filter(r => r.judged === false).length;
  },
  // 本组错题数（服务端已入错题本）
  gxWrongCountOfQuiz() {
    return ((this.gxQResult && this.gxQResult.results) || [])
      .filter(r => r.judged && r.is_correct === false).length;
  },
  // 案例作答是否可提交（至少 20 字，避免空跑一次 AI）
  gxC_canSubmit() {
    return (this.gxC_answer || '').trim().length >= 20 && !this.gxCaseGrading;
  },
  // ── 按小问刷（展示层展开，不新增题目行）──
  gxSubCur() {
    return this.gxSubList[this.gxSubIdx] || null;
  },
  // 已练小问数：只统计当前列表里的 key（换知识域筛选后不串数）
  gxSubDoneCount() {
    const s = this.gxSubScores || {};
    return (this.gxSubList || []).filter(it => s[it.key] !== undefined).length;
  },
  gxSubCanSubmit() {
    return (this.gxS_answer || '').trim().length >= 5 && !this.gxSubGrading && !!this.gxSubCur;
  },
  // 背景：小问依赖情境，必须能读到；详情是异步拉的，未到位时给占位
  gxSubBgText() {
    const cur = this.gxSubCur, d = this.gxSubDetail;
    if (!cur || !d || d.id !== cur.question_id) return '背景加载中…';
    return d.background || '（这道案例没有背景材料）';
  },
  // 当前小问的参考答案要点（详情到位后才有；资料没给就是空串）
  gxSubRefAnswer() {
    const cur = this.gxSubCur, d = this.gxSubDetail;
    if (!cur || !d || d.id !== cur.question_id) return '';
    return (((d.sub_questions || [])[cur.sub_index] || {}).answer) || '';
  },
  // 论文正文是否可提交（服务端要求 ≥100 字；2000 字才是考试要求，前端只做提示）
  gxE_canSubmit() {
    return (this.gxE_answer || '').trim().length >= 100 && !this.gxEssayGrading && !!this.gxEssayDetail;
  },
  // 论文字数（去空白计，贴近期刊/考试的「字数」口径）
  gxEssayWords() {
    return (this.gxE_answer || '').replace(/\s/g, '').length;
  },
  // 论文四维评分行（补中文维度名与权重，模板直接渲染）
  gxEssayRubric() {
    return (((this.gxE_result || {}).rubric) || []).map(r => ({
      dim: r.dim,
      label: RUBRIC_LABELS[r.dim] || r.dim,
      weight: RUBRIC_WEIGHTS[r.dim] || 0,
      score: r.score,
      comment: r.comment,
    }));
  },
  // 错题本按当前分栏过滤（服务端已给 by_kind 计数，这里只做前端过滤，省一次请求）
  gxWrongShown() {
    if (!this.gxWrongKind) return this.gxWrong;
    return this.gxWrong.filter(w => w.kind === this.gxWrongKind);
  },
  gxWrongTabs() { return WRONG_TABS; },
  // 进度总览（未加载时兜底空结构）
  gxProgressRows() {
    return (this.gxProgress && this.gxProgress.domains) || [];
  },
  // 点选 chip 时统一按 value 取（catalog 项为 {value,count}）
  gxSourceKindOptions() {
    return ((this.gxCatalog || {}).source_kinds) || [];
  },
  gxChapterOptions() {
    return ((this.gxCatalog || {}).chapters) || [];
  },
  // 知识点资料类型（后端按 KN_ORDER 排序，含中文 label 与条数）——知识点页的首层筛选
  gxKKindOptions() {
    return ((this.gxCatalog || {}).knowledge_kinds) || [];
  },
  gxKChapterOptions() {
    return ((this.gxCatalog || {}).knowledge_chapters) || [];
  },
  // 知识点列表按「资料类型」分节：类型不同可读性差很多（必背清单 vs 课堂课件），
  // 混在一个列表里就是用户说的「内容很混乱」→ 不筛选时按类型分节展示
  gxKGroups() {
    const list = this.gxKList || [];
    // readN = 该节里已读了几条（分组头显示「已读 x」）。已读状态由列表接口给出
    // （后端按 user 批量查 gx_knowledge_reads，见 routers/gaoxiang.list_knowledge）
    const readN = (items) => items.filter(k => k.read).length;
    if (this.gxKKind) {
      return [{ kind: this.gxKKind, label: this.gxKKindLabel(this.gxKKind),
                items: list, readN: readN(list) }];
    }
    const order = this.gxKKindOptions.map(k => k.value);
    const map = {};
    list.forEach(k => {
      const key = k.kind || 'list';
      if (!map[key]) map[key] = [];
      map[key].push(k);
    });
    return Object.keys(map)
      .sort((a, b) => {
        const ia = order.indexOf(a), ib = order.indexOf(b);
        return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
      })
      .map(k => ({ kind: k, label: this.gxKKindLabel(k), items: map[k],
                   readN: readN(map[k]) }));
  },
  // 知识点正文结构化 HTML（后端存的是 PDF 抽取原文，直接塞 div 会挤成一大坨）：
  // 小标题/条目/空框的解析与拼装见顶部 gxKParseBlocks / gxKBlocksHtml。
  // 2026-09-29：填空速记已统一转成完整知识点，不再分「题目 / 答案」两段展示。
  gxKHtml() {
    return gxKBlocksHtml(((this.gxKDetail || {}).content) || '');
  },
};

// 错因分析文本拼装（与后端写库格式一致：`【类型】分析` + 记忆锚点）
function reasonText(it) {
  return `【${(it && it.reason_type) || '其它'}】${(it && it.analysis) || ''}`
    + (((it && it.tips)) ? `\n记忆锚点：${it.tips}` : '');
}

export const gaoxiangMethods = {
  /* ─────────── 进入页面（goTab('gaoxiang') 钩子调用） ─────────── */
  initGaoxiang() {
    if (!this.user) return;
    if (!this.gxDomains.length) {
      this.api('/api/gx/domains').then(d => {
        this.gxDomains = (d && d.domains) || [];
        this.gxChapters = (d && d.chapters) || [];
        if (d && d.pass_score) this.gxPassScore = d.pass_score;
      }).catch(() => {});
    }
    this.gxLoadCatalog();
    this.gxLoadProgress();
    this.gxLoadKnowledge();
    this.gxLoadWrong();
    // 不再进页自动出题：由用户选好题型/筛选后点「开始练习」（AI 出题还需显式勾选 gxUseAi）
  },

  // 隐藏入口：设置页「关于」行连点 5 次 → 跳转高项备考（该页不在侧边栏展示，仅供本人使用）
  gxSecretTap() {
    this.gxSecretTaps += 1;
    if (this.gxSecretTaps >= 5) {
      this.gxSecretTaps = 0;
      this.goTab('gaoxiang');
    } else if (this.gxSecretTaps >= 3) {
      this.showToast(`再点 ${5 - this.gxSecretTaps} 次进入高项备考`);
    }
  },

  // 筛选项（只含库里有条目的）——失败也不影响主流程
  gxLoadCatalog() {
    this.api('/api/gx/catalog').then(d => { this.gxCatalog = d || null; }).catch(() => {});
  },

  /* ─────────── 知识点 ─────────── */
  gxLoadKnowledge() {
    this.gxKLoading = true;
    const p = new URLSearchParams({ user_id: this.user });
    if (this.gxKDomain) p.set('domain', this.gxKDomain);
    if (this.gxKChapter) p.set('chapter', this.gxKChapter);
    if (this.gxKKind) p.set('kind', this.gxKKind);
    if ((this.gxKQ || '').trim()) p.set('q', this.gxKQ.trim());
    this.api('/api/gx/knowledge?' + p.toString())
      .then(d => { this.gxKList = (d && d.items) || []; })
      .catch(() => { this.gxKList = []; })
      .finally(() => { this.gxKLoading = false; });
  },
  // 资料类型中文名：优先用后端 catalog 的 label，兜底一张本地表（首屏 catalog 未回时也有字）
  gxKKindLabel(kind) {
    const hit = (this.gxKKindOptions || []).find(k => k.value === kind);
    if (hit && hit.label) return hit.label;
    return (KN_LABELS_FALLBACK[kind] || kind || '知识点');
  },
  gxPickKKind(k) {
    this.gxKKind = k;
    this.gxLoadKnowledge();
  },
  gxPickDomain(d) {
    this.gxKDomain = d;
    this.gxKDetail = null;
    this.gxLoadKnowledge();
  },
  gxPickKChapter(ch) { this.gxKChapter = ch; this.gxLoadKnowledge(); },
  gxSearchKnowledge() { this.gxLoadKnowledge(); },
  gxClearKnowledgeFilter() {
    this.gxKDomain = ''; this.gxKChapter = ''; this.gxKQ = ''; this.gxKKind = '';
    this.gxLoadKnowledge();
  },
  gxOpenKnowledge(k) {
    this.api(`/api/gx/knowledge/${k.id}?user_id=${encodeURIComponent(this.user)}`)
      .then(d => {
        this.gxKDetail = d || null;
        // 后端在详情接口里已经落了「已读」（幂等），这里就地更新列表那一条，
        // 关掉弹层立刻能看到标记 —— 不重拉列表，用户当前的分节与滚动位置都不会跳。
        if (d && d.read) this.gxMarkRead(d.id);
      })
      .catch(() => this.showToast('读取失败，稍后再试'));
  },
  // 把列表里某条标为已读（就地替换，不重新请求）。用 map 造新数组是显式替换，
  // 免得依赖「数组元素属性被改」这种深层响应式的细节。
  gxMarkRead(id) {
    this.gxKList = (this.gxKList || []).map(k => (k.id === id ? { ...k, read: true } : k));
  },
  gxCloseKnowledge() { this.gxKDetail = null; },
  // AI 生成该知识域知识点（慢操作，按钮转圈防重复）
  gxGenerateKnowledge() {
    if (this.gxKGenning) return;
    const domain = this.gxKDomain || this.gxDomains[0] || '';
    if (!domain) return;
    this.gxKGenning = true;
    this.api('/api/gx/knowledge/generate', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, domain: domain }),
    }).then(d => {
      const added = (d && d.added) || 0;
      this.showToast(added > 0 ? `已生成 ${added} 个新知识点` : '该知识域知识点已齐（无新增）');
      this.gxLoadKnowledge();
    }).catch(() => this.showToast('AI 生成失败，稍后再试'))
      .finally(() => { this.gxKGenning = false; });
  },

  /* ─────────── 刷题 ─────────── */
  gxQuizDomain(d) { this.gxQDomain = d; },
  gxQuizType(t) { this.gxQType = t; },
  gxQuizCount(n) { this.gxQCount = n; },
  gxQuizSourceKind(v) { this.gxQSourceKind = (this.gxQSourceKind === v ? '' : v); },
  gxQuizChapter(v) { this.gxQChapter = v; },
  gxResetQuizFilter() {
    this.gxQSourceKind = ''; this.gxQChapter = ''; this.gxQDomain = '';
  },
  gxQuizStart() {
    if (this.gxQLoading) return;
    this.gxQLoading = true;
    this.gxQScope = '';
    this.gxQuestions = []; this.gxAnswers = {}; this.gxQResult = null;
    this.gxReasonMap = {}; this.gxAnalyzing = null;
    this.api('/api/gx/quiz/generate', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, domain: this.gxQDomain,
                             qtype: this.gxQType, count: this.gxQCount,
                             source_kind: this.gxQSourceKind, chapter: this.gxQChapter,
                             scope: '',
                             // 未勾选 AI 时只从已导入题库取（import），杜绝误触 AI 扣费
                             source: this.gxUseAi ? 'all' : 'import' }),
    }).then(d => {
      this.gxQuestions = (d && d.questions) || [];
      this.gxQAiAdded = (d && d.ai_added) || 0;
      if (!this.gxQuestions.length) {
        this.showToast(this.gxUseAi ? '这批条件下没找到题，换个筛选再试'
                                    : '题库里没有符合筛选的题目；勾选「允许 AI 出题」可让 AI 补题');
      }
      this.gxQStartAt = Date.now();
    }).catch(() => this.showToast('出题失败，稍后再试'))
      .finally(() => { this.gxQLoading = false; });
  },
  // 错题重练：把错题本里未掌握的题凑一组抽出来（服务端 scope=wrong 不再过滤「做过的题」）
  gxQuizWrongStart(qtype) {
    if (this.gxQLoading) return;
    if (!this.gxWrong.length) { this.showToast('错题本是空的，先去刷几组题'); return; }
    this.gxSub = 'quiz';
    this.gxQLoading = true;
    this.gxQScope = 'wrong';
    this.gxQType = qtype || 'single';
    this.gxQuestions = []; this.gxAnswers = {}; this.gxQResult = null;
    this.gxReasonMap = {}; this.gxAnalyzing = null;
    this.api('/api/gx/quiz/generate', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, domain: '', qtype: this.gxQType,
                             count: this.gxQCount, source_kind: '', chapter: '',
                             scope: 'wrong', source: 'import' }),
    }).then(d => {
      this.gxQuestions = (d && d.questions) || [];
      this.gxQAiAdded = 0;
      if (!this.gxQuestions.length) this.showToast('没有待重练的错题了');
      this.gxQStartAt = Date.now();
    }).catch(() => this.showToast('出题失败，稍后再试'))
      .finally(() => { this.gxQLoading = false; });
  },
  // 多选点击选项：切换选中（归一为字母升序），单选直接置值
  gxToggleOption(q, opt) {
    if (this.gxQResult) return;   // 已提交锁定
    const letter = (opt || '').trim().charAt(0).toUpperCase();
    if (!/^[A-Z]$/.test(letter)) return;
    if (q.qtype === 'multi') {
      const cur = new Set((this.gxAnswers[q.id] || '').split('').filter(c => /[A-Z]/.test(c)));
      cur.add(letter);
      this.gxAnswers = Object.assign({}, this.gxAnswers,
        { [q.id]: [...cur].sort().join('') });
    } else {
      this.gxAnswers = Object.assign({}, this.gxAnswers, { [q.id]: letter });
    }
  },
  gxIsPicked(q, opt) {
    const letter = (opt || '').trim().charAt(0).toUpperCase();
    return ((this.gxAnswers[q.id] || '').indexOf(letter) >= 0);
  },
  gxSubmitQuiz() {
    if (this.gxQSubmitting || !this.gxAllAnswered) return;
    this.gxQSubmitting = true;
    const dur = Date.now() - (this.gxQStartAt || Date.now());
    this.api('/api/gx/quiz/submit', {
      method: 'POST',
      body: JSON.stringify({
        user_id: this.user,
        answers: this.gxQuestions.map(q => ({
          question_id: q.id, answer: this.gxAnswers[q.id] || '',
          duration_ms: Math.round(dur / this.gxQuestions.length),
        })),
      }),
    }).then(d => {
      this.gxQResult = d || { results: [] };
      this.gxLoadWrong();      // 答错可能新增错题，静默刷新错题本
      this.gxLoadProgress();   // 进度同步刷新
      // 做完立刻分析错题（限量，避免长等待；余下的可在错题本逐题点分析）
      const wrongIds = ((d && d.results) || [])
        .filter(r => r.judged && r.is_correct === false)
        .map(r => r.question_id);
      if (wrongIds.length) {
        this.showToast(`答错 ${wrongIds.length} 题，已入错题本，正在分析错因…`);
        this.gxAutoAnalyze(wrongIds);
      }
    }).catch(() => this.showToast('提交失败，稍后再试'))
      .finally(() => { this.gxQSubmitting = false; });
  },
  // 单题反馈样式：对/错/未判分
  gxResultClass(qid) {
    const r = this.gxResultMap[qid];
    if (!r) return '';
    if (r.judged === false) return 'skip';
    return r.is_correct === true ? 'ok' : 'bad';
  },
  // 自动错因分析：串行调用（每题一次 AI），逐题回填，不阻塞页面
  gxAutoAnalyze(ids) {
    const todo = (ids || []).slice(0, AUTO_ANALYZE_MAX);
    if (!todo.length) return;
    this.gxAnalyzing = { total: todo.length, done: 0 };
    const step = (i) => {
      if (i >= todo.length) {
        this.gxAnalyzing = null;
        this.gxLoadWrong();     // 分析结果已落库，刷新错题本带上错因
        return;
      }
      this.api('/api/gx/wrong/analyze', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, question_id: todo[i] }),
      }).then(d => {
        const it = ((d && d.items) || [])[0];
        if (it && it.ok) {
          this.gxReasonMap = Object.assign({}, this.gxReasonMap,
            { [it.question_id]: reasonText(it) });
        }
      }).catch(() => {}).finally(() => {
        this.gxAnalyzing = { total: todo.length, done: i + 1 };
        step(i + 1);
      });
    };
    step(0);
  },

  /* ─────────── 案例分析（资料真题 + AI 现场出题） ─────────── */
  gxCaseDomainPick(d) {
    this.gxCaseDomain = (this.gxCaseDomain === d ? '' : d);
    // 知识域对两种模式都生效，只刷新当前模式的列表
    if (this.gxCaseMode === 'sub') {
      this.gxSubIdx = 0;
      this.gxSubDetail = null;
      this.gxLoadCaseSubs();
    } else {
      this.gxLoadCaseList();
    }
  },
  gxLoadCaseList() {
    this.gxCaseListLoading = true;
    const p = new URLSearchParams({ user_id: this.user, limit: '50' });
    if (this.gxCaseDomain) p.set('domain', this.gxCaseDomain);
    this.api('/api/gx/case/list?' + p.toString())
      .then(d => { this.gxCaseList = (d && d.items) || []; })
      .catch(() => { this.gxCaseList = []; })
      .finally(() => { this.gxCaseListLoading = false; });
  },
  gxOpenCase(item) {
    if (!item || !item.id) return;
    this.gxCaseDetail = null; this.gxCaseExtra = null;
    this.gxC_answer = ''; this.gxC_result = null; this.gxCaseShowAnswer = false;
    this.api(`/api/gx/case/${item.id}?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.gxCaseDetail = d || null; })
      .catch(() => this.showToast('读取案例题失败，稍后再试'));
  },
  gxCloseCase() {
    this.gxCaseDetail = null; this.gxCaseExtra = null;
    this.gxC_answer = ''; this.gxC_result = null;
  },
  // AI 现场出一道案例大题（落库后按 id 走同一套渲染与批改）
  gxCaseGenAI() {
    if (this.gxCaseGenning) return;
    const domain = this.gxCaseDomain || this.gxDomains[0] || '';
    if (!domain) return;
    this.gxCaseGenning = true;
    this.api('/api/gx/case/generate', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, domain: domain }),
    }).then(d => {
      if (!d || !d.question_id) { this.showToast('没出出来，稍后再试一次'); return; }
      this.gxCaseDetail = { id: d.question_id, title: 'AI 现场出题（' + domain + '）',
                            domain: domain, background: d.background,
                            sub_questions: d.sub_questions || [] };
      this.gxCaseExtra = d.question_id;
      this.gxC_answer = ''; this.gxC_result = null; this.gxCaseShowAnswer = false;
      this.showToast('已出题，写在下面提交批改');
    }).catch(() => this.showToast('出题失败，稍后再试'))
      .finally(() => { this.gxCaseGenning = false; });
  },
  gxCaseGrade() {
    if (!this.gxC_canSubmit || !this.gxCaseDetail) return;
    this.gxCaseGrading = true;
    this.api('/api/gx/case/grade', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user,
                             question_id: this.gxCaseDetail.id || null,
                             user_answer: this.gxC_answer }),
    }).then(d => {
      this.gxC_result = d || null;
      this.gxLoadProgress();
      this.gxCaseShowAnswer = true;   // 批改后自动展开参考答案要点，对照着看
      if (d && d.in_wrong_book) {
        this.showToast(`得分低于 ${this.gxPassScore}，已入错题本，正在分析错因…`);
        this.gxAutoAnalyze([this.gxCaseDetail.id]);
      }
      this.gxLoadWrong();
    }).catch(() => this.showToast('批改失败，稍后再试'))
      .finally(() => { this.gxCaseGrading = false; });
  },
  gxToggleCaseAnswer() { this.gxCaseShowAnswer = !this.gxCaseShowAnswer; },

  /* ─────────── 案例「按小问刷」：一问一练，只批改当前小问 ─────────── */
  gxPickCaseMode(m) {
    if (!m || this.gxCaseMode === m) return;
    this.gxCaseMode = m;
    if (m === 'sub') this.gxLoadCaseSubs();
  },
  gxLoadCaseSubs() {
    this.gxSubLoading = true;
    this._gxSubLoadScores();     // 历史得分从 localStorage 恢复（刷新不丢「已练几问」）
    const p = new URLSearchParams({ user_id: this.user, limit: '200' });
    if (this.gxCaseDomain) p.set('domain', this.gxCaseDomain);
    this.api('/api/gx/case/sub/list?' + p.toString())
      .then(d => {
        this.gxSubList = (d && d.items) || [];
        if (this.gxSubIdx >= this.gxSubList.length) this.gxSubIdx = 0;
        this.gxS_answer = ''; this.gxSubResult = null; this.gxSubShowAnswer = false;
        this.gxSubGo(this.gxSubIdx);   // 顺带把当前小问的草稿与大题详情带上
      })
      .catch(() => { this.gxSubList = []; })
      .finally(() => { this.gxSubLoading = false; });
  },
  // 切到第 i 个小问：先存当前草稿，再载入目标小问的草稿 + 所属大题详情
  gxSubGo(i) {
    const n = (this.gxSubList || []).length;
    if (!n) return;
    const cur = this.gxSubCur;
    if (cur) {
      this.gxSubAnswers = Object.assign({}, this.gxSubAnswers, { [cur.key]: this.gxS_answer });
    }
    this.gxSubIdx = Math.max(0, Math.min(n - 1, i));
    const nx = this.gxSubCur;
    this.gxS_answer = (nx && this.gxSubAnswers[nx.key]) || '';
    this.gxSubResult = null; this.gxSubShowAnswer = false;
    this.gxSubEnsureDetail();
  },
  gxSubNext() { this.gxSubGo(this.gxSubIdx + 1); },
  gxSubPrev() { this.gxSubGo(this.gxSubIdx - 1); },
  // 背景与参考答案要点都在大题详情里，按当前小问所属题目懒加载一次
  gxSubEnsureDetail() {
    const cur = this.gxSubCur;
    if (!cur) return;
    if (this.gxSubDetail && this.gxSubDetail.id === cur.question_id) return;
    this.gxSubDetail = null;
    this.api(`/api/gx/case/${cur.question_id}?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.gxSubDetail = d || null; })
      .catch(() => {});
  },
  gxSubGrade() {
    const cur = this.gxSubCur;
    if (!cur || !this.gxSubCanSubmit) return;
    this.gxSubGrading = true;
    this.api('/api/gx/case/sub/grade', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, question_id: cur.question_id,
                             sub_index: cur.sub_index, user_answer: this.gxS_answer }),
    }).then(d => {
      this.gxSubResult = d || null;
      this.gxSubScores = Object.assign({}, this.gxSubScores,
        { [cur.key]: (d && d.score) || 0 });
      this._gxSubSaveScores();
      this.gxLoadProgress();
      this.gxSubShowAnswer = true;   // 批改后对照参考答案要点看
      this.gxSubEnsureDetail();
      if (d && d.in_wrong_book) {
        this.showToast(`得分低于 ${this.gxPassScore}，已入错题本，正在分析错因…`);
        this.gxAutoAnalyze([cur.question_id]);
      }
      this.gxLoadWrong();
    }).catch(() => this.showToast('批改失败，稍后再试'))
      .finally(() => { this.gxSubGrading = false; });
  },
  gxToggleSubBg() { this.gxSubShowBg = !this.gxSubShowBg; },
  gxToggleSubAnswer() {
    this.gxSubShowAnswer = !this.gxSubShowAnswer;
    if (this.gxSubShowAnswer) this.gxSubEnsureDetail();
  },
  // 历史得分存本地：后端没有「小问」这一层，不值得为此加一张表
  _gxSubStoreKey() { return 'gx_case_sub_scores_' + (this.user || ''); },
  _gxSubLoadScores() {
    try {
      const raw = localStorage.getItem(this._gxSubStoreKey());
      this.gxSubScores = raw ? (JSON.parse(raw) || {}) : {};
    } catch (e) { this.gxSubScores = {}; }
  },
  _gxSubSaveScores() {
    try {
      localStorage.setItem(this._gxSubStoreKey(), JSON.stringify(this.gxSubScores || {}));
    } catch (e) { /* 隐私模式下 localStorage 不可写，忽略即可 */ }
  },

  /* ─────────── 论文练习 ─────────── */
  gxEssayDomainPick(d) {
    this.gxEssayDomain = (this.gxEssayDomain === d ? '' : d);
    this.gxLoadEssay();
  },
  gxLoadEssay() {
    this.gxEssayLoading = true;
    const p = new URLSearchParams({ user_id: this.user, limit: '50' });
    if (this.gxEssayDomain) p.set('domain', this.gxEssayDomain);
    this.api('/api/gx/essay/list?' + p.toString())
      .then(d => { this.gxEssayList = (d && d.items) || []; })
      .catch(() => { this.gxEssayList = []; })
      .finally(() => { this.gxEssayLoading = false; });
  },
  gxOpenEssay(item) {
    if (!item || !item.id) return;
    this.gxEssayDetail = null;
    this.gxE_answer = ''; this.gxE_result = null; this.gxEssayShowReq = true;
    this.api(`/api/gx/essay/${item.id}?user_id=${encodeURIComponent(this.user)}`)
      .then(d => {
        this.gxEssayDetail = d || null;
        this.gxE_answer = '';
      })
      .catch(() => this.showToast('读取论文题失败，稍后再试'));
  },
  gxOpenEssayById(qid) {
    if (!qid) return;
    this.gxSub = 'essay';
    this.gxOpenEssay({ id: qid });
  },
  gxCloseEssay() {
    this.gxEssayDetail = null; this.gxE_answer = ''; this.gxE_result = null;
  },
  gxToggleEssayReq() { this.gxEssayShowReq = !this.gxEssayShowReq; },
  gxEssayGrade() {
    if (!this.gxE_canSubmit) return;
    this.gxEssayGrading = true;
    this.api('/api/gx/essay/grade', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user,
                             question_id: this.gxEssayDetail.id,
                             user_answer: this.gxE_answer }),
    }).then(d => {
      this.gxE_result = d || null;
      this.gxLoadProgress();
      if (d && d.in_wrong_book) {
        this.showToast(`得分低于 ${this.gxPassScore}，已入错题本，正在分析错因…`);
        this.gxAutoAnalyze([this.gxEssayDetail.id]);
      }
      this.gxLoadWrong();
    }).catch(() => this.showToast('批改失败，稍后再试'))
      .finally(() => { this.gxEssayGrading = false; });
  },

  /* ─────────── 错题本 ─────────── */
  gxLoadWrong() {
    this.gxWrongLoading = true;
    this.api(`/api/gx/wrong?user_id=${encodeURIComponent(this.user)}`)
      .then(d => {
        this.gxWrong = (d && d.items) || [];
        this.gxWrongByKind = (d && d.by_kind) || { choice: 0, case: 0, essay: 0 };
        // 错因已落库的同步进 gxReasonMap，刷题页与错题本共用一份展示
        const m = Object.assign({}, this.gxReasonMap);
        this.gxWrong.forEach(w => { if (w.wrong_reason) m[w.question_id] = w.wrong_reason; });
        this.gxReasonMap = m;
      })
      .catch(() => { this.gxWrong = []; })
      .finally(() => { this.gxWrongLoading = false; });
  },
  gxPickWrongKind(k) { this.gxWrongKind = k; },
  gxMasterWrong(w) {
    this.api('/api/gx/wrong/master', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, question_id: w.question_id }),
    }).then(() => { this.showToast('已标记掌握'); this.gxLoadWrong(); })
      .catch(() => this.showToast('操作失败，稍后再试'));
  },
  // 单题错因分析（手动触发，命中缓存时几乎瞬时返回）
  gxAnalyzeWrong(w) {
    if (this.gxWrongAnalyzing) return;
    this.gxWrongAnalyzing = w.question_id;
    this.api('/api/gx/wrong/analyze', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, question_id: w.question_id }),
    }).then(d => {
      const it = ((d && d.items) || [])[0];
      if (!it || !it.ok) { this.showToast('分析失败，稍后再试'); return; }
      this.gxReasonMap = Object.assign({}, this.gxReasonMap,
        { [it.question_id]: reasonText(it) });
    }).catch(() => this.showToast('分析失败，稍后再试'))
      .finally(() => { this.gxWrongAnalyzing = 0; });
  },
  // 批量补分析（服务端每次最多 5 题，串行不并发避免超时）
  gxAnalyzeWrongBatch() {
    if (this.gxWrongBatchAnalyzing) return;
    this.gxWrongBatchAnalyzing = true;
    this.api('/api/gx/wrong/analyze', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, limit: 3 }),
    }).then(d => {
      const n = (d && d.analyzed) || 0;
      this.showToast(n > 0 ? `已分析 ${n} 道错题` : '没有待分析的错题');
      this.gxLoadWrong();
    }).catch(() => this.showToast('分析失败，稍后再试'))
      .finally(() => { this.gxWrongBatchAnalyzing = false; });
  },
  // 从错题重做：选择题复用刷题区；案例/论文跳到各自页签打开原题
  gxRetryWrong(w) {
    if (w.kind === 'case') { this.gxSub = 'case'; this.gxOpenCase({ id: w.question_id }); return; }
    if (w.kind === 'essay') { this.gxOpenEssayById(w.question_id); return; }
    this.gxSub = 'quiz';
    this.gxQScope = '';
    this.gxQDomain = w.domain || '';
    this.gxQType = w.qtype === 'multi' ? 'multi' : 'single';
    this.gxQSourceKind = ''; this.gxQChapter = '';
    this.gxQuestions = [{ id: w.question_id, qtype: w.qtype || 'single',
                          question: w.question, options: w.options,
                          chapter: w.chapter, source_kind: w.source_kind }];
    this.gxAnswers = {}; this.gxQResult = null;
    this.gxQStartAt = Date.now();
  },
  // 错因分析文本（错题本与刷题页共用）
  gxReasonOf(qid) { return this.gxReasonMap[qid] || ''; },

  /* ─────────── 进度 ─────────── */
  gxLoadProgress() {
    this.api(`/api/gx/progress?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.gxProgress = d || null; })
      .catch(() => {});
  },
  // 正确率文案（null=还没做过）
  gxAccText(row) {
    return row.accuracy === null || row.accuracy === undefined ? '未开始' : row.accuracy + '%';
  },
  /* ─────────── 子页签 ─────────── */
  gxPickSub(sub) {
    this.gxSub = sub;
    if (sub === 'wrong') this.gxLoadWrong();
    if (sub === 'progress') this.gxLoadProgress();
    if (sub === 'knowledge' && !this.gxKList.length) this.gxLoadKnowledge();
    if (sub === 'case') {
      if (this.gxCaseMode === 'sub') {
        if (!this.gxSubList.length) this.gxLoadCaseSubs();
      } else if (!this.gxCaseList.length) {
        this.gxLoadCaseList();
      }
    }
    if (sub === 'essay' && !this.gxEssayList.length) this.gxLoadEssay();
  },
};
