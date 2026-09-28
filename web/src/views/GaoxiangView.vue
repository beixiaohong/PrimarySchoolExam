<template>
<div class="fade-enter">
  <!-- hero：与小学页面视觉区分（深蓝→青，指向职业/成人考试），并明确「非学生」定位 -->
  <div class="hero gx-hero">
    <div style="flex:1">
      <h1>🎯 高项备考</h1>
      <p class="sub" style="color:rgba(255,255,255,.92)">
        软考高级「信息系统项目管理师」· 十大知识域 · AI 出题与案例批改（成人备考专用）
      </p>
    </div>
    <div class="gx-hero-stat" v-if="appCtx.gxProgress">
      <div class="gx-hero-num">{{appCtx.gxProgress.summary.quiz_total}}<em>题</em></div>
      <div class="gx-hero-label">
        正确率 {{appCtx.gxProgress.summary.accuracy === null ? '—' : appCtx.gxProgress.summary.accuracy + '%'}}
      </div>
    </div>
  </div>

  <!-- 子页签 -->
  <div class="gx-tabs">
    <button v-for="t in gxTabs" :key="t.k" class="gx-tab"
            :class="{active: appCtx.gxSub === t.k}" @click="appCtx.gxPickSub(t.k)">
      {{t.label}}
    </button>
  </div>

  <!-- ───────── 刷题 ───────── -->
  <div v-if="appCtx.gxSub === 'quiz'" class="card">
    <div class="card-head"><b>刷题</b><span class="card-desc">按知识域出题，AI 生成的题会存进题库复用</span></div>

    <div class="gx-row">
      <span class="gx-label">知识域</span>
      <div class="gx-chips">
        <button v-for="d in appCtx.gxDomains" :key="d" class="gx-chip"
                :class="{on: appCtx.gxQDomain === d}" @click="appCtx.gxQuizDomain(d)">{{d}}</button>
      </div>
    </div>

    <div class="gx-row">
      <span class="gx-label">题型</span>
      <div class="gx-chips">
        <button class="gx-chip" :class="{on: appCtx.gxQType === 'single'}" @click="appCtx.gxQuizType('single')">单选</button>
        <button class="gx-chip" :class="{on: appCtx.gxQType === 'multi'}" @click="appCtx.gxQuizType('multi')">多选</button>
      </div>
      <button class="btn btn-primary gx-start-btn" :disabled="appCtx.gxQLoading" @click="appCtx.gxQuizStart()">
        {{appCtx.gxQLoading ? '出题中…' : '开始出题'}}
      </button>
    </div>

    <div v-if="appCtx.gxQuestions.length" class="gx-quiz-wrap">
      <!-- 结算条 -->
      <div v-if="appCtx.gxQResult" class="gx-score-bar">
        本组答对 <b>{{appCtx.gxCorrectCount}}</b> / {{appCtx.gxQuestions.length}} 题
      </div>

      <div v-for="(q, i) in appCtx.gxQuestions" :key="q.id" class="gx-q" :class="appCtx.gxResultClass(q.id)">
        <div class="gx-q-head">
          <b>{{i + 1}}.</b>
          <span class="gx-q-type">{{q.qtype === 'multi' ? '多选' : '单选'}}</span>
          <span class="gx-q-text">{{q.question}}</span>
        </div>
        <div class="gx-opts" v-if="q.options">
          <button v-for="(o, oi) in q.options" :key="oi" class="gx-opt"
                  :class="{picked: appCtx.gxIsPicked(q, o)}"
                  @click="appCtx.gxToggleOption(q, o)">{{o}}</button>
        </div>
        <!-- 提交后才展示答案与解析（答案不下发前端，来自服务端判分响应） -->
        <div v-if="appCtx.gxResultMap[q.id]" class="gx-fb">
          <span :class="appCtx.gxResultMap[q.id].is_correct ? 'gx-ok' : 'gx-bad'">
            {{appCtx.gxResultMap[q.id].is_correct ? '✅ 答对' : '❌ 答错'}}
          </span>
          <span>你的答案：{{appCtx.gxAnswers[q.id] || '—'}}　正确答案：{{appCtx.gxResultMap[q.id].correct}}</span>
          <div class="gx-analysis" v-if="appCtx.gxResultMap[q.id].analysis">解析：{{appCtx.gxResultMap[q.id].analysis}}</div>
        </div>
      </div>

      <div class="gx-actions" v-if="!appCtx.gxQResult">
        <button class="btn btn-primary" :disabled="!appCtx.gxAllAnswered || appCtx.gxQSubmitting"
                @click="appCtx.gxSubmitQuiz()">
          {{appCtx.gxQSubmitting ? '提交中…' : '提交答案'}}
        </button>
        <span class="card-desc">答完所有题才能提交</span>
      </div>
      <div class="gx-actions" v-else>
        <button class="btn btn-primary" @click="appCtx.gxQuizStart()">再来一组</button>
        <button class="btn" @click="appCtx.gxPickSub('wrong')">查看错题本</button>
      </div>
    </div>
    <div v-else class="card-desc gx-empty">
      选好知识域与题型，点「开始出题」—— 优先用题库里你没做过的题，不够时 AI 现场补题。
    </div>
  </div>

  <!-- ───────── 知识点 ───────── -->
  <div v-else-if="appCtx.gxSub === 'knowledge'" class="card">
    <div class="card-head">
      <b>知识点</b>
      <span class="card-desc">按考纲知识域浏览；没有内容时可让 AI 生成一批</span>
    </div>

    <div class="gx-row">
      <span class="gx-label">知识域</span>
      <div class="gx-chips">
        <button v-for="d in appCtx.gxDomains" :key="d" class="gx-chip"
                :class="{on: appCtx.gxKDomain === d}" @click="appCtx.gxPickDomain(d)">{{d}}</button>
      </div>
    </div>

    <div class="gx-actions">
      <button class="btn btn-primary" :disabled="appCtx.gxKGenning" @click="appCtx.gxGenerateKnowledge()">
        {{appCtx.gxKGenning ? 'AI 生成中…' : 'AI 生成该知识域知识点'}}
      </button>
      <span class="card-desc">生成的内容会落库复用，重复点击只补新增</span>
    </div>

    <div v-if="appCtx.gxKLoading" class="card-desc">加载中…</div>
    <div v-else-if="!appCtx.gxKList.length" class="card-desc gx-empty">
      「{{appCtx.gxKDomain}}」还没有知识点，点上面的按钮让 AI 生成一批。
    </div>
    <div v-else class="gx-klist">
      <div v-for="k in appCtx.gxKList" :key="k.id" class="gx-kitem" @click="appCtx.gxOpenKnowledge(k)">
        <b>{{k.code ? k.code + ' ' : ''}}{{k.title}}</b>
        <span class="card-desc">{{k.summary}}</span>
      </div>
    </div>
  </div>

  <!-- ───────── 案例分析 ───────── -->
  <div v-else-if="appCtx.gxSub === 'case'" class="card">
    <div class="card-head"><b>案例分析</b><span class="card-desc">AI 出大题，你写答案，AI 按要点批改评分</span></div>

    <div class="gx-row">
      <span class="gx-label">知识域</span>
      <div class="gx-chips">
        <button v-for="d in appCtx.gxDomains" :key="d" class="gx-chip"
                :class="{on: appCtx.gxC_domain === d}" @click="appCtx.gxCdomain(d)">{{d}}</button>
      </div>
    </div>
    <div class="gx-actions">
      <button class="btn btn-primary" :disabled="appCtx.gxC_loading" @click="appCtx.gxCaseStart()">
        {{appCtx.gxC_loading ? 'AI 出题中…' : '来一道案例大题'}}
      </button>
    </div>

    <template v-if="appCtx.gxC_question">
      <div class="gx-case-bg">{{appCtx.gxC_question.background}}</div>
      <div class="gx-case-qs">
        <div class="gx-case-q-label">答题要求</div>
        <div v-for="(s, i) in appCtx.gxC_question.sub_questions" :key="i" class="gx-case-q">
          （{{i + 1}}）{{s.q}} <span class="gx-case-pt">（{{s.points}} 分）</span>
        </div>
      </div>
      <textarea class="gx-textarea" v-model="appCtx.gxC_answer"
                placeholder="在这里作答，建议分点写（问题/原因/对策），不少于 20 字…"></textarea>
      <div class="gx-actions">
        <button class="btn btn-primary" :disabled="!appCtx.gxC_canSubmit" @click="appCtx.gxCaseGrade()">
          {{appCtx.gxC_grading ? 'AI 批改中…' : '提交批改'}}
        </button>
        <span class="card-desc">批改约需数秒，请勿重复点击</span>
      </div>
    </template>

    <div v-if="appCtx.gxC_result" class="gx-case-result">
      <div class="gx-case-score">得分：<b>{{appCtx.gxC_result.score}}</b> / 100</div>
      <pre class="gx-case-fb">{{appCtx.gxC_result.feedback}}</pre>
    </div>
  </div>

  <!-- ───────── 错题本 ───────── -->
  <div v-else-if="appCtx.gxSub === 'wrong'" class="card">
    <div class="card-head"><b>错题本</b>
      <span class="card-desc">重做连对 3 次自动掌握；{{appCtx.gxWrong.length}} 题待复习</span></div>
    <div v-if="appCtx.gxWrongLoading" class="card-desc">加载中…</div>
    <div v-else-if="!appCtx.gxWrong.length" class="card-desc gx-empty">还没有错题，去刷一组题吧。</div>
    <div v-else>
      <div v-for="w in appCtx.gxWrong" :key="w.id" class="gx-wrong">
        <div class="gx-wrong-head">
          <span class="gx-q-type">{{w.domain}}</span>
          <span class="gx-bad">错 {{w.wrong_count}} 次</span>
          <span class="gx-streak" v-if="w.correct_streak">已连对 {{w.correct_streak}} 次</span>
        </div>
        <div class="gx-q-text">{{w.question}}</div>
        <div class="gx-opts" v-if="w.options">
          <span v-for="(o, oi) in w.options" :key="oi" class="gx-opt static">{{o}}</span>
        </div>
        <div class="gx-actions">
          <button class="btn btn-primary" @click="appCtx.gxRetryWrong(w)">重做这题</button>
          <button class="btn" @click="appCtx.gxMasterWrong(w)">标记已掌握</button>
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
        <div class="gx-sum-item"><b>{{appCtx.gxProgress.summary.case_count}}</b><span>案例批改</span></div>
        <div class="gx-sum-item"><b>{{appCtx.gxProgress.summary.knowledge_read}}</b><span>读过知识点</span></div>
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
      <div class="gx-modal-body">{{appCtx.gxKDetail.content}}</div>
    </div>
  </div>
