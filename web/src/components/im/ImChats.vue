<template>
  <!-- IM 会话列表：好友私聊 + 群聊，按最近消息倒序 -->
  <div class="im-chats">
    <div v-if="ctx.imChatsLoading" class="im-loading">加载中...</div>
    <div v-else-if="!ctx.imChatsSorted.length" class="im-empty-tip">还没有会话，去联系人发起一个吧</div>
    <ul v-else class="im-chat-list">
      <li
        v-for="c in ctx.imChatsSorted"
        :key="c.id"
        class="im-chat-item"
        :class="{ active: c.id === ctx.imActiveChatId }"
        @click="ctx.imOpenChat(c)"
      >
        <span class="im-avatar" :class="{ 'is-group': c.chat_type === 'group' }">
          {{ ctx.imAvatarText(c) }}
        </span>
        <div class="im-chat-meta">
          <div class="im-chat-row">
            <span class="im-chat-name">{{ c.name || ctx.imAvatarText(c) }}</span>
            <span class="im-chat-time">{{ ctx.imTimeFmt(c.last_time) }}</span>
          </div>
          <div class="im-chat-row im-chat-row-sub">
            <span class="im-chat-last">{{ c.last_message || '...' }}</span>
            <span v-if="ctx.imUnreadByChat[c.id]" class="im-chat-unread">{{ ctx.imUnreadByChat[c.id] }}</span>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<script>
export default {
  name: 'ImChats',
  inject: ['appCtx'],
  computed: { ctx() { return this.appCtx } },
}
</script>

<style scoped>
.im-chats { flex: 1; overflow-y: auto; }
.im-loading, .im-empty-tip { padding: 24px; text-align: center; color: #909399; font-size: 13px; }
.im-chat-list { list-style: none; margin: 0; padding: 0; }
.im-chat-item {
  display: flex; gap: 10px; padding: 10px 14px; cursor: pointer;
  border-bottom: 1px solid #f0f2f5;
  transition: background .15s;
}
.im-chat-item:hover { background: #f5f7fa; }
.im-chat-item.active { background: #e8f3ff; }
.im-avatar {
  flex: 0 0 40px; width: 40px; height: 40px; border-radius: 50%;
  background: linear-gradient(135deg, #6da9ff, #6ee2c5);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 16px;
}
.im-avatar.is-group { background: linear-gradient(135deg, #ffb86c, #ff7e7e); }
.im-chat-meta { flex: 1; min-width: 0; }
.im-chat-row { display: flex; justify-content: space-between; align-items: center; }
.im-chat-row-sub { margin-top: 2px; }
.im-chat-name { font-size: 14px; font-weight: 500; color: #303133; }
.im-chat-time { font-size: 11px; color: #909399; }
.im-chat-last { font-size: 12px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 180px; }
.im-chat-unread {
  background: #f56c6c; color: #fff; border-radius: 9px;
  font-size: 11px; padding: 0 5px; min-width: 18px; text-align: center;
}
</style>
