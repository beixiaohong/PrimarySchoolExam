<template>
<div class="fade-enter">
  <!-- hero：与小学页面视觉区分（深蓝→青，指向职业/成人考试），并明确「非学生」定位 -->
  <div class="hero gx-hero">
    <div style="flex:1">
      <h1>🎯 高项备考</h1>
      <p class="sub" style="color:rgba(255,255,255,.92)">
        软考高级「信息系统项目管理师」· 考纲 24 章 · 真题练习 + AI 出题/批改 · 错题自动分析入库
      </p>
    </div>
    <div class="gx-hero-stat" v-if="appCtx.gxProgress">
      <div class="gx-hero-num">{{appCtx.gxProgress.summary.quiz_total}}<em>题</em></div>
      <div class="gx-hero-label">
        正确率 {{appCtx.gxProgress.summary.accuracy === null ? '—' : appCtx.gxProgress.summary.accuracy + '%'}}
        <template v-if="appCtx.gxWrong.length">· 待复习 {{appCtx.gxWrong.length}}</template>
      </div>
    </div>
  </div>

  <!-- 子页签 -->
  <div class="gx-tabs">
    <button v-for="t in gxTabs" :key="t.k" class="gx-tab"
            :class="{active: appCtx.gxSub === t.k}" @click="appCtx.gxPickSub(t.k)">
      {{t.label}}<span class="gx-tab-n" v-if="t.k === 'wrong' && appCtx.gxWrong.length">{{appCtx.gxWrong.length}}</span>
    </button>
  </div>

  <!-- ───────── 刷题 ───────── -->
  <div v-if="appCtx.gxSub === 'quiz'" class="card">
    <div class="card-head">
      <b>刷题</b><span class="card-desc">默认只用已导入的真题库（不产生 AI 费用）；勾选「AI 补题」后题库不够才由 AI 现场出题并入库复用</span>
    </div>

    <div class="gx-row">
      <span class="gx-label">知识域</span>
      <div class="gx-chips">
        <button class="gx-chip" :class="{on: !appCtx.gxQDomain}" @click="appCtx.gxQuizDomain('')">不限</button>
        <button v-for="d in appCtx.gxDomains" :key="d" class="gx-chip"
                :class="{on: appCtx.gxQDomain === d}" @click="appCtx.gxQuizDomain(d)">{{d}}</button>
      </div>
    </div>

    <div class="gx-row">
      <span class="gx-label">资料</span>
      <div class="gx-chips">
        <button class="gx-chip" :class="{on: !appCtx.gxQSourceKind}"
                @click="appCtx.gxQuizSourceKind('')">全部资料</button>
        <button v-for="s in appCtx.gxSourceKindOptions" :key="s.value" class="gx-chip"
                :class="{on: appCtx.gxQSourceKind === s.value}"
                @click="appCtx.gxQuizSourceKind(s.value)">{{s.value}}（{{s.count}}）</button>
      </div>
    </div>

    <div class="gx-row">
      <span class="gx-label">章节</span>
      <select class="gx-select" :value="appCtx.gxQChapter"
              @change="appCtx.gxQuizChapter($event.target.value)">
        <option value="">不限章节</option>
        <option v-for="c in appCtx.gxChapterOptions" :key="c.value" :value="c.value">
          {{c.value}}（{{c.count}}）
        </option>
      </select>
      <button class="btn gx-clear-btn" @click="appCtx.gxResetQuizFilter()">清空筛选</button>
    </div>

    <div class="gx-row">
      <span class="gx-label">题型</span>
      <div class="gx-chips">
        <button class="gx-chip" :class="{on: appCtx.gxQType === 'single'}" @click="appCtx.gxQuizType('single')">单选</button>
        <button class="gx-chip" :class="{on: appCtx.gxQType === 'multi'}" @click="appCtx.gxQuizType('multi')">多选</button>
      </div>
      <span class="gx-label gx-label-inline">题量</span>
      <div class="gx-chips gx-chips-narrow">
        <button v-for="n in [5, 10, 20]" :key="n" class="gx-chip"
                :class="{on: appCtx.gxQCount === n}" @click="appCtx.gxQuizCount(n)">{{n}}</button>
      </div>
      <button class="btn btn-primary gx-start-btn" :disabled="appCtx.gxQLoading" @click="appCtx.gxQuizStart()">
        {{appCtx.gxQLoading ? '出题中…' : '开始出题'}}
      </button>
    </div>

    <div class="gx-row">
      <span class="gx-label">出题源</span>
      <label class="gx-ai-toggle" style="display:inline-flex;align-items:center;gap:6px;cursor:pointer">
        <input type="checkbox" v-model="appCtx.gxUseAi">
        允许 AI 出题<span class="card-desc">（勾选后题库不足时由 AI 生成新题，消耗钻石；不勾只刷已导入真题）</span>
      </label>
    </div>

    <div class="gx-row" v-if="appCtx.gxWrong.length">
      <span class="gx-label">错题</span>
      <div class="gx-chips">
        <button class="btn gx-mini-btn" @click="appCtx.gxQuizWrongStart('single')">错题重练（单选）</button>
        <button class="btn gx-mini-btn" @click="appCtx.gxQuizWrongStart('multi')">错题重练（多选）</button>
        <span class="card-desc">共 {{appCtx.gxWrong.length}} 道待复习，重做连对 3 次自动掌握</span>
      </div>
    </div>

    <div v-if="appCtx.gxQuestions.length" class="gx-quiz-wrap">
      <!-- 结算条 -->
      <div v-if="appCtx.gxQResult" class="gx-score-bar">
        <span v-if="appCtx.gxQScope === 'wrong'">【错题重练】</span>
        本组答对 <b>{{appCtx.gxCorrectCount}}</b> / {{appCtx.gxQuestions.length}} 题
        <span v-if="appCtx.gxWrongCountOfQuiz" class="gx-bad">
          · 错 {{appCtx.gxWrongCountOfQuiz}} 题已入错题本
        </span>
        <span v-if="appCtx.gxUngradedCount" class="gx-skip">
          · {{appCtx.gxUngradedCount}} 题资料里没抓到答案，不计分
        </span>
        <span v-if="appCtx.gxAnalyzing" class="gx-analyzing">
          · 错因分析中 {{appCtx.gxAnalyzing.done}}/{{appCtx.gxAnalyzing.total}}…
        </span>
      </div>
      <div v-else-if="appCtx.gxQAiAdded" class="gx-score-bar">
        本组有 {{appCtx.gxQAiAdded}} 道是 AI 现场出的新题（已入库，下次可复用）
      </div>

      <div v-for="(q, i) in appCtx.gxQuestions" :key="q.id" class="gx-q" :class="appCtx.gxResultClass(q.id)">
        <div class="gx-q-head">
          <b>{{i + 1}}.</b>
          <span class="gx-q-type">{{q.qtype === 'multi' ? '多选' : '单选'}}</span>
          <span class="gx-q-badge" v-if="q.chapter">{{q.chapter}}</span>
          <span class="gx-q-badge" v-if="q.source_kind">{{q.source_kind}}</span>
          <span class="gx-q-badge" v-if="q.deck">{{q.deck}}</span>
          <span class="gx-q-text">{{q.question}}</span>
        </div>
        <div class="gx-opts" v-if="q.options">
          <button v-for="(o, oi) in q.options" :key="oi" class="gx-opt"
                  :class="{picked: appCtx.gxIsPicked(q, o)}"
                  @click="appCtx.gxToggleOption(q, o)">{{o}}</button>
        </div>
        <!-- 提交后才展示答案与解析（答案不下发前端，来自服务端判分响应） -->
        <div v-if="appCtx.gxResultMap[q.id]" class="gx-fb">
          <span v-if="appCtx.gxResultMap[q.id].judged === false" class="gx-skip">
            ⚠️ 本题资料里没有参考答案，不计分、不入错题本
          </span>
          <template v-else>
            <span :class="appCtx.gxResultMap[q.id].is_correct ? 'gx-ok' : 'gx-bad'">
              {{appCtx.gxResultMap[q.id].is_correct ? '✅ 答对' : '❌ 答错'}}
            </span>
            <span>你的答案：{{appCtx.gxAnswers[q.id] || '—'}}　正确答案：{{appCtx.gxResultMap[q.id].correct}}</span>
          </template>
          <div class="gx-analysis" v-if="appCtx.gxResultMap[q.id].analysis">解析：{{appCtx.gxResultMap[q.id].analysis}}</div>
          <!-- 错因分析：提交后自动生成（最多 3 道），也可到错题本逐题点 -->
          <div class="gx-reason" v-if="appCtx.gxReasonOf(q.id)">🔍 错因分析：{{appCtx.gxReasonOf(q.id)}}</div>
          <div class="gx-reason pending" v-else-if="appCtx.gxResultMap[q.id].is_correct === false && appCtx.gxAnalyzing">
            🔍 错因分析生成中…
          </div>
        </div>
      </div>

      <div class="gx-actions" v-if="!appCtx.gxQResult">
        <button class="btn btn-primary" :disabled="!appCtx.gxAllAnswered || appCtx.gxQSubmitting"
                @click="appCtx.gxSubmitQuiz()">
          {{appCtx.gxQSubmitting ? '提交中…' : '提交答案'}}
        </button>
        <span class="card-desc">答完所有题才能提交；提交后自动判分并把错题入库</span>
      </div>
      <div class="gx-actions" v-else>
        <button class="btn btn-primary" @click="appCtx.gxQuizStart()">再来一组</button>
        <button class="btn" @click="appCtx.gxPickSub('wrong')">查看错题本</button>
        <button class="btn" v-if="appCtx.gxWrong.length" @click="appCtx.gxQuizWrongStart('single')">错题重练</button>
      </div>
    </div>
    <div v-else class="card-desc gx-empty">
      选好知识域 / 资料 / 章节与题型后点「开始出题」。题库没题时想用 AI 补题，需勾选上方「允许 AI 出题」。
    </div>
  </div>

  <!-- ───────── 知识点 ───────── -->
  <div v-else-if="appCtx.gxSub === 'knowledge'" class="card">
    <div class="card-head">
      <b>知识点</b>
      <span class="card-desc">资料已按类型分类：先选资料类型（速记/清单/导图…），再按考纲章节定位</span>
    </div>

    <div class="gx-row">
      <span class="gx-label">资料类型</span>
      <div class="gx-chips">
        <button class="gx-chip" :class="{on: !appCtx.gxKKind}" @click="appCtx.gxPickKKind('')">全部</button>
        <button v-for="k in appCtx.gxKKindOptions" :key="k.value" class="gx-chip"
                :class="{on: appCtx.gxKKind === k.value}"
                @click="appCtx.gxPickKKind(k.value)">{{k.label}}（{{k.count}}）</button>
      </div>
    </div>

    <div class="gx-row">
      <span class="gx-label">知识域</span>
      <div class="gx-chips">
        <button class="gx-chip" :class="{on: !appCtx.gxKDomain}" @click="appCtx.gxPickDomain('')">不限</button>
        <button v-for="d in appCtx.gxDomains" :key="d" class="gx-chip"
                :class="{on: appCtx.gxKDomain === d}" @click="appCtx.gxPickDomain(d)">{{d}}</button>
      </div>
    </div>

    <div class="gx-row">
      <span class="gx-label">章节</span>
      <select class="gx-select" :value="appCtx.gxKChapter"
              @change="appCtx.gxPickKChapter($event.target.value)">
        <option value="">不限章节</option>
        <option v-for="c in appCtx.gxKChapterOptions" :key="c.value" :value="c.value">
          {{c.value}}（{{c.count}}）
        </option>
      </select>
      <input class="gx-input" v-model="appCtx.gxKQ" placeholder="搜标题或正文关键词"
             @keyup.enter="appCtx.gxSearchKnowledge()" />
      <button class="btn gx-mini-btn" @click="appCtx.gxSearchKnowledge()">搜索</button>
      <button class="btn gx-mini-btn" @click="appCtx.gxClearKnowledgeFilter()">重置</button>
    </div>

    <div v-if="appCtx.gxKLoading" class="card-desc">加载中…</div>
    <div v-else-if="!appCtx.gxKList.length" class="card-desc gx-empty">
      这个筛选条件下还没有知识点，换个条件，或让下面的 AI 生成一批。
    </div>
    <div v-else class="gx-kgroups">
      <div v-for="g in appCtx.gxKGroups" :key="g.kind" class="gx-kgroup">
        <div class="gx-kgroup-head" v-if="!appCtx.gxKKind">
          <b>{{g.label}}</b><span class="gx-kgroup-n">{{g.items.length}} 条</span>
          <span class="gx-kgroup-n gx-kgroup-read" v-if="g.readN">已读 {{g.readN}}</span>
        </div>
        <div class="gx-klist">
          <div v-for="k in g.items" :key="k.id" class="gx-kitem" @click="appCtx.gxOpenKnowledge(k)">
            <div class="gx-kitem-head">
              <b>{{k.title}}</b>
              <span class="gx-kitem-flags">
                <span class="gx-read-badge" v-if="k.read">已读</span>
                <span class="gx-kitem-tag">{{appCtx.gxKKindLabel(k.kind)}}</span>
              </span>
            </div>
            <span class="gx-kitem-meta" v-if="k.domain || k.chapter">
              {{k.domain || '未归类'}}<template v-if="k.chapter"> · {{k.chapter}}</template>
            </span>
            <span class="gx-kitem-sum" v-if="k.summary">{{k.summary}}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="gx-actions">
      <button class="btn btn-primary" :disabled="appCtx.gxKGenning" @click="appCtx.gxGenerateKnowledge()">
        {{appCtx.gxKGenning ? 'AI 生成中…' : 'AI 生成该知识域知识点'}}
      </button>
      <span class="card-desc">生成的内容会落库复用，重复点击只补新增</span>
    </div>
  </div>

  <!-- ───────── 案例分析 ───────── -->
  <div v-else-if="appCtx.gxSub === 'case'" class="card">
    <div class="card-head"><b>案例分析</b>
      <span class="card-desc">做资料里的真题，或让 AI 现场出题；写完后 AI 按要点批改，低于 {{appCtx.gxPassScore}} 分自动入错题本</span>
    </div>

    <div class="gx-row">
      <span class="gx-label">知识域</span>
      <div class="gx-chips">
        <button class="gx-chip" :class="{on: !appCtx.gxCaseDomain}" @click="appCtx.gxCaseDomainPick('')">不限</button>
        <button v-for="d in appCtx.gxDomains" :key="d" class="gx-chip"
                :class="{on: appCtx.gxCaseDomain === d}" @click="appCtx.gxCaseDomainPick(d)">{{d}}</button>
      </div>
    </div>

    <div class="gx-actions">
      <button class="btn btn-primary" :disabled="appCtx.gxCaseGenning" @click="appCtx.gxCaseGenAI()">
        {{appCtx.gxCaseGenning ? 'AI 出题中…' : 'AI 现场出一道'}}
      </button>
      <span class="card-desc">题库共 {{appCtx.gxCaseList.length}} 道资料真题</span>
    </div>

    <div v-if="appCtx.gxCaseListLoading" class="card-desc">加载中…</div>
    <div v-else-if="!appCtx.gxCaseList.length" class="card-desc gx-empty">
      这个知识域下没有资料真题，点「AI 现场出一道」。
    </div>
    <div v-else class="gx-pick-list">
      <button v-for="c in appCtx.gxCaseList" :key="c.id" class="gx-pick-item"
              :class="{on: appCtx.gxCaseDetail && appCtx.gxCaseDetail.id === c.id}"
              @click="appCtx.gxOpenCase(c)">
        <b>{{c.title || ('案例题 #' + c.id)}}</b>
        <span class="card-desc">{{c.domain}}<template v-if="c.chapter"> · {{c.chapter}}</template>
          <template v-if="c.source_kind"> · {{c.source_kind}}</template> · {{c.sub_count}} 个小问</span>
      </button>
    </div>

    <template v-if="appCtx.gxCaseDetail">
      <div class="gx-detail-head">
        <b>{{appCtx.gxCaseDetail.title || '案例题'}}</b>
        <button class="gx-modal-x" @click="appCtx.gxCloseCase()">✕</button>
      </div>
      <div class="gx-case-bg">{{appCtx.gxCaseDetail.background}}</div>
      <div class="gx-case-qs" v-if="appCtx.gxCaseDetail.sub_questions && appCtx.gxCaseDetail.sub_questions.length">
        <div class="gx-case-q-label">答题要求</div>
        <div v-for="(s, i) in appCtx.gxCaseDetail.sub_questions" :key="i" class="gx-case-q">
          （{{i + 1}}）{{s.q}}<span class="gx-case-pt" v-if="s.points">（{{s.points}} 分）</span>
        </div>
      </div>
      <textarea class="gx-textarea" v-model="appCtx.gxC_answer"
                placeholder="在这里作答，建议分点写（问题/原因/对策），不少于 20 字…"></textarea>
      <div class="gx-actions">
        <button class="btn btn-primary" :disabled="!appCtx.gxC_canSubmit" @click="appCtx.gxCaseGrade()">
          {{appCtx.gxCaseGrading ? 'AI 批改中…' : '提交批改'}}
        </button>
        <button class="btn gx-mini-btn" @click="appCtx.gxToggleCaseAnswer()">
          {{appCtx.gxCaseShowAnswer ? '收起参考答案要点' : '查看参考答案要点'}}
        </button>
        <span class="card-desc">批改约需数秒，请勿重复点击</span>
      </div>
      <!-- 参考答案要点：默认收起（先自己写再对答案），批改后自动展开 -->
      <div class="gx-ref" v-if="appCtx.gxCaseShowAnswer">
        <div class="gx-ref-item" v-for="(s, i) in (appCtx.gxCaseDetail.sub_questions || [])" :key="i">
          <b>（{{i + 1}}）</b><span class="gx-ref-q">{{s.q}}</span>
          <div class="gx-ref-a" v-if="s.answer">{{s.answer}}</div>
          <div class="card-desc" v-else>该小问资料里没有给参考答案</div>
        </div>
      </div>
    </template>

    <div v-if="appCtx.gxC_result" class="gx-case-result">
      <div class="gx-case-score">
        得分：<b>{{appCtx.gxC_result.score}}</b> / 100
        <span class="gx-bad" v-if="appCtx.gxC_result.in_wrong_book">（低于 {{appCtx.gxC_result.pass_score}}，已入错题本）</span>
        <span class="gx-ok" v-else>（已达标）</span>
      </div>
      <pre class="gx-case-fb">{{appCtx.gxC_result.feedback}}</pre>
    </div>
  </div>

  <!-- ───────── 论文练习 ───────── -->
  <div v-else-if="appCtx.gxSub === 'essay'" class="card">
    <div class="card-head"><b>论文练习</b>
      <span class="card-desc">考试要求 2000 字以上；AI 按「切题 / 结构 / 实践 / 文字」四维评分，低于 {{appCtx.gxPassScore}} 分自动入错题本</span>
    </div>

    <div class="gx-row">
      <span class="gx-label">知识域</span>
      <div class="gx-chips">
        <button class="gx-chip" :class="{on: !appCtx.gxEssayDomain}" @click="appCtx.gxEssayDomainPick('')">不限</button>
        <button v-for="d in appCtx.gxDomains" :key="d" class="gx-chip"
                :class="{on: appCtx.gxEssayDomain === d}" @click="appCtx.gxEssayDomainPick(d)">{{d}}</button>
      </div>
    </div>

    <div v-if="appCtx.gxEssayLoading" class="card-desc">加载中…</div>
    <div v-else-if="!appCtx.gxEssayList.length" class="card-desc gx-empty">
      这个知识域下还没有论文题。论文题来自备考资料的书本真题。
    </div>
    <div v-else class="gx-pick-list">
      <button v-for="e in appCtx.gxEssayList" :key="e.id" class="gx-pick-item"
              :class="{on: appCtx.gxEssayDetail && appCtx.gxEssayDetail.id === e.id}"
              @click="appCtx.gxOpenEssay(e)">
        <b>{{e.title || ('论文题 #' + e.id)}}</b>
        <span class="card-desc">{{e.domain}}<template v-if="e.chapter"> · {{e.chapter}}</template>
          <template v-if="e.source_kind"> · {{e.source_kind}}</template> · {{e.sub_count}} 条论述要求</span>
      </button>
    </div>

    <template v-if="appCtx.gxEssayDetail">
      <div class="gx-detail-head">
        <b>{{appCtx.gxEssayDetail.title || '论文题'}}</b>
        <button class="gx-modal-x" @click="appCtx.gxCloseEssay()">✕</button>
      </div>
      <div class="gx-case-bg">{{appCtx.gxEssayDetail.background}}</div>
      <div class="gx-case-qs" v-if="appCtx.gxEssayDetail.sub_questions && appCtx.gxEssayDetail.sub_questions.length">
        <div class="gx-case-q-label">
          论述要求
          <button class="gx-link-btn" @click="appCtx.gxToggleEssayReq()">
            {{appCtx.gxEssayShowReq ? '收起' : '展开'}}
          </button>
        </div>
        <template v-if="appCtx.gxEssayShowReq">
          <div v-for="(s, i) in appCtx.gxEssayDetail.sub_questions" :key="i" class="gx-case-q">
            （{{i + 1}}）{{s.q}}
          </div>
        </template>
      </div>
      <textarea class="gx-textarea gx-textarea-lg" v-model="appCtx.gxE_answer"
                placeholder="按摘要 → 正文（项目管理过程 + 本项目实践细节）→ 结尾的结构写，建议 2000 字以上…"></textarea>
      <div class="gx-actions">
        <button class="btn btn-primary" :disabled="!appCtx.gxE_canSubmit" @click="appCtx.gxEssayGrade()">
          {{appCtx.gxEssayGrading ? 'AI 阅卷中…' : '提交批改'}}
        </button>
        <span class="gx-wordcount" :class="{warn: appCtx.gxEssayWords > 0 && appCtx.gxEssayWords < 2000}">
          当前 {{appCtx.gxEssayWords}} 字<span v-if="appCtx.gxEssayWords && appCtx.gxEssayWords < 2000">（考试要求 2000 字以上）</span>
        </span>
        <span class="card-desc">至少 100 字才能提交（判分需调用 AI，请勿重复点击）</span>
      </div>
    </template>

    <div v-if="appCtx.gxE_result" class="gx-case-result">
      <div class="gx-case-score">
        总分：<b>{{appCtx.gxE_result.score}}</b> / 100
        <span class="gx-bad" v-if="appCtx.gxE_result.in_wrong_book">（低于 {{appCtx.gxE_result.pass_score}}，已入错题本）</span>
        <span class="gx-ok" v-else>（已达标）</span>
      </div>
      <div class="gx-rubric" v-if="appCtx.gxEssayRubric.length">
        <div class="gx-rubric-row" v-for="r in appCtx.gxEssayRubric" :key="r.dim">
          <span class="gx-rubric-dim">{{r.label}}<em>（{{r.weight}}%）</em></span>
          <span class="gx-pbar"><span class="gx-pbar-fill" :style="{width: (r.score || 0) + '%'}"></span></span>
          <span class="gx-rubric-score">{{r.score === null || r.score === undefined ? '—' : r.score}}</span>
          <div class="gx-rubric-cmt">{{r.comment}}</div>
        </div>
      </div>
      <pre class="gx-case-fb" v-if="appCtx.gxE_result.feedback">{{appCtx.gxE_result.feedback}}</pre>
    </div>
  </div>

  <!-- ───────── 错题本 ───────── -->
  <div v-else-if="appCtx.gxSub === 'wrong'" class="card">
    <div class="card-head"><b>错题本</b>
      <span class="card-desc">
        做完题自动判错入库；重做连对 3 次自动掌握。
        {{appCtx.gxWrong.length}} 题待复习
      </span>
    </div>

    <div class="gx-tabs gx-tabs-sub">
      <button v-for="t in appCtx.gxWrongTabs" :key="t.k" class="gx-tab"
              :class="{active: appCtx.gxWrongKind === t.k}" @click="appCtx.gxPickWrongKind(t.k)">
        {{t.label}}
        <span class="gx-tab-n">{{t.k === '' ? appCtx.gxWrong.length : (appCtx.gxWrongByKind[t.k] || 0)}}</span>
      </button>
    </div>

    <div class="gx-actions">
      <button class="btn btn-primary" :disabled="appCtx.gxWrongBatchAnalyzing" @click="appCtx.gxAnalyzeWrongBatch()">
        {{appCtx.gxWrongBatchAnalyzing ? 'AI 分析中…' : '批量分析错因（最多 3 题）'}}
      </button>
      <button class="btn gx-mini-btn" v-if="appCtx.gxWrong.length" @click="appCtx.gxQuizWrongStart('single')">错题重练（单选）</button>
      <button class="btn gx-mini-btn" v-if="appCtx.gxWrong.length" @click="appCtx.gxQuizWrongStart('multi')">错题重练（多选）</button>
    </div>

    <div v-if="appCtx.gxWrongLoading" class="card-desc">加载中…</div>
    <div v-else-if="!appCtx.gxWrongShown.length" class="card-desc gx-empty">
      这个分栏还没有错题。
    </div>
    <div v-else>
      <div v-for="w in appCtx.gxWrongShown" :key="w.id" class="gx-wrong">
        <div class="gx-wrong-head">
          <span class="gx-q-type">{{w.kind === 'choice' ? (w.qtype === 'multi' ? '多选' : '单选') : (w.kind === 'essay' ? '论文' : '案例')}}</span>
          <span class="gx-q-badge" v-if="w.domain">{{w.domain}}</span>
          <span class="gx-q-badge" v-if="w.chapter">{{w.chapter}}</span>
          <span class="gx-bad">错 {{w.wrong_count}} 次</span>
          <span class="gx-streak" v-if="w.correct_streak">已连对 {{w.correct_streak}} 次</span>
          <span class="gx-streak" v-if="w.last_score">上次 {{w.last_score}} 分</span>
        </div>
        <div class="gx-q-text">{{w.question}}</div>
        <div class="gx-opts" v-if="w.options">
          <span v-for="(o, oi) in w.options" :key="oi" class="gx-opt static">{{o}}</span>
        </div>
        <div class="gx-fb" v-if="w.kind === 'choice'">
          <span v-if="w.correct">正确答案：{{w.correct}}</span>
          <span v-if="w.user_answer">你的答案：{{w.user_answer}}</span>
        </div>
        <div class="gx-analysis" v-if="w.analysis">解析：{{w.analysis}}</div>
        <!-- 错因分析：有缓存直接显示，没有则一键 AI 分析 -->
        <div class="gx-reason" v-if="appCtx.gxReasonOf(w.question_id)">
          🔍 错因分析：{{appCtx.gxReasonOf(w.question_id)}}
        </div>
        <div class="gx-actions">
          <button class="btn btn-primary" @click="appCtx.gxRetryWrong(w)">
            {{w.kind === 'choice' ? '重做这题' : '打开原题重做'}}
          </button>
          <button class="btn gx-mini-btn" :disabled="appCtx.gxWrongAnalyzing === w.question_id"
                  @click="appCtx.gxAnalyzeWrong(w)">
            {{appCtx.gxWrongAnalyzing === w.question_id ? 'AI 分析中…' :
              (appCtx.gxReasonOf(w.question_id) ? '重新分析错因' : '分析错因')}}
          </button>
          <button class="btn gx-mini-btn" @click="appCtx.gxMasterWrong(w)">标记已掌握</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ───────── 进度 ───────── -->
  <div v-else class="card">
    <div class="card-head"><b>学习进度</b><span class="card-desc">按知识域统计（没学过的显示 0）</span></div>
    <div v-if="!appCtx.gxProgress" class="card-desc">加载中…</div>
    <template v-else>
      <div class="gx-sum">
        <div class="gx-sum-item"><b>{{appCtx.gxProgress.summary.quiz_total}}</b><span>累计刷题</span></div>
        <div class="gx-sum-item"><b>{{appCtx.gxProgress.summary.quiz_correct}}</b><span>答对</span></div>
        <div class="gx-sum-item"><b>{{appCtx.gxProgress.summary.accuracy === null ? '—' : appCtx.gxProgress.summary.accuracy + '%'}}</b><span>正确率</span></div>
        <div class="gx-sum-item"><b>{{appCtx.gxProgress.summary.case_count}}</b><span>主观题批改</span></div>
        <div class="gx-sum-item"><b>{{appCtx.gxProgress.summary.knowledge_read}}</b><span>读过知识点</span></div>
        <div class="gx-sum-item"><b>{{appCtx.gxWrong.length}}</b><span>待复习错题</span></div>
      </div>
      <div class="gx-plist">
        <div v-for="row in appCtx.gxProgressRows" :key="row.domain" class="gx-prow">
          <span class="gx-pname">{{row.domain}}</span>
          <span class="gx-pbar">
            <span class="gx-pbar-fill" :style="{width: (row.accuracy === null ? 0 : row.accuracy) + '%'}"></span>
          </span>
          <span class="gx-pval">{{appCtx.gxAccText(row)}}</span>
          <span class="gx-pnum">{{row.quiz_correct}}/{{row.quiz_total}}</span>
        </div>
      </div>
    </template>
  </div>

  <!-- 知识点正文弹层 -->
  <div v-if="appCtx.gxKDetail" class="gx-modal" @click.self="appCtx.gxCloseKnowledge()">
    <div class="gx-modal-box">
      <div class="gx-modal-head">
        <b>{{appCtx.gxKDetail.code ? appCtx.gxKDetail.code + ' ' : ''}}{{appCtx.gxKDetail.title}}</b>
        <button class="gx-modal-x" @click="appCtx.gxCloseKnowledge()">✕</button>
      </div>
      <div class="gx-modal-meta">
        <span class="gx-q-badge" v-if="appCtx.gxKDetail.domain">{{appCtx.gxKDetail.domain}}</span>
        <span class="gx-q-badge" v-if="appCtx.gxKDetail.chapter">{{appCtx.gxKDetail.chapter}}</span>
        <span class="gx-q-badge" v-if="appCtx.gxKDetail.kind">{{appCtx.gxKKindLabel(appCtx.gxKDetail.kind)}}</span>
        <span class="gx-read-badge" v-if="appCtx.gxKDetail.read">✓ 已读</span>
        <span class="gx-modal-src" v-if="appCtx.gxKDetail.source_file">出处：{{appCtx.gxKDetail.source_file}}</span>
      </div>
      <div class="gx-modal-body gx-kcontent" v-html="appCtx.gxKAskHtml"></div>
      <!-- 填空速记：答案默认折叠 —— 先自己填，再点开对答案，保留原本的自测用法 -->
      <div class="gx-fill-answer" v-if="appCtx.gxKHasAnswer">
        <button class="gx-fill-btn" @click="appCtx.gxKToggleAnswer()">
          {{appCtx.gxKShowAnswer ? '收起答案' : '显示答案'}}
        </button>
        <div class="gx-fill-body" v-if="appCtx.gxKShowAnswer" v-html="appCtx.gxKAnswerHtml"></div>
      </div>
    </div>
  </div>
