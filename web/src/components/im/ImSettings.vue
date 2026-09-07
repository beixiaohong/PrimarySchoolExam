<template>
  <!-- IM 个人设置：黑名单 + 通知偏好 + 个人资料 -->
  <div class="im-settings">
    <header class="im-pane-header">
      <span class="im-pane-title">设置</span>
      <span class="im-pane-spacer"></span>
      <button class="im-icon-btn" @click="ctx.imGoTab('chats')" title="返回">×</button>
    </header>

    <div v-if="ctx.imProfile" class="im-section">
      <h4>个人资料</h4>
      <ul>
        <li><span>昵称</span><span>{{ ctx.imProfile.nickname }}</span></li>
        <li><span>年级</span><span>{{ ctx.imProfile.grade }}</span></li>
        <li><span>钻石余额</span><span>{{ (ctx.imProfile.diamond_balance || 0) / 1000 }} 钻</span></li>
      </ul>
    </div>

    <div class="im-section">
      <h4>消息通知</h4>
      <ul>
        <li>
          <label><input type="checkbox" v-model="ctx.imSettings.mute_notification" /> 静音通知</label>
        </li>
        <li>
          <label><input type="checkbox" v-model="ctx.imSettings.enter_to_send" /> 回车发送（默认开）</label>
        </li>
      </ul>
    </div>

    <div class="im-section">
      <h4>黑名单 ({{ ctx.imBlockedUsers.length }})</h4>
      <div v-if="!ctx.imBlockedUsers.length" class="im-hint">无</div>
      <ul v-else>
        <li v-for="u in ctx.imBlockedUsers" :key="u.user_id">
          <span class="im-avatar-sm">{{ (u.nickname || '?').slice(0,1) }}</span>
          <span class="im-name">{{ u.nickname }}</span>
          <span class="im-spacer"></span>
          <button @click="ctx.imUnblock(u.user_id)">解除</button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ImSettings',
  inject: ['appCtx'],
  computed: { ctx() { return this.appCtx } },
  mounted() { this.ctx.imLoadBlocked() },
}
</script>

<style scoped>
.im-settings { flex: 1; overflow-y: auto; }
.im-pane-header { display: flex; align-items: center; padding: 12px 14px; border-bottom: 1px solid #ebeef2; background: #fff; }
.im-pane-title { font-size: 15px; font-weight: 600; }
.im-pane-spacer { flex: 1; }
.im-icon-btn { border: 0; background: transparent; font-size: 18px; width: 28px; height: 28px; cursor: pointer; }
.im-section { padding: 10px 14px; }
.im-section h4 { margin: 0 0 6px; font-size: 12px; color: #909399; font-weight: 500; }
.im-section ul { list-style: none; margin: 0; padding: 0; }
.im-section li { display: flex; align-items: center; gap: 8px; padding: 6px 0; }
.im-avatar-sm {
  width: 28px; height: 28px; border-radius: 50%;
  background: linear-gradient(135deg, #6da9ff, #6ee2c5);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 12px; flex: 0 0 28px;
}
.im-name { font-size: 13px; }
.im-spacer { flex: 1; }
.im-hint { color: #909399; font-size: 12px; }
.im-section button { border: 1px solid #dcdfe6; background: #fff; padding: 2px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; }
</style>
