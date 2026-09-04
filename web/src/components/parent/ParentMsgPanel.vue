<template>
  <!-- 沟通类：「给孩子写信」= 原「留言给孩子」+「周报寄语」两个入口合并（后端两处存储与接口都不动，仅 UI 合并）。
       默认展开。一个 textarea + 两个明确动作：发给孩子看（登录即见） / 放进本周周报。 -->
  <div class="pc-fold-group">
    <details class="pc-fold" open>
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">💬 给孩子写信</span>
        <span class="more">发到孩子登录页，或放进本周成长周报</span>
      </summary>
      <div class="pc-fold-body">
        <textarea v-model="appCtx.parentMsg" class="fill-input pc-textarea" maxlength="200" rows="2"
          placeholder="写句悄悄话：如 今天数学做得不错，继续保持！"
          @compositionstart="appCtx.composing = true" @compositionend="appCtx.composing = false"
          @keydown.enter="onEnter"></textarea>
        <div class="pc-row" style="margin-top:8px;flex-wrap:wrap;gap:8px">
          <button class="btn btn-primary btn-sm" @click="appCtx.sendParentMsg()">发给孩子看（登录即见）</button>
          <button class="btn btn-ghost btn-sm" @click="putIntoWeekly()">放进本周周报</button>
        </div>
        <p class="pc-hint" v-if="appCtx.parentNote">当前周报寄语：{{appCtx.parentNote}}</p>
        <p class="pc-hint">「发给孩子看」孩子一登录就能看到（未读有提醒）；「放进本周周报」会出现在孩子的成长周报里。Enter 发送、Shift+Enter 换行。</p>
        <div class="pc-list" v-if="appCtx.sentMsgs.length">
          <div class="pc-item" v-for="m in appCtx.sentMsgs.slice(0,5)" :key="m.id">
            <div class="c-body"><b>💌 {{m.content}}</b><span>{{m.created_at}}</span></div>
          </div>
        </div>
      </div>
    </details>
  </div>
</template>

<script>
// 家长管理·沟通面板。inject appCtx 委托业务动作。留言走 /api/parent/message（parent_messages 表），
// 周报寄语走 /api/rewards/parent-note（weekly_reports.parent_note），两处后端存储与接口都不动，仅在此合并入口。
export default {
  name: 'ParentMsgPanel',
  inject: ['appCtx'],
  methods: {
    // Enter 发送、Shift+Enter 换行；IME 组词态（composing）不拦截、不发送，避免误触（沿用原留言框的 composing 保护）
    onEnter(e) {
      if (e.shiftKey) return;
      if (this.appCtx.composing) return;
      e.preventDefault();
      this.appCtx.sendParentMsg();
    },
    // 「放进本周周报」：把当前文本同步进 parentNote 再保存（后端 saveParentNote 提交 weekly_reports.parent_note）
    putIntoWeekly() {
      this.appCtx.parentNote = this.appCtx.parentMsg;
      this.appCtx.saveParentNote();
    },
  },
}
</script>