</div>
</template>

<script>
// GaoxiangView（高项备考，面向非学生成人用户）。业务逻辑由 App.vue 壳通过 appOptions
// mixin 统一持有（见 logic/gaoxiang.js 三字典），本组件仅 inject appCtx，自身零 data/methods
// （gxTabs 除外：纯展示配置，无业务语义）。
export default {
  name: 'GaoxiangView',
  inject: ['appCtx'],
  data() {
    return {
      gxTabs: [
        { k: 'quiz', label: '刷题' },
        { k: 'knowledge', label: '知识点' },
        { k: 'case', label: '案例分析' },
        { k: 'essay', label: '论文练习' },
        { k: 'wrong', label: '错题本' },
        { k: 'progress', label: '进度' },
      ],
    };
  },
}
</script>

<style scoped>
/* 本文件样式分两类：
   1) 普通结构化样式（如 .gx-hero / .gx-tab / .gx-kitem / 已读徽标 .gx-read-badge）—— scoped 正常作用，无需特殊处理；
   2) 知识点正文（下方 .gx-kcontent 段）—— 由 v-html 渲染，产出的 DOM 不带 scoped 的 data-v 属性，
      故其后所有选择器必须用 :deep() 穿透，详见该段顶部注释。改这里时别把 :deep() 去掉。
   已读徽标（.gx-read-badge）/ 类型角标（.gx-kitem-tag）/ 分组头「已读 x」（.gx-kgroup-read）均属第 1) 类。 */
