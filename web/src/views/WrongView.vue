<template>
<div class="fade-enter">
        <div class="grid-4">
          <div class="stat-card"><div class="ico">📚</div><b>{{appCtx.wrongAnalysis.total}}</b><span>累计错题</span></div>
          <div class="stat-card highlight"><div class="ico">⏳</div><b>{{appCtx.wrongAnalysis.pending}}</b><span>待攻克</span></div>
          <div class="stat-card"><div class="ico">✅</div><b>{{appCtx.wrongAnalysis.mastered}}</b><span>已掌握</span></div>
          <div class="stat-card"><div class="ico">🎯</div><b>{{appCtx.wrongAnalysis.mastery_rate}}%</b><span>掌握率</span></div>
        </div>

        <!-- 列表 -->
        <div v-if="appCtx.wrongScreen==='list'">
          <div class="filter-bar">
            <button class="pill" :class="{active: appCtx.wrongKind==='all'}" @click="appCtx.wrongKind='all'; appCtx.loadWrongItems()">全部</button>
            <button class="pill" :class="{active: appCtx.wrongKind==='exam'}" @click="appCtx.wrongKind='exam'; appCtx.loadWrongItems()">📝 试卷错题</button>
            <button class="pill" :class="{active: appCtx.wrongKind==='study'}" @click="appCtx.wrongKind='study'; appCtx.loadWrongItems()">✏️ 学习错题</button>
            <span class="filter-sep"></span>
            <button class="pill" :class="{active: appCtx.wrongStatus==='pending'}" @click="appCtx.wrongStatus='pending'; appCtx.loadWrongItems()">未掌握</button>
            <button class="pill" :class="{active: appCtx.wrongStatus==='mastered'}" @click="appCtx.wrongStatus='mastered'; appCtx.loadWrongItems()">已掌握</button>
            <span class="filter-sep"></span><span class="tag tag-blue">{{appCtx.subject}}</span>
            <button class="btn btn-primary btn-sm" style="margin-left:auto" @click="appCtx.startWrongPractice()" title="从错题本随机抽 5 道错题，每道配 3 道同类型题，整组全对自动掌握">🎯 练习错题</button>
            <button class="btn btn-ghost btn-sm" @click="appCtx.loadAnalysis(); appCtx.wrongScreen='analysis'">📊 错因分析</button>
          </div>
          <div class="card teach-due" v-if="appCtx.tomorrowQueue.count>0" @click="appCtx.wrongStatus='pending'; appCtx.loadWrongItems()">
            <b>🌙 明日复习队列：{{appCtx.tomorrowQueue.count}} 道题重做仍错，明天再来一次</b>
            <span>{{(appCtx.tomorrowQueue.items||[]).slice(0,3).map(i=>i.subject+(i.module_name?'·'+i.module_name:'')).join('、')}}<template v-if="appCtx.tomorrowQueue.count>3"> 等</template> · 点我查看</span>
          </div>
          <div class="card teach-due" v-if="appCtx.teachDue.length" @click="appCtx.openRecheck()">
            <b>🔁 7 天到啦，考考自己还记得吗？</b>
            <span>有 {{appCtx.teachDue.length}} 道讲给家长的题待复习验证，点我开始</span>
          </div>
          <div class="card">
            <div v-if="!appCtx.wrongItems.length" class="empty"><div class="em">🎉</div><h3>太棒了，这里没有错题</h3><p>继续保持，或者去刷题中心练练手</p><button class="btn btn-primary" @click="appCtx.goTab('practice')">去刷题</button></div>
            <div v-for="w in (appCtx.showAllWrong ? appCtx.wrongItems : appCtx.wrongItems.slice(0,100))" :key="w.key" class="wrong-item" :class="{mastered: w.mastered}" @click="appCtx.openWrongDetail(w)">
              <div class="wi-ico" :class="w.kind==='exam'?'t-blue':'t-violet'">{{w.kind==='exam'?'📝':'✏️'}}</div>
              <div class="wi-body">
                <div class="wi-q">{{w.question}}</div>
                <div class="wi-meta">
                  <span class="tag" :class="w.kind==='exam'?'tag-blue':'tag-violet'">{{w.source}}</span>
                  <span class="tag tag-gray">{{w.subject}}</span>
                  <span v-if="w.is_unanswered" class="tag tag-yellow">未答</span>
                  <span v-else-if="!w.mastered" class="tag tag-red">答错</span>
                  <span v-if="!w.mastered && w.cause" class="tag tag-orange">{{appCtx.causeLabel(w.cause)}}</span>
                  <span class="wi-count">错 {{w.error_count}} 次</span>
                  <span class="wi-last">{{w.wrong_at}}</span>
                </div>
              </div>
              <span v-if="w.mastered" class="tag tag-green">已掌握</span>
              <span class="arrow">›</span>
            </div>
            <button v-if="appCtx.wrongItems.length > 100" class="link-btn" @click="appCtx.showAllWrong = !appCtx.showAllWrong" style="margin-top:10px">{{ appCtx.showAllWrong ? '收起 ▴' : '查看全部 ' + appCtx.wrongItems.length + ' 条错题 ▾' }}</button>
          </div>
        </div>

        <!-- 详情复盘 -->
        <div v-if="appCtx.wrongScreen==='detail' && appCtx.curWrong">
          <button class="btn btn-ghost btn-sm" @click="appCtx.wrongScreen='list'">← 返回列表</button>
          <div class="card" style="margin-top:12px">
            <div class="card-head"><b>错题复盘</b><span class="tag" :class="appCtx.curWrong.kind==='exam'?'tag-blue':'tag-violet'" style="margin-left:auto">{{appCtx.curWrong.source}}</span></div>
            <div class="quiz-q" style="font-size:17px;margin:16px 0 4px">{{appCtx.curWrong.question}}</div>
            <p class="quiz-sub">回顾当时为什么错，才能不再错</p>
            <!-- 未答题：先作答再判断对错，不直接显示答案 -->
            <div v-if="appCtx.curWrong.is_unanswered" class="unanswered-box" style="margin:12px 0">
              <p style="color:#8B7CF6;font-weight:600;margin-bottom:8px">这道题当时未作答，请先作答：</p>
              <div style="display:flex;gap:8px;align-items:center">
                <input v-model="appCtx.curWrong._answerInput" class="quiz-fill-input" placeholder="输入你的答案" style="flex:1" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" @compositionstart="appCtx.composing = true" @compositionend="appCtx.composing = false" @keydown.enter="!appCtx.composing && appCtx.answerUnanswered()">
                <button class="btn btn-primary" @click="appCtx.answerUnanswered">提交</button>
              </div>
            </div>
            <!-- 答错题：显示答案对比 -->
            <div v-else class="detail-compare">
              <div class="answer-box wrong"><span>我的答案</span><b>{{appCtx.curWrong.user_answer || '（未作答）'}}</b></div>
              <div class="answer-box right"><span>正确答案</span><b>{{appCtx.curWrong.correct_answer}}</b></div>
            </div>
            <div v-if="appCtx.curWrong.explanation" class="feedback ok" style="display:block">
              <h4>📖 解析</h4><p>{{appCtx.curWrong.explanation}}</p>
            </div>
            <!-- AI 讲解（内联展示在题目下方，不弹窗） -->
            <div class="inline-explain" v-if="appCtx.curWrong.explaining || appCtx.curWrong.aiText || appCtx.curWrong.aiError">
              <div v-if="appCtx.curWrong.explaining" class="explain-loading">
                <span class="explain-spin"></span>🤖 老师正在讲解…（通常 3-10 秒，请稍等）
              </div>
              <template v-else-if="appCtx.curWrong.aiText">
                <div class="explain-seg" v-for="(s,i) in appCtx.explainSectionsOf(appCtx.curWrong.aiText)" :key="i" :class="{first: i===0}">
                  <div class="seg-title" v-if="s.title">【{{s.title}}】</div>
                  <div class="seg-body">
                    <p v-for="(line,li) in s.body.split('\n').filter(x=>x.trim())" :key="li">{{line}}</p>
                  </div>
                </div>
                <p class="explain-deg" v-if="appCtx.curWrong.aiDegraded">（离线讲解版 · 已尽力帮到你了）</p>
              </template>
              <p v-else class="explain-err">😵 {{appCtx.curWrong.aiError}} <button class="btn btn-ghost btn-sm" @click="appCtx.openExplain(appCtx.curWrong)">重试</button></p>
            </div>
            <div class="card-head" style="margin-top:22px"><b>💡 这次错在哪？</b><span class="more">选择后系统会针对性推送变式练习</span></div>
            <div class="cause-grid">
              <button class="cause-item" :class="{selected: appCtx.curWrong.cause==='careless'}" @click="appCtx.submitCause('careless')"><span class="ci-ico">😅</span>粗心大意<span class="ci-d">看错数字 / 符号 / 漏字</span></button>
              <button class="cause-item" :class="{selected: appCtx.curWrong.cause==='concept'}" @click="appCtx.submitCause('concept')"><span class="ci-ico">🤔</span>概念不清<span class="ci-d">知识点本身没掌握</span></button>
              <button class="cause-item" :class="{selected: appCtx.curWrong.cause==='method'}" @click="appCtx.submitCause('method')"><span class="ci-ico">🛠️</span>方法不会<span class="ci-d">不知道用什么方法解题</span></button>
              <button class="cause-item" :class="{selected: appCtx.curWrong.cause==='reading'}" @click="appCtx.submitCause('reading')"><span class="ci-ico">👀</span>审题失误<span class="ci-d">没看清题目要求 / 条件</span></button>
            </div>
            <div class="mastery-row" v-if="appCtx.curWrong.mastered">
              <span>🎉 已掌握</span>
              <div class="progress"><i style="width:100%;background:var(--success)"></i></div>
            </div>
            <div class="detail-actions">
              <button class="btn btn-primary" v-if="appCtx.curWrong.kind==='exam' && appCtx.curWrong.question_id" :disabled="appCtx.curWrong.explaining || !appCtx.curWrong.cause" @click="appCtx.openExplain(appCtx.curWrong)">{{appCtx.curWrong.explaining ? '⏳ 讲解中…' : '🤖 AI 讲解'}}</button>
              <button class="btn btn-primary" :disabled="!appCtx.curWrong.cause" @click="appCtx.openTeach(appCtx.curWrong)">🎓 出题给家长</button>
              <button class="btn btn-primary" :disabled="!appCtx.curWrong.cause" @click="appCtx.startWrongRetry(appCtx.curWrong)">🎯 变式重练</button>
              <button class="btn btn-success" v-if="!appCtx.curWrong.mastered" :disabled="!appCtx.curWrong.cause" @click="appCtx.markWrongMastered(appCtx.curWrong)" title="先做 3 道同类型题，全部答对才标记已掌握">✅ 检测掌握（3 题全对）</button>
              <button class="btn btn-ghost" v-if="appCtx.curWrong.kind==='exam' && appCtx.curWrong.question_id && !appCtx.curWrong.is_unanswered" :disabled="appCtx.rejudging" @click="appCtx.aiRejudgeWrong(appCtx.curWrong)" title="让 AI 重新判断，参考答案本身算错会自动修正并加分">🤖 用 AI 重判</button>
              <button class="btn btn-ghost" @click="appCtx.wrongScreen='list'">返回列表</button>
            </div>
            <p v-if="!appCtx.curWrong.cause && !appCtx.curWrong.is_unanswered" style="text-align:center;color:var(--text-3);font-size:13px;margin-top:8px">💡 请先选择错因，才能进行讲解、重练等操作</p>
          </div>
        </div>

        <!-- 错因分析 -->
        <div v-if="appCtx.wrongScreen==='analysis'">
          <button class="btn btn-ghost btn-sm" @click="appCtx.wrongScreen='list'">← 返回列表</button>
          <div class="card" style="margin-top:12px">
            <div class="card-head"><b>📊 错因分析</b><span class="more">共 {{appCtx.wrongAnalysis.total}} 道错题 · {{appCtx.wrongAnalysis.pending}} 道待攻克</span></div>
            <div class="chart-wrap">
              <div class="donut">
                <svg width="220" height="220" viewBox="0 0 220 220">
                  <circle cx="110" cy="110" r="90" fill="none" stroke="#EDF0F8" stroke-width="26"/>
                  <circle v-for="(seg,i) in appCtx.donutSegs" :key="i" cx="110" cy="110" r="90" fill="none" :stroke="seg.color" stroke-width="26" :stroke-dasharray="(seg.len)+' 999'" :stroke-dashoffset="seg.off" transform="rotate(-90 110 110)"/>
                </svg>
                <div class="center"><b>{{appCtx.wrongAnalysis.pending}}</b><span>待攻克错题</span></div>
              </div>
              <div class="legend">
                <div class="legend-row" v-for="c in appCtx.wrongAnalysis.by_cause" :key="c.code">
                  <span class="sw" :style="{background: appCtx.causeColor(c.code)}"></span>
                  <span>{{c.label}}</span><span class="pct" :style="{color: appCtx.causeColor(c.code)}">{{c.count}} 道</span>
                </div>
                <div v-if="!(appCtx.wrongAnalysis.by_cause||[]).length" class="empty" style="padding:20px"><div class="em">🍀</div><h3>暂无错因数据</h3><p>去错题详情里选择错因吧</p></div>
              </div>
            </div>
          </div>
          <div class="card" style="margin-top:16px">
            <div class="card-head"><b>📈 按学科分布</b></div>
            <div class="bar-row" v-for="s in appCtx.wrongAnalysis.by_subject" :key="s.subject" style="margin-top:14px">
              <div class="bl"><span>{{s.subject}}</span><b>{{s.count}} 道</b></div>
              <div class="bar-track"><div class="bar-fill" :style="{width: appCtx.subjPct(s)+'%', background: appCtx.subjColor(s)}"></div></div>
            </div>
            <div class="card-head" style="margin-top:24px"><b>🕒 待攻克错因分布</b></div>
            <div class="bar-row" v-for="c in appCtx.wrongAnalysis.by_cause" :key="c.code" style="margin-top:14px">
              <div class="bl"><span>{{c.label}}</span><b>{{c.pending}} 道</b></div>
              <div class="bar-track"><div class="bar-fill" :style="{width: appCtx.causePct(c)+'%', background: appCtx.causeColor(c.code)}"></div></div>
            </div>
            <div class="suggest-card" v-if="appCtx.topCause">
              <div class="s-ico">💡</div>
              <div><b>优先攻克「{{appCtx.topCause.label}}」</b><p>这是你失分最多的原因，建议回到对应知识点重新学习，再配合变式练习巩固</p></div>
              <button class="btn btn-primary" @click="appCtx.retryTopCause()">去练习 →</button>
            </div>
          </div>
        </div>
</div>
</template>

<script>
// WrongView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'WrongView',
  inject: ['appCtx'],
}
</script>
