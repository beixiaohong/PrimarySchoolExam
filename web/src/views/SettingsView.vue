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

        <!-- ═══ 分组：通知设置（OneSignal Web Push，逻辑见 logic/push.js）═══ -->
        <div class="set-group-title">通知设置</div>
        <div class="card set-card" v-if="appCtx.pushEnabled">
          <div class="card-head">
            <b>🔔 消息推送</b>
            <!-- 状态徽标：颜色即状态，不必逐字读灰字 -->
            <span class="push-pill" :class="'is-' + appCtx.pushDeviceState.tone">{{appCtx.pushDeviceState.title}}</span>
          </div>
          <!-- SDK 脚本被浏览器拦掉时不会弹授权提示：必须给出可执行的下一步，否则用户只会反复点开关 -->
          <div class="push-hint push-alert" v-if="appCtx.pushSdkError">
            浏览器把推送脚本当作广告追踪器拦掉了（OneSignal 在跟踪防护列表里属「广告」类），
            所以一直没有弹出授权提示。请把本网站加入「跟踪防护 / 广告拦截」的例外，然后刷新页面。<br>
            <b>Edge</b>：设置 → 隐私、搜索和服务 → 跟踪防护 → 例外 → 添加本站域名
          </div>
          <!-- 本设备开关。状态用三重表达：文字 + 色点 + 开关位置。
               原先是一个按钮、按钮上写着状态词「已开启/已关闭」，点下去却是反向操作，
               用户看不出当前是开还是关（反馈原话：「我都不知道当前是开的还是关的」）。 -->
          <div class="info-row push-row">
            <span class="push-row-main">
              <span class="push-dot" :class="'is-' + appCtx.pushDeviceState.tone"></span>
              <span class="push-row-txt">
                <b>本设备接收推送：{{appCtx.pushDeviceState.title}}</b><br>
                <em class="push-hint">{{appCtx.pushDeviceState.hint}}</em>
              </span>
            </span>
            <!-- 左侧已写明状态（色点 + 文字），这里不再重复 label，只留开关本身 -->
            <state-switch :on="!!appCtx.pushOptedIn" :busy="appCtx.pushLoading"
                          :disabled="appCtx.pushLoading || !appCtx.pushReady"
                          :title="appCtx.pushOptedIn ? '点击关闭本设备推送' : '点击开启本设备推送'"
                          @toggle="appCtx.pushToggleDevice()" />
          </div>
          <!-- 逐场景开关：不接收的场景后端根本不会下发（services/push.py 的 _PREF_FIELD） -->
          <div class="info-row" v-for="f in appCtx.pushEventFields" :key="f.field">
            <span>{{f.label}}<br><em class="push-hint">{{f.desc}}</em></span>
            <state-switch :on="!!appCtx.pushPrefs[f.field]"
                          :label="appCtx.pushPrefs[f.field] ? '接收' : '不接收'"
                          :tone="appCtx.pushPrefs[f.field] ? 'ok' : 'off'"
                          :title="appCtx.pushPrefs[f.field] ? '点击改为不接收' : '点击改为接收'"
                          @toggle="appCtx.pushSavePref(f.field, !appCtx.pushPrefs[f.field])" />
          </div>
          <!-- 免打扰：用户自设静音时段（与平台宵禁无关，后者只针对未成年人护眼） -->
          <div class="info-row">
            <span>免打扰时段<br><em class="push-hint">该时段内不推送，留空表示不启用</em></span>
            <span style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end">
              <input type="time" v-model="appCtx.pushQuietForm.start" class="push-time">
              <em class="push-hint">至</em>
              <input type="time" v-model="appCtx.pushQuietForm.end" class="push-time">
              <button class="btn btn-sm btn-ghost" @click="appCtx.pushSaveQuiet()">保存</button>
            </span>
          </div>
          <div class="detail-actions" style="margin-top:12px">
            <button class="btn btn-ghost btn-sm" :disabled="appCtx.pushTesting" @click="appCtx.pushSendTest()">
              {{appCtx.pushTesting ? '发送中…' : '发送测试推送'}}
            </button>
            <span class="more" style="margin-left:8px">收不到时先点这里自检</span>
          </div>
        </div>
        <!-- 通道未配置时也给一行说明：否则用户翻遍设置页也找不到推送开关，只会以为功能坏了 -->
        <div class="card set-card" v-else>
          <div class="card-head"><b>🔔 消息推送</b><span class="push-pill is-muted">{{appCtx.pushDeviceState.title}}</span></div>
          <div class="push-hint">推送通道由管理员在后台「三方配置」中开通；开通后这里会出现开关。</div>
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
          <!-- 状态 = 文字 + 颜色，动作 = 开关位置（统一控件 StateSwitch，勿在此另写一套） -->
          <div class="info-row"><span>极速模式（答题动画加速）</span>
            <state-switch :on="!!appCtx.turbo" :label="appCtx.turbo ? '已开启' : '已关闭'"
                          :tone="appCtx.turbo ? 'ok' : 'off'"
                          :title="appCtx.turbo ? '点击关闭极速模式' : '点击开启极速模式'"
                          @toggle="appCtx.toggleTurbo()" /></div>
          <!-- 高项备考隐藏入口：普通用户不可见入口，连点 5 次跳转（逻辑见 logic/gaoxiang.js gxSecretTap） -->
          <div class="info-row" style="cursor:pointer" role="button" @click="appCtx.gxSecretTap()"><span>关于</span><b>智学学堂 v1.0</b></div>
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

