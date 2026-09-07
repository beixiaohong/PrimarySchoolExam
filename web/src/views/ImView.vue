<template>
  <!-- IM 即时通讯视图（tab='im'）
       入口：与父 LedgerView 同构；业务全在 logic/im.js，组件通过 inject('appCtx') 访问响应式状态。
       布局：移动端单栏切换（chats <-> messages），桌面端三栏（chats | messages | contacts/settings） -->
  <div class="im-shell" :class="mobileView">
    <!-- 左侧：会话列表（桌面常驻，移动端独屏时显示） -->
    <section v-show="mobileView !== 'message'" class="im-pane im-pane-left">
      <header class="im-pane-header">
        <span class="im-pane-title">消息</span>
        <span v-if="ctx.imUnreadTotal" class="im-badge">{{ ctx.imUnreadTotal }}</span>
        <span class="im-pane-spacer"></span>
        <button class="im-icon-btn" @click="ctx.imGoTab('contacts')" title="联系人">＋</button>
      </header>
      <im-chats />
    </section>

    <!-- 中间：消息区 -->
    <section v-show="mobileView !== 'chat'" class="im-pane im-pane-mid">
      <im-messages v-if="ctx.imActiveChat" />
      <div v-else class="im-empty">
        <p>选择左侧任一会话开始聊天</p>
      </div>
    </section>

    <!-- 右侧：联系人 / 设置（桌面常驻，移动端独屏时显示） -->
    <aside v-show="mobileView !== 'chat'" class="im-pane im-pane-right">
      <im-contacts v-if="ctx.imTab === 'contacts'" />
      <im-settings v-else-if="ctx.imTab === 'settings'" />
      <im-group-info v-else-if="ctx.imTab === 'group' && ctx.imIsGroup" />
      <div v-else class="im-empty im-empty-thin">
        <p v-if="ctx.imIsGroup">点击右上角「群信息」查看</p>
        <p v-else-if="ctx.imIsPrivate">点击右上角「设置」配置黑名单</p>
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
    // 移动端单栏切换：有未读角标时默认回 chats，有 active chat 时进 message
    mobileView() {
      if (!this.ctx.imActiveChat) return 'chat'
      return this.ctx._imMobileView || 'message'
    },
  },
}
</script>

<style scoped>
.im-shell {
  display: flex;
  height: 100%;
  background: var(--zx-bg, #f7f8fa);
}
.im-pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-right: 1px solid var(--zx-border, #ebeef2);
  background: #fff;
}
.im-pane-right { border-right: 0; background: #fafbfc; }
.im-pane-left { width: 280px; flex: 0 0 280px; }
.im-pane-mid { flex: 1; min-width: 0; }
.im-pane-right { width: 320px; flex: 0 0 320px; }
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
@media (max-width: 768px) {
  .im-pane-left { width: 100%; flex-basis: 100%; }
  .im-pane-mid { display: none; }
  .im-pane-right { display: none; }
  .im-shell.mobile-message .im-pane-left { display: none; }
  .im-shell.mobile-message .im-pane-mid { display: flex; width: 100%; flex-basis: 100%; }
  .im-shell.mobile-chat .im-pane-mid { display: none; }
  .im-shell.mobile-chat .im-pane-left { display: flex; width: 100%; flex-basis: 100%; }
}
</style>
