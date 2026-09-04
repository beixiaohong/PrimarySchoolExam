<template>
<div class="fade-enter">
        <!-- 家长管理（独立成 tab='parent'）：4 态门禁逐字沿用原 SettingsView 家长卡
             unset(设密码) / locked+reset(验证) / open(功能面板) / loading(校验兜底，#181 闪烁修复) -->
        <div class="card parent-card" style="max-width:640px">
          <div class="card-head"><b>👨‍👩‍👧 家长管理</b><span class="more">家长密码保护 · 孩子进不来</span></div>

          <!-- ① 首次使用：设置家长密码 -->
          <div v-if="appCtx.parentPhase==='unset'" class="pc-sec">
            <div class="pc-title">🔒 设置家长密码 <span class="more">设置后进入家长管理需要输密码，防止孩子乱动</span></div>
            <div class="pc-row">
              <input v-model="appCtx.pwdForm.pwd" type="password" class="fill-input" maxlength="32" placeholder="家长密码（4-32 位）" style="max-width:180px">
              <input v-model="appCtx.pwdForm.pwd2" type="password" class="fill-input" maxlength="32" placeholder="再输一次" style="max-width:180px">
            </div>
            <div class="pc-row" style="margin-top:8px">
              <input v-model="appCtx.pwdForm.hintQ" class="fill-input" maxlength="100" placeholder="密保问题（忘记密码时用，如：孩子的小名是？）">
            </div>
            <div class="pc-row" style="margin-top:8px">
              <input v-model="appCtx.pwdForm.hintA" class="fill-input" maxlength="50" placeholder="密保答案（家长才能答对哦）" style="max-width:240px">
              <button class="btn btn-primary btn-sm" @click="appCtx.setupParentPwd()">设置并进入</button>
            </div>
          </div>

          <!-- ② 已设密码：输入密码解锁 -->
          <div v-else-if="appCtx.parentPhase==='locked' || appCtx.parentPhase==='reset'" class="pc-sec">
            <div class="pc-title">🔑 家长验证</div>
            <template v-if="appCtx.parentPhase==='locked'">
              <div class="pc-row">
                <input v-model="appCtx.pwdForm.unlock" type="password" class="fill-input" maxlength="32" placeholder="输入家长密码" style="max-width:200px" @keyup.enter="appCtx.unlockParent()">
                <button class="btn btn-primary btn-sm" @click="appCtx.unlockParent()">解锁</button>
                <button class="btn btn-ghost btn-sm" @click="appCtx.parentPhase='reset'">忘记密码？</button>
              </div>
              <p class="pc-hint">孩子完成每日任务、兑换券、心愿都由家长在这里管理</p>
            </template>
            <template v-else>
              <div class="pc-row">
                <span class="more" style="font-size:13px">密保问题：{{appCtx.pwdForm.hintQ}}</span>
              </div>
              <div class="pc-row" style="margin-top:8px">
                <input v-model="appCtx.pwdForm.resetA" class="fill-input" maxlength="50" placeholder="密保答案" style="max-width:200px">
                <input v-model="appCtx.pwdForm.resetPwd" type="password" class="fill-input" maxlength="32" placeholder="新密码" style="max-width:180px">
                <button class="btn btn-primary btn-sm" @click="appCtx.resetParentPwd()">重置</button>
                <button class="btn btn-ghost btn-sm" @click="appCtx.parentPhase='locked'">返回</button>
              </div>
              <p class="pc-hint">答对密保问题即可重置密码（家长预设的问题）</p>
            </template>
          </div>

          <!-- ③ 已解锁：家长管理全部功能（按 5 类折叠面板，各面板见 components/parent/） -->
          <template v-else-if="appCtx.parentPhase==='open'">
          <div class="pc-row" style="justify-content:space-between;margin-bottom:8px">
            <span class="more" style="font-size:13px">🔓 家长模式已解锁</span>
            <button class="btn btn-ghost btn-sm" @click="appCtx.exitParentMode()">退出家长模式 →</button>
          </div>
          <parent-todo-panel></parent-todo-panel>
          <parent-study-config></parent-study-config>
          <parent-reward-panel></parent-reward-panel>
          <parent-msg-panel></parent-msg-panel>
          <parent-data-panel></parent-data-panel>
          </template>

          <!-- ④ 加载/校验中：避免首屏 parentPhase='' 误落入「已解锁」面板造成闪烁（#181 修复，必须保留） -->
          <template v-else>
            <div class="pc-sec">
              <div class="pc-title">🔄 正在校验家长密码…</div>
              <p class="pc-hint">请稍候，正在确认家长管理模式</p>
            </div>
          </template>
        </div>
</div>
</template>

<script>
// ParentView（家长管理独立视图，tab='parent'）。业务逻辑仍由 App.vue 壳经 appOptions + logic/parent.js
// 统一持有，本视图与子组件仅 inject appCtx 访问壳的响应式状态与方法，自身不持有业务 data/methods。
// 4 态门禁与 open 态下的 5 个折叠面板（待办/学习配置/激励兑现/沟通/数据与账号）逐字沿用原 SettingsView 家长卡。
import ParentTodoPanel from '../components/parent/ParentTodoPanel.vue'
import ParentStudyConfig from '../components/parent/ParentStudyConfig.vue'
import ParentRewardPanel from '../components/parent/ParentRewardPanel.vue'
import ParentMsgPanel from '../components/parent/ParentMsgPanel.vue'
import ParentDataPanel from '../components/parent/ParentDataPanel.vue'
export default {
  name: 'ParentView',
  inject: ['appCtx'],
  components: { ParentTodoPanel, ParentStudyConfig, ParentRewardPanel, ParentMsgPanel, ParentDataPanel },
}
</script>