<style scoped>
/* 推送设置专用样式：卡片/行沿用全局的 set-card / info-row / btn，开关用 components/StateSwitch.vue */
.push-hint{font-style:normal;font-size:12px;color:var(--muted,#909399);line-height:1.5}
/* 被浏览器拦截时的醒目提示（普通 .push-hint 是灰色小字，不够引起注意） */
.push-alert{margin:8px 0 4px;padding:8px 10px;border-radius:8px;font-size:12px;line-height:1.7;
  background:#FFF7E6;border:1px solid #F5D08A;color:#8A5A00}
.push-time{padding:6px 8px;border:1px solid #E5E1F5;border-radius:8px;font-size:13px;
  background:var(--card,#fff);color:inherit}

/* ── 推送状态可视化：颜色即状态，避免用户只能靠读灰字判断开关 ── */

/* 卡片标题右侧的状态徽标 */
.push-pill{font-size:12px;font-weight:600;padding:2px 10px;border-radius:999px;
  background:var(--bg);color:var(--text-3);border:1px solid var(--border)}
.push-pill.is-ok{background:var(--success-light);color:var(--success);border-color:transparent}
.push-pill.is-warn{background:var(--warning-light);color:var(--warning);border-color:transparent}
.push-pill.is-danger{background:var(--danger-light);color:var(--danger);border-color:transparent}
.push-pill.is-muted{background:var(--bg);color:var(--text-3)}

/* 本设备状态行：色点 + 文字 + 开关 */
.push-row{align-items:center;gap:10px}
.push-row-main{display:flex;align-items:flex-start;gap:8px;min-width:0}
.push-row-txt{display:block;line-height:1.5}
.push-dot{flex:0 0 auto;width:8px;height:8px;border-radius:50%;margin-top:6px;background:var(--text-3)}
.push-dot.is-ok{background:var(--success)}
.push-dot.is-warn{background:var(--warning)}
.push-dot.is-danger{background:var(--danger)}
.push-dot.is-muted{background:var(--text-3)}

/* 逐场景开关行的「状态文字 + 开关」、以及本设备行的开关，已统一由
   components/StateSwitch.vue 提供（状态 = 文字 + 颜色，动作 = 开关位置）。
   此处不再保留第二套开关样式，否则同一判定会漂移成两种实现。 */
</style>
