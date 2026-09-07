<template>
  <!-- IM 联系人页：好友列表 + 搜索 + 待处理申请 + 建群入口 -->
  <div class="im-contacts">
    <header class="im-pane-header">
      <span class="im-pane-title">联系人</span>
      <span class="im-pane-spacer"></span>
      <button class="im-icon-btn" @click="ctx.imGoTab('chats')" title="返回">×</button>
    </header>

    <!-- 搜索 -->
    <div class="im-search">
      <input
        v-model="ctx.imSearchKeyword"
        placeholder="搜索用户 ID / 昵称"
        @keyup.enter="ctx.imSearchUser"
      />
      <button @click="ctx.imSearchUser">搜索</button>
    </div>

    <!-- 待我处理 -->
    <div v-if="ctx.imPendingRequests.length" class="im-section">
      <h4>待处理申请 ({{ ctx.imPendingRequests.length }})</h4>
      <ul>
        <li v-for="r in ctx.imPendingRequests" :key="r.friendship_id">
          <span class="im-avatar-sm">{{ (r.requester_nickname || '?').slice(0,1) }}</span>
          <span class="im-name">{{ r.requester_nickname }}</span>
          <span class="im-spacer"></span>
          <button class="primary" @click="ctx.imAcceptFriend(r.friendship_id)">接受</button>
        </li>
      </ul>
    </div>

    <!-- 搜索结果 -->
    <div v-if="ctx.imSearchResults.length" class="im-section">
      <h4>搜索结果</h4>
      <ul>
        <li v-for="u in ctx.imSearchResults" :key="u.user_id">
          <span class="im-avatar-sm">{{ (u.nickname || '?').slice(0,1) }}</span>
          <span class="im-name">{{ u.nickname }}<small v-if="u.grade">{{ u.grade }}年级</small></span>
          <span class="im-spacer"></span>
          <button @click="ctx.imStartPrivate(u.user_id)">私聊</button>
          <button @click="ctx.imAddFriend(u.user_id)">加好友</button>
        </li>
      </ul>
    </div>

    <!-- 好友列表 -->
    <div class="im-section">
      <h4>好友 ({{ ctx.imFriends.length }})</h4>
      <ul>
        <li v-for="f in ctx.imFriends" :key="f.user_id">
          <span class="im-avatar-sm">{{ (f.nickname || '?').slice(0,1) }}</span>
          <span class="im-name">
            {{ f.nickname }}
            <small v-if="f.is_online" class="im-online">在线</small>
          </span>
          <span class="im-spacer"></span>
          <button @click="ctx.imStartPrivate(f.user_id)">私聊</button>
        </li>
      </ul>
    </div>

    <!-- 建群 -->
    <div class="im-section">
      <h4>建群</h4>
      <div class="im-create-group">
        <input v-model="newGroupName" placeholder="群名" />
        <button class="primary" @click="createGroup">创建</button>
      </div>
      <p class="im-hint">先选好友作为初始成员（在「好友」上方勾选）</p>
      <ul>
        <li v-for="f in ctx.imFriends" :key="'pg-'+f.user_id">
          <label>
            <input type="checkbox" :value="f.user_id" v-model="newGroupMembers" />
            <span class="im-name">{{ f.nickname }}</span>
          </label>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ImContacts',
  inject: ['appCtx'],
  data() { return { newGroupName: '', newGroupMembers: [] } },
  computed: { ctx() { return this.appCtx } },
  mounted() { if (!this.ctx.imFriends.length) this.ctx.imLoadFriends() },
  methods: {
    createGroup() {
      if (!this.newGroupName || !this.newGroupMembers.length) return
      this.ctx.imCreateGroup(this.newGroupName, this.newGroupMembers)
      this.newGroupName = ''
      this.newGroupMembers = []
    },
  },
}
</script>

<style scoped>
.im-contacts { flex: 1; overflow-y: auto; padding-bottom: 24px; }
.im-pane-header {
  display: flex; align-items: center; padding: 12px 14px;
  border-bottom: 1px solid #ebeef2; background: #fff;
}
.im-pane-title { font-size: 15px; font-weight: 600; }
.im-pane-spacer { flex: 1; }
.im-icon-btn { border: 0; background: transparent; font-size: 18px; width: 28px; height: 28px; cursor: pointer; }

.im-search { display: flex; gap: 6px; padding: 10px 14px; background: #fff; border-bottom: 1px solid #f0f2f5; }
.im-search input { flex: 1; border: 1px solid #dcdfe6; border-radius: 4px; padding: 4px 8px; font-size: 13px; }
.im-search button { border: 0; background: #409eff; color: #fff; padding: 0 12px; border-radius: 4px; cursor: pointer; }

.im-section { padding: 10px 14px; }
.im-section h4 { margin: 0 0 6px; font-size: 12px; color: #909399; font-weight: 500; }
.im-section ul { list-style: none; margin: 0; padding: 0; }
.im-section li {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 6px; border-radius: 6px;
}
.im-section li:hover { background: #f5f7fa; }
.im-avatar-sm {
  width: 32px; height: 32px; border-radius: 50%;
  background: linear-gradient(135deg, #6da9ff, #6ee2c5);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 13px; flex: 0 0 32px;
}
.im-name { font-size: 14px; }
.im-name small { color: #909399; font-size: 11px; margin-left: 4px; }
.im-spacer { flex: 1; }
.im-online { color: #67c23a; }
.im-section button {
  border: 1px solid #dcdfe6; background: #fff; padding: 2px 10px;
  border-radius: 4px; font-size: 12px; cursor: pointer;
}
.im-section button.primary { background: #409eff; color: #fff; border-color: #409eff; }
.im-create-group { display: flex; gap: 6px; }
.im-create-group input { flex: 1; border: 1px solid #dcdfe6; border-radius: 4px; padding: 4px 8px; }
.im-create-group button { border: 0; background: #409eff; color: #fff; padding: 0 12px; border-radius: 4px; cursor: pointer; }
.im-hint { color: #909399; font-size: 11px; margin: 4px 0; }
</style>
