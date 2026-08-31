<template>
<div class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#00b09b,#96c93d)">
          <div style="flex:1">
            <h1>🎲 AI 趣味出题</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">AI 老师把题目包装成冒险、太空、恐龙、美食、魔法主题，全对还能拿金币！答错的题会自动进错题本。</p>
          </div>
          <div class="focus-stats" v-if="appCtx.aiQuizPlayed">
            <div class="focus-stats-num">{{appCtx.aiQuizPlayed}}<em>次</em></div>
            <div class="focus-stats-label">玩过的闯关</div>
          </div>
        </div>

        <!-- 配置区 -->
        <div v-if="!appCtx.aiQuiz.loading && !appCtx.aiQuiz.quiz" class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>🎮 选好主题，AI 老师就出题</b></div>
          <div class="form-grid" style="margin-top:16px">
            <div class="form-item"><label>学科</label>
              <select v-model="appCtx.aiQuiz.subject">
                <option>数学</option><option>语文</option><option>英语</option>
              </select>
            </div>
            <div class="form-item"><label>年级</label>
              <select v-model="appCtx.aiQuiz.grade">
                <option v-for="g in [1,2,3,4,5,6,7,8,9]" :key="'aiq-'+g" :value="g">{{g}}年级</option>
              </select>
            </div>
          </div>
          <div class="dict-mode-row" style="margin-top:14px">
            <button v-for="(t, k) in appCtx.aiQuizThemes" :key="k" class="dict-mode-btn" :class="{on: appCtx.aiQuiz.theme === k}" @click="appCtx.aiQuiz.theme = k">
              {{appCtx.aiQuizThemeEmoji[k]}} {{t}}
            </button>
          </div>
          <div style="margin-top:18px">
            <button class="btn btn-primary" @click="appCtx.aiQuizGenerate()">✨ 让 AI 出 5 道题</button>
          </div>
          <p class="card-desc" style="margin-top:10px">💡 AI 生成大约需要 10 秒，请耐心等待。每道题都有 4 个选项，全对奖励 +5 金币，答错的进错题本！</p>
        </div>

        <!-- 加载中 -->
        <div v-if="appCtx.aiQuiz.loading" class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>🤖 AI 老师正在出题…</b></div>
          <p class="card-desc">正在把 {{appCtx.aiQuiz.subject}}{{appCtx.aiQuiz.grade}}年级题目包装成「{{appCtx.aiQuizThemeEmoji[appCtx.aiQuiz.theme]}} {{appCtx.aiQuizThemes[appCtx.aiQuiz.theme]}}」主题，请稍候</p>
          <div class="loading-bar"><div class="loading-bar-inner"></div></div>
        </div>

        <!-- 作答区 -->
        <template v-if="appCtx.aiQuiz.quiz && !appCtx.aiQuiz.graded">
          <div class="card" style="max-width:760px;margin-top:16px">
            <div class="card-head"><b>🎯 {{appCtx.aiQuiz.themeName}} · {{appCtx.aiQuiz.subject}}闯关</b>
              <span style="float:right;font-size:13px;color:#999">已答 {{appCtx.aiQuizAnswered}}/{{appCtx.aiQuiz.quiz.length}} 题</span>
            </div>
            <div class="quiz-q" v-for="(q, i) in appCtx.aiQuiz.quiz" :key="i">
              <div class="quiz-q-title">{{i + 1}}. {{q.question}}</div>
              <div v-if="q.options && q.options.length" class="quiz-options">
                <button v-for="(o, j) in q.options" :key="j" class="quiz-opt-btn"
                        :class="{on: appCtx.aiQuiz.answers[i] === o[0]}"
                        @click="appCtx.aiQuizPick(i, o[0])">{{o}}</button>
              </div>
              <input v-else class="quiz-fill" v-model="appCtx.aiQuiz.inputs[i]" placeholder="想一想，把答案打在这里" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" @compositionstart="appCtx.composing = true" @compositionend="appCtx.composing = false" @keydown.enter="!appCtx.composing && appCtx.aiQuizGrade()">
            </div>
            <div style="margin-top:18px;text-align:center">
              <button class="btn btn-primary" :disabled="appCtx.aiQuizAnswered < appCtx.aiQuiz.quiz.length" @click="appCtx.aiQuizGrade()">✅ 交卷判分</button>
            </div>
          </div>
        </template>

        <!-- 判分结果 -->
        <template v-if="appCtx.aiQuiz.quiz && appCtx.aiQuiz.graded">
          <div class="card" style="max-width:760px;margin-top:16px">
            <div class="card-head"><b>{{appCtx.aiQuiz.score.correct === appCtx.aiQuiz.quiz.length ? '🎉 全对！太厉害了！' : '📋 判分结果'}}</b></div>
            <div class="dict-done-text" style="margin-bottom:14px">
              答对 <b style="color:var(--primary)">{{appCtx.aiQuiz.score.correct}}</b> / {{appCtx.aiQuiz.quiz.length}} 题
              <span v-if="appCtx.aiQuiz.rewardGranted" style="color:#e6a23c"> · 全对奖励金币 +{{appCtx.aiQuiz.rewardGranted}} 💰</span>
            </div>
            <div class="quiz-q" v-for="(q, i) in appCtx.aiQuiz.quiz" :key="i">
              <div class="quiz-q-title" :class="appCtx.aiQuiz.score.detail[i] ? 'q-right' : 'q-wrong'">
                {{i + 1}}. {{q.question}} <span class="q-mark">{{appCtx.aiQuiz.score.detail[i] ? '✓' : '✗'}}</span>
              </div>
              <div class="quiz-fun" v-if="!appCtx.aiQuiz.score.detail[i]">你的答案：{{appCtx.aiQuizUserAnswer(i)}} · 正确答案：{{q.answer}}</div>
              <div class="quiz-fun">{{q.explanation}}</div>
              <div class="quiz-fun" style="background:linear-gradient(90deg,#fff7e6,#fffbe6);border-color:#ffd591">🧠 {{q.fun}}</div>
            </div>
            <div style="margin-top:18px;text-align:center">
              <button class="btn btn-primary" @click="appCtx.aiQuizReset()">🔁 再来一组</button>
            </div>
          </div>
        </template>
</div>
</template>

<script>
// AiquizView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'AiquizView',
  inject: ['appCtx'],
}
</script>
