<template>
  <!-- 待办类：今日任务确认 / 补签卡待确认 / 孩子的申诉 / 心愿确认。
       每类一个原生 <details>，有待办的默认展开、空的收起；折叠零 JS 状态（open 由数据派生初值）。 -->
  <div class="pc-fold-group">
    <details class="pc-fold" :open="pendingConfirmTasks.length>0">
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">🎯 今日任务确认</span>
        <span class="more">讲题/朗读/听写由家长确认完成，数量可在下方设置</span>
        <span v-if="pendingConfirmTasks.length" class="tag tag-orange">{{pendingConfirmTasks.length}} 条待处理</span>
      </summary>
      <div class="pc-fold-body">
        <div class="pc-row" v-for="t in appCtx.dailyTasks" :key="t.id" style="justify-content:space-between;flex-wrap:wrap">
          <span style="font-size:13px;color:#3a4a6b">{{t.subject}} · {{t.title}}</span>
          <span style="display:inline-flex;align-items:center;gap:8px">
            <span v-if="t.status==='done'" class="tag tag-green">✅ 已完成</span>
            <template v-else-if="t.manual && t.status==='pending_confirm'">
              <span class="tag tag-orange">孩子已提交</span>
              <button class="btn btn-primary btn-sm" @click="appCtx.parentConfirmTask(t)">确认完成 ✓</button>
            </template>
            <template v-else-if="t.manual">
              <span class="more">待孩子提交</span>
            </template>
            <span v-else class="more">{{t.progress}} / {{t.target}}</span>
          </span>
        </div>
      </div>
    </details>

    <details class="pc-fold" :open="appCtx.pendingMakeups.length>0">
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">🎫 补签卡待确认</span>
        <span class="more">孩子用补签卡完成的任务，需家长确认生效，拒绝则退回</span>
        <span v-if="appCtx.pendingMakeups.length" class="tag tag-orange">{{appCtx.pendingMakeups.length}} 条待处理</span>
      </summary>
      <div class="pc-fold-body">
        <div class="pc-list" v-if="appCtx.pendingMakeups.length">
          <div class="pc-item" v-for="m in appCtx.pendingMakeups" :key="m.log_id" style="flex-wrap:wrap">
            <div class="c-body" style="flex:1;min-width:200px">
              <b>{{m.task_title || '任务'}}</b>
              <span class="more">提交于 {{m.used_at}}</span>
            </div>
            <button class="btn btn-success btn-sm" @click="appCtx.confirmMakeup(m.log_id, 'confirm')">确认生效 ✓</button>
            <button class="btn btn-ghost btn-sm" @click="appCtx.confirmMakeup(m.log_id, 'reject')">拒绝退回</button>
          </div>
        </div>
        <p v-else class="pc-empty">没有待确认的补签申请</p>
      </div>
    </details>

    <details class="pc-fold" :open="appCtx.pendingAppeals.length>0">
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">✋ 孩子的申诉</span>
        <span class="more">孩子觉得题判错了，请家长二次确认</span>
        <span v-if="appCtx.pendingAppeals.length" class="tag tag-orange">{{appCtx.pendingAppeals.length}} 条待处理</span>
      </summary>
      <div class="pc-fold-body">
        <div class="pc-list" v-if="appCtx.pendingAppeals.length">
          <div class="pc-item" v-for="a in (appCtx.showAllPending ? appCtx.pendingAppeals : appCtx.pendingAppeals.slice(0,30))" :key="a.id" style="flex-wrap:wrap">
            <div class="c-body" style="flex:1;min-width:220px">
              <b class="appeal-q" @click="appCtx.toggleAppeal(a.id)" title="点击查看完整题目">
                [{{a.subject || '未分科'}}]
                <template v-if="!appCtx.appealExpanded[a.id]">{{ (a.question || '').length > 60 ? (a.question || '').slice(0,60)+'…' : (a.question || '') }}</template>
                <template v-else>{{ a.question || '' }}</template>
                <span class="q-toggle">{{ appCtx.appealExpanded[a.id] ? '收起 ▴' : '查看完整题目 ▾' }}</span>
              </b>
              <span>孩子答案：{{a.user_answer}} · 参考答案：{{a.correct_answer}}</span>
              <span class="more">{{a.created_at}} 提交</span>
              <input class="fill-input appeal-note" v-model="appCtx.appealNotes[a.id]" placeholder="判题备注（可选）：可填写判对/判错的理由" />
            </div>
            <button class="btn btn-primary btn-sm" :disabled="appCtx.recheckingId===a.id" @click="appCtx.aiRecheckAppeal(a)" title="让 AI 重判该题，参考答案有误会自动修正并直接通过申诉">{{ appCtx.recheckingId===a.id ? '复核中…' : '🤖 AI 复核' }}</button>
            <button class="btn btn-success btn-sm" :disabled="a._deciding" @click="appCtx.decideAppeal(a, true)" title="确认后该题改判正确、本卷得分重算">{{ a._deciding ? '处理中…' : '确认做对了 ✓' }}</button>
            <button class="btn btn-ghost btn-sm" :disabled="a._deciding" @click="appCtx.decideAppeal(a, false)">{{ a._deciding ? '处理中…' : '维持判错' }}</button>
          </div>
          <button v-if="appCtx.pendingAppeals.length > 30" class="link-btn" @click="appCtx.showAllPending = !appCtx.showAllPending">{{ appCtx.showAllPending ? '收起 ▴' : '查看全部 ' + appCtx.pendingAppeals.length + ' 条 ▾' }}</button>
        </div>
        <p v-else class="pc-empty">没有待处理的申诉</p>
      </div>
    </details>

    <details class="pc-fold" :open="appCtx.pendingWishes.length>0">
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">🌟 心愿确认</span>
        <span class="more">孩子的心愿需要家长确认才能开始，达标后由家长兑现</span>
        <span v-if="appCtx.pendingWishes.length" class="tag tag-orange">{{appCtx.pendingWishes.length}} 条待处理</span>
      </summary>
      <div class="pc-fold-body">
        <div class="pc-list" v-if="appCtx.pendingWishes.length">
          <div class="pc-item" v-for="w in appCtx.pendingWishes" :key="w.id" style="flex-wrap:wrap">
            <div class="c-body" style="flex:1"><b>{{w.title}}</b><span>{{w.status==='pending' ? '待确认' : '已完成，待兑现'}} · 进度 {{w.progress}}/{{w.target}}{{w.deadline ? ' · 截止 '+w.deadline : ''}}</span></div>
            <input v-if="w.status==='pending_redeem'" v-model="w.redeemReason" class="fill-input" maxlength="50" placeholder="兑现理由（选填）" style="max-width:150px">
            <button class="btn btn-success btn-sm" @click="appCtx.confirmWish(w)">{{w.status==='pending' ? '确认开始' : '确认兑现'}}</button>
            <button class="btn btn-ghost btn-sm" @click="appCtx.archiveWish(w)">移除</button>
          </div>
        </div>
        <p v-else class="pc-empty">没有待处理的心愿</p>
      </div>
    </details>
  </div>
</template>

<script>
// 家长管理·待办面板（tab='parent' open 态）。仅 inject appCtx，业务动作全部委托 appCtx（logic/parent.js）。
// pendingConfirmTasks 只用于「今日任务确认」的默认展开与计数徽标，口径与 notices.pending_task_confirms 一致
// （manual && status==='pending_confirm'，均为今日 dailyTasks）。
export default {
  name: 'ParentTodoPanel',
  inject: ['appCtx'],
  computed: {
    pendingConfirmTasks() {
      return (this.appCtx.dailyTasks || []).filter(t => t.manual && t.status === 'pending_confirm');
    },
  },
}
</script>
