<template>
<div class="fade-enter">
        <!-- 家长管理跳转卡：家长管理已独立成 tab='parent'，此卡是移动端唯一入口（TABBAR 已满 6 项不加）。
             副文案显示待办计数（notices.todo_total，对孩子也可见，提醒去找家长）。 -->
        <div class="card set-card parent-jump" role="button" @click="appCtx.goTab('parent')">
          <div class="pj-row">
            <span class="pj-icon">👨‍👩‍👧</span>
            <div class="pj-body">
              <b>家长管理</b>
              <span class="more" v-if="appCtx.parentTodoTotal>0">{{appCtx.parentTodoTotal}} 件待处理 · 点击查看 →</span>
              <span class="more" v-else>任务确认 · 兑换券 · 心愿 · 学习配置（需家长密码）</span>
            </div>
            <span class="pj-arrow">→</span>
          </div>
        </div>

        <!-- ═══ 分组：学习设置 ═══ -->
        <div class="set-group-title">学习设置</div>
        <div class="card set-card">
          <div class="card-head"><b>🎓 年级与默认学科</b></div>
          <div class="form-grid" style="margin-top:16px">
            <div class="form-item"><label>年级</label><select v-model="appCtx.grade" @change="appCtx.onGradeChange"><option v-for="g in [1,2,3,4,5,6,7,8,9]" :key="'set-'+g" :value="g">{{g}}年级</option></select></div>
            <div class="form-item"><label>默认学科</label><select v-model="appCtx.subject" @change="appCtx.onSubjectChange"><option v-for="s in appCtx.subjectOptions" :key="'def-'+s">{{s}}</option></select></div>
          </div>
          <p class="card-desc">当前年级：{{appCtx.grade}}年级 · 每年9月自动升一年级 · 学习数据按用户名保存在本地服务器</p>
        </div>
        <div class="card set-card">
          <div class="card-head"><b>📖 教材版本</b><span class="more">背单词/听写按所选版本取词，未选择时默认最靠前的版本</span></div>
          <div class="form-grid" style="margin-top:16px">
            <div v-for="p in appCtx.textbookPrefs" :key="p.subject" class="form-item">
              <label>{{p.subject}}</label>
              <select :value="p.textbook_id || 0" @change="appCtx.onTextbookChange(p.subject, $event)">
                <option value="0">默认（最靠前）</option>
                <option v-for="v in appCtx.textbookVersions[p.subject] || []" :key="v.id" :value="v.id">{{v.name}}</option>
              </select>
            </div>
          </div>
        </div>

        <!-- ═══ 分组：我的账号 ═══ -->
        <div class="set-group-title">我的账号</div>
        <div class="card set-card">
          <div class="card-head"><b>🔐 用户名与账号安全</b><span class="more">绑定邮箱后可跨设备登录与找回密码</span></div>
          <div class="form-grid" style="margin-top:16px">
            <div class="form-item"><label>用户名</label><input :value="appCtx.user" disabled style="background:var(--bg)"></div>
          </div>
          <div class="info-row"><span>邮箱</span><b>{{appCtx.authInfo.email || '未绑定'}}</b></div>
          <div class="info-row"><span>登录密码</span><b>{{appCtx.authInfo.has_password ? '已设置' : '未设置'}}</b></div>
          <div v-if="!appCtx.authInfo.email" style="margin-top:12px">
            <div class="pc-title">📧 绑定邮箱</div>
            <div class="pc-row">
              <input v-model="appCtx.bindTarget" class="fill-input" placeholder="输入邮箱" style="max-width:220px">
              <button class="btn btn-ghost btn-sm" :disabled="appCtx.authCooldown>0 || !appCtx.bindTarget.trim()" @click="appCtx.sendAuthCode('bind', appCtx.bindTarget)">{{appCtx.authCooldown>0 ? appCtx.authCooldown+'s' : '获取验证码'}}</button>
            </div>
            <div class="pc-row" style="margin-top:8px">
              <input v-model="appCtx.bindCode" class="fill-input" maxlength="6" placeholder="验证码" style="max-width:140px">
              <button class="btn btn-primary btn-sm" :disabled="!appCtx.bindTarget.trim() || appCtx.bindCode.trim().length<6" @click="appCtx.bindAccount()">绑定</button>
            </div>
          </div>
        </div>

        <!-- ═══ 分组：数据与其他 ═══ -->
        <div class="set-group-title">数据与其他</div>
        <div class="card set-card">
          <div class="card-head"><b>📚 我的学习成果</b><span class="more">累计数据（自注册以来，与家长侧「本周学习数据」时间窗不同）</span></div>
          <div class="info-row"><span>连续学习</span><b>🔥 {{appCtx.streakDays}} 天</b></div>
          <div class="info-row"><span>累计单词</span><b>{{appCtx.vocabStats.learned_count||0}} / {{appCtx.vocabStats.total_words||0}}</b></div>
          <div class="info-row"><span>累计古诗文</span><b>{{appCtx.classicalStats.learned||0}} / {{appCtx.classicalStats.total||0}}</b></div>
          <div class="info-row"><span>错题总数</span><b>{{appCtx.wrongAnalysis.total||0}}（已掌握 {{appCtx.wrongAnalysis.mastered||0}}）</b></div>
        </div>
        <div class="card set-card">
          <div class="card-head"><b>🏙️ 我的城市</b><span class="more">用于首页天气展示</span></div>
          <div class="pc-row">
            <input v-model="appCtx.cityInput" placeholder="如：杭州" maxlength="50" style="flex:1;padding:9px 12px;border:1px solid #E5E1F5;border-radius:10px;font-size:14px">
            <button class="btn btn-primary" @click="appCtx.saveCity" style="padding:9px 20px">保存</button>
          </div>
        </div>
        <div class="card set-card">
          <div class="card-head"><b>⚙️ 其他</b></div>
          <div class="info-row"><span>极速模式（答题动画加速）</span><button class="btn btn-sm" :class="appCtx.turbo ? 'btn-primary' : 'btn-ghost'" @click="appCtx.toggleTurbo()">{{appCtx.turbo ? '已开启' : '已关闭'}}</button></div>
          <div class="detail-actions" style="margin-top:14px">
            <button class="btn btn-danger" @click="appCtx.logout()">退出登录</button>
          </div>
        </div>
</div>
</template>

<script>
// SettingsView（孩子侧设置页）。业务逻辑由 App.vue 壳通过 appOptions 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
// 家长管理已迁出到独立视图 ParentView（tab='parent'），此页仅保留一张跳转卡作为移动端入口。
export default {
  name: 'SettingsView',
  inject: ['appCtx'],
}
</script>