.gx-hero{background:linear-gradient(135deg,#1e3a8a,#0e7490)}
.gx-hero-stat{text-align:right;color:#fff}
.gx-hero-num{font-size:30px;font-weight:800;line-height:1.1}
.gx-hero-num em{font-size:13px;font-style:normal;margin-left:2px}
.gx-hero-label{font-size:12px;opacity:.9}

.gx-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 4px}
.gx-tabs-sub{margin:6px 0 2px}
.gx-tab{padding:7px 16px;border-radius:999px;border:1px solid var(--line,#e5e7eb);
  background:transparent;color:inherit;cursor:pointer;font-size:14px}
.gx-tab.active{background:#0e7490;border-color:#0e7490;color:#fff}
.gx-tab-n{margin-left:6px;font-size:12px;opacity:.75}

.gx-row{display:flex;gap:10px;align-items:center;margin:10px 0;flex-wrap:wrap}
.gx-label{font-size:13px;opacity:.7;min-width:44px;padding-top:2px}
.gx-label-inline{min-width:auto;padding-top:0}
.gx-chips{display:flex;gap:6px;flex-wrap:wrap;flex:1}
.gx-chips-narrow{flex:0 0 auto}
.gx-chip{padding:5px 12px;border-radius:8px;border:1px solid var(--line,#e5e7eb);
  background:transparent;color:inherit;cursor:pointer;font-size:13px}
.gx-chip.on{background:#e0f2fe;border-color:#0e7490;color:#0e7490;font-weight:600}
.gx-start-btn{margin-left:auto}
.gx-clear-btn{padding:5px 12px;font-size:13px}
.gx-mini-btn{padding:5px 12px;font-size:13px}
.gx-link-btn{border:none;background:transparent;color:#0e7490;cursor:pointer;
  font-size:12px;padding:0 6px;text-decoration:underline}

.gx-select{padding:6px 10px;border-radius:8px;border:1px solid var(--line,#e5e7eb);
  background:transparent;color:inherit;font-size:13px;max-width:340px}
.gx-input{padding:6px 10px;border-radius:8px;border:1px solid var(--line,#e5e7eb);
  background:transparent;color:inherit;font-size:13px;min-width:200px}

.gx-quiz-wrap{margin-top:12px;border-top:1px solid var(--line,#eee);padding-top:12px}
.gx-score-bar{padding:8px 12px;border-radius:8px;background:#f0f9ff;color:#0e7490;
  font-size:14px;margin-bottom:10px}
.gx-analyzing{opacity:.8}
.gx-q{padding:12px;border:1px solid var(--line,#eee);border-radius:10px;margin-bottom:10px}
.gx-q.ok{border-color:#86efac}
.gx-q.bad{border-color:#fca5a5}
.gx-q.skip{border-style:dashed;opacity:.9}
.gx-q-head{font-size:15px;line-height:1.6}
.gx-q-type{display:inline-block;font-size:11px;padding:1px 7px;border-radius:6px;
  background:#f1f5f9;margin:0 6px;vertical-align:middle}
.gx-q-badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:6px;
  background:#ecfeff;color:#0e7490;margin:0 4px 2px 0;vertical-align:middle}
.gx-q-text{white-space:pre-wrap}
.gx-opts{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.gx-opt{text-align:left;padding:7px 12px;border-radius:8px;border:1px solid var(--line,#e5e7eb);
  background:transparent;color:inherit;cursor:pointer;font-size:14px}
.gx-opt.picked{border-color:#0e7490;background:#e0f2fe;font-weight:600}
.gx-opt.static{cursor:default;opacity:.85}
.gx-fb{margin-top:10px;font-size:13px;display:flex;gap:12px;flex-wrap:wrap;align-items:baseline}
.gx-ok{color:#15803d;font-weight:700}
.gx-bad{color:#b91c1c;font-weight:700}
.gx-skip{color:#b45309;font-weight:600}
.gx-analysis{width:100%;line-height:1.6;opacity:.9;margin-top:4px}
.gx-reason{width:100%;line-height:1.7;margin-top:6px;padding:8px 10px;border-radius:8px;
  background:#fff7ed;border-left:3px solid #fb923c;white-space:pre-wrap;font-size:13px}
.gx-reason.pending{opacity:.7;background:#f8fafc;border-left-color:#cbd5e1}

.gx-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}
.gx-empty{margin-top:12px}

.gx-klist{margin-top:12px;display:flex;flex-direction:column;gap:8px}
.gx-kitem{padding:12px;border:1px solid var(--line,#eee);border-radius:10px;cursor:pointer;
  display:flex;flex-direction:column;gap:4px}
.gx-kitem:hover{border-color:#0e7490}
/* 知识点分节（按资料类型）：类型可读性差异大，分节 + 类型角标避免混成一坨 */
.gx-kgroups{margin-top:12px;display:flex;flex-direction:column;gap:18px}
.gx-kgroup-head{display:flex;align-items:center;gap:8px;padding-bottom:6px;
  border-bottom:1px solid var(--line,#eee);font-size:14px}
.gx-kgroup-n{font-size:12px;opacity:.6}
.gx-kgroup .gx-klist{margin-top:8px}
.gx-kitem-head{display:flex;align-items:flex-start;gap:8px;justify-content:space-between}
.gx-kitem-head b{font-size:14px;line-height:1.5}
.gx-kitem-tag{flex:0 0 auto;font-size:11px;padding:1px 6px;border-radius:6px;
  background:#ecfeff;color:#0e7490;border:1px solid #a5f3fc;white-space:nowrap}
.gx-kitem-flags{flex:0 0 auto;display:flex;align-items:center;gap:6px}
/* 已读标记：打开详情即记已读（后端幂等，仅首次才计入「读过知识点」）。
   明细表 gx_knowledge_reads 是真相源，gx_progress.knowledge_read 只是它的去重计数。 */
.gx-read-badge{flex:0 0 auto;font-size:11px;padding:1px 6px;border-radius:6px;
  background:#E6F9F0;color:#1F9D63;font-weight:600;white-space:nowrap}
.gx-kgroup-read{opacity:1;color:#1F9D63}
.gx-kitem-meta{font-size:12px;opacity:.65}
.gx-kitem-sum{font-size:13px;line-height:1.6;opacity:.8;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
/* 知识点正文：PDF 抽取原文按行分段，去掉挤成一大坨的观感。
   ⚠️ 正文由 v-html 渲染（见 logic/gaoxiang.js 的 gxKBlocksHtml），v-html 产出的 DOM
   **不带 scoped 的 data-v 属性**，故所有后代选择器必须用 :deep() 穿透——否则一条都不生效
   （正文挤成一坨、填空空框不显示）。改这里时别把 :deep() 去掉。 */
.gx-kcontent :deep(p){margin:0 0 10px;line-height:1.8;font-size:14px}
.gx-kcontent :deep(p:last-child){margin-bottom:0}
/* 结构化正文：小标题 / 编号条目 / 填空空框（解析见 logic/gaoxiang.js 的 gxKParseBlocks） */
.gx-kcontent :deep(.gx-k-h){margin:14px 0 8px;padding-left:8px;border-left:3px solid #0e7490;
  font-weight:700;font-size:14.5px;line-height:1.6}
.gx-kcontent :deep(.gx-k-h:first-child){margin-top:0}
.gx-kcontent :deep(.gx-k-ul){margin:0 0 10px;display:flex;flex-direction:column;gap:6px}
.gx-kcontent :deep(.gx-k-ul:last-child){margin-bottom:0}
.gx-kcontent :deep(.gx-k-li){display:flex;gap:6px;align-items:baseline}
.gx-kcontent :deep(.gx-k-li-no){flex:0 0 auto;min-width:2.2em;text-align:right;color:#0e7490;
  font-weight:600;font-size:13px;opacity:.9}
.gx-kcontent :deep(.gx-k-li-tx){line-height:1.8}
.gx-kcontent :deep(.gx-k-blank){display:inline-block;min-width:4em;height:1em;
  border-bottom:1.5px solid currentColor;opacity:.55;margin:0 2px}
.gx-fill-body :deep(.gx-k-blank){border-bottom-color:#4E7CF6;opacity:.9}

/* 填空速记的答案区：默认折叠（先自测再对答案），展开后用底色与题目区分开 */
.gx-fill-answer{margin-top:12px;padding-top:12px;border-top:1px dashed var(--line,#E5EAF4)}
.gx-fill-btn{padding:6px 14px;border:1px solid var(--primary,#4E7CF6);border-radius:8px;
  background:transparent;color:var(--primary,#4E7CF6);font-size:13px;cursor:pointer}
.gx-fill-btn:hover{background:var(--primary-light,#EAF0FE)}
.gx-fill-body{margin-top:10px;padding:10px 12px;border-radius:10px;background:var(--primary-light,#EAF0FE)}
.gx-fill-body :deep(p){margin:0 0 8px;line-height:1.8;font-size:14px}
.gx-fill-body :deep(p:last-child){margin-bottom:0}

.gx-pick-list{margin-top:10px;display:flex;flex-direction:column;gap:8px;
  max-height:280px;overflow:auto}
.gx-pick-item{text-align:left;padding:10px 12px;border:1px solid var(--line,#eee);
  border-radius:10px;background:transparent;color:inherit;cursor:pointer;
  display:flex;flex-direction:column;gap:4px}
.gx-pick-item.on{border-color:#0e7490;background:#f0f9ff}
.gx-detail-head{display:flex;justify-content:space-between;align-items:center;
  margin-top:14px;padding-top:10px;border-top:1px solid var(--line,#eee)}

.gx-case-bg{padding:12px;border-radius:10px;background:#f8fafc;color:#0f172a;
  line-height:1.7;white-space:pre-wrap;margin-top:12px}
.gx-case-qs{margin-top:10px}
.gx-case-q-label{font-size:12px;opacity:.6;margin-bottom:4px}
.gx-case-q{line-height:1.7;font-size:14px}
.gx-case-pt{font-size:12px;opacity:.6}
.gx-textarea{width:100%;min-height:140px;margin-top:10px;padding:10px;border-radius:10px;
  border:1px solid var(--line,#e5e7eb);background:transparent;color:inherit;
  font-size:14px;line-height:1.6;resize:vertical;box-sizing:border-box}
.gx-textarea-lg{min-height:300px}
.gx-wordcount{font-size:13px;font-weight:600;color:#0e7490}
.gx-wordcount.warn{color:#b45309}
.gx-ref{margin-top:12px;padding:10px 12px;border-radius:10px;background:#fffbeb;
  border:1px solid #fde68a}
.gx-ref-item{font-size:14px;line-height:1.7;margin-bottom:8px}
.gx-ref-q{opacity:.8}
.gx-ref-a{white-space:pre-wrap;margin-top:2px}

.gx-case-result{margin-top:14px;padding:12px;border-radius:10px;background:#f0f9ff}
.gx-case-score{font-size:15px;color:#0e7490}
.gx-case-score b{font-size:22px}
.gx-case-fb{white-space:pre-wrap;font-family:inherit;font-size:14px;line-height:1.7;margin:8px 0 0}
.gx-rubric{margin-top:10px;display:flex;flex-direction:column;gap:8px}
.gx-rubric-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:13px}
.gx-rubric-dim{min-width:150px}
.gx-rubric-dim em{font-style:normal;opacity:.6;font-size:12px}
.gx-rubric-score{min-width:34px;text-align:right;font-weight:700}
.gx-rubric-cmt{flex-basis:100%;opacity:.85;line-height:1.6;
  padding-left:160px}

.gx-wrong{padding:12px;border:1px solid var(--line,#eee);border-radius:10px;margin-bottom:10px}
.gx-wrong-head{display:flex;gap:8px;align-items:center;font-size:12px;margin-bottom:6px;flex-wrap:wrap}
.gx-streak{opacity:.7}

.gx-sum{display:flex;gap:18px;flex-wrap:wrap;margin:8px 0 14px}
.gx-sum-item{display:flex;flex-direction:column}
.gx-sum-item b{font-size:20px}
.gx-sum-item span{font-size:12px;opacity:.65}
.gx-plist{display:flex;flex-direction:column;gap:8px}
.gx-prow{display:flex;align-items:center;gap:10px;font-size:13px}
.gx-pname{min-width:96px}
.gx-pbar{flex:1;height:8px;border-radius:99px;background:#eef2f7;overflow:hidden;min-width:80px}
.gx-pbar-fill{display:block;height:100%;background:linear-gradient(90deg,#0e7490,#22d3ee)}
.gx-pval{min-width:52px;text-align:right}
.gx-pnum{min-width:52px;text-align:right;opacity:.6}

.gx-modal{position:fixed;inset:0;background:rgba(15,23,42,.55);display:flex;
  align-items:center;justify-content:center;z-index:60;padding:20px}
.gx-modal-box{background:var(--bg-card,#fff);color:inherit;border-radius:14px;
  max-width:760px;width:100%;max-height:80vh;display:flex;flex-direction:column}
.gx-modal-head{display:flex;justify-content:space-between;align-items:center;
  padding:14px 16px;border-bottom:1px solid var(--line,#eee)}
.gx-modal-x{border:none;background:transparent;color:inherit;font-size:16px;cursor:pointer}
.gx-modal-meta{padding:10px 16px 0;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.gx-modal-src{font-size:12px;opacity:.6;word-break:break-all}
.gx-modal-body{padding:12px 16px 16px;overflow:auto;white-space:pre-wrap;
  line-height:1.8;font-size:14px}
</style>
