<template>
<div class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#654ea3,#eaafc8)">
          <div style="flex:1">
            <h1>🧑‍🏫 AI 学习助手</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">AI 老师认识你的学习数据！可以问它「今天该学什么」「帮我分析错题」「夸夸我」，它会结合你的真实情况回答。</p>
          </div>
          <div class="focus-stats" v-if="appCtx.assistantProfile">
            <div class="focus-stats-num">{{appCtx.assistantProfile.grade}}<em>年级</em></div>
            <div class="focus-stats-label">{{appCtx.assistantProfile.subject}} · {{appCtx.assistantChipCount}} 条学习数据</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>💬 和 AI 老师聊聊</b></div>

          <!-- 快捷提问 -->
          <div class="dict-mode-row" style="margin-top:10px;margin-bottom:6px" v-if="!appCtx.assistantLoading">
            <button v-for="q in appCtx.assistantChips" :key="q" class="dict-mode-btn" @click="appCtx.assistantAsk(q)">{{q}}</button>
          </div>

          <!-- 消息区 -->
          <div class="chat-box" ref="chatBox">
            <div v-if="!appCtx.assistantMsgs.length" class="chat-empty">
              <div style="font-size:34px">🤖</div>
              <p>嗨！我是你的 AI 学习助手，我已经看过你的学习数据啦～</p>
              <p class="chat-empty-tip">点上面任意一个问题，或者直接在下面打字问我！</p>
            </div>
            <div v-for="(m, i) in appCtx.assistantMsgs" :key="i" class="chat-row" :class="m.role === 'me' ? 'chat-me' : 'chat-ai'">
              <div class="chat-bubble" :class="m.role === 'me' ? 'bubble-me' : 'bubble-ai'">
                <span v-if="m.role === 'me'" class="chat-name">我</span>
                <span v-else class="chat-name">AI 老师</span>
                <div class="chat-text" style="white-space:pre-wrap">{{m.text}}</div>
              </div>
            </div>
            <div v-if="appCtx.assistantLoading" class="chat-row chat-ai">
              <div class="chat-bubble bubble-ai"><span class="chat-name">AI 老师</span><div class="chat-dots"><i></i><i></i><i></i></div></div>
            </div>
          </div>

          <!-- 输入区 -->
          <div class="chat-input-row">
            <input class="chat-input" v-model="appCtx.assistantDraft" placeholder="问问 AI 老师…（它会结合你的学习数据回答）"
                   @compositionstart="appCtx.composing = true" @compositionend="appCtx.composing = false" @keydown.enter="!appCtx.composing && appCtx.assistantSend()" :disabled="appCtx.assistantLoading">
            <button class="btn btn-primary" style="flex-shrink:0" :disabled="appCtx.assistantLoading || !appCtx.assistantDraft.trim()" @click="appCtx.assistantSend()">发送</button>
          </div>
        </div>
</div>
</template>

<script>
// AssistantView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'AssistantView',
  inject: ['appCtx'],
}
</script>
