<template>
<div class="fade-enter">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px"><h2 style="font-size:19px">学习统计</h2><span class="tag tag-blue">{{appCtx.subject}}</span></div>
        <div class="card compare-card" v-if="appCtx.selfCompare" style="margin-bottom:16px">
          <div class="card-head"><b>🚀 自我超越</b><span class="tag tag-violet">只和自己比</span></div>
          <div class="cmp-grid">
            <div class="cmp-item" v-if="appCtx.attemptDeltaText"><span class="cmp-ico">📝</span><p>{{appCtx.attemptDeltaText}}</p></div>
            <div class="cmp-item" v-if="appCtx.vocabDeltaText"><span class="cmp-ico">🔤</span><p>{{appCtx.vocabDeltaText}}</p></div>
            <div class="cmp-item" v-if="appCtx.classicalDeltaText"><span class="cmp-ico">📜</span><p>{{appCtx.classicalDeltaText}}</p></div>
            <div class="cmp-item" v-if="appCtx.selfCompare.mastered_7d>0"><span class="cmp-ico">💪</span><p>本周已消灭 {{appCtx.selfCompare.mastered_7d}} 道错题</p></div>
            <div class="cmp-item empty" v-if="!appCtx.attemptDeltaText && !appCtx.vocabDeltaText && !appCtx.classicalDeltaText && !(appCtx.selfCompare.mastered_7d>0)"><span class="cmp-ico">🌱</span><p>完成一次做题或背诵后，这里会出现"和自己比"的记录</p></div>
          </div>
        </div>
        <!-- 心情压力预警（家长视角） -->
        <div class="card mood-alert" v-if="appCtx.moodTrend && appCtx.moodTrend.alert" style="margin-bottom:16px">
          <div class="alert-ico">🤗</div>
          <div class="alert-body">
            <b>给家长的小提示</b>
            <p>{{appCtx.moodTrend.alert.text}}</p>
          </div>
        </div>
        <div class="grid-4">
          <div class="stat-card highlight"><div class="ico">🔥</div><b>{{appCtx.streakDays}}</b><span>连续学习天数</span></div>
          <div class="stat-card"><div class="ico">📝</div><b>{{appCtx.statsAttempts}}</b><span>完成试卷</span></div>
          <div class="stat-card"><div class="ico">💯</div><b>{{appCtx.avgScore}}%</b><span>平均得分</span></div>
          <div class="stat-card"><div class="ico">✅</div><b>{{appCtx.masteredTotal}}</b><span>已掌握错题</span></div>
        </div>
        <div class="grid-3" style="margin-top:16px">
          <div class="card" v-if="appCtx.subject==='英语'">
            <div class="card-head"><b>📖 单词</b><span class="tag tag-blue">{{appCtx.vocabStats.learning_count||0}} 学习中</span></div>
            <div class="big-num">{{appCtx.vocabStats.learned_count||0}}<span> / {{appCtx.vocabStats.total_words||0}}</span></div>
            <div class="progress"><i :style="{width: appCtx.statPct(appCtx.vocabStats.learned_count, appCtx.vocabStats.total_words)+'%'}"></i></div>
            <div class="mini-stats">
              <div><b>{{appCtx.vocabStats.mastered_count||0}}</b><span>已掌握</span></div>
              <div><b>{{appCtx.vocabStats.due_today||0}}</b><span>今日待复习</span></div>
              <div><b>{{appCtx.vocabStats.streak_days||0}}</b><span>连续天数</span></div>
            </div>
          </div>
          <div class="card" v-if="appCtx.subject==='语文'">
            <div class="card-head"><b>📜 古诗文</b><span class="tag tag-violet">{{appCtx.classicalStats.mastered||0}} 已掌握</span></div>
            <div class="big-num">{{appCtx.classicalStats.learned||0}}<span> / {{appCtx.classicalStats.total||0}}</span></div>
            <div class="progress"><i :style="{width: appCtx.statPct(appCtx.classicalStats.learned, appCtx.classicalStats.total)+'%'}"></i></div>
            <div class="mini-stats">
              <div><b>{{appCtx.classicalStats.mastered||0}}</b><span>已掌握</span></div>
              <div><b>{{appCtx.classicalStats.due_today||0}}</b><span>今日待复习</span></div>
              <div><b>{{appCtx.classicalStats.streak_days||0}}</b><span>连续天数</span></div>
            </div>
          </div>
          <div class="card" v-if="appCtx.subject==='英语'">
            <div class="card-head"><b>📊 语法练习</b><span class="tag tag-orange">{{appCtx.wrongAnalysis.pending||0}} 待攻克</span></div>
            <div class="big-num">{{appCtx.grammarStats.total_exercises||0}}<span> 道题库</span></div>
            <p class="card-desc">覆盖 {{appCtx.grammarStats.total_points||0}} 个语法点</p>
            <div class="mini-stats">
              <div><b>{{appCtx.wrongAnalysis.total||0}}</b><span>累计错题</span></div>
              <div><b>{{appCtx.wrongAnalysis.mastered||0}}</b><span>已掌握</span></div>
              <div><b>{{appCtx.wrongAnalysis.mastery_rate||0}}%</b><span>掌握率</span></div>
            </div>
          </div>
        </div>
        <div class="card" style="margin-top:16px">
          <div class="card-head"><b>📄 最近做题</b><button class="btn btn-ghost btn-sm" style="margin-left:auto" @click="appCtx.goTab('practice'); appCtx.practiceSub='records'">查看全部</button></div>
          <div v-if="!appCtx.recentAttempts.length" class="empty" style="padding:26px"><div class="em">📄</div><h3>暂无做题记录</h3><p>完成第一份试卷后这里会展示得分趋势</p></div>
          <div v-for="a in appCtx.recentAttempts" :key="a.id" class="attempt-item" @click="appCtx.viewAttempt(a)">
            <div class="a-score" :style="{background: a.score>=80?'var(--success-light)':a.score>=60?'var(--warning-light)':'var(--danger-light)', color: a.score>=80?'var(--success)':a.score>=60?'var(--warning)':'var(--danger)'}">{{a.score}}分</div>
            <div class="a-body"><b>{{a.exam_title}}</b><span>{{a.created_at}} · 对 {{a.correct}} / 共 {{a.total}} 题 · 用时 {{a.duration_sec}}s</span></div>
            <span class="tag" :class="a.score>=80?'tag-green':a.score>=60?'tag-orange':'tag-red'">{{a.score>=80?'优秀':a.score>=60?'良好':'待提升'}}</span>
            <span class="a-more">查看详情 ›</span>
          </div>
        </div>
</div>
</template>

<script>
// StatsView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'StatsView',
  inject: ['appCtx'],
}
</script>
