<template>
  <div class="fade-enter">
    <div class="sub-tabs">
      <button class="pill" :class="{active: appCtx.practiceSub==='generate'}" @click="appCtx.practiceSub='generate'">生成试卷</button>
      <button class="pill" :class="{active: appCtx.practiceSub==='grammar'}" @click="appCtx.practiceSub='grammar'; appCtx.loadGrammarPoints()" v-if="appCtx.subject==='英语'">语法练习</button>
      <button class="pill" :class="{active: appCtx.practiceSub==='records'}" @click="appCtx.practiceSub='records'; appCtx.loadAttempts()">做题记录</button>
    </div>

    <!-- 生成试卷 -->
    <div v-if="appCtx.practiceSub==='generate'">
      <div class="card" style="max-width:720px">
        <h3 style="font-size:17px;margin-bottom:18px">生成新试卷</h3>
        <div class="form-grid">
          <div class="form-item">
            <label>学科</label>
            <select v-model="appCtx.subject" @change="appCtx.onSubjectChange"><option v-for="s in appCtx.subjectOptions" :key="'gen-'+s">{{s}}</option></select>
          </div>
          <div class="form-item">
            <label>题数</label>
            <input type="number" v-model.number="appCtx.genCount" min="1" max="200">
          </div>
          <div class="form-item full">
            <label>出题策略</label>
            <div style="font-size:13px;color:var(--text-2);line-height:1.7">难度根据最近成绩自动调整；约 30% 题目针对未掌握的错题题型</div>
          </div>
        </div>
        <div style="margin-top:22px;display:flex;gap:12px">
          <button class="btn btn-primary" :disabled="appCtx.generating" @click="appCtx.generateExam">{{appCtx.generating ? '生成中…' : '生成并开始做题'}}</button>
          <span style="font-size:12px;color:var(--text-3);align-self:center">生成后自动入库，答错的题自动进入错题本</span>
        </div>
      </div>
    </div>

    <!-- 语法练习 -->
    <div v-if="appCtx.practiceSub==='grammar'">
      <div class="card" v-if="!appCtx.grammarQuiz.length">
        <h3 style="font-size:17px;margin-bottom:14px">语法点选择</h3>
        <div class="filter-bar" style="margin:0 0 14px">
          <button class="pill" :class="{active: appCtx.grammarCategory===''}" @click="appCtx.grammarCategory=''; appCtx.loadGrammarPoints()">全部</button>
          <button class="pill" :class="{active: appCtx.grammarCategory==='时态'}" @click="appCtx.grammarCategory='时态'; appCtx.loadGrammarPoints()">时态</button>
          <button class="pill" :class="{active: appCtx.grammarCategory==='词法'}" @click="appCtx.grammarCategory='词法'; appCtx.loadGrammarPoints()">词法</button>
          <button class="pill" :class="{active: appCtx.grammarCategory==='句型'}" @click="appCtx.grammarCategory='句型'; appCtx.loadGrammarPoints()">句型</button>
        </div>
        <div v-for="p in appCtx.grammarPoints" :key="p.id" class="text-card" @click="appCtx.selectGrammarPoint(p)">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <div class="t-title">{{p.name}}</div>
              <div class="t-meta">{{p.category}} · {{p.exercise_count}} 题 · {{p.grade}}年级起</div>
            </div>
            <span class="tag" :class="p.exercise_count>0?'tag-blue':'tag-gray'">{{p.exercise_count}} 题</span>
          </div>
        </div>
      </div>
      <div v-else class="quiz-wrap" style="max-width:720px;margin:0">
        <div class="quiz-top">
          <span class="qname">📝 语法练习</span>
          <div class="progress"><i :style="{width: (appCtx.grammarQuizIndex/appCtx.grammarQuiz.length*100)+'%'}"></i></div>
          <span class="qcount">{{appCtx.grammarQuizIndex+1}} / {{appCtx.grammarQuiz.length}}</span>
        </div>
        <div class="quiz-card">
          <div class="quiz-sub"><span class="tag tag-violet">{{appCtx.grammarQuiz[appCtx.grammarQuizIndex].grammar_point_name}}</span> <span class="tag tag-gray">{{appCtx.typeLabel(appCtx.grammarQuiz[appCtx.grammarQuizIndex].exercise_type)}}</span></div>
          <div class="quiz-q">{{appCtx.grammarQuiz[appCtx.grammarQuizIndex].question}}</div>
          <template v-if="appCtx.grammarQuiz[appCtx.grammarQuizIndex].exercise_type==='choice'">
            <button v-for="(opt, oi) in appCtx.grammarQuiz[appCtx.grammarQuizIndex].options" :key="oi" class="option"
                    :class="appCtx.optClass(opt, appCtx.grammarQuiz[appCtx.grammarQuizIndex])" :disabled="appCtx.grammarSubmitted"
                    @click="appCtx.grammarAnswer(opt)">{{opt}}</button>
          </template>
          <input v-else class="fill-input" v-model="appCtx.grammarInput" placeholder="输入答案后回车" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" @compositionstart="appCtx.composing = true" @compositionend="appCtx.composing = false" @keydown.enter="!appCtx.composing && appCtx.grammarSubmit()" :disabled="appCtx.grammarSubmitted">
          <div class="feedback" :class="{on: appCtx.grammarSubmitted, ok: appCtx.grammarFeedbackOk, no: !appCtx.grammarFeedbackOk}">
            <h4>{{appCtx.grammarFeedbackOk ? '✓ 回答正确！' : '✗ 答错了，看看解析'}}</h4>
            <p v-if="!appCtx.grammarFeedbackOk">正确答案：{{appCtx.grammarCurrentAnswer}}</p>
            <p v-if="appCtx.grammarCurrentExplanation">💡 {{appCtx.grammarCurrentExplanation}}</p>
          </div>
          <div class="quiz-actions">
            <span style="font-size:12px;color:var(--text-3)">答错的题自动进入错题本</span>
            <div class="right">
              <button class="btn btn-ghost" @click="appCtx.grammarExit()">退出</button>
              <button class="btn btn-primary" :disabled="!appCtx.grammarSubmitted" @click="appCtx.grammarNext()">{{appCtx.grammarQuizIndex===appCtx.grammarQuiz.length-1 ? '查看结果 →' : '下一题 →'}}</button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="appCtx.grammarResult" class="done-wrap">
        <div class="done-illus" :class="{no: appCtx.grammarResult.score<60}">{{appCtx.grammarResult.score>=90 ? '🏆' : appCtx.grammarResult.score>=60 ? '🎉' : '💪'}}</div>
        <h2>{{appCtx.grammarResult.score>=90 ? '太棒了！' : appCtx.grammarResult.score>=60 ? '继续加油！' : '别灰心，再来一次'}}</h2>
        <p class="sub">语法练习完成</p>
        <div class="done-grid">
          <div class="done-cell"><b>{{appCtx.grammarResult.score}}分</b><span>得分</span></div>
          <div class="done-cell"><b>{{appCtx.grammarResult.correct}}/{{appCtx.grammarResult.total}}</b><span>答对题数</span></div>
          <div class="done-cell"><b>{{appCtx.grammarResult.wrong}}</b><span>错题（已入本）</span></div>
        </div>
        <div class="done-note" v-if="appCtx.grammarResult.wrong>0">📝 {{appCtx.grammarResult.wrong}} 道错题已自动加入错题本，可在「错题本」中复盘错因并变式重练</div>
        <div class="done-actions">
          <button class="btn btn-ghost" @click="appCtx.grammarResult=null; appCtx.grammarQuiz=[]; appCtx.loadGrammarPoints()">再来一组</button>
          <button class="btn btn-primary" @click="appCtx.goTab('wrong')">去错题本复盘</button>
        </div>
      </div>
    </div>

    <!-- 做题记录（跟随顶部学科，只显示当前学科） -->
    <div v-if="appCtx.practiceSub==='records'">
      <div class="card">
        <h3 style="font-size:17px;margin-bottom:14px">做题记录 · {{appCtx.subject}}</h3>
        <div v-if="appCtx.attempts===null" class="empty">⏳ 加载中…</div>
        <div v-else-if="!appCtx.attempts.length" class="empty"><div class="em">📄</div><h3>暂无做题记录</h3><p>去刷题中心生成试卷开始练习吧</p><button class="btn btn-primary" @click="appCtx.practiceSub='generate'">去生成试卷</button></div>
        <div v-else>
          <div v-for="a in appCtx.attempts" :key="a.id" class="attempt-item" @click="appCtx.viewAttempt(a)">
            <div class="a-score" :style="{background: a.score>=80?'var(--success-light)':a.score>=60?'var(--warning-light)':'var(--danger-light)', color: a.score>=80?'var(--success)':a.score>=60?'var(--warning)':'var(--danger)'}">{{a.score}}分</div>
            <div class="a-body"><b>{{a.exam_title}}</b><span>{{a.created_at}} · 对 {{a.correct}} / 共 {{a.total}} 题 · 用时 {{a.duration_sec}}s</span></div>
            <span class="tag" :class="a.score>=80?'tag-green':a.score>=60?'tag-orange':'tag-red'">{{a.score>=80?'优秀':a.score>=60?'良好':'待提升'}}</span>
            <span class="a-more">查看详情 ›</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// 刷题中心（B1 组件化第二批）。同 ReciteView：业务逻辑由壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'PracticeView',
  inject: ['appCtx'],
}
</script>
