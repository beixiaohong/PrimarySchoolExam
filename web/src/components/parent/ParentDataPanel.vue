<template>
  <!-- 数据与账号类：本周学习数据 + 修改家长密码（密码再嵌一层 details）。默认收起。
       注意：家长侧 childStats 是「本周一至今」窗口，孩子侧「累计学习成果」是累计值，数据源与时间窗都不同，
       故只改名 + 标注时间窗消除歧义，不物理合并（计划 §Step5「为什么不物理合并两处学习数据」）。 -->
  <div class="pc-fold-group">
    <details class="pc-fold">
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">📊 数据与账号</span>
        <span class="more">孩子本周学习概况 · 家长密码维护</span>
      </summary>
      <div class="pc-fold-body">
        <div class="pc-subtitle">本周学习数据 <span class="more">本周一至今 · 与孩子侧「累计学习成果」时间窗不同，不可直接比较</span></div>
        <div class="stats-grid">
          <div class="sg"><b>{{appCtx.childStats.week_attempts}}</b><span>本周做题(套)</span></div>
          <div class="sg"><b>{{appCtx.childStats.week_avg_score}}%</b><span>平均正确率</span></div>
          <div class="sg"><b>{{appCtx.childStats.unmastered_wrong}}</b><span>未消灭错题</span></div>
          <div class="sg"><b>{{appCtx.childStats.streak_days}}</b><span>连续学习(天)</span></div>
          <div class="sg"><b>{{appCtx.childStats.week_tasks_done}}</b><span>本周完成任务</span></div>
        </div>
        <details class="pc-fold pc-fold-nested">
          <summary class="pc-fold-head">
            <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
            <span class="pc-fold-title">🔐 修改家长密码</span>
            <span class="more">需验证当前密码</span>
          </summary>
          <div class="pc-fold-body">
            <div class="pc-row" style="flex-wrap:wrap">
              <input v-model="appCtx.pwdForm.old" type="password" class="fill-input" maxlength="32" placeholder="当前密码" style="max-width:140px">
              <input v-model="appCtx.pwdForm.new1" type="password" class="fill-input" maxlength="32" placeholder="新密码" style="max-width:140px">
              <input v-model="appCtx.pwdForm.new2" type="password" class="fill-input" maxlength="32" placeholder="再输一次" style="max-width:140px">
              <button class="btn btn-primary btn-sm" @click="appCtx.changeParentPwd()">修改</button>
            </div>
          </div>
        </details>
      </div>
    </details>
  </div>
</template>

<script>
// 家长管理·数据与账号面板。仅 inject appCtx，纯模板，无自身业务 data/methods。
export default {
  name: 'ParentDataPanel',
  inject: ['appCtx'],
}
</script>