</div>
</template>

<script>
// GaoxiangView（高项备考，面向非学生成人用户）。业务逻辑由 App.vue 壳通过 appOptions
// mixin 统一持有（见 logic/gaoxiang.js 三字典），本组件仅 inject appCtx，自身零 data/methods。
export default {
  name: 'GaoxiangView',
  inject: ['appCtx'],
  data() {
    // 子页签写在这里而非 logic：纯展示配置，无业务语义，不进响应式业务状态
    return {
      gxTabs: [
        { k: 'quiz', label: '刷题' },
        { k: 'knowledge', label: '知识点' },
        { k: 'case', label: '案例分析' },
        { k: 'wrong', label: '错题本' },
        { k: 'progress', label: '进度' },
      ],
    };
  },
}
</script>

<style scoped>
.gx-hero{background:linear-gradient(135deg,#1e3a8a,#0e7490)}
.gx-hero-stat{text-align:right;color:#fff}
.gx-hero-num{font-size:30px;font-weight:800;line-height:1.1}
.gx-hero-num em{font-size:13px;font-style:normal;margin-left:2px}
.gx-hero-label{font-size:12px;opacity:.9}

.gx-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 4px}
.gx-tab{padding:7px 16px;border-radius:999px;border:1px solid var(--line,#e5e7eb);
  background:transparent;color:inherit;cursor:pointer;font-size:14px}
.gx-tab.active{background:#0e7490;border-color:#0e7490;color:#fff}

.gx-row{display:flex;gap:10px;align-items:flex-start;margin:10px 0;flex-wrap:wrap}
.gx-label{font-size:13px;opacity:.7;min-width:44px;padding-top:6px}
.gx-chips{display:flex;gap:6px;flex-wrap:wrap;flex:1}
.gx-chip{padding:5px 12px;border-radius:8px;border:1px solid var(--line,#e5e7eb);
  background:transparent;color:inherit;cursor:pointer;font-size:13px}
.gx-chip.on{background:#e0f2fe;border-color:#0e7490;color:#0e7490;font-weight:600}
.gx-start-btn{margin-left:auto}

.gx-quiz-wrap{margin-top:12px;border-top:1px solid var(--line,#eee);padding-top:12px}
.gx-score-bar{padding:8px 12px;border-radius:8px;background:#f0f9ff;color:#0e7490;
  font-size:14px;margin-bottom:10px}
.gx-q{padding:12px;border:1px solid var(--line,#eee);border-radius:10px;margin-bottom:10px}
.gx-q.ok{border-color:#86efac}
.gx-q.bad{border-color:#fca5a5}
.gx-q-head{font-size:15px;line-height:1.6}
.gx-q-type{display:inline-block;font-size:11px;padding:1px 7px;border-radius:6px;
  background:#f1f5f9;margin:0 6px;vertical-align:middle}
.gx-q-text{white-space:pre-wrap}
.gx-opts{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.gx-opt{text-align:left;padding:7px 12px;border-radius:8px;border:1px solid var(--line,#e5e7eb);
  background:transparent;color:inherit;cursor:pointer;font-size:14px}
.gx-opt.picked{border-color:#0e7490;background:#e0f2fe;font-weight:600}
.gx-opt.static{cursor:default;opacity:.85}
.gx-fb{margin-top:10px;font-size:13px;display:flex;gap:12px;flex-wrap:wrap;align-items:baseline}
.gx-ok{color:#15803d;font-weight:700}
.gx-bad{color:#b91c1c;font-weight:700}
.gx-analysis{width:100%;line-height:1.6;opacity:.9;margin-top:4px}

.gx-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}
.gx-empty{margin-top:12px}

.gx-klist{margin-top:12px;display:flex;flex-direction:column;gap:8px}
.gx-kitem{padding:12px;border:1px solid var(--line,#eee);border-radius:10px;cursor:pointer;
  display:flex;flex-direction:column;gap:4px}
.gx-kitem:hover{border-color:#0e7490}

.gx-case-bg{padding:12px;border-radius:10px;background:#f8fafc;color:#0f172a;
  line-height:1.7;white-space:pre-wrap;margin-top:12px}
.gx-case-qs{margin-top:10px}
.gx-case-q-label{font-size:12px;opacity:.6;margin-bottom:4px}
.gx-case-q{line-height:1.7;font-size:14px}
.gx-case-pt{font-size:12px;opacity:.6}
.gx-textarea{width:100%;min-height:140px;margin-top:10px;padding:10px;border-radius:10px;
  border:1px solid var(--line,#e5e7eb);background:transparent;color:inherit;
  font-size:14px;line-height:1.6;resize:vertical;box-sizing:border-box}
.gx-case-result{margin-top:14px;padding:12px;border-radius:10px;background:#f0f9ff}
.gx-case-score{font-size:15px;color:#0e7490}
.gx-case-score b{font-size:22px}
.gx-case-fb{white-space:pre-wrap;font-family:inherit;font-size:14px;line-height:1.7;margin:8px 0 0}

.gx-wrong{padding:12px;border:1px solid var(--line,#eee);border-radius:10px;margin-bottom:10px}
.gx-wrong-head{display:flex;gap:8px;align-items:center;font-size:12px;margin-bottom:6px}
.gx-streak{opacity:.7}

.gx-sum{display:flex;gap:18px;flex-wrap:wrap;margin:8px 0 14px}
.gx-sum-item{display:flex;flex-direction:column}
.gx-sum-item b{font-size:20px}
.gx-sum-item span{font-size:12px;opacity:.65}
.gx-plist{display:flex;flex-direction:column;gap:8px}
.gx-prow{display:flex;align-items:center;gap:10px;font-size:13px}
.gx-pname{min-width:76px}
.gx-pbar{flex:1;height:8px;border-radius:99px;background:#eef2f7;overflow:hidden}
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
.gx-modal-body{padding:16px;overflow:auto;white-space:pre-wrap;line-height:1.8;font-size:14px}
</style>
