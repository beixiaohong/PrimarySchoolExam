<template>
<div class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#667eea,#764ba2)">
          <div style="flex:1">
            <h1>❓ 十万个为什么</h1>
            <p class="sub" style="color:rgba(255,255,255,.9)">想问什么就问什么，AI 老师来解答！相同问题直接秒回，不重复问 AI</p>
          </div>
        </div>
        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>💬 对话</b>
            <span class="more">
              <button class="qa-tab" :class="{on: !appCtx.qaSessionId}" @click="appCtx.newQaSession()">➕ 新对话</button>
            </span>
          </div>
          <div class="qa-model-row">
            <span class="qa-model-label">选 AI 老师：</span>
            <button v-for="m in appCtx.qaModels" :key="m.key" class="qa-model-btn"
                    :class="{on: appCtx.qaProvider===m.key, off: !m.available}"
                    :disabled="!m.available" :title="m.vip_only && !appCtx.qaModelsVip ? 'DeepSeek 仅 VIP 用户可用' : ''"
                    @click="appCtx.qaProvider=m.key">
              {{m.label}}<span v-if="m.vip_only" class="tag tag-gold" style="margin-left:4px">VIP</span>
            </button>
            <span v-if="appCtx.qaModels && !appCtx.qaModelsVip" class="qa-vip-tip">💎 DeepSeek 仅 VIP 用户可用，找家长开通哦</span>
          </div>
          <div class="qa-sess-row" v-if="appCtx.qaSessions.length">
            <span class="qa-model-label">会话：</span>
            <button v-for="s in appCtx.qaSessions.slice(0, 6)" :key="s.session_id" class="qa-sess-btn"
                    :class="{on: appCtx.qaSessionId===s.session_id}"
                    :title="s.first_question" @click="appCtx.openQaSession(s.session_id)">
              {{s.first_question.slice(0, 10)}} <em>{{s.rounds}}轮</em>
            </button>
          </div>
          <div class="qa-chat" ref="qaChat">
            <div v-if="!appCtx.qaMessages.length" class="empty" style="padding:20px">
              <div class="em">🌱</div><h3>开始一段新对话吧</h3>
              <p>问一个问题，然后可以接着追问，AI 老师会记住我们聊过的内容</p>
            </div>
            <div v-for="(m, mi) in appCtx.qaMessages" :key="mi" class="qa-bubble" :class="m.role==='user' ? 'user' : 'ai'">
              <div class="qa-bubble-text" :class="{degraded: m.degraded}">{{m.text}}</div>
              <div class="qa-bubble-meta" v-if="m.role==='ai' && (m.provider || m.cached || m.degraded)">
                <span v-if="m.cached" class="tag tag-green" style="font-size:11px">⚡ 秒回 · 缓存</span>
                <span v-else-if="m.degraded" class="tag tag-orange" style="font-size:11px">AI 暂不可用</span>
                <span v-else class="tag tag-blue" style="font-size:11px">{{appCtx.qaModelLabel(m.provider)}}<template v-if="m.model"> · {{m.model}}</template></span>
              </div>
            </div>
          </div>
          <div class="qa-ask-row" style="margin-top:12px">
            <textarea v-model="appCtx.qaAsk" class="qa-input" rows="2" maxlength="300"
                      placeholder="例如：为什么天是蓝色的？……（问完可以继续追问，AI 会记得上下文）"
                      @keydown.enter.exact.prevent="appCtx.askQa()"></textarea>
            <button class="btn btn-primary" :disabled="appCtx.qaLoading || !appCtx.qaAsk.trim()" @click="appCtx.askQa()">
              {{appCtx.qaLoading ? 'AI 老师思考中…' : '发送 →'}}
            </button>
          </div>
        </div>
        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>📚 我的记录</b>
            <span class="more">
              <button class="qa-tab" :class="{on: appCtx.qaHistType==='all'}" @click="appCtx.qaHistType='all'; appCtx.loadQaHistory()">全部</button>
              <button class="qa-tab" :class="{on: appCtx.qaHistType==='qa'}" @click="appCtx.qaHistType='qa'; appCtx.loadQaHistory()">提问</button>
              <button class="qa-tab" :class="{on: appCtx.qaHistType==='explain'}" @click="appCtx.qaHistType='explain'; appCtx.loadQaHistory()">题目讲解</button>
            </span>
          </div>
          <div v-if="!appCtx.qaHistory.length" class="empty" style="padding:24px">
            <div class="em">🌱</div><h3>还没有记录</h3><p>问一个问题试试吧！</p>
          </div>
          <div v-else class="qa-hist-list">
            <div v-for="h in appCtx.qaHistory" :key="h.id" class="qa-hist-item" @click="h._open = !h._open">
              <div class="qa-hist-head">
                <span class="qa-hist-q">{{h.question}}</span>
                <span class="tag" :class="h.q_type==='qa' ? 'tag-blue' : 'tag-violet'">{{h.q_type==='qa' ? '提问' : '讲解'}}</span>
                <span class="qa-hist-time">{{h.created_at}}</span>
              </div>
              <div class="qa-hist-a" v-show="h._open">{{h.answer}}</div>
            </div>
          </div>
        </div>
</div>
</template>

<script>
// QaView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'QaView',
  inject: ['appCtx'],
}
</script>
