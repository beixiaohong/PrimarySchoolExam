<template>
  <!-- IM 群信息页：群成员 + 群公告编辑 -->
  <div class="im-group-info">
    <header class="im-pane-header">
      <span class="im-pane-title">群信息</span>
      <span class="im-pane-spacer"></span>
      <button class="im-icon-btn" @click="ctx.imGoTab('chats')" title="返回">×</button>
    </header>

    <div class="im-section">
      <h4>群公告</h4>
      <textarea
        v-model="ctx.imAnnouncement"
        rows="3"
        placeholder="群主可编辑群公告"
        :readonly="!ctx.imEditingAnnouncement"
      />
      <div class="im-actions">
        <button v-if="!ctx.imEditingAnnouncement" @click="ctx.imEditingAnnouncement = true">编辑</button>
        <template v-else>
          <button @click="ctx.imEditingAnnouncement = false">取消</button>
          <button class="primary" @click="ctx.imSaveAnnouncement">保存</button>
        </template>
      </div>
    </div>

    <div class="im-section">
      <h4>群成员 ({{ (ctx.imGroupMembers[ctx.imActiveChatId] || []).length }})</h4>
      <ul>
        <li v-for="m in (ctx.imGroupMembers[ctx.imActiveChatId] || [])" :key="m.user_id">
          <span class="im-avatar-sm">{{ (m.nickname || '?').slice(0,1) }}</span>
          <span class="im-name">{{ m.nickname }}<small v-if="m.role !== 'member'">{{ m.role === 'owner' ? '群主' : '管理员' }}</small></span>
          <span class="im-spacer"></span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ImGroupInfo',
  inject: ['appCtx'],
  computed: { ctx() { return this.appCtx } },
}
</script>

<style scoped>
.im-group-info { flex: 1; overflow-y: auto; }
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
.im-name small { color: #909399; font-size: 11px; margin-left: 4px; }
.im-spacer { flex: 1; }
.im-section textarea { width: 100%; border: 1px solid #dcdfe6; border-radius: 4px; padding: 6px 8px; font-size: 13px; resize: vertical; }
.im-actions { margin-top: 6px; display: flex; gap: 6px; }
.im-actions button { border: 1px solid #dcdfe6; background: #fff; padding: 4px 12px; border-radius: 4px; cursor: pointer; }
.im-actions button.primary { background: #409eff; color: #fff; border-color: #409eff; }
</style>
