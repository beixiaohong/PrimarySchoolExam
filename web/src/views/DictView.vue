<template>
<div class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#a18cd1,#fbc2eb)">
          <div style="flex:1">
            <h1>👂 听写磨耳朵</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">听一听，写一写，耳朵和手都练起来！全对还能赚金币哦</p>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="dict-mode-row">
            <button class="dict-mode-btn" :class="{on: appCtx.dictMode==='word'}" @click="appCtx.dictSwitchMode('word')">🔤 单词听写</button>
            <button class="dict-mode-btn" :class="{on: appCtx.dictMode==='text'}" @click="appCtx.dictSwitchMode('text')">📜 古诗文听写</button>
            <span class="dict-tip">💡 听不清就点 🔊 再听一遍</span>
          </div>

          <div v-if="!appCtx.dictSession.active" class="dict-start">
            <div class="dict-start-info">
              <p><b>{{appCtx.dictMode==='word' ? '🔤 单词听写' : '📜 古诗文听写'}}</b></p>
              <p class="dict-start-desc">{{appCtx.dictMode==='word' ? '电脑朗读单词，你写出拼写，锻炼耳朵和拼写！' : '电脑朗读古诗文句子，你默写出来，加深记忆！'}}</p>
            </div>
            <button class="btn btn-primary" @click="appCtx.dictStart()">🎧 开始听写（{{appCtx.dictMode==='word' ? 10 : 5}} 题）</button>
          </div>

          <div v-else class="dict-session">
            <div class="dict-progress">第 {{appCtx.dictSession.i + 1}} / {{appCtx.dictSession.items.length}} 题</div>
            <div class="dict-question" v-if="!appCtx.dictSession.revealed">
              <button class="dict-play-btn" @click="appCtx.dictSpeak(appCtx.dictSession.current)">🔊 播放</button>
              <div class="dict-hint">{{appCtx.dictMode==='word' ? '听到单词了吗？写出它！' : '听句子，默写出来'}}</div>
              <anti-cheat-input
                v-model="appCtx.dictSession.answer"
                :mode="appCtx.dictMode==='word' ? 'alpha' : 'text'"
                :chars="appCtx.dictMode==='word' ? [] : appCtx.dictSession.candidateChars"
                :placeholder="appCtx.dictMode==='word' ? '点击字母拼出单词' : '用输入法输入句子'"
              ></anti-cheat-input>
              <button class="btn btn-primary" @click="appCtx.dictCheck()" :disabled="!appCtx.dictSession.answer.trim()">✓ 提交</button>
            </div>
            <div v-else class="dict-result" :class="{ok: appCtx.dictSession.lastOk}">
              <div class="dict-result-head">{{appCtx.dictSession.lastOk ? '✅ 答对啦！' : '❌ 再听一遍，记住它'}}</div>
              <div class="dict-result-ans">
                <div class="dict-result-line"><span>你写的：</span><b>{{appCtx.dictSession.answer}}</b></div>
                <div class="dict-result-line" v-if="!appCtx.dictSession.lastOk"><span>正确答案：</span><b class="dict-correct">{{appCtx.dictSession.current.answer}}</b></div>
                <div class="dict-result-line" v-if="appCtx.dictMode==='word' && !appCtx.dictSession.lastOk"><span>意思：</span><em>{{appCtx.dictSession.current.meaning}}</em></div>
              </div>
              <div class="dict-result-actions">
                <button class="btn" @click="appCtx.dictReplay()">🔊 再听一遍</button>
                <button class="btn btn-primary" @click="appCtx.dictNext()">{{appCtx.dictSession.i < appCtx.dictSession.items.length - 1 ? '下一题 →' : '看成绩 🏁'}}</button>
              </div>
            </div>
          </div>

          <div v-if="appCtx.dictSession.done" class="dict-done">
            <div class="dict-done-score">{{appCtx.dictSession.correct}} / {{appCtx.dictSession.items.length}}</div>
            <div class="dict-done-text" v-if="appCtx.dictSession.correct === appCtx.dictSession.items.length">🎉 全对！赚到 3 金币，去宠物家园喂小宠物吧！</div>
            <div class="dict-done-text" v-else-if="appCtx.dictSession.correct >= appCtx.dictSession.items.length * 0.6">👏 不错哦，再练几遍就能全对啦！</div>
            <div class="dict-done-text" v-else>💪 多听几遍，磨磨耳朵再来一次！</div>
            <button class="btn btn-primary" @click="appCtx.dictStart()">🔁 再来一组</button>
          </div>
        </div>
</div>
</template>

<script>
// DictView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'DictView',
  inject: ['appCtx'],
}
</script>
