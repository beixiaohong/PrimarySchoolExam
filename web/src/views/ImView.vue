<template>
  <!-- IM 即时通讯视图（tab='im'）
       入口：与父 LedgerView 同构；业务全在 logic/im.js，组件通过 inject('appCtx') 访问响应式状态。
       布局：桌面(>768px)恒三栏 chats | messages | right；移动端(≤768px)单栏，
       由 mobileCls 状态类切换显示哪一栏（im-mv-chats / im-mv-message / im-mv-panel） -->
  <div class="im-shell" :class="mobileCls">
    <!-- 左侧：会话列表（桌面常驻；移动端无会话/未点开聊天时独占一屏） -->
    <section class="im-pane im-pane-left">
      <header class="im-pane-header">
        <span class="im-pane-title">消息</span>
        <span v-if="ctx.imUnreadTotal" class="im-badge">{{ ctx.imUnreadTotal }}</span>
        <span class="im-pane-spacer"></span>
        <button class="im-icon-btn" @click="ctx.imGoTab('contacts')" title="联系人">＋</button>
      </header>
      <im-chats />
    </section>

    <!-- 中间：消息区（桌面常驻；移动端选中会话后独占一屏） -->
    <section class="im-pane im-pane-mid">
      <im-messages v-if="ctx.imActiveChat" />
      <div v-else class="im-empty">
        <p>选择左侧任一会话开始聊天</p>
      </div>
    </section>

    <!-- 右侧：联系人 / 设置 / 群信息（桌面常驻；移动端进入对应 tab 后独占一屏） -->
    <aside class="im-pane im-pane-right">
      <im-contacts v-if="ctx.imTab === 'contacts'" />
      <im-settings v-else-if="ctx.imTab === 'settings'" />
      <im-group-info v-else-if="ctx.imTab === 'group' && ctx.imIsGroup" />
      <div v-else class="im-empty im-empty-thin">
        <p v-if="ctx.imIsGroup">点击右上角「群信息」查看</p>
        <p v-else-if="ctx.imIsPrivate">点击右上角「设置」配置黑名单</p>
        <p v-else>点击「＋」发起聊天，或选择会话开始聊天</p>
      </div>
    </aside>

    <input id="im-file-input" type="file" hidden @change="ctx.imOnFileChange" />
  </div>
</template>

<script>
import ImChats from '../components/im/ImChats.vue'
import ImMessages from '../components/im/ImMessages.vue'
import ImContacts from '../components/im/ImContacts.vue'
import ImSettings from '../components/im/ImSettings.vue'
import ImGroupInfo from '../components/im/ImGroupInfo.vue'

export default {
  name: 'ImView',
  components: { ImChats, ImMessages, ImContacts, ImSettings, ImGroupInfo },
  inject: ['appCtx'],
  computed: {
    ctx() { return this.appCtx },
    // 移动端单栏状态类：
    //   - 在右栏功能页（联系人/设置/群信息，imTab ≠ chats）→ 独占一屏显示右栏
    //   - 否则有选中会话 → 显示消息栏；无会话 → 显示会话列表
    mobileCls() {
      if (this.ctx.imTab !== 'chats') return 'im-mv-panel'
      return this.ctx.imActiveChat ? 'im-mv-message' : 'im-mv-chats'
    },
  },
}
</script>

<style scoped>
.im-shell {
  display: flex;
  height: 100%;
  background: var(--zx-bg, #f7f8fa);
  overflow: hidden;
}
.im-pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-right: 1px solid var(--zx-border, #ebeef2);
  background: #fff;
}
.im-pane-left { width: 280px; flex: 0 0 280px; }
.im-pane-mid { flex: 1; min-width: 0; }
.im-pane-right { border-right: 0; border-left: 1px solid var(--zx-border, #ebeef2); background: #fafbfc; width: 320px; flex: 0 0 320px; }
.im-pane-header {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; border-bottom: 1px solid var(--zx-border, #ebeef2);
  font-weight: 600;
}
.im-pane-title { font-size: 16px; }
.im-pane-spacer { flex: 1; }
.im-icon-btn {
  border: 0; background: transparent; cursor: pointer;
  font-size: 20px; width: 28px; height: 28px; border-radius: 6px;
  color: var(--zx-text-2, #606266);
}
.im-icon-btn:hover { background: #f0f2f5; }
.im-badge {
  background: #f56c6c; color: #fff; border-radius: 9px;
  font-size: 11px; padding: 0 6px; min-width: 18px; text-align: center;
}
.im-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: var(--zx-text-3, #909399); font-size: 14px;
}
.im-empty-thin { padding: 24px; }

/* 移动端(≤768px)：默认三栏全隐，按 shell 状态类只显示一栏（单栏布局） */
@media (max-width: 768px) {
  .im-pane-left, .im-pane-mid, .im-pane-right { display: none; width: 100%; flex-basis: 100%; }
  .im-shell.im-mv-chats .im-pane-left { display: flex; }
  .im-shell.im-mv-message .im-pane-mid { display: flex; }
  .im-shell.im-mv-panel .im-pane-right { display: flex; }
}
</style>
