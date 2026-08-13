<template>
<div class="app-root">

<!-- ═══════════════════ 登录屏（注册登录 · 昵称快捷入口） ═══════════════════ -->
<div class="login-page" v-if="!user">
  <div class="login-card">
    <div class="login-logo">📘</div>
    <h1>智学学堂</h1>
    <p class="sub">全学科学习中心 · 刷题 · 背诵 · 错题闭环</p>
    <div class="auth-tabs" v-if="authMode!=='reset'">
      <button :class="{active: authMode==='login'}" @click="authMode='login'">登录</button>
      <button :class="{active: authMode==='register'}" @click="authMode='register'">注册</button>
    </div>

    <!-- 登录 -->
    <template v-if="authMode==='login'">
      <div class="field">
        <label>账号</label>
        <input v-model="username" placeholder="邮箱 / 手机号 / 昵称" @keyup.enter="login">
      </div>
      <div class="field" v-if="isAccountCredential">
        <label>密码</label>
        <input v-model="loginPwd" type="password" placeholder="请输入密码" @keyup.enter="login">
      </div>
      <button class="btn btn-primary btn-lg login-btn" :disabled="!username.trim()" @click="login">进入学习 →</button>
      <p class="login-tip" v-if="!isAccountCredential && username.trim()">老账号：输入名字即可直接进入</p>
      <p class="login-tip link" @click="authMode='reset'">忘记密码？</p>
    </template>

    <!-- 注册 -->
    <template v-if="authMode==='register'">
      <div class="field">
        <label>邮箱或手机号</label>
        <input v-model="regTarget" placeholder="用于接收验证码">
      </div>
      <div class="field">
        <label>验证码</label>
        <div class="code-row">
          <input v-model="regCode" placeholder="6 位验证码" maxlength="6">
          <button class="btn btn-ghost btn-sm" :disabled="authCooldown>0 || !regTarget.trim()" @click="sendAuthCode('register', regTarget)">{{authCooldown>0 ? authCooldown+'s' : '获取验证码'}}</button>
        </div>
      </div>
      <div class="field">
        <label>设置密码</label>
        <input v-model="regPwd" type="password" placeholder="以后登录用">
      </div>
      <div class="field">
        <label>昵称（可选）</label>
        <input v-model="regNickname" placeholder="不填则用账号作为昵称">
      </div>
      <button class="btn btn-primary btn-lg login-btn" :disabled="!regTarget.trim() || regCode.trim().length<6 || !regPwd" @click="register">注册并开始学习 →</button>
    </template>

    <!-- 重置密码 -->
    <template v-if="authMode==='reset'">
      <div class="field">
        <label>已注册的邮箱/手机号</label>
        <input v-model="rstTarget" placeholder="注册时用的邮箱或手机号">
      </div>
      <div class="field">
        <label>验证码</label>
        <div class="code-row">
          <input v-model="rstCode" placeholder="6 位验证码" maxlength="6">
          <button class="btn btn-ghost btn-sm" :disabled="authCooldown>0 || !rstTarget.trim()" @click="sendAuthCode('reset', rstTarget)">{{authCooldown>0 ? authCooldown+'s' : '获取验证码'}}</button>
        </div>
      </div>
      <div class="field">
        <label>新密码</label>
        <input v-model="rstPwd" type="password" placeholder="设置新密码">
      </div>
      <button class="btn btn-primary btn-lg login-btn" :disabled="!rstTarget.trim() || rstCode.trim().length<6 || !rstPwd" @click="resetPassword">重置密码 →</button>
      <p class="login-tip link" @click="authMode='login'">← 返回登录</p>
    </template>
  </div>
</div>

<!-- ═══════════════════ 首次进入 · 选择年级弹窗 ═══════════════════ -->
<div class="grade-modal-overlay" v-if="showGradeModal">
  <div class="grade-modal">
    <h2>👋 欢迎来到智学学堂</h2>
    <p>请选择你当前的年级，后续每年9月会自动升级哦</p>
    <div class="grade-grid">
      <button v-for="g in [1,2,3,4,5,6,7,8,9]" :key="g"
              class="grade-btn" :class="{active: grade===g}"
              @click="grade=g">{{g}}年级</button>
    </div>
    <button class="btn btn-primary btn-lg" style="margin-top:20px;width:100%" @click="selectInitialGrade">开始学习 →</button>
  </div>
</div>

<!-- 升年级引导（登录后 promoted） -->
<div class="grade-modal-overlay" v-if="promotedInfo">
  <div class="grade-modal">
    <h2>🎉 恭喜，你升级啦！</h2>
    <p>9月1日自动升级：你从 {{promotedInfo.prev_grade}}年级升入了 <b>{{promotedInfo.new_grade}}年级</b>，新学期的学习内容已解锁</p>
    <button class="btn btn-primary btn-lg" style="margin-top:20px;width:100%" @click="closePromoted()">开始{{promotedInfo.new_grade}}年级的学习 →</button>
  </div>
</div>

<!-- ═══════════════════ App Shell ═══════════════════ -->
<div class="app" v-if="user && !showGradeModal">
  <aside class="sidebar">
    <div class="logo">
      <div class="logo-badge">📘</div>
      <div><b>智学学堂</b><span>全学科学习中心</span></div>
    </div>
    <nav class="nav">
      <div class="nav-group" v-for="g in NAV_GROUPS" :key="g.title">
        <div class="nav-group-title">{{g.title}}</div>
        <button v-for="it in g.items" :key="it.tab" class="nav-item" :class="{active: tab===it.tab}" @click="goTab(it.tab)">
          <span class="ico">{{it.ico}}</span>{{it.label}}
          <span v-if="it.badge==='wrong' && wrongBadge>0" class="badge">{{wrongBadge}}</span>
          <span v-if="it.badge==='pet' && petProfile && petLeveledUp" class="badge badge-gold">升级</span>
          <span v-if="it.badge==='badge' && badgeNew.length" class="badge badge-gold">新</span>
        </button>
      </div>
    </nav>
    <div class="user">
      <div class="avatar">{{user.charAt(0)}}</div>
      <div><b>{{user}}</b><span>🔥 连续学习 {{streakDays}} 天</span></div>
    </div>
  </aside>

  <div class="main">
    <header class="topbar">
      <div class="subject-pills" v-if="tab==='practice' || tab==='wrong'">
        <button v-for="s in subjectOptions" :key="s" :class="{active: subject===s}" @click="switchSubject(s)">{{s}}</button>
      </div>
      <button class="icon-btn" @click="showToast('🔔 暂无新通知，加油学习！')">🔔</button>
      <div class="me">
        <div class="avatar" style="width:32px;height:32px;font-size:12px">{{user.charAt(0)}}</div>
        <b>{{user}}</b><span class="streak">🔥{{streakDays}}</span><span class="diamonds" title="钻石余额">💎{{diamonds}}</span>
      </div>
    </header>

    <main class="content">
      <!-- ═══════════ 今日学习首页 ═══════════ -->
      <div v-if="tab==='home'" class="fade-enter">
        <div class="hero">
          <div style="flex:1">
            <h1>{{greeting}}，{{user}} 👋 <span class="title-badge" v-if="titleInfo" :title="titleInfo.next ? '再做 '+titleInfo.next.need+' 项学习升级' : '已是最高称号'">{{titleInfo.icon}} {{titleInfo.name}}</span></h1>
            <p v-if="taskRemain>0">今天还差 <b style="color:#fff">{{taskRemain}}</b> 项任务完成全勤<template v-if="dailyTaskStats.streak_days"> · 🔥 已连续 {{dailyTaskStats.streak_days}} 天</template>，点击任务卡即可开始</p>
            <p v-else>🎉 三科任务全部完成，今天全勤！<template v-if="dailyTaskStats.streak_days">已连续 {{dailyTaskStats.streak_days}} 天 🔥</template></p>
          </div>
          <div class="hero-right">
            <div class="hero-ring">
              <svg width="74" height="74" viewBox="0 0 74 74">
                <circle cx="37" cy="37" r="32" fill="none" stroke="rgba(255,255,255,.25)" stroke-width="7"/>
                <circle cx="37" cy="37" r="32" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-dasharray="201" stroke-dashoffset="201" :style="{strokeDashoffset: 201-(201*taskPct/100)}"/>
              </svg>
              <div class="num">{{dailyTaskStats.done_count}}/{{dailyTaskStats.total || 3}}<small>今日任务</small></div>
            </div>
            <div class="hero-stats">
              <div><b>{{streakDays}}<small style="font-size:11px">天</small></b><span>连续学习</span></div>
              <div><b>{{avgScore}}%</b><span>平均正确率</span></div>
              <div><b>{{masteredTotal}}</b><span>已掌握错题</span></div>
            </div>
          </div>
        </div>

        <!-- 今日提醒条（P5：聚合待办提醒，点击直达） -->
        <div class="today-remind" v-if="taskRemain>0 || wrongBadge>0">
          <span class="tr-ico">⏰</span>
          <button v-if="taskRemain>0" class="tr-item" @click="scrollToTasks">📋 还差 <b>{{taskRemain}}</b> 项任务全勤</button>
          <button v-if="wrongBadge>0" class="tr-item tr-warn" @click="goTab('wrong')">📕 <b>{{wrongBadge}}</b> 道错题待消灭</button>
        </div>

        <!-- 绑定引导（P5：昵称登录且未绑定邮箱/手机时提醒） -->
        <div class="bind-guide" v-if="authInfo && !authInfo.email && !authInfo.phone">
          <span>🔒 绑定邮箱或手机号，可跨设备登录与找回密码</span>
          <button class="bg-btn" @click="goTab('settings')">去绑定 →</button>
        </div>

        <!-- 天气卡片（P3：实时天气 + 3 日预报，4h 缓存） -->
        <div class="card weather-card" v-if="weather">
          <div class="card-head"><b>🌤️ {{weather.city}}</b><span class="more">{{weather.cached ? '缓存数据' : '实时数据'}} · 更新于 {{(weather.update_time || '').slice(11, 16)}}</span></div>
          <div v-if="!weather.now" class="wx-empty">{{weather.error || '天气数据暂不可用'}}</div>
          <div v-else>
            <div class="wx-now">
              <div class="wx-temp">{{weather.now.temp}}°</div>
              <div class="wx-desc"><b>{{weather.now.text}}</b><span>体感 {{weather.now.feelsLike}}° · 湿度 {{weather.now.humidity}}% · {{weather.now.windDir}}{{weather.now.windScale}}级</span></div>
            </div>
            <div class="wx-forecast">
              <div class="wx-day" v-for="d in weather.forecast" :key="d.fxDate">
                <span class="wd-date">{{wxDayLabel(d.fxDate)}}</span>
                <span class="wd-text">{{d.textDay}}</span>
                <span class="wd-temp">{{d.tempMin}}° ~ {{d.tempMax}}°</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 我的称号（Sprint 4） -->
        <div class="card title-card" v-if="titleInfo">
          <div class="card-head"><b>{{titleInfo.icon}} 我的称号：{{titleInfo.name}}</b><span class="more" v-if="titleInfo.next">再完成 {{titleInfo.next.need}} 项学习 → 升级「{{titleInfo.next.icon}} {{titleInfo.next.name}}」</span><span class="more" v-else>👑 已是最高称号！</span></div>
          <div class="badge-row">
            <div class="badge-item" v-for="b in titleBadges" :key="b.code" :class="{unlocked: b.unlocked}" :title="b.name">
              <span class="bi">{{b.unlocked ? b.icon : '🔒'}}</span>
              <div><b>{{b.name}}</b><i>{{b.unlocked ? '已解锁' : b.progress + ' / ' + b.target}}</i></div>
            </div>
          </div>
        </div>

        <!-- 家长提醒条（未读留言 / 心愿待办） -->
        <div class="notice-bar" v-if="notices && (notices.unread_messages>0 || notices.pending_wishes>0 || notices.pending_redeem>0)">
          <span v-if="notices.unread_messages>0" class="nb-item nb-msg" @click="openMessages()">✉️ 家长留言 {{notices.unread_messages}} 条未读</span>
          <span v-if="notices.pending_wishes>0" class="nb-item">🌟 心愿在等家长确认</span>
          <span v-if="notices.pending_redeem>0" class="nb-item nb-hot">🎉 心愿达标啦，快找家长兑现！</span>
        </div>

        <!-- 强制任务：三科各1条，完成即全勤 -->
        <div class="section-title">✅ 每日强制任务 <span class="more">三科全完成 = 今日全勤 · 🔥连续 {{dailyTaskStats.streak_days}} 天</span></div>
        <div class="grid-3" v-if="dailyTasks">
          <div class="card dtask" :class="{done: t.status==='done'}" v-for="t in mandatoryTasks" :key="'m-'+t.subject+'-'+t.task_code">
            <div class="dtask-head">
              <span class="tag" :class="t.subject==='数学' ? 'tag-orange' : (t.subject==='语文' ? 'tag-green' : 'tag-blue')">{{t.subject}}</span>
              <span class="dtask-state" :class="{ok: t.status==='done'}">{{t.status==='done' ? '✅ 已完成' : t.progress + ' / ' + t.target}}</span>
            </div>
            <div class="dtask-ico">{{t.ico}}</div>
            <b class="dtask-title">{{t.title}}</b>
            <div class="dtask-desc">{{t.desc}}</div>
            <div class="dtask-actions">
              <button v-if="t.manual && t.status==='pending'" class="btn btn-primary btn-sm" @click="childSubmitTask(t.id)">我完成了 ✓</button>
              <span v-else-if="t.manual && t.status==='pending_confirm'" class="tag tag-orange">已提交，待家长确认</span>
              <span v-else-if="t.status==='done'" class="tag tag-green">全勤 +1</span>
              <button v-if="t.status!=='done' && !t.makeup_pending && makeupCards>0" class="btn btn-ghost btn-sm" style="margin-left:6px;font-size:11px" @click="makeupCompleteTask(t.id)">🎫补签</button>
              <span v-else-if="t.makeup_pending" class="tag tag-orange" style="margin-left:6px;font-size:11px">🎫 待家长确认</span>
            </div>
            <div class="dtask-bar"><div class="dtask-bar-in" :style="{width: (t.target ? Math.min(100, t.progress / t.target * 100) : 0) + '%'}"></div></div>
          </div>
        </div>
        <div v-else class="card"><div class="empty"><div class="em">🎯</div><h3>加载今日任务中…</h3></div></div>

        <!-- 可选任务：系统每日生成3条，全完成获得补签卡 -->
        <div class="section-title" style="margin-top:20px">🎯 每日可选任务 <span class="more">系统每日自动分配 · 全部完成获 🎫补签卡×1</span>
          <span v-if="makeupCards>0" style="margin-left:12px;font-size:12px;color:#8B7CF6;font-weight:600">🎫 补签卡 ×{{makeupCards}}</span>
        </div>
        <div class="grid-3" v-if="dailyTasks">
          <div class="card dtask" :class="{done: t.status==='done'}" v-for="(t,i) in optionalTasks" :key="'o-'+i+'-'+t.task_code">
            <div class="dtask-head">
              <span class="tag" :class="t.subject==='数学' ? 'tag-orange' : (t.subject==='语文' ? 'tag-green' : 'tag-blue')">{{t.subject}}</span>
              <span class="dtask-state" :class="{ok: t.status==='done'}">{{t.status==='done' ? '✅ 已完成' : t.progress + ' / ' + t.target}}</span>
            </div>
            <div class="dtask-ico">{{t.ico}}</div>
            <b class="dtask-title">{{t.title}}</b>
            <div class="dtask-desc">{{t.desc}}</div>
            <div class="dtask-actions">
              <button v-if="t.manual && t.status==='pending'" class="btn btn-primary btn-sm" @click="childSubmitTask(t.id)">我完成了 ✓</button>
              <span v-else-if="t.manual && t.status==='pending_confirm'" class="tag tag-orange">已提交，待家长确认</span>
              <span v-else-if="t.status==='done'" class="tag tag-green">已完成</span>
              <button v-if="t.status!=='done' && !t.makeup_pending && makeupCards>0" class="btn btn-ghost btn-sm" style="margin-left:6px;font-size:11px" @click="makeupCompleteTask(t.id)">🎫补签</button>
              <span v-else-if="t.makeup_pending" class="tag tag-orange" style="margin-left:6px;font-size:11px">🎫 待家长确认</span>
            </div>
            <div class="dtask-bar"><div class="dtask-bar-in" :style="{width: (t.target ? Math.min(100, t.progress / t.target * 100) : 0) + '%'}"></div></div>
          </div>
        </div>

        <!-- 今日任务包（点击卡片直接开始，无确认弹窗） -->
        <div class="section-title">🗂️ 今日任务包 <span class="more">点击卡片立即开始，按遗忘曲线自动安排</span></div>
        <div class="grid-3" v-if="dashboard">
          <template v-for="t in todayTasks" :key="t.key">
            <button class="card task-card" :class="{done: t.done}" @click="startTask(t)">
              <div class="task-ico" :class="t.icoCls">{{t.ico}}</div>
              <div class="task-info">
                <b>{{t.title}}</b>
                <div class="meta"><span>{{t.subject}}</span><span class="dot">·</span><span>{{t.detail}}</span></div>
                <div class="meta" v-if="t.tag"><span class="tag" :class="t.tagCls">{{t.tag}}</span></div>
              </div>
              <span class="btn" :class="t.done ? 'btn-ghost btn-sm' : 'btn-primary btn-sm'" @click.stop="startTask(t)">{{t.done ? '已完成 ✓' : '开始'}}</span>
            </button>
          </template>
        </div>
        <div v-else class="card"><div class="empty"><div class="em">⏳</div><h3>加载今日任务中…</h3></div></div>

        <!-- 复习队列 -->
        <div class="section-title">🧭 复习队列 <span class="more">艾宾浩斯遗忘曲线 · 自动安排</span></div>
        <div class="timeline">
          <div class="tl-node today"><b>今天</b><span>{{queueToday}} 项到期</span><span class="count">{{queueTodayNames}}</span></div>
          <div class="tl-node"><b>明天</b><span>{{queueTomorrow}} 项到期</span><span class="count">按曲线节奏自动安排</span></div>
          <div class="tl-node"><b>后天</b><span>{{queueDayAfter}} 项到期</span><span class="count">单词 · 古诗文</span></div>
          <div class="tl-node"><b>3 天后</b><span>{{queueLater}} 项到期</span><span class="count">坚持每天来复习</span></div>
        </div>
        <div class="card" style="margin-top:12px" v-if="reviewQueue">
          <div v-for="it in reviewQueue.items.slice(0,6)" :key="it.type+it.id" class="queue-item">
            <div class="qi-ico" :class="it.type==='vocab' ? 't-blue' : 't-green'">{{it.type==='vocab' ? '🔤' : '📜'}}</div>
            <div class="qi-body"><b>{{it.title}}</b><span>{{it.subtitle}} · {{it.type==='vocab' ? '单词' : '古诗文'}}复习</span></div>
            <span class="tag" :class="it.overdue_days>0 ? 'tag-red' : 'tag-orange'" style="flex-shrink:0">{{it.overdue_days>0 ? '已逾期'+it.overdue_days+'天' : '今天到期'}}</span>
          </div>
          <div v-if="!reviewQueue.items.length" class="empty" style="padding:24px"><div class="em">🌱</div><h3>今天没有到期复习</h3><p>记忆保鲜中，明天再来巩固</p></div>
        </div>

        <!-- 今日心情（Sprint 2） -->
        <div class="card mood-card" style="margin-top:14px" v-if="moodTrend">
          <div class="card-head"><b>🌈 今日心情</b><span class="more">打个卡，爸爸妈妈会更懂你</span></div>
          <div class="mood-7">
            <div class="mood-day" v-for="d in moodTrend.days" :key="d.date" :class="{today: d.date===moodTodayStr, neg: d.negative}">
              <span class="md-week">{{d.weekday}}</span>
              <span class="md-face">{{d.mood ? moodFace(d.mood) : '·'}}</span>
              <span class="md-note" v-if="d.note">{{d.note}}</span>
            </div>
          </div>
          <template v-if="!moodTrend.today_mood || moodPicking">
            <div class="mood-pick">
              <button v-for="m in moodOptions" :key="m.code" class="mood-btn" @click="doMoodCheckin(m.code)">
                <span class="mf">{{m.face}}</span><b>{{m.label}}</b>
              </button>
            </div>
            <div class="mood-note-row">
              <input v-model="moodNote" class="fill-input" maxlength="50" placeholder="一句话说说今天的感受（选填，先点上面的表情）" style="max-width:360px">
            </div>
          </template>
          <div v-else class="mood-done">
            <span class="md-face big">{{moodFace(moodTrend.today_mood)}}</span>
            <span>今天已打卡：{{moodLabel(moodTrend.today_mood)}}<template v-if="moodTrend.days[6].note"> · {{moodTrend.days[6].note}}</template></span>
            <button class="btn btn-ghost btn-sm" @click="resetMoodPick()">换个心情</button>
          </div>
        </div>

        <!-- 完成确认（孩子提交完成 → 家长确认/拒绝），显示在奖励小屋上方 -->
        <div class="card confirm-card" style="margin-top:14px">
          <div class="card-head">
            <b>📋 完成确认</b>
            <span class="more">孩子提交完成，家长在首页确认</span>
          </div>
          <div v-if="taskConfirms.length" class="confirm-list">
            <div class="confirm-item" v-for="c in taskConfirms" :key="c.id">
              <div class="ci-row">
                <b class="ci-title">{{c.title}}</b>
                <span class="ci-sum">{{c.summary}}</span>
              </div>
              <div class="ci-row ci-sub">
                <span class="ci-time">{{c.created_at}}</span>
                <span class="tag" :class="c.status==='pending' ? 'tag-orange' : (c.status==='approved' ? 'tag-green' : 'tag-red')">
                  {{c.status==='pending' ? '待确认' : (c.status==='approved' ? '已通过 ✓' : '已拒绝')}}
                </span>
              </div>
              <div v-if="c.status==='rejected' && c.reject_reason" class="ci-reason">家长意见：{{c.reject_reason}}</div>
              <div v-if="c.status==='pending' && parentPhase==='open'" class="ci-actions">
                <button class="btn btn-success btn-sm" @click="resolveTaskConfirm(c.id,'approve')">通过 ✓</button>
                <button class="btn btn-ghost btn-sm" @click="openReject(c.id)">拒绝</button>
              </div>
              <div v-if="taskReject.id===c.id" class="ci-reject-box">
                <input v-model="taskReject.reason" class="fill-input" maxlength="100" placeholder="请填写拒绝理由（必填）">
                <button class="btn btn-primary btn-sm" @click="resolveTaskConfirm(c.id,'reject')">提交拒绝</button>
                <button class="btn btn-ghost btn-sm" @click="cancelReject()">取消</button>
              </div>
            </div>
          </div>
          <p v-else class="pc-empty">家长反馈激励展示</p>
          <!-- 错题申诉结果：家长判对/判错，反馈到首页家长反馈区 -->
          <div v-if="decidedAppeals.length" class="confirm-appeals">
            <div class="ca-head">📨 错题申诉结果 <span class="more">家长对申诉的判对 / 判错</span></div>
            <div class="ca-item" v-for="a in decidedAppeals" :key="a.id">
              <div class="ci-row">
                <b class="appeal-q" @click="toggleAppeal(a.id)" title="点击查看完整题目">
                  [{{a.subject || '未分科'}}]
                  <template v-if="!appealExpanded[a.id]">{{ a.question.length > 50 ? a.question.slice(0,50)+'…' : a.question }}</template>
                  <template v-else>{{ a.question }}</template>
                  <span class="q-toggle">{{ appealExpanded[a.id] ? '收起 ▴' : '查看完整题目 ▾' }}</span>
                </b>
              </div>
              <div class="ci-row ci-sub">
                <span class="more">孩子答案 {{a.user_answer}} · 参考 {{a.correct_answer}}</span>
                <span class="tag" :class="a.status==='approved' ? 'tag-green' : 'tag-red'">
                  {{ a.status==='approved' ? '判对 ✓' : '判错（维持）' }}
                </span>
              </div>
              <div class="ci-row ci-sub"><span class="more">{{a.created_at}} 提交 · {{a.decided_at}} 裁决</span></div>
            </div>
          </div>
        </div>

        <!-- 奖励闭环（Sprint 3） -->
        <div class="card reward-card" style="margin-top:14px" v-if="rewards">
          <div class="card-head"><b>🎁 奖励小屋</b><span class="more" v-if="rewards.wish && rewards.wish.status==='pending'">心愿待家长确认中</span><span class="more" v-else-if="rewards.wish && rewards.wish.status==='pending_redeem'">心愿达标啦！快找家长兑现</span></div>
          <div v-if="rewards.wish" class="wish-box">
            <div class="wish-head">
              <b>🌟 {{rewards.wish.title}}</b>
              <span class="tag" :class="rewards.wish.status==='pending' ? 'tag-orange' : (rewards.wish.status==='pending_redeem' ? 'tag-red' : 'tag-blue')">{{wishStatusLabel(rewards.wish.status)}}</span>
            </div>
            <div class="progress" style="margin:8px 0"><i :style="{width: Math.min(100, rewards.wish.progress/rewards.wish.target*100)+'%'}"></i></div>
            <div class="wish-foot">
              <span v-if="rewards.wish.wish_type === 'optional_streak'">{{rewards.wish.progress}} / {{rewards.wish.target}} 天 · 每天完成 {{rewards.wish.daily_target || 3}} 个可选任务</span>
              <span v-else>{{rewards.wish.progress}} / {{rewards.wish.target}} · 每完成 1 个可选任务 +1</span>
              <span v-if="rewards.wish.deadline" class="more" style="font-size:11px">截止 {{rewards.wish.deadline}}</span>
              <button v-if="rewards.wish.status==='pending_redeem'" class="btn btn-primary btn-sm" @click="showToast('去找家长兑现吧，家长可在「设置-家长管理」确认 🎉')">找家长兑现 →</button>
            </div>
          </div>
          <div v-else class="wish-box wish-empty">
            <div class="wish-head"><b>🌟 还没有心愿？</b><button class="btn btn-ghost btn-sm" @click="startWish()">许一个心愿 →</button></div>
            <p>写下想要的小奖励，完成每日任务就能让它成真</p>
          </div>
          <div class="coupon-list" v-if="rewards.coupons.length">
            <div class="coupon-item" v-for="c in rewards.coupons" :key="c.id">
              <span class="ci">{{couponIcon(c.kind)}}</span>
              <div class="c-body">
                <b>{{c.title}}</b>
                <span v-if="c.required_days>0">{{c.kind_label}}<template v-if="c.granted_count>0"> · ✅ 已获得 {{c.granted_count}} 张，剩余 {{c.left}} 张</template><template v-else> · 三科任务全勤 {{c.required_days}} 天可得<template v-if="c.required_within_days>0">，限 {{c.required_within_days}} 天内（剩 {{c.days_left>=0 ? c.days_left : 0}} 天，截止 {{c.cycle_deadline}}）</template>，当前 {{c.progress_days}}/{{c.required_days}} 天</template><template v-if="c.required_within_days>0"><span class="more" style="font-size:11px"> · 超时进度清零重启</span></template><template v-else><span class="more" style="font-size:11px"> · 7天内最多缺1天，超出从头计算</span></template></span>
                <span v-else>{{c.kind_label}} · 可直接使用，剩余 {{c.left}} 张</span>
                <span v-if="c.reason" class="c-reason">🎯 {{c.reason}}</span>
              </div>
              <span class="tag" :class="c.left>0 ? 'tag-green' : 'tag-blue'">{{c.left>0 ? '可用' : (c.required_days>0 ? '待达成' : '已用完')}}</span>
            </div>
          </div>
          <div class="timeline-box" v-if="rewardTimeline.length">
            <div class="tl-title">🏆 成长奖励记录</div>
            <div class="tl-item" v-for="(it,i) in rewardTimeline" :key="i">
              <span class="tl-ico" :class="it.kind==='wish' ? 't-gold' : 't-blue'">{{it.kind==='wish' ? '🌟' : '🎫'}}</span>
              <div class="tl-body"><b>{{it.title}}</b><span>{{it.reason}}<template v-if="it.at"> · {{it.at}}</template></span></div>
            </div>
          </div>
        </div>

        <!-- 家长留言（孩子端） -->
        <div class="card msg-card" style="margin-top:14px">
          <div class="card-head">
            <b>✉️ 家长留言</b>
            <span class="more" v-if="parentMsgs.unread>0" @click="markMsgsRead()">点开即已读，共 {{parentMsgs.unread}} 条未读</span>
            <span class="more" v-else>家长写给你的悄悄话</span>
          </div>
          <div v-if="parentMsgs.messages && parentMsgs.messages.length" class="msg-list">
            <div class="msg-item" :class="{unread: !m.read}" v-for="m in parentMsgs.messages.slice(0,6)" :key="m.id">
              <span class="msg-ico">💌</span>
              <div class="msg-body"><p>{{m.content}}</p><span>{{m.created_at}}<template v-if="!m.read"> · 未读</template></span></div>
            </div>
          </div>
          <div v-else class="empty" style="padding:18px">
            <p style="color:#8a97b0;font-size:13px">还没有留言，等爸爸妈妈来说悄悄话吧</p>
          </div>
        </div>

        <!-- 成长周报入口（Sprint 3） -->
        <div class="card weekly-entry" style="margin-top:14px" @click="openWeekly()">
          <div class="w-ico">📮</div>
          <div class="w-body">
            <b>上周成长周报</b>
            <span>AI 为你总结一周亮点，还有家长的悄悄话</span>
          </div>
          <span class="btn btn-ghost btn-sm">查看 →</span>
        </div>

        <!-- 挑战赛 + 学期目标（Sprint 4） -->
        <div class="grid-2" style="margin-top:14px">
          <div class="card chal-entry" @click="openChal()">
            <div class="w-ico">⚡</div>
            <div class="w-body">
              <b>60 秒挑战赛</b>
              <span>口算 / 单词快答，刷新纪录赢徽章</span>
            </div>
            <span class="btn btn-ghost btn-sm">开战 →</span>
          </div>
          <div class="card goal-entry" @click="goalOverlay.show=true; loadGoals()">
            <div class="w-ico">🎯</div>
            <div class="w-body">
              <b>学期目标</b>
              <span>分数 / 消灭错题 / 背诵 倒计时</span>
            </div>
            <span class="btn btn-ghost btn-sm">查看 →</span>
          </div>
        </div>

        <!-- 学习概览 -->
        <div class="section-title">📈 学习概览</div>
        <div class="grid-3">
          <div class="card stat-card"><div class="ico">📚</div><b>{{vocabTotal ? vocabLearned+'/'+vocabTotal : 0}}</b><span>已学单词</span></div>
          <div class="card stat-card highlight"><div class="ico">🎯</div><b>{{avgScore}}%</b><span>平均正确率</span></div>
          <div class="card stat-card"><div class="ico">🏅</div><b>{{masteredTotal}}</b><span>已掌握错题</span></div>
        </div>
      </div>

      <!-- ═══════════ 刷题中心 ═══════════ -->
      <div v-if="tab==='practice'" class="fade-enter">
        <div class="sub-tabs">
          <button class="pill" :class="{active: practiceSub==='generate'}" @click="practiceSub='generate'">生成试卷</button>
          <button class="pill" :class="{active: practiceSub==='grammar'}" @click="practiceSub='grammar'; loadGrammarPoints()" v-if="subject==='英语'">语法练习</button>
          <button class="pill" :class="{active: practiceSub==='records'}" @click="practiceSub='records'; loadAttempts()">做题记录</button>
        </div>

        <!-- 生成试卷 -->
        <div v-if="practiceSub==='generate'">
          <div class="card" style="max-width:720px">
            <h3 style="font-size:17px;margin-bottom:18px">生成新试卷</h3>
            <div class="form-grid">
              <div class="form-item">
                <label>学科</label>
                <select v-model="subject" @change="onSubjectChange"><option v-for="s in subjectOptions" :key="'gen-'+s">{{s}}</option></select>
              </div>
              <div class="form-item">
                <label>题数</label>
                <input type="number" v-model.number="genCount" min="1" max="200">
              </div>
              <div class="form-item full">
                <label>出题策略</label>
                <div style="font-size:13px;color:var(--text-2);line-height:1.7">难度根据最近成绩自动调整；约 30% 题目针对未掌握的错题题型</div>
              </div>
            </div>
            <div style="margin-top:22px;display:flex;gap:12px">
              <button class="btn btn-primary" :disabled="generating" @click="generateExam">{{generating ? '生成中…' : '生成并开始做题'}}</button>
              <span style="font-size:12px;color:var(--text-3);align-self:center">生成后自动入库，答错的题自动进入错题本</span>
            </div>
          </div>
        </div>

        <!-- 语法练习 -->
        <div v-if="practiceSub==='grammar'">
          <div class="card" v-if="!grammarQuiz.length">
            <h3 style="font-size:17px;margin-bottom:14px">语法点选择</h3>
            <div class="filter-bar" style="margin:0 0 14px">
              <button class="pill" :class="{active: grammarCategory===''}" @click="grammarCategory=''; loadGrammarPoints()">全部</button>
              <button class="pill" :class="{active: grammarCategory==='时态'}" @click="grammarCategory='时态'; loadGrammarPoints()">时态</button>
              <button class="pill" :class="{active: grammarCategory==='词法'}" @click="grammarCategory='词法'; loadGrammarPoints()">词法</button>
              <button class="pill" :class="{active: grammarCategory==='句型'}" @click="grammarCategory='句型'; loadGrammarPoints()">句型</button>
            </div>
            <div v-for="p in grammarPoints" :key="p.id" class="text-card" @click="selectGrammarPoint(p)">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                  <div class="t-title">{{p.name}}</div>
                  <div class="t-meta">{{p.category}} · {{p.exercise_count}} 题 · {{p.grade}}年级起</div>
                </div>
                <span class="tag" :class="p.exercise_count>0?'tag-blue':'tag-gray'">{{p.exercise_count}} 题</span>
              </div>
            </div>
          </div>
          <div v-else class="quiz-wrap" style="max-width:720px;margin:0">
            <div class="quiz-top">
              <span class="qname">📝 语法练习</span>
              <div class="progress"><i :style="{width: (grammarQuizIndex/grammarQuiz.length*100)+'%'}"></i></div>
              <span class="qcount">{{grammarQuizIndex+1}} / {{grammarQuiz.length}}</span>
            </div>
            <div class="quiz-card">
              <div class="quiz-sub"><span class="tag tag-violet">{{grammarQuiz[grammarQuizIndex].grammar_point_name}}</span> <span class="tag tag-gray">{{typeLabel(grammarQuiz[grammarQuizIndex].exercise_type)}}</span></div>
              <div class="quiz-q">{{grammarQuiz[grammarQuizIndex].question}}</div>
              <template v-if="grammarQuiz[grammarQuizIndex].exercise_type==='choice'">
                <button v-for="(opt, oi) in grammarQuiz[grammarQuizIndex].options" :key="oi" class="option"
                        :class="optClass(opt, grammarQuiz[grammarQuizIndex])" :disabled="grammarSubmitted"
                        @click="grammarAnswer(opt)">{{opt}}</button>
              </template>
              <input v-else class="fill-input" v-model="grammarInput" placeholder="输入答案后回车" @keyup.enter="grammarSubmit()" :disabled="grammarSubmitted">
              <div class="feedback" :class="{on: grammarSubmitted, ok: grammarFeedbackOk, no: !grammarFeedbackOk}">
                <h4>{{grammarFeedbackOk ? '✓ 回答正确！' : '✗ 答错了，看看解析'}}</h4>
                <p v-if="!grammarFeedbackOk">正确答案：{{grammarCurrentAnswer}}</p>
                <p v-if="grammarCurrentExplanation">💡 {{grammarCurrentExplanation}}</p>
              </div>
              <div class="quiz-actions">
                <span style="font-size:12px;color:var(--text-3)">答错的题自动进入错题本</span>
                <div class="right">
                  <button class="btn btn-ghost" @click="grammarExit()">退出</button>
                  <button class="btn btn-primary" :disabled="!grammarSubmitted" @click="grammarNext()">{{grammarQuizIndex===grammarQuiz.length-1 ? '查看结果 →' : '下一题 →'}}</button>
                </div>
              </div>
            </div>
          </div>
          <div v-if="grammarResult" class="done-wrap">
            <div class="done-illus" :class="{no: grammarResult.score<60}">{{grammarResult.score>=90 ? '🏆' : grammarResult.score>=60 ? '🎉' : '💪'}}</div>
            <h2>{{grammarResult.score>=90 ? '太棒了！' : grammarResult.score>=60 ? '继续加油！' : '别灰心，再来一次'}}</h2>
            <p class="sub">语法练习完成</p>
            <div class="done-grid">
              <div class="done-cell"><b>{{grammarResult.score}}分</b><span>得分</span></div>
              <div class="done-cell"><b>{{grammarResult.correct}}/{{grammarResult.total}}</b><span>答对题数</span></div>
              <div class="done-cell"><b>{{grammarResult.wrong}}</b><span>错题（已入本）</span></div>
            </div>
            <div class="done-note" v-if="grammarResult.wrong>0">📝 {{grammarResult.wrong}} 道错题已自动加入错题本，可在「错题本」中复盘错因并变式重练</div>
            <div class="done-actions">
              <button class="btn btn-ghost" @click="grammarResult=null; grammarQuiz=[]; loadGrammarPoints()">再来一组</button>
              <button class="btn btn-primary" @click="goTab('wrong')">去错题本复盘</button>
            </div>
          </div>
        </div>

        <!-- 做题记录（跟随顶部学科，只显示当前学科） -->
        <div v-if="practiceSub==='records'">
          <div class="card">
            <h3 style="font-size:17px;margin-bottom:14px">做题记录 · {{subject}}</h3>
            <div v-if="attempts===null" class="empty">⏳ 加载中…</div>
            <div v-else-if="!attempts.length" class="empty"><div class="em">📄</div><h3>暂无做题记录</h3><p>去刷题中心生成试卷开始练习吧</p><button class="btn btn-primary" @click="practiceSub='generate'">去生成试卷</button></div>
            <div v-else>
              <div v-for="a in attempts" :key="a.id" class="attempt-item" @click="viewAttempt(a)">
                <div class="a-score" :style="{background: a.score>=80?'var(--success-light)':a.score>=60?'var(--warning-light)':'var(--danger-light)', color: a.score>=80?'var(--success)':a.score>=60?'var(--warning)':'var(--danger)'}">{{a.score}}分</div>
                <div class="a-body"><b>{{a.exam_title}}</b><span>{{a.created_at}} · 对 {{a.correct}} / 共 {{a.total}} 题 · 用时 {{a.duration_sec}}s</span></div>
                <span class="tag" :class="a.score>=80?'tag-green':a.score>=60?'tag-orange':'tag-red'">{{a.score>=80?'优秀':a.score>=60?'良好':'待提升'}}</span>
                <span class="a-more">查看详情 ›</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════ 背诵中心 ═══════════ -->
      <div v-if="tab==='recite'" class="fade-enter">
        <div class="sub-tabs">
          <button class="pill" :class="{active: reciteSub==='words'}" @click="switchRecite('words')">📖 背单词</button>
          <button class="pill" :class="{active: reciteSub==='classical'}" @click="switchRecite('classical')">📜 古诗文</button>
        </div>

        <!-- 背单词 -->
        <div v-if="reciteSub==='words'">
          <div class="grid-2">
            <div class="card recite-card">
              <div class="card-head"><b>📖 今日新词</b><span class="tag tag-blue">{{vocabToday.stats.new_remaining}} 个待学</span></div>
              <p class="card-desc">每轮学 {{vocabToday.stats.new_remaining}} 个新单词，学完可再来一轮，不限次数</p>
              <button class="btn btn-primary btn-lg recite-btn" :disabled="vocabToday.stats.new_remaining<=0" @click="startWordSession('new')">开始学习新词 →</button>
            </div>
            <div class="card recite-card">
              <div class="card-head"><b>🔁 今日复习</b><span class="tag tag-orange">{{vocabToday.stats.due_today}} 个待复习</span></div>
              <p class="card-desc">到期的单词现在复习，记忆效果最好</p>
              <button class="btn btn-warning btn-lg recite-btn" :disabled="vocabToday.stats.due_today<=0" @click="startWordSession('review')">开始复习 →</button>
            </div>
          </div>
          <div class="card" style="margin-top:16px">
            <div class="card-head"><b>学习进度</b><span class="more">{{vocabToday.stats.learned}} / {{vocabToday.stats.total_words}} 已学</span></div>
            <div class="progress" style="margin:14px 0 18px"><i :style="{width: vocabPct+'%'}"></i></div>
            <div class="recite-stats">
              <div><b>{{vocabToday.stats.learned}}</b><span>已学单词</span></div>
              <div><b>{{vocabToday.stats.mastered}}</b><span>已掌握</span></div>
              <div><b>{{vocabToday.stats.streak_days}}</b><span>连续天数</span></div>
              <div><b>{{vocabToday.stats.new_today}}</b><span>今日新学</span></div>
            </div>
          </div>
        </div>

        <!-- 古诗文 -->
        <div v-if="reciteSub==='classical'">
          <div class="grid-2">
            <div class="card recite-card">
              <div class="card-head"><b>📜 今日新篇</b><span class="tag tag-blue">{{classicalToday.stats.new_remaining}} 篇待背</span></div>
              <p class="card-desc">每轮背 {{classicalToday.stats.new_remaining}} 篇古诗文，背完可再来一轮，不限次数</p>
              <button class="btn btn-primary btn-lg recite-btn" :disabled="classicalToday.stats.new_remaining<=0" @click="startTextSession('new')">开始背诵 →</button>
            </div>
            <div class="card recite-card">
              <div class="card-head"><b>🔁 今日复习</b><span class="tag tag-orange">{{classicalToday.stats.due_today}} 篇待复习</span></div>
              <p class="card-desc">按记忆曲线复习，背过的篇目要定期巩固</p>
              <button class="btn btn-warning btn-lg recite-btn" :disabled="classicalToday.stats.due_today<=0" @click="startTextSession('review')">开始复习 →</button>
            </div>
          </div>
          <div class="card" style="margin-top:16px">
            <div class="card-head"><b>📚 篇目列表</b><span class="more">已背 {{classicalToday.stats.learned}} / {{classicalToday.stats.total}} 篇</span></div>
            <div class="text-list" style="margin-top:6px">
              <div v-for="t in classicalTexts" :key="t.id" class="text-item">
                <div class="t-main"><b>《{{t.title}}》</b><span>{{t.author}} · {{t.dynasty}} · {{t.grade}}年级</span></div>
                <span class="tag tag-gray">{{t.text_type==='prose'?'古文':'古诗'}}</span>
                <button class="btn btn-ghost btn-sm" @click="openTextDetail(t)">查看</button>
              </div>
              <div v-if="!classicalTexts.length" class="empty"><div class="em">📜</div><h3>暂无篇目</h3><p>当前年级还没有古诗文数据，换个年级试试</p></div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════ 错题本 ═══════════ -->
      <div v-if="tab==='wrong'" class="fade-enter">
        <div class="grid-4">
          <div class="stat-card"><div class="ico">📚</div><b>{{wrongAnalysis.total}}</b><span>累计错题</span></div>
          <div class="stat-card highlight"><div class="ico">⏳</div><b>{{wrongAnalysis.pending}}</b><span>待攻克</span></div>
          <div class="stat-card"><div class="ico">✅</div><b>{{wrongAnalysis.mastered}}</b><span>已掌握</span></div>
          <div class="stat-card"><div class="ico">🎯</div><b>{{wrongAnalysis.mastery_rate}}%</b><span>掌握率</span></div>
        </div>

        <!-- 列表 -->
        <div v-if="wrongScreen==='list'">
          <div class="filter-bar">
            <button class="pill" :class="{active: wrongKind==='all'}" @click="wrongKind='all'; loadWrongItems()">全部</button>
            <button class="pill" :class="{active: wrongKind==='exam'}" @click="wrongKind='exam'; loadWrongItems()">📝 试卷错题</button>
            <button class="pill" :class="{active: wrongKind==='study'}" @click="wrongKind='study'; loadWrongItems()">✏️ 学习错题</button>
            <span class="filter-sep"></span>
            <button class="pill" :class="{active: wrongStatus==='pending'}" @click="wrongStatus='pending'; loadWrongItems()">未掌握</button>
            <button class="pill" :class="{active: wrongStatus==='mastered'}" @click="wrongStatus='mastered'; loadWrongItems()">已掌握</button>
            <span class="filter-sep"></span><span class="tag tag-blue">{{subject}}</span>
            <button class="btn btn-primary btn-sm" style="margin-left:auto" @click="startWrongPractice()" title="从错题本随机抽 5 道错题，每道配 3 道同类型题，整组全对自动掌握">🎯 练习错题</button>
            <button class="btn btn-ghost btn-sm" @click="loadAnalysis(); wrongScreen='analysis'">📊 错因分析</button>
          </div>
          <div class="card teach-due" v-if="tomorrowQueue.count>0" @click="wrongStatus='pending'; loadWrongItems()">
            <b>🌙 明日复习队列：{{tomorrowQueue.count}} 道题重做仍错，明天再来一次</b>
            <span>{{(tomorrowQueue.items||[]).slice(0,3).map(i=>i.subject+(i.module_name?'·'+i.module_name:'')).join('、')}}<template v-if="tomorrowQueue.count>3"> 等</template> · 点我查看</span>
          </div>
          <div class="card teach-due" v-if="teachDue.length" @click="openRecheck()">
            <b>🔁 7 天到啦，考考自己还记得吗？</b>
            <span>有 {{teachDue.length}} 道讲给家长的题待复习验证，点我开始</span>
          </div>
          <div class="card">
            <div v-if="!wrongItems.length" class="empty"><div class="em">🎉</div><h3>太棒了，这里没有错题</h3><p>继续保持，或者去刷题中心练练手</p><button class="btn btn-primary" @click="goTab('practice')">去刷题</button></div>
            <div v-for="w in wrongItems" :key="w.key" class="wrong-item" :class="{mastered: w.mastered}" @click="openWrongDetail(w)">
              <div class="wi-ico" :class="w.kind==='exam'?'t-blue':'t-violet'">{{w.kind==='exam'?'📝':'✏️'}}</div>
              <div class="wi-body">
                <div class="wi-q">{{w.question}}</div>
                <div class="wi-meta">
                  <span class="tag" :class="w.kind==='exam'?'tag-blue':'tag-violet'">{{w.source}}</span>
                  <span class="tag tag-gray">{{w.subject}}</span>
                  <span v-if="w.is_unanswered" class="tag tag-yellow">未答</span>
                  <span v-else-if="!w.mastered" class="tag tag-red">答错</span>
                  <span v-if="!w.mastered && w.cause" class="tag tag-orange">{{causeLabel(w.cause)}}</span>
                  <span class="wi-count">错 {{w.error_count}} 次</span>
                  <span class="wi-last">{{w.wrong_at}}</span>
                </div>
              </div>
              <span v-if="w.mastered" class="tag tag-green">已掌握</span>
              <span class="arrow">›</span>
            </div>
          </div>
        </div>

        <!-- 详情复盘 -->
        <div v-if="wrongScreen==='detail' && curWrong">
          <button class="btn btn-ghost btn-sm" @click="wrongScreen='list'">← 返回列表</button>
          <div class="card" style="margin-top:12px">
            <div class="card-head"><b>错题复盘</b><span class="tag" :class="curWrong.kind==='exam'?'tag-blue':'tag-violet'" style="margin-left:auto">{{curWrong.source}}</span></div>
            <div class="quiz-q" style="font-size:17px;margin:16px 0 4px">{{curWrong.question}}</div>
            <p class="quiz-sub">回顾当时为什么错，才能不再错</p>
            <!-- 未答题：先作答再判断对错，不直接显示答案 -->
            <div v-if="curWrong.is_unanswered" class="unanswered-box" style="margin:12px 0">
              <p style="color:#8B7CF6;font-weight:600;margin-bottom:8px">这道题当时未作答，请先作答：</p>
              <div style="display:flex;gap:8px;align-items:center">
                <input v-model="curWrong._answerInput" class="quiz-fill-input" placeholder="输入你的答案" style="flex:1" @keyup.enter="answerUnanswered">
                <button class="btn btn-primary" @click="answerUnanswered">提交</button>
              </div>
            </div>
            <!-- 答错题：显示答案对比 -->
            <div v-else class="detail-compare">
              <div class="answer-box wrong"><span>我的答案</span><b>{{curWrong.user_answer || '（未作答）'}}</b></div>
              <div class="answer-box right"><span>正确答案</span><b>{{curWrong.correct_answer}}</b></div>
            </div>
            <div v-if="curWrong.explanation" class="feedback ok" style="display:block">
              <h4>📖 解析</h4><p>{{curWrong.explanation}}</p>
            </div>
            <!-- AI 讲解（内联展示在题目下方，不弹窗） -->
            <div class="inline-explain" v-if="curWrong.explaining || curWrong.aiText || curWrong.aiError">
              <div v-if="curWrong.explaining" class="explain-loading">
                <span class="explain-spin"></span>🤖 老师正在讲解…（通常 3-10 秒，请稍等）
              </div>
              <template v-else-if="curWrong.aiText">
                <div class="explain-seg" v-for="(s,i) in explainSectionsOf(curWrong.aiText)" :key="i" :class="{first: i===0}">
                  <div class="seg-title" v-if="s.title">【{{s.title}}】</div>
                  <div class="seg-body">
                    <p v-for="(line,li) in s.body.split('\n').filter(x=>x.trim())" :key="li">{{line}}</p>
                  </div>
                </div>
                <p class="explain-deg" v-if="curWrong.aiDegraded">（离线讲解版 · 已尽力帮到你了）</p>
              </template>
              <p v-else class="explain-err">😵 {{curWrong.aiError}} <button class="btn btn-ghost btn-sm" @click="openExplain(curWrong)">重试</button></p>
            </div>
            <div class="card-head" style="margin-top:22px"><b>💡 这次错在哪？</b><span class="more">选择后系统会针对性推送变式练习</span></div>
            <div class="cause-grid">
              <button class="cause-item" :class="{selected: curWrong.cause==='careless'}" @click="submitCause('careless')"><span class="ci-ico">😅</span>粗心大意<span class="ci-d">看错数字 / 符号 / 漏字</span></button>
              <button class="cause-item" :class="{selected: curWrong.cause==='concept'}" @click="submitCause('concept')"><span class="ci-ico">🤔</span>概念不清<span class="ci-d">知识点本身没掌握</span></button>
              <button class="cause-item" :class="{selected: curWrong.cause==='method'}" @click="submitCause('method')"><span class="ci-ico">🛠️</span>方法不会<span class="ci-d">不知道用什么方法解题</span></button>
              <button class="cause-item" :class="{selected: curWrong.cause==='reading'}" @click="submitCause('reading')"><span class="ci-ico">👀</span>审题失误<span class="ci-d">没看清题目要求 / 条件</span></button>
            </div>
            <div class="mastery-row" v-if="curWrong.mastered">
              <span>🎉 已掌握</span>
              <div class="progress"><i style="width:100%;background:var(--success)"></i></div>
            </div>
            <div class="detail-actions">
              <button class="btn btn-primary" v-if="curWrong.kind==='exam' && curWrong.question_id" :disabled="curWrong.explaining || !curWrong.cause" @click="openExplain(curWrong)">{{curWrong.explaining ? '⏳ 讲解中…' : '🤖 AI 讲解'}}</button>
              <button class="btn btn-primary" :disabled="!curWrong.cause" @click="openTeach(curWrong)">🎓 出题给家长</button>
              <button class="btn btn-primary" :disabled="!curWrong.cause" @click="startWrongRetry(curWrong)">🎯 变式重练</button>
              <button class="btn btn-success" v-if="!curWrong.mastered" :disabled="!curWrong.cause" @click="markWrongMastered(curWrong)" title="先做 3 道同类型题，全部答对才标记已掌握">✅ 检测掌握（3 题全对）</button>
              <button class="btn btn-ghost" @click="wrongScreen='list'">返回列表</button>
            </div>
            <p v-if="!curWrong.cause && !curWrong.is_unanswered" style="text-align:center;color:var(--text-3);font-size:13px;margin-top:8px">💡 请先选择错因，才能进行讲解、重练等操作</p>
          </div>
        </div>

        <!-- 错因分析 -->
        <div v-if="wrongScreen==='analysis'">
          <button class="btn btn-ghost btn-sm" @click="wrongScreen='list'">← 返回列表</button>
          <div class="card" style="margin-top:12px">
            <div class="card-head"><b>📊 错因分析</b><span class="more">共 {{wrongAnalysis.total}} 道错题 · {{wrongAnalysis.pending}} 道待攻克</span></div>
            <div class="chart-wrap">
              <div class="donut">
                <svg width="220" height="220" viewBox="0 0 220 220">
                  <circle cx="110" cy="110" r="90" fill="none" stroke="#EDF0F8" stroke-width="26"/>
                  <circle v-for="(seg,i) in donutSegs" :key="i" cx="110" cy="110" r="90" fill="none" :stroke="seg.color" stroke-width="26" :stroke-dasharray="(seg.len)+' 999'" :stroke-dashoffset="seg.off" transform="rotate(-90 110 110)"/>
                </svg>
                <div class="center"><b>{{wrongAnalysis.pending}}</b><span>待攻克错题</span></div>
              </div>
              <div class="legend">
                <div class="legend-row" v-for="c in wrongAnalysis.by_cause" :key="c.code">
                  <span class="sw" :style="{background: causeColor(c.code)}"></span>
                  <span>{{c.label}}</span><span class="pct" :style="{color: causeColor(c.code)}">{{c.count}} 道</span>
                </div>
                <div v-if="!(wrongAnalysis.by_cause||[]).length" class="empty" style="padding:20px"><div class="em">🍀</div><h3>暂无错因数据</h3><p>去错题详情里选择错因吧</p></div>
              </div>
            </div>
          </div>
          <div class="card" style="margin-top:16px">
            <div class="card-head"><b>📈 按学科分布</b></div>
            <div class="bar-row" v-for="s in wrongAnalysis.by_subject" :key="s.subject" style="margin-top:14px">
              <div class="bl"><span>{{s.subject}}</span><b>{{s.count}} 道</b></div>
              <div class="bar-track"><div class="bar-fill" :style="{width: subjPct(s)+'%', background: subjColor(s)}"></div></div>
            </div>
            <div class="card-head" style="margin-top:24px"><b>🕒 待攻克错因分布</b></div>
            <div class="bar-row" v-for="c in wrongAnalysis.by_cause" :key="c.code" style="margin-top:14px">
              <div class="bl"><span>{{c.label}}</span><b>{{c.pending}} 道</b></div>
              <div class="bar-track"><div class="bar-fill" :style="{width: causePct(c)+'%', background: causeColor(c.code)}"></div></div>
            </div>
            <div class="suggest-card" v-if="topCause">
              <div class="s-ico">💡</div>
              <div><b>优先攻克「{{topCause.label}}」</b><p>这是你失分最多的原因，建议回到对应知识点重新学习，再配合变式练习巩固</p></div>
              <button class="btn btn-primary" @click="retryTopCause()">去练习 →</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════ 试卷中心 ═══════════ -->
      <div v-if="tab==='papers'" class="fade-enter">
        <div class="filter-bar">
          <button class="btn btn-primary" @click="goTab('practice')">＋ 生成新试卷</button>
          <span class="filter-sep"></span><span class="tag tag-blue">{{subject}}</span>
        </div>
        <div class="card">
          <div v-if="!papers.length" class="empty"><div class="em">📄</div><h3>还没有试卷</h3><p>去刷题中心生成第一份试卷吧</p><button class="btn btn-primary" @click="goTab('practice')">去生成</button></div>
          <div v-for="p in papers" :key="p.id" class="paper-item">
            <div class="p-ico" :class="p.subject==='数学'?'t-orange':p.subject==='语文'?'t-violet':'t-blue'">{{p.subject==='数学'?'🧮':p.subject==='语文'?'📖':'🔤'}}</div>
            <div class="p-body">
              <b>{{p.title}}</b>
              <span class="meta">{{p.subject}} · {{p.grade}}年级 · {{p.difficulty}} · {{p.question_count}}题 · {{p.created_at}}</span>
            </div>
            <div class="p-actions">
              <button class="btn btn-ghost btn-sm" @click="previewPaper(p)">在线做题</button>
              <button class="btn btn-ghost btn-sm" @click="downloadPaper(p)">下载 Word</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════ 学习统计 ═══════════ -->
      <div v-if="tab==='stats'" class="fade-enter">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px"><h2 style="font-size:19px">学习统计</h2><span class="tag tag-blue">{{subject}}</span></div>
        <div class="card compare-card" v-if="selfCompare" style="margin-bottom:16px">
          <div class="card-head"><b>🚀 自我超越</b><span class="tag tag-violet">只和自己比</span></div>
          <div class="cmp-grid">
            <div class="cmp-item" v-if="attemptDeltaText"><span class="cmp-ico">📝</span><p>{{attemptDeltaText}}</p></div>
            <div class="cmp-item" v-if="vocabDeltaText"><span class="cmp-ico">🔤</span><p>{{vocabDeltaText}}</p></div>
            <div class="cmp-item" v-if="classicalDeltaText"><span class="cmp-ico">📜</span><p>{{classicalDeltaText}}</p></div>
            <div class="cmp-item" v-if="selfCompare.mastered_7d>0"><span class="cmp-ico">💪</span><p>本周已消灭 {{selfCompare.mastered_7d}} 道错题</p></div>
            <div class="cmp-item empty" v-if="!attemptDeltaText && !vocabDeltaText && !classicalDeltaText && !(selfCompare.mastered_7d>0)"><span class="cmp-ico">🌱</span><p>完成一次做题或背诵后，这里会出现"和自己比"的记录</p></div>
          </div>
        </div>
        <!-- 心情压力预警（家长视角） -->
        <div class="card mood-alert" v-if="moodTrend && moodTrend.alert" style="margin-bottom:16px">
          <div class="alert-ico">🤗</div>
          <div class="alert-body">
            <b>给家长的小提示</b>
            <p>{{moodTrend.alert.text}}</p>
          </div>
        </div>
        <div class="grid-4">
          <div class="stat-card highlight"><div class="ico">🔥</div><b>{{streakDays}}</b><span>连续学习天数</span></div>
          <div class="stat-card"><div class="ico">📝</div><b>{{statsAttempts}}</b><span>完成试卷</span></div>
          <div class="stat-card"><div class="ico">💯</div><b>{{avgScore}}%</b><span>平均得分</span></div>
          <div class="stat-card"><div class="ico">✅</div><b>{{masteredTotal}}</b><span>已掌握错题</span></div>
        </div>
        <div class="grid-3" style="margin-top:16px">
          <div class="card" v-if="subject==='英语'">
            <div class="card-head"><b>📖 单词</b><span class="tag tag-blue">{{vocabStats.learning_count||0}} 学习中</span></div>
            <div class="big-num">{{vocabStats.learned_count||0}}<span> / {{vocabStats.total_words||0}}</span></div>
            <div class="progress"><i :style="{width: statPct(vocabStats.learned_count, vocabStats.total_words)+'%'}"></i></div>
            <div class="mini-stats">
              <div><b>{{vocabStats.mastered_count||0}}</b><span>已掌握</span></div>
              <div><b>{{vocabStats.due_today||0}}</b><span>今日待复习</span></div>
              <div><b>{{vocabStats.streak_days||0}}</b><span>连续天数</span></div>
            </div>
          </div>
          <div class="card" v-if="subject==='语文'">
            <div class="card-head"><b>📜 古诗文</b><span class="tag tag-violet">{{classicalStats.mastered||0}} 已掌握</span></div>
            <div class="big-num">{{classicalStats.learned||0}}<span> / {{classicalStats.total||0}}</span></div>
            <div class="progress"><i :style="{width: statPct(classicalStats.learned, classicalStats.total)+'%'}"></i></div>
            <div class="mini-stats">
              <div><b>{{classicalStats.mastered||0}}</b><span>已掌握</span></div>
              <div><b>{{classicalStats.due_today||0}}</b><span>今日待复习</span></div>
              <div><b>{{classicalStats.streak_days||0}}</b><span>连续天数</span></div>
            </div>
          </div>
          <div class="card" v-if="subject==='英语'">
            <div class="card-head"><b>📊 语法练习</b><span class="tag tag-orange">{{wrongAnalysis.pending||0}} 待攻克</span></div>
            <div class="big-num">{{grammarStats.total_exercises||0}}<span> 道题库</span></div>
            <p class="card-desc">覆盖 {{grammarStats.total_points||0}} 个语法点</p>
            <div class="mini-stats">
              <div><b>{{wrongAnalysis.total||0}}</b><span>累计错题</span></div>
              <div><b>{{wrongAnalysis.mastered||0}}</b><span>已掌握</span></div>
              <div><b>{{wrongAnalysis.mastery_rate||0}}%</b><span>掌握率</span></div>
            </div>
          </div>
        </div>
        <div class="card" style="margin-top:16px">
          <div class="card-head"><b>📄 最近做题</b><button class="btn btn-ghost btn-sm" style="margin-left:auto" @click="goTab('practice'); practiceSub='records'">查看全部</button></div>
          <div v-if="!recentAttempts.length" class="empty" style="padding:26px"><div class="em">📄</div><h3>暂无做题记录</h3><p>完成第一份试卷后这里会展示得分趋势</p></div>
          <div v-for="a in recentAttempts" :key="a.id" class="attempt-item" @click="viewAttempt(a)">
            <div class="a-score" :style="{background: a.score>=80?'var(--success-light)':a.score>=60?'var(--warning-light)':'var(--danger-light)', color: a.score>=80?'var(--success)':a.score>=60?'var(--warning)':'var(--danger)'}">{{a.score}}分</div>
            <div class="a-body"><b>{{a.exam_title}}</b><span>{{a.created_at}} · 对 {{a.correct}} / 共 {{a.total}} 题 · 用时 {{a.duration_sec}}s</span></div>
            <span class="tag" :class="a.score>=80?'tag-green':a.score>=60?'tag-orange':'tag-red'">{{a.score>=80?'优秀':a.score>=60?'良好':'待提升'}}</span>
            <span class="a-more">查看详情 ›</span>
          </div>
        </div>
      </div>

      <!-- ═══════════ 设置 ═══════════ -->
      <!-- ═══════════ 十万个为什么 ═══════════ -->
      <div v-if="tab==='qa'" class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#667eea,#764ba2)">
          <div style="flex:1">
            <h1>❓ 十万个为什么</h1>
            <p class="sub" style="color:rgba(255,255,255,.9)">想问什么就问什么，AI 老师来解答！相同问题直接秒回，不重复问 AI</p>
          </div>
        </div>
        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>💬 对话</b>
            <span class="more">
              <button class="qa-tab" :class="{on: !qaSessionId}" @click="newQaSession()">➕ 新对话</button>
            </span>
          </div>
          <div class="qa-model-row">
            <span class="qa-model-label">选 AI 老师：</span>
            <button v-for="m in qaModels" :key="m.key" class="qa-model-btn"
                    :class="{on: qaProvider===m.key, off: !m.available}"
                    :disabled="!m.available" :title="m.vip_only && !qaModelsVip ? 'DeepSeek 仅 VIP 用户可用' : ''"
                    @click="qaProvider=m.key">
              {{m.label}}<span v-if="m.vip_only" class="tag tag-gold" style="margin-left:4px">VIP</span>
            </button>
            <span v-if="qaModels && !qaModelsVip" class="qa-vip-tip">💎 DeepSeek 仅 VIP 用户可用，找家长开通哦</span>
          </div>
          <div class="qa-sess-row" v-if="qaSessions.length">
            <span class="qa-model-label">会话：</span>
            <button v-for="s in qaSessions.slice(0, 6)" :key="s.session_id" class="qa-sess-btn"
                    :class="{on: qaSessionId===s.session_id}"
                    :title="s.first_question" @click="openQaSession(s.session_id)">
              {{s.first_question.slice(0, 10)}} <em>{{s.rounds}}轮</em>
            </button>
          </div>
          <div class="qa-chat" ref="qaChat">
            <div v-if="!qaMessages.length" class="empty" style="padding:20px">
              <div class="em">🌱</div><h3>开始一段新对话吧</h3>
              <p>问一个问题，然后可以接着追问，AI 老师会记住我们聊过的内容</p>
            </div>
            <div v-for="(m, mi) in qaMessages" :key="mi" class="qa-bubble" :class="m.role==='user' ? 'user' : 'ai'">
              <div class="qa-bubble-text" :class="{degraded: m.degraded}">{{m.text}}</div>
              <div class="qa-bubble-meta" v-if="m.role==='ai' && (m.provider || m.cached || m.degraded)">
                <span v-if="m.cached" class="tag tag-green" style="font-size:11px">⚡ 秒回 · 缓存</span>
                <span v-else-if="m.degraded" class="tag tag-orange" style="font-size:11px">AI 暂不可用</span>
                <span v-else class="tag tag-blue" style="font-size:11px">{{qaModelLabel(m.provider)}}<template v-if="m.model"> · {{m.model}}</template></span>
              </div>
            </div>
          </div>
          <div class="qa-ask-row" style="margin-top:12px">
            <textarea v-model="qaAsk" class="qa-input" rows="2" maxlength="300"
                      placeholder="例如：为什么天是蓝色的？……（问完可以继续追问，AI 会记得上下文）"
                      @keydown.enter.exact.prevent="askQa()"></textarea>
            <button class="btn btn-primary" :disabled="qaLoading || !qaAsk.trim()" @click="askQa()">
              {{qaLoading ? 'AI 老师思考中…' : '发送 →'}}
            </button>
          </div>
        </div>
        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>📚 我的记录</b>
            <span class="more">
              <button class="qa-tab" :class="{on: qaHistType==='all'}" @click="qaHistType='all'; loadQaHistory()">全部</button>
              <button class="qa-tab" :class="{on: qaHistType==='qa'}" @click="qaHistType='qa'; loadQaHistory()">提问</button>
              <button class="qa-tab" :class="{on: qaHistType==='explain'}" @click="qaHistType='explain'; loadQaHistory()">题目讲解</button>
            </span>
          </div>
          <div v-if="!qaHistory.length" class="empty" style="padding:24px">
            <div class="em">🌱</div><h3>还没有记录</h3><p>问一个问题试试吧！</p>
          </div>
          <div v-else class="qa-hist-list">
            <div v-for="h in qaHistory" :key="h.id" class="qa-hist-item" @click="h._open = !h._open">
              <div class="qa-hist-head">
                <span class="qa-hist-q">{{h.question}}</span>
                <span class="tag" :class="h.q_type==='qa' ? 'tag-blue' : 'tag-violet'">{{h.q_type==='qa' ? '提问' : '讲解'}}</span>
                <span class="qa-hist-time">{{h.created_at}}</span>
              </div>
              <div class="qa-hist-a" v-show="h._open">{{h.answer}}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════ 宠物家园（P2-1 金币宠物） ═══════════ -->
      <div v-if="tab==='pet'" class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#f7971e,#ffd200)">
          <div style="flex:1">
            <h1>🐣 宠物家园</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">完成任务、答对题目、讲清错题都能赚金币，喂饱小宠物陪它长大！</p>
          </div>
          <div class="pet-coin" v-if="petProfile">
            <div class="pet-coin-num">{{petProfile.coins}}</div>
            <div class="pet-coin-label">🪙 金币</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="pet-stage" v-if="petProfile">
            <div class="pet-emoji">{{petEmoji(petProfile.level)}}</div>
            <div class="pet-name">{{petName(petProfile.level)}}<span class="tag tag-gold" style="margin-left:8px">Lv.{{petProfile.level}}</span></div>
            <div class="pet-desc">{{petDesc(petProfile.level)}}</div>
            <div class="pet-exp-bar">
              <div class="pet-exp-fill" :style="{width: petExpPct(petProfile) + '%'}"></div>
            </div>
            <div class="pet-exp-text" v-if="petProfile.exp_next">{{petProfile.exp}} / {{petProfile.exp_next}} 经验<span v-if="petProfile.max_level">（已满级）</span></div>
            <div v-else class="pet-exp-text">⭐ 已满级，太棒啦！</div>
            <div class="pet-actions">
              <button class="btn btn-primary" :disabled="petBusy || (petProfile && petProfile.coins < 10)" @click="petFeed()">
                🍎 喂食（-10 金币，+5 经验）<span v-if="petProfile && petProfile.feeds_today"> · 今天已喂 {{petProfile.feeds_today}} 次</span>
              </button>
              <button class="btn" :disabled="petBusy || (petProfile && petProfile.pats_today >= 3)" @click="petPat()">
                🤗 摸摸头（+1 经验）<span v-if="petProfile"> · 今天 {{petProfile.pats_today}}/3 次</span>
              </button>
            </div>
            <div v-if="petMsg" class="pet-msg">{{petMsg}}</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>🪙 金币流水</b><span class="more" style="font-size:12px;color:var(--text-3)">余额：{{petProfile ? petProfile.coins : 0}}</span></div>
          <div v-if="!petLedger.length" class="empty" style="padding:24px">
            <div class="em">🪙</div><h3>还没有金币记录</h3><p>完成任务、答题全对、错题掌握、小老师讲清楚都可以赚金币哦</p>
          </div>
          <div v-else class="pet-ledger-list">
            <div v-for="(l, i) in petLedger" :key="i" class="pet-ledger-item">
              <span class="pet-ledger-reason">{{l.reason}}</span>
              <span class="pet-ledger-time">{{l.created_at}}</span>
              <span class="pet-ledger-amt" :class="{minus: l.amount < 0}">{{l.amount > 0 ? '+' : ''}}{{l.amount}}</span>
            </div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>📜 赚金币规则</b></div>
          <div class="pet-rules">
            <div v-for="r in petRules" :key="r.action" class="pet-rule-item">
              <div class="pet-rule-left"><b>{{r.action}}</b><span class="pet-rule-desc">{{r.desc}}</span></div>
              <span class="pet-rule-coin" :class="{minus: r.coins < 0}">{{r.coins > 0 ? '+' : ''}}{{r.coins}}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════ 成长树（P2-2 创意 7） ═══════════ -->
      <div v-if="tab==='tree'" class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#11998e,#38ef7d)">
          <div style="flex:1">
            <h1>🌳 成长树</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">你的每一次学习都在浇灌这棵树，只和自己比，看着它慢慢长大！</p>
          </div>
          <div class="tree-score" v-if="treeData">
            <div class="tree-score-num">{{treeData.score}}</div>
            <div class="tree-score-label">🌱 成长值</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="tree-stage" v-if="treeData">
            <div class="tree-emoji">{{treeData.stage.emoji}}</div>
            <div class="tree-name">{{treeData.stage.name}}</div>
            <div class="tree-bar"><div class="tree-fill" :style="{width: treeData.stage.pct + '%'}"></div></div>
            <div class="tree-bar-text" v-if="treeData.stage.next">再攒 {{treeData.stage.next - treeData.score}} 成长值，长成「{{treeStageName(treeData.stage.stage + 1)}}」！</div>
            <div class="tree-bar-text" v-else>已经长成「森林之王」，太厉害了！</div>
            <div class="tree-path">
              <div v-for="(s, i) in treeStages" :key="i" class="tree-path-node"
                   :class="{done: i <= (treeData.stage.stage), cur: i === treeData.stage.stage}">
                <span class="tree-path-emoji">{{s.emoji}}</span><span class="tree-path-name">{{s.name}}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>📈 成长值来源</b><span class="more" style="font-size:12px;color:var(--text-3)">总计 {{treeData ? treeData.score : 0}}</span></div>
          <div v-if="!treeData || !treeData.parts.length" class="empty" style="padding:24px">
            <div class="em">🌱</div><h3>成长值还是 0</h3><p>去刷一套题，或者背几个单词，小树就会发芽啦！</p>
          </div>
          <div v-else class="tree-parts">
            <div v-for="p in treeData.parts" :key="p.key" class="tree-part-item">
              <span class="tree-part-label">{{p.label}}<em class="tree-part-val">{{p.value}} 次</em></span>
              <span class="tree-part-score">+{{p.score}}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════ 成就徽章墙（P2-3 创意 8） ═══════════ -->
      <div v-if="tab==='badges'" class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#f093fb,#f5576c)">
          <div style="flex:1">
            <h1>🏅 成就徽章墙</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">每达成一个里程碑，就点亮一枚徽章。看看你已经收集了多少枚？</p>
          </div>
          <div class="badge-count" v-if="badgeData">
            <div class="badge-count-num">{{badgeData.earned}} / {{badgeData.total}}</div>
            <div class="badge-count-label">🏅 已点亮</div>
          </div>
        </div>

        <div v-if="badgeNew.length" class="card" style="max-width:760px;margin-top:16px;border-color:#F0C98A;background:#FFF8EC">
          <div class="card-head"><b>🎉 恭喜获得新徽章！</b></div>
          <div class="badge-new-list">
            <div v-for="b in badgeNew" :key="b.code" class="badge-new-item">
              <span class="badge-new-emoji">{{b.emoji}}</span>
              <div class="badge-new-info"><b>{{b.name}}</b><span>{{b.desc}}</span></div>
            </div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="badge-grid" v-if="badgeData">
            <div v-for="b in badgeData.items" :key="b.code" class="badge-item" :class="{locked: !b.earned}">
              <div class="badge-medal">{{b.earned ? b.emoji : '🔒'}}</div>
              <div class="badge-name">{{b.name}}</div>
              <div class="badge-desc">{{b.desc}}</div>
              <div class="badge-date" v-if="b.earned">{{b.earned_at}} 获得</div>
              <div class="badge-date" v-else>待解锁</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════ 知识卡图鉴（P2-4 创意 13） ═══════════ -->
      <div v-if="tab==='cards'" class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#4facfe,#00f2fe)">
          <div style="flex:1">
            <h1>🃏 知识卡图鉴</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">掌握一个知识点就点亮一张卡，集齐图鉴成为知识收藏家！</p>
          </div>
          <div class="card-count" v-if="cardData">
            <div class="card-count-num">{{cardData.collected}} / {{cardData.total}}</div>
            <div class="card-count-label">🃏 已点亮</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>🎴 今日抽卡</b>
            <button class="btn btn-primary" style="padding:6px 14px;font-size:12.5px" @click="cardDraw()" :disabled="cardDrawing">
              {{cardDrawing ? '抽卡中…' : '抽 3 张 →'}}
            </button>
          </div>
          <p class="card-desc">从还没点亮的卡里抽 3 张，看看今天该去学什么！</p>
          <div v-if="drawAllCollected" class="empty" style="padding:20px">
            <div class="em">🏆</div><h3>全部收集完成！</h3><p>你就是知识收藏家！</p>
          </div>
          <div v-else-if="drawCards.length" class="draw-cards">
            <div v-for="(c, i) in drawCards" :key="i" class="draw-card" :style="{animationDelay: i * 0.15 + 's'}">
              <div class="draw-card-emoji">{{c.emoji}}</div>
              <div class="draw-card-title">{{c.title}}</div>
              <div class="draw-card-sub">{{c.sub}}</div>
              <div class="draw-card-desc">{{c.desc}}</div>
            </div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>📚 我的图鉴</b><span class="more" style="font-size:12px;color:var(--text-3)">掌握即点亮</span></div>
          <div v-if="!cardData || !cardData.categories.length" class="empty" style="padding:24px">
            <div class="em">🃏</div><h3>图鉴还是空的</h3><p>掌握第一个知识点，点亮第一张卡吧！</p>
          </div>
          <div v-else v-for="cat in cardData.categories" :key="cat.key" class="card-cat">
            <div class="card-cat-head"><b>{{cat.emoji}} {{cat.name}}</b><span class="more" style="font-size:12px;color:var(--text-3)">{{cat.collected}} / {{cat.total}}</span></div>
            <div v-if="!cat.cards.length" class="card-cat-empty">还没有收集，去学习吧！</div>
            <div v-else class="card-grid">
              <div v-for="c in cat.cards" :key="c.id" class="card-tile">
                <span class="card-tile-emoji">{{c.emoji}}</span>
                <span class="card-tile-title">{{c.title}}</span>
                <span class="card-tile-sub">{{c.sub}}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════ 听写磨耳朵（P2-5 创意 25） ═══════════ -->
      <div v-if="tab==='dict'" class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#a18cd1,#fbc2eb)">
          <div style="flex:1">
            <h1>👂 听写磨耳朵</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">听一听，写一写，耳朵和手都练起来！全对还能赚金币哦</p>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="dict-mode-row">
            <button class="dict-mode-btn" :class="{on: dictMode==='word'}" @click="dictSwitchMode('word')">🔤 单词听写</button>
            <button class="dict-mode-btn" :class="{on: dictMode==='text'}" @click="dictSwitchMode('text')">📜 古诗文听写</button>
            <span class="dict-tip">💡 听不清就点 🔊 再听一遍</span>
          </div>

          <div v-if="!dictSession.active" class="dict-start">
            <div class="dict-start-info">
              <p><b>{{dictMode==='word' ? '🔤 单词听写' : '📜 古诗文听写'}}</b></p>
              <p class="dict-start-desc">{{dictMode==='word' ? '电脑朗读单词，你写出拼写，锻炼耳朵和拼写！' : '电脑朗读古诗文句子，你默写出来，加深记忆！'}}</p>
            </div>
            <button class="btn btn-primary" @click="dictStart()">🎧 开始听写（{{dictMode==='word' ? 10 : 5}} 题）</button>
          </div>

          <div v-else class="dict-session">
            <div class="dict-progress">第 {{dictSession.i + 1}} / {{dictSession.items.length}} 题</div>
            <div class="dict-question" v-if="!dictSession.revealed">
              <button class="dict-play-btn" @click="dictSpeak(dictSession.current)">🔊 播放</button>
              <div class="dict-hint">{{dictMode==='word' ? '听到单词了吗？写出它！' : '听句子，默写出来'}}</div>
              <input v-model="dictSession.answer" class="dict-input" :placeholder="dictMode==='word' ? '输入单词拼写' : '输入句子'"
                     @keyup.enter="dictCheck()" autofocus>
              <button class="btn btn-primary" @click="dictCheck()" :disabled="!dictSession.answer.trim()">✓ 提交</button>
            </div>
            <div v-else class="dict-result" :class="{ok: dictSession.lastOk}">
              <div class="dict-result-head">{{dictSession.lastOk ? '✅ 答对啦！' : '❌ 再听一遍，记住它'}}</div>
              <div class="dict-result-ans">
                <div class="dict-result-line"><span>你写的：</span><b>{{dictSession.answer}}</b></div>
                <div class="dict-result-line" v-if="!dictSession.lastOk"><span>正确答案：</span><b class="dict-correct">{{dictSession.current.answer}}</b></div>
                <div class="dict-result-line" v-if="dictMode==='word' && !dictSession.lastOk"><span>意思：</span><em>{{dictSession.current.meaning}}</em></div>
              </div>
              <div class="dict-result-actions">
                <button class="btn" @click="dictReplay()">🔊 再听一遍</button>
                <button class="btn btn-primary" @click="dictNext()">{{dictSession.i < dictSession.items.length - 1 ? '下一题 →' : '看成绩 🏁'}}</button>
              </div>
            </div>
          </div>

          <div v-if="dictSession.done" class="dict-done">
            <div class="dict-done-score">{{dictSession.correct}} / {{dictSession.items.length}}</div>
            <div class="dict-done-text" v-if="dictSession.correct === dictSession.items.length">🎉 全对！赚到 3 金币，去宠物家园喂小宠物吧！</div>
            <div class="dict-done-text" v-else-if="dictSession.correct >= dictSession.items.length * 0.6">👏 不错哦，再练几遍就能全对啦！</div>
            <div class="dict-done-text" v-else>💪 多听几遍，磨磨耳朵再来一次！</div>
            <button class="btn btn-primary" @click="dictStart()">🔁 再来一组</button>
          </div>
        </div>
      </div>

      <!-- ═══════════ 番茄专注钟（P2-6 创意 22） ═══════════ -->
      <div v-if="tab==='focus'" class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#ff512f,#dd2476)">
          <div style="flex:1">
            <h1>⏰ 番茄专注钟</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">专注 25 分钟，休息 5 分钟。每完成一次专注 +2 金币，保护眼睛也攒金币！</p>
          </div>
          <div class="focus-stats" v-if="focusToday">
            <div class="focus-stats-num">{{focusToday.count}}<em>次</em></div>
            <div class="focus-stats-label">今日专注 {{focusToday.minutes}} 分钟</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="focus-pick-row" v-if="!focusTimer.running && !focusTimer.paused">
            <button v-for="m in [10, 15, 25]" :key="m" class="focus-pick-btn" :class="{on: focusTimer.total === m}" @click="focusSet(m)">
              {{m}} 分钟
            </button>
          </div>

          <div class="focus-clock" :class="{running: focusTimer.running, done: focusDone}">
            <div class="focus-ring" :style="{background: focusRingStyle}">
              <div class="focus-time">{{focusTimeText}}</div>
              <div class="focus-state">{{focusTimer.running ? '专注中…' : focusDone ? '完成！' : (focusTimer.paused ? '已暂停' : '准备好就开始')}}</div>
            </div>
          </div>

          <div class="focus-actions">
            <template v-if="!focusDone">
              <button v-if="!focusTimer.running && !focusTimer.paused" class="btn btn-primary" @click="focusStart()">▶ 开始专注</button>
              <button v-if="focusTimer.running && !focusTimer.paused" class="btn" @click="focusPause()">⏸ 暂停</button>
              <button v-if="focusTimer.paused" class="btn btn-primary" @click="focusResume()">▶ 继续</button>
              <button v-if="focusTimer.running || focusTimer.paused" class="btn" @click="focusReset()">↺ 放弃</button>
            </template>
            <button v-else class="btn btn-primary" @click="focusReset()">🔁 再来一次</button>
          </div>

          <div v-if="focusMsg" class="focus-msg">{{focusMsg}}</div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>📊 专注统计</b></div>
          <div v-if="!focusStats" class="card-desc">完成一次专注后，这里会显示你的专注数据</div>
          <div v-else class="focus-stat-grid">
            <div class="focus-stat-item"><b>{{focusStats.today.count}}</b><span>今日（{{focusStats.today.minutes}} 分钟）</span></div>
            <div class="focus-stat-item"><b>{{focusStats.week.count}}</b><span>本周（{{focusStats.week.minutes}} 分钟）</span></div>
            <div class="focus-stat-item"><b>{{focusStats.total.count}}</b><span>累计（{{focusStats.total.minutes}} 分钟）</span></div>
          </div>
          <p class="card-desc" style="margin-top:8px">💡 小贴士：每专注 25 分钟记得站起来看看远处，眼睛休息一下哦</p>
        </div>
      </div>

      <!-- ═══════════ AI 趣味出题（AI-2 创意 24） ═══════════ -->
      <div v-if="tab==='aiquiz'" class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#00b09b,#96c93d)">
          <div style="flex:1">
            <h1>🎲 AI 趣味出题</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">AI 老师把题目包装成冒险、太空、恐龙、美食、魔法主题，全对还能拿金币！答错的题会自动进错题本。</p>
          </div>
          <div class="focus-stats" v-if="aiQuizPlayed">
            <div class="focus-stats-num">{{aiQuizPlayed}}<em>次</em></div>
            <div class="focus-stats-label">玩过的闯关</div>
          </div>
        </div>

        <!-- 配置区 -->
        <div v-if="!aiQuiz.loading && !aiQuiz.quiz" class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>🎮 选好主题，AI 老师就出题</b></div>
          <div class="form-grid" style="margin-top:16px">
            <div class="form-item"><label>学科</label>
              <select v-model="aiQuiz.subject">
                <option>数学</option><option>语文</option><option>英语</option>
              </select>
            </div>
            <div class="form-item"><label>年级</label>
              <select v-model="aiQuiz.grade">
                <option v-for="g in [1,2,3,4,5,6,7,8,9]" :key="'aiq-'+g" :value="g">{{g}}年级</option>
              </select>
            </div>
          </div>
          <div class="dict-mode-row" style="margin-top:14px">
            <button v-for="(t, k) in aiQuizThemes" :key="k" class="dict-mode-btn" :class="{on: aiQuiz.theme === k}" @click="aiQuiz.theme = k">
              {{aiQuizThemeEmoji[k]}} {{t}}
            </button>
          </div>
          <div style="margin-top:18px">
            <button class="btn btn-primary" @click="aiQuizGenerate()">✨ 让 AI 出 5 道题</button>
          </div>
          <p class="card-desc" style="margin-top:10px">💡 AI 生成大约需要 10 秒，请耐心等待。每道题都有 4 个选项，全对奖励 +5 金币，答错的进错题本！</p>
        </div>

        <!-- 加载中 -->
        <div v-if="aiQuiz.loading" class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>🤖 AI 老师正在出题…</b></div>
          <p class="card-desc">正在把 {{aiQuiz.subject}}{{aiQuiz.grade}}年级题目包装成「{{aiQuizThemeEmoji[aiQuiz.theme]}} {{aiQuizThemes[aiQuiz.theme]}}」主题，请稍候</p>
          <div class="loading-bar"><div class="loading-bar-inner"></div></div>
        </div>

        <!-- 作答区 -->
        <template v-if="aiQuiz.quiz && !aiQuiz.graded">
          <div class="card" style="max-width:760px;margin-top:16px">
            <div class="card-head"><b>🎯 {{aiQuiz.themeName}} · {{aiQuiz.subject}}闯关</b>
              <span style="float:right;font-size:13px;color:#999">已答 {{aiQuizAnswered}}/{{aiQuiz.quiz.length}} 题</span>
            </div>
            <div class="quiz-q" v-for="(q, i) in aiQuiz.quiz" :key="i">
              <div class="quiz-q-title">{{i + 1}}. {{q.question}}</div>
              <div v-if="q.options && q.options.length" class="quiz-options">
                <button v-for="(o, j) in q.options" :key="j" class="quiz-opt-btn"
                        :class="{on: aiQuiz.answers[i] === o[0]}"
                        @click="aiQuizPick(i, o[0])">{{o}}</button>
              </div>
              <input v-else class="quiz-fill" v-model="aiQuiz.inputs[i]" placeholder="想一想，把答案打在这里" @keyup.enter="aiQuizGrade()">
            </div>
            <div style="margin-top:18px;text-align:center">
              <button class="btn btn-primary" :disabled="aiQuizAnswered < aiQuiz.quiz.length" @click="aiQuizGrade()">✅ 交卷判分</button>
            </div>
          </div>
        </template>

        <!-- 判分结果 -->
        <template v-if="aiQuiz.quiz && aiQuiz.graded">
          <div class="card" style="max-width:760px;margin-top:16px">
            <div class="card-head"><b>{{aiQuiz.score.correct === aiQuiz.quiz.length ? '🎉 全对！太厉害了！' : '📋 判分结果'}}</b></div>
            <div class="dict-done-text" style="margin-bottom:14px">
              答对 <b style="color:var(--primary)">{{aiQuiz.score.correct}}</b> / {{aiQuiz.quiz.length}} 题
              <span v-if="aiQuiz.rewardGranted" style="color:#e6a23c"> · 全对奖励金币 +{{aiQuiz.rewardGranted}} 💰</span>
            </div>
            <div class="quiz-q" v-for="(q, i) in aiQuiz.quiz" :key="i">
              <div class="quiz-q-title" :class="aiQuiz.score.detail[i] ? 'q-right' : 'q-wrong'">
                {{i + 1}}. {{q.question}} <span class="q-mark">{{aiQuiz.score.detail[i] ? '✓' : '✗'}}</span>
              </div>
              <div class="quiz-fun" v-if="!aiQuiz.score.detail[i]">你的答案：{{aiQuizUserAnswer(i)}} · 正确答案：{{q.answer}}</div>
              <div class="quiz-fun">{{q.explanation}}</div>
              <div class="quiz-fun" style="background:linear-gradient(90deg,#fff7e6,#fffbe6);border-color:#ffd591">🧠 {{q.fun}}</div>
            </div>
            <div style="margin-top:18px;text-align:center">
              <button class="btn btn-primary" @click="aiQuizReset()">🔁 再来一组</button>
            </div>
          </div>
        </template>
      </div>

      <!-- ═══════════ AI 学习助手（AI-5） ═══════════ -->
      <div v-if="tab==='assistant'" class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#654ea3,#eaafc8)">
          <div style="flex:1">
            <h1>🧑‍🏫 AI 学习助手</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">AI 老师认识你的学习数据！可以问它「今天该学什么」「帮我分析错题」「夸夸我」，它会结合你的真实情况回答。</p>
          </div>
          <div class="focus-stats" v-if="assistantProfile">
            <div class="focus-stats-num">{{assistantProfile.grade}}<em>年级</em></div>
            <div class="focus-stats-label">{{assistantProfile.subject}} · {{assistantChipCount}} 条学习数据</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>💬 和 AI 老师聊聊</b></div>

          <!-- 快捷提问 -->
          <div class="dict-mode-row" style="margin-top:10px;margin-bottom:6px" v-if="!assistantLoading">
            <button v-for="q in assistantChips" :key="q" class="dict-mode-btn" @click="assistantAsk(q)">{{q}}</button>
          </div>

          <!-- 消息区 -->
          <div class="chat-box" ref="chatBox">
            <div v-if="!assistantMsgs.length" class="chat-empty">
              <div style="font-size:34px">🤖</div>
              <p>嗨！我是你的 AI 学习助手，我已经看过你的学习数据啦～</p>
              <p class="chat-empty-tip">点上面任意一个问题，或者直接在下面打字问我！</p>
            </div>
            <div v-for="(m, i) in assistantMsgs" :key="i" class="chat-row" :class="m.role === 'me' ? 'chat-me' : 'chat-ai'">
              <div class="chat-bubble" :class="m.role === 'me' ? 'bubble-me' : 'bubble-ai'">
                <span v-if="m.role === 'me'" class="chat-name">我</span>
                <span v-else class="chat-name">AI 老师</span>
                <div class="chat-text" style="white-space:pre-wrap">{{m.text}}</div>
              </div>
            </div>
            <div v-if="assistantLoading" class="chat-row chat-ai">
              <div class="chat-bubble bubble-ai"><span class="chat-name">AI 老师</span><div class="chat-dots"><i></i><i></i><i></i></div></div>
            </div>
          </div>

          <!-- 输入区 -->
          <div class="chat-input-row">
            <input class="chat-input" v-model="assistantDraft" placeholder="问问 AI 老师…（它会结合你的学习数据回答）"
                   @keyup.enter="assistantSend()" :disabled="assistantLoading">
            <button class="btn btn-primary" style="flex-shrink:0" :disabled="assistantLoading || !assistantDraft.trim()" @click="assistantSend()">发送</button>
          </div>
        </div>
      </div>

      <!-- ═══════════ 钱包（P5 新增） ═══════════ -->
      <div v-if="tab==='wallet'" class="fade-enter">
        <div class="wallet-wrap">
          <div class="wallet-cards">
            <div class="wallet-card wc-diamond">
              <div class="wc-ico">💎</div>
              <div class="wc-num">{{wallet.diamonds}}</div>
              <div class="wc-label">钻石</div>
            </div>
            <div class="wallet-card wc-coin">
              <div class="wc-ico">🪙</div>
              <div class="wc-num">{{wallet.coins}}</div>
              <div class="wc-label">金币</div>
            </div>
            <div class="wallet-card wc-makeup">
              <div class="wc-ico">🎫</div>
              <div class="wc-num">{{makeupCards}}</div>
              <div class="wc-label">补签卡</div>
            </div>
          </div>
          <div class="wallet-coming">💳 充值 / 兑换商城 · 即将上线</div>
          <div class="wallet-ledger card" v-if="wallet.diamondLedger.length">
            <h3>💎 钻石明细</h3>
            <div class="wl-row" v-for="r in wallet.diamondLedger" :key="r.id">
              <span class="wl-reason">{{r.reason}}</span>
              <span class="wl-amt" :class="r.amount>0?'up':'down'">{{r.amount>0?'+':''}}{{r.amount}}</span>
              <span class="wl-time">{{r.created_at}}</span>
            </div>
          </div>
        </div>
      </div>
      
      <div v-if="tab==='settings'" class="fade-enter">
        <div class="card" style="max-width:640px">
          <div class="card-head"><b>👤 个人信息</b></div>
          <div class="form-grid" style="margin-top:16px">
            <div class="form-item"><label>用户名</label><input :value="user" disabled style="background:var(--bg)"></div>
            <div class="form-item"><label>年级</label><select v-model="grade" @change="onGradeChange"><option v-for="g in [1,2,3,4,5,6,7,8,9]" :key="'set-'+g" :value="g">{{g}}年级</option></select></div>
            <div class="form-item"><label>默认学科</label><select v-model="subject" @change="onSubjectChange"><option v-for="s in subjectOptions" :key="'def-'+s">{{s}}</option></select></div>
          </div>
          <p class="card-desc">当前年级：{{grade}}年级 · 每年9月自动升一年级 · 学习数据按用户名保存在本地服务器</p>
        </div>
        <div class="card" style="max-width:640px;margin-top:16px">
          <div class="card-head"><b>🏙️ 我的城市</b><span class="more">用于首页天气展示</span></div>
          <div class="pc-row">
            <input v-model="cityInput" placeholder="如：杭州" maxlength="50" style="flex:1;padding:9px 12px;border:1px solid #E5E1F5;border-radius:10px;font-size:14px">
            <button class="btn btn-primary" @click="saveCity" style="padding:9px 20px">保存</button>
          </div>
        </div>
        <div class="card" style="max-width:640px;margin-top:16px">
          <div class="card-head"><b>🔐 账号安全</b><span class="more">绑定邮箱/手机号后可跨设备登录与找回密码</span></div>
          <div class="info-row"><span>邮箱</span><b>{{authInfo.email || '未绑定'}}</b></div>
          <div class="info-row"><span>手机号</span><b>{{authInfo.phone || '未绑定'}}</b></div>
          <div class="info-row"><span>登录密码</span><b>{{authInfo.has_password ? '已设置' : '未设置'}}</b></div>
          <div v-if="!authInfo.email || !authInfo.phone" style="margin-top:12px">
            <div class="pc-title">{{authInfo.email ? '📱 绑定手机号' : '📧 绑定邮箱'}}</div>
            <div class="pc-row">
              <input v-model="bindTarget" class="fill-input" :placeholder="authInfo.email ? '输入手机号' : '输入邮箱'" style="max-width:220px">
              <button class="btn btn-ghost btn-sm" :disabled="authCooldown>0 || !bindTarget.trim()" @click="sendAuthCode('bind', bindTarget)">{{authCooldown>0 ? authCooldown+'s' : '获取验证码'}}</button>
            </div>
            <div class="pc-row" style="margin-top:8px">
              <input v-model="bindCode" class="fill-input" maxlength="6" placeholder="验证码" style="max-width:140px">
              <button class="btn btn-primary btn-sm" :disabled="!bindTarget.trim() || bindCode.trim().length<6" @click="bindAccount()">绑定</button>
            </div>
          </div>
        </div>
        <div class="card" style="max-width:640px;margin-top:16px">
          <div class="card-head"><b>📚 学习数据</b></div>
          <div class="info-row"><span>连续学习</span><b>🔥 {{streakDays}} 天</b></div>
          <div class="info-row"><span>累计单词</span><b>{{vocabStats.learned_count||0}} / {{vocabStats.total_words||0}}</b></div>
          <div class="info-row"><span>累计古诗文</span><b>{{classicalStats.learned||0}} / {{classicalStats.total||0}}</b></div>
          <div class="info-row"><span>错题总数</span><b>{{wrongAnalysis.total||0}}（已掌握 {{wrongAnalysis.mastered||0}}）</b></div>
        </div>
        <div class="card" style="max-width:640px;margin-top:16px">
          <div class="card-head"><b>⚙️ 其他</b></div>
          <div class="info-row"><span>极速模式（答题动画加速）</span><button class="btn btn-sm" :class="turbo ? 'btn-primary' : 'btn-ghost'" @click="toggleTurbo()">{{turbo ? '已开启' : '已关闭'}}</button></div>
          <div class="detail-actions" style="margin-top:14px">
            <button class="btn btn-ghost" @click="showToast('已是最新版本 v2.0')">检查更新</button>
            <button class="btn btn-danger" @click="logout()">退出登录</button>
          </div>
        </div>

        <!-- 家长管理（密码保护 + 任务设置 + 兑换券/心愿 + 留言/学习数据/题数设置） -->
        <div class="card parent-card" style="max-width:640px;margin-top:16px">
          <div class="card-head"><b>👨‍👩‍👧 家长管理</b><span class="more">家长密码保护 · 孩子进不来</span></div>

          <!-- ① 首次使用：设置家长密码 -->
          <div v-if="parentPhase==='unset'" class="pc-sec">
            <div class="pc-title">🔒 设置家长密码 <span class="more">设置后进入家长管理需要输密码，防止孩子乱动</span></div>
            <div class="pc-row">
              <input v-model="pwdForm.pwd" type="password" class="fill-input" maxlength="32" placeholder="家长密码（4-32 位）" style="max-width:180px">
              <input v-model="pwdForm.pwd2" type="password" class="fill-input" maxlength="32" placeholder="再输一次" style="max-width:180px">
            </div>
            <div class="pc-row" style="margin-top:8px">
              <input v-model="pwdForm.hintQ" class="fill-input" maxlength="100" placeholder="密保问题（忘记密码时用，如：孩子的小名是？）">
            </div>
            <div class="pc-row" style="margin-top:8px">
              <input v-model="pwdForm.hintA" class="fill-input" maxlength="50" placeholder="密保答案（家长才能答对哦）" style="max-width:240px">
              <button class="btn btn-primary btn-sm" @click="setupParentPwd()">设置并进入</button>
            </div>
          </div>

          <!-- ② 已设密码：输入密码解锁 -->
          <div v-else-if="parentPhase==='locked' || parentPhase==='reset'" class="pc-sec">
            <div class="pc-title">🔑 家长验证</div>
            <template v-if="parentPhase==='locked'">
              <div class="pc-row">
                <input v-model="pwdForm.unlock" type="password" class="fill-input" maxlength="32" placeholder="输入家长密码" style="max-width:200px" @keyup.enter="unlockParent()">
                <button class="btn btn-primary btn-sm" @click="unlockParent()">解锁</button>
                <button class="btn btn-ghost btn-sm" @click="parentPhase='reset'">忘记密码？</button>
              </div>
              <p class="pc-hint">孩子完成每日任务、兑换券、心愿都由家长在这里管理</p>
            </template>
            <template v-else>
              <div class="pc-row">
                <span class="more" style="font-size:13px">密保问题：{{pwdForm.hintQ}}</span>
              </div>
              <div class="pc-row" style="margin-top:8px">
                <input v-model="pwdForm.resetA" class="fill-input" maxlength="50" placeholder="密保答案" style="max-width:200px">
                <input v-model="pwdForm.resetPwd" type="password" class="fill-input" maxlength="32" placeholder="新密码" style="max-width:180px">
                <button class="btn btn-primary btn-sm" @click="resetParentPwd()">重置</button>
                <button class="btn btn-ghost btn-sm" @click="parentPhase='locked'">返回</button>
              </div>
              <p class="pc-hint">答对密保问题即可重置密码（家长预设的问题）</p>
            </template>
          </div>

          <!-- ③ 已解锁：家长管理全部功能 -->
          <template v-else>
          <div class="pc-row" style="justify-content:space-between;margin-bottom:8px">
            <span class="more" style="font-size:13px">🔓 家长模式已解锁</span>
            <button class="btn btn-ghost btn-sm" @click="exitParentMode()">退出家长模式 →</button>
          </div>
          <div class="pc-sec">
            <div class="pc-title">🎯 今日任务确认 <span class="more">讲题/朗读/听写由家长确认完成，数量可在下方设置</span></div>
            <div class="pc-row" v-for="t in dailyTasks" :key="t.id" style="justify-content:space-between;flex-wrap:wrap">
              <span style="font-size:13px;color:#3a4a6b">{{t.subject}} · {{t.title}}</span>
              <span style="display:inline-flex;align-items:center;gap:8px">
                <span v-if="t.status==='done'" class="tag tag-green">✅ 已完成</span>
                <template v-else-if="t.manual && t.status==='pending_confirm'">
                  <span class="tag tag-orange">孩子已提交</span>
                  <button class="btn btn-primary btn-sm" @click="parentConfirmTask(t)">确认完成 ✓</button>
                </template>
                <template v-else-if="t.manual">
                  <span class="more">待孩子提交</span>
                </template>
                <span v-else class="more">{{t.progress}} / {{t.target}}</span>
              </span>
            </div>
          </div>

          <!-- 家长面板补签待确认区块：孩子用补签卡完成任务的申请在此由家长确认生效/拒绝退回 -->
          <div class="pc-sec">
            <div class="pc-title">🎫 补签卡待确认 <span class="more">孩子用补签卡完成的任务，需家长确认生效，拒绝则退回</span><span v-if="pendingMakeups.length" class="tag tag-orange">{{pendingMakeups.length}} 条待处理</span></div>
            <div class="pc-list" v-if="pendingMakeups.length">
              <div class="pc-item" v-for="m in pendingMakeups" :key="m.log_id" style="flex-wrap:wrap">
                <div class="c-body" style="flex:1;min-width:200px">
                  <b>{{m.task_title || '任务'}}</b>
                  <span class="more">提交于 {{m.used_at}}</span>
                </div>
                <button class="btn btn-success btn-sm" @click="confirmMakeup(m.log_id, 'confirm')">确认生效 ✓</button>
                <button class="btn btn-ghost btn-sm" @click="confirmMakeup(m.log_id, 'reject')">拒绝退回</button>
              </div>
            </div>
            <p v-else class="pc-empty">没有待确认的补签申请</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">✋ 孩子的申诉 <span class="more">孩子觉得题判错了，请家长二次确认</span><span v-if="pendingAppeals.length" class="tag tag-orange">{{pendingAppeals.length}} 条待处理</span></div>
            <div class="pc-list" v-if="pendingAppeals.length">
              <div class="pc-item" v-for="a in pendingAppeals" :key="a.id" style="flex-wrap:wrap">
                <div class="c-body" style="flex:1;min-width:220px">
                  <b class="appeal-q" @click="toggleAppeal(a.id)" title="点击查看完整题目">
                    [{{a.subject || '未分科'}}]
                    <template v-if="!appealExpanded[a.id]">{{ a.question.length > 60 ? a.question.slice(0,60)+'…' : a.question }}</template>
                    <template v-else>{{ a.question }}</template>
                    <span class="q-toggle">{{ appealExpanded[a.id] ? '收起 ▴' : '查看完整题目 ▾' }}</span>
                  </b>
                  <span>孩子答案：{{a.user_answer}} · 参考答案：{{a.correct_answer}}</span>
                  <span class="more">{{a.created_at}} 提交</span>
                </div>
                <button class="btn btn-success btn-sm" @click="decideAppeal(a, true)" title="确认后该题改判正确、本卷得分重算">确认做对了 ✓</button>
                <button class="btn btn-ghost btn-sm" @click="decideAppeal(a, false)">维持判错</button>
              </div>
            </div>
            <p v-else class="pc-empty">没有待处理的申诉</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">📋 每日任务设置 <span class="more">管理强制任务和可选任务</span></div>
            <div v-if="taskSettings" style="font-size:13px;color:#666;margin-bottom:8px">
              强制任务 3 科 · 可选任务 {{(taskSettings.optional || []).length}} 个已配置
            </div>
            <div class="pc-row" style="margin-top:8px">
              <button class="btn btn-primary btn-sm" @click="showTaskSettingsDialog()">管理任务</button>
            </div>
          </div>

          <div class="pc-sec">
            <div class="pc-title">📝 试卷最少题数 <span class="more">孩子生成试卷（含每日练习）不得少于这个数</span></div>
            <div class="pc-row" style="gap:12px">
              <span class="more" style="font-size:13px">数学</span>
              <input v-model.number="examMin.math_min" type="number" min="1" max="50" class="fill-input" style="max-width:70px">
              <span class="more" style="font-size:13px">语文</span>
              <input v-model.number="examMin.chi_min" type="number" min="1" max="50" class="fill-input" style="max-width:70px">
              <span class="more" style="font-size:13px">英语</span>
              <input v-model.number="examMin.eng_min" type="number" min="1" max="50" class="fill-input" style="max-width:70px">
              <button class="btn btn-primary btn-sm" @click="saveExamSettings()">保存</button>
            </div>
            <p class="pc-hint">范围 1-50 题。比如数学设 20，孩子怎么选都不会少于 20 题</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">📅 学习同步设置 <span class="more">学期解锁 · 课堂同步 · 小升初衔接</span></div>
            <div class="pc-row" style="justify-content:space-between">
              <span style="font-size:13px;color:#3a4a6b">预习下学期（提前解锁下学期词书/古诗文）</span>
              <button class="btn btn-sm" :class="studyFlags.include_next ? 'btn-primary' : 'btn-ghost'" @click="toggleStudyFlag('include_next')">{{studyFlags.include_next ? '已开启' : '已关闭'}}</button>
            </div>
            <div class="pc-row" style="justify-content:space-between">
              <span style="font-size:13px;color:#3a4a6b">课堂同步（背单词/听写按教学进度的当前单元）</span>
              <button class="btn btn-sm" :class="studyFlags.sync_mode ? 'btn-primary' : 'btn-ghost'" @click="toggleStudyFlag('sync_mode')">{{studyFlags.sync_mode ? '已开启' : '已关闭'}}</button>
            </div>
            <div class="pc-row" style="justify-content:space-between" v-if="grade===6">
              <span style="font-size:13px;color:#3a4a6b">小升初衔接（六年级新学批次混入 30% 七年级内容）</span>
              <button class="btn btn-sm" :class="studyFlags.xsc_bridge ? 'btn-primary' : 'btn-ghost'" @click="toggleStudyFlag('xsc_bridge')">{{studyFlags.xsc_bridge ? '已开启' : '已关闭'}}</button>
            </div>
            <p class="pc-hint">预习：提前学下学期内容；课堂同步需先在下方设置教学进度；衔接仅六年级生效</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">📖 教学进度 <span class="more">孩子英语当前词书/单元，课堂同步按此出题</span></div>
            <div class="pc-row" style="flex-wrap:wrap;gap:8px">
              <select v-model.number="teachProgress.book_id" class="fill-input" style="max-width:220px" @change="onTeachBookChange()">
                <option :value="0">选择词书</option>
                <option v-for="b in teachBooks" :key="b.book_id" :value="b.book_id">{{b.book_name}}（{{b.semester}}学期）</option>
              </select>
              <select v-model="teachProgress.chapter" class="fill-input" style="max-width:130px">
                <option value="">选择单元</option>
                <option v-for="u in teachUnitOptions" :key="u">{{u}}</option>
              </select>
              <button class="btn btn-primary btn-sm" @click="saveTeachProgress()">保存进度</button>
            </div>
            <p class="pc-hint" v-if="teachProgressText">当前进度：{{teachProgressText}}</p>
            <p class="pc-hint" v-else>尚未设置；开启「课堂同步」后，背单词/听写只出当前单元的词汇，额度不足时回退全量</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">📊 孩子学习数据 <span class="more">本周概况</span></div>
            <div class="stats-grid">
              <div class="sg"><b>{{childStats.week_attempts}}</b><span>本周做题(套)</span></div>
              <div class="sg"><b>{{childStats.week_avg_score}}%</b><span>平均正确率</span></div>
              <div class="sg"><b>{{childStats.unmastered_wrong}}</b><span>未消灭错题</span></div>
              <div class="sg"><b>{{childStats.streak_days}}</b><span>连续学习(天)</span></div>
              <div class="sg"><b>{{childStats.week_tasks_done}}</b><span>本周完成任务</span></div>
            </div>
          </div>

          <div class="pc-sec">
            <div class="pc-title">💬 留言给孩子 <span class="more">孩子一登录就能看到，未读有提醒</span></div>
            <div class="pc-row">
              <input v-model="parentMsg" class="fill-input" maxlength="300" placeholder="写句悄悄话：如 今天数学做得不错，继续保持！" @keyup.enter="sendParentMsg()">
              <button class="btn btn-primary btn-sm" @click="sendParentMsg()">发送</button>
            </div>
            <div class="pc-list" v-if="sentMsgs.length">
              <div class="pc-item" v-for="m in sentMsgs.slice(0,5)" :key="m.id">
                <div class="c-body"><b>💌 {{m.content}}</b><span>{{m.created_at}}</span></div>
              </div>
            </div>
          </div>

          <div class="pc-sec">
            <div class="pc-title">💌 给孩子写悄悄话（周报寄语）</div>
            <div class="pc-row">
              <input v-model="parentNote" class="fill-input" maxlength="200" placeholder="写一句鼓励的话，会出现在孩子的成长周报里">
              <button class="btn btn-primary btn-sm" @click="saveParentNote()">保存</button>
            </div>
          </div>

          <div class="pc-sec">
            <div class="pc-title">🎫 兑换券管理 <span class="more">可设全勤天数门槛，孩子达成即获得；家长核销兑现 · 成长奖励记录只展示已获取的券</span></div>
            <div class="pc-row" style="flex-wrap:wrap">
              <input v-model="newCoupon.title" class="fill-input" maxlength="30" placeholder="如：周末看动画半小时" style="min-width:150px">
              <select v-model="newCoupon.kind" class="fill-input" style="max-width:110px">
                <option value="cartoon">动画时间</option><option value="snack">零食券</option>
                <option value="sticker">贴纸券</option><option value="toy">玩具券</option>
                <option value="outing">外出券</option><option value="custom">自定义</option>
              </select>
              <input v-model.number="newCoupon.requiredDays" type="number" min="0" max="30" class="fill-input" style="max-width:84px" placeholder="全勤几天">
              <span class="more">0=添加即获得</span>
              <input v-model.number="newCoupon.requiredWithinDays" type="number" min="0" max="365" :disabled="!newCoupon.requiredDays" class="fill-input" style="max-width:84px" placeholder="限几天内">
              <span class="more">0=不限期</span>
              <input v-model="newCoupon.reason" class="fill-input" maxlength="50" placeholder="奖励理由（选填）" style="min-width:150px">
              <button class="btn btn-primary btn-sm" @click="createCoupon()">添加</button>
            </div>
            <div class="pc-list" v-if="allCoupons.length">
              <div class="pc-item" v-for="c in allCoupons" :key="c.id" style="flex-wrap:wrap">
                <span class="ci">{{couponIcon(c.kind)}}</span>
                <div class="c-body">
                  <b>{{c.title}}</b>
                  <span>{{c.kind_label}}<template v-if="c.required_days>0"> · 三科全勤 {{c.required_days}} 天得 1 张<template v-if="c.required_within_days>0"> · 限 {{c.required_within_days}} 天内<span class="more" style="font-size:11px"> · 超时进度清零重启</span></template><template v-else><span class="more" style="font-size:11px"> · 7天内最多缺1天，超出从头计算</span></template></template><template v-if="c.reason"> · 🎯 {{c.reason}}</template></span>
                  <span v-if="c.status==='active'">已获得 {{c.granted_count}} 张 · 剩余 {{c.left}} 张</span>
                  <span v-else>已停用（历史获得 {{c.granted_count}} 张）</span>
                </div>
                <button v-if="c.status==='active' && c.left>0" class="btn btn-success btn-sm" @click="redeemCoupon(c)">核销 1 张</button>
                <button class="btn btn-sm" :class="c.status==='active' ? 'btn-ghost' : 'btn-primary'" @click="toggleCoupon(c)">{{c.status==='active' ? '停用' : '启用'}}</button>
              </div>
            </div>
          </div>

          <div class="pc-sec">
            <div class="pc-title">🌟 心愿确认 <span class="more">孩子的心愿需要家长确认才能开始，达标后由家长兑现</span></div>
            <div class="pc-list" v-if="pendingWishes.length">
              <div class="pc-item" v-for="w in pendingWishes" :key="w.id" style="flex-wrap:wrap">
                <div class="c-body" style="flex:1"><b>{{w.title}}</b><span>{{w.status==='pending' ? '待确认' : '已完成，待兑现'}} · 进度 {{w.progress}}/{{w.target}}{{w.deadline ? ' · 截止 '+w.deadline : ''}}</span></div>
                <input v-if="w.status==='pending_redeem'" v-model="w.redeemReason" class="fill-input" maxlength="50" placeholder="兑现理由（选填）" style="max-width:150px">
                <button class="btn btn-success btn-sm" @click="confirmWish(w)">{{w.status==='pending' ? '确认开始' : '确认兑现'}}</button>
                <button class="btn btn-ghost btn-sm" @click="archiveWish(w)">移除</button>
              </div>
            </div>
            <p v-else class="pc-empty">没有待处理的心愿</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">🔐 修改家长密码 <span class="more">需验证当前密码</span></div>
            <div class="pc-row" style="flex-wrap:wrap">
              <input v-model="pwdForm.old" type="password" class="fill-input" maxlength="32" placeholder="当前密码" style="max-width:140px">
              <input v-model="pwdForm.new1" type="password" class="fill-input" maxlength="32" placeholder="新密码" style="max-width:140px">
              <input v-model="pwdForm.new2" type="password" class="fill-input" maxlength="32" placeholder="再输一次" style="max-width:140px">
              <button class="btn btn-primary btn-sm" @click="changeParentPwd()">修改</button>
            </div>
          </div>
          </template>
        </div>
      </div>

      <SearchView v-if="tab==='search'"></SearchView>
      <SyncView v-if="tab==='sync'"></SyncView>
      <ReadingView v-if="tab==='reading'"></ReadingView>
    </main>
  </div>

  <!-- 移动端底部 TabBar（P5：≤900px 显示，修复旧版隐藏侧边栏后无法导航） -->
  <nav class="tabbar">
    <button v-for="it in TABBAR" :key="it.tab" class="tabbar-item" :class="{active: tab===it.tab}" @click="goTab(it.tab)">
      <span class="ti-ico">{{it.ico}}</span><span class="ti-label">{{it.label}}</span>
    </button>
  </nav>
</div>

<!-- ═══════════ 成长周报浮层（Sprint 3） ═══════════ -->
<div class="quiz-overlay overlay-pop" v-if="weeklyOverlay.show" @click.self="weeklyOverlay.show=false">
  <div class="quiz-shell weekly-shell">
    <div class="quiz-top">
      <span class="qname">📮 上周成长周报</span>
      <button class="icon-btn" @click="weeklyOverlay.show=false" title="关闭">✕</button>
    </div>
    <div class="weekly-body">
      <div v-if="weeklyLoading" class="empty" style="padding:60px 20px"><div class="em">📮</div><h3>正在生成周报…</h3><p>AI 正在总结你的一周，通常 3-10 秒</p></div>
      <template v-else-if="weekly">
        <div class="share-target">
          <div class="weekly-head">
            <div class="wh-title">📮 成长周报</div>
            <div class="wh-sub">{{weekly.week_start}} ~ {{weekly.week_end}}</div>
          </div>
          <div class="weekly-hl">
            <div class="whl-item" v-for="(h,i) in weekly.highlights" :key="i">✨ {{h}}</div>
          </div>
          <div class="weekly-advice">
            <b>下周小建议</b>
            <p>{{weekly.advice}}</p>
          </div>
          <div class="weekly-stats">
            <div class="ws"><b>{{weekly.stats.attempts}}</b><span>完成练习</span></div>
            <div class="ws"><b>{{weekly.stats.avg_score}}%</b><span>平均正确率</span></div>
            <div class="ws"><b>{{weekly.stats.wrong_mastered}}</b><span>消灭错题</span></div>
            <div class="ws"><b>{{weekly.stats.new_words}}</b><span>新学单词</span></div>
            <div class="ws"><b>{{weekly.stats.full_days}}</b><span>全勤天数</span></div>
          </div>
          <div class="weekly-note" v-if="weekly.parent_note">
            <div class="wn-ico">💌</div>
            <div><b>家长的悄悄话</b><p>{{weekly.parent_note}}</p></div>
          </div>
          <div class="weekly-note empty" v-else>
            <div class="wn-ico">💌</div>
            <div><b>还没有家长寄语</b><p>家长可在「设置-家长管理」里给孩子写悄悄话</p></div>
          </div>
        </div>
        <div class="weekly-actions">
          <button class="btn btn-primary" @click="shareWeekly()">📤 生成分享图</button>
          <button class="btn btn-ghost" @click="weeklyOverlay.show=false">关闭</button>
        </div>
        <div class="share-result" v-if="shareImg">
          <img :src="shareImg" alt="周报分享图">
          <p>长按图片保存，或截图转发给家人 ✨</p>
        </div>
      </template>
    </div>
  </div>
</div>

<!-- ═══════════ 许愿弹窗（Sprint 3） ═══════════ -->
<div class="quiz-overlay overlay-pop" v-if="wishOverlay.show" @click.self="wishOverlay.show=false">
  <div class="quiz-shell wish-shell">
    <div class="quiz-top">
      <span class="qname">🌟 许一个心愿</span>
      <button class="icon-btn" @click="wishOverlay.show=false" title="关闭">✕</button>
    </div>
    <div class="wish-form">
      <label>心愿内容</label>
      <input v-model="wishOverlay.title" class="fill-input" maxlength="50" placeholder="例如：想要一套乐高 / 周末去吃冰淇淋">
      <label style="margin-top:12px">完成方式</label>
      <select v-model="wishOverlay.wish_type" class="fill-input" style="max-width:260px">
        <option value="task_count">累计完成指定数量的每日任务</option>
        <option value="optional_streak">连续N天每天完成指定数量可选任务</option>
      </select>
      <template v-if="wishOverlay.wish_type === 'task_count'">
        <label style="margin-top:12px">需要完成几个每日任务？</label>
        <select v-model="wishOverlay.target" class="fill-input" style="max-width:200px">
          <option v-for="n in [3,5,7,10,14,20,30]" :key="n" :value="n">{{n}} 个任务</option>
        </select>
        <div class="wish-tip">心愿会先请家长确认，确认后每完成 1 个每日任务进度 +1</div>
      </template>
      <template v-else>
        <label style="margin-top:12px">连续几天？</label>
        <select v-model="wishOverlay.target" class="fill-input" style="max-width:200px">
          <option v-for="n in [3,5,7,10,14,21,30]" :key="n" :value="n">{{n}} 天</option>
        </select>
        <label style="margin-top:12px">每天完成几个可选任务？</label>
        <select v-model="wishOverlay.daily_target" class="fill-input" style="max-width:200px">
          <option v-for="n in [1,2,3,4,5]" :key="n" :value="n">{{n}} 个可选任务</option>
        </select>
        <div class="wish-tip">连续N天每天完成M个可选任务即达标，中断则重新计数</div>
      </template>
      <label style="margin-top:12px">截止日期（选填）</label>
      <input v-model="wishOverlay.deadline" type="date" class="fill-input" style="max-width:200px">
      <div class="wish-tip">超过截止日期还未完成的心愿会自动过期；不填则不限期</div>
      <div class="detail-actions" style="margin-top:16px">
        <button class="btn btn-primary" @click="submitWish()">许下心愿 ✨</button>
        <button class="btn btn-ghost" @click="wishOverlay.show=false">取消</button>
      </div>
    </div>
  </div>
</div>

<!-- ═══════════ 任务设置弹窗 ═══════════ -->
<div class="quiz-overlay overlay-pop" v-if="taskDialog.show" @click.self="taskDialog.show=false">
  <div class="quiz-shell" style="max-width:520px;max-height:85vh;overflow-y:auto">
    <div class="quiz-top">
      <span class="qname">📋 任务设置</span>
      <button class="icon-btn" @click="taskDialog.show=false" title="关闭">✕</button>
    </div>
    <div style="padding:16px">
      <div style="font-size:12px;color:#888;margin-bottom:10px;line-height:1.5">数量 = 每天要完成的目标（如试卷张数 / 题目数 / 次数）；任务标题里的数字会随数量自动变化</div>
      <div style="font-weight:bold;margin-bottom:10px;color:#3a4a6b">强制任务（每科默认任务固定，可再添加多个）</div>
      <div v-for="d in taskDialog.defaults" :key="'def-'+d.code" style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <span style="min-width:36px;font-size:13px">{{d.subject}}</span>
        <span class="fill-input" style="flex:1;font-size:12px;display:flex;align-items:center;gap:6px">{{taskOptTitle(d.def, d.target)}}<i class="tag tag-gray" style="font-style:normal">默认</i></span>
        <input v-model.number="d.target" type="number" min="1" max="50" class="fill-input" style="width:56px;font-size:12px" placeholder="数量" title="每天要完成的数量">
      </div>
      <div v-for="(ex, idx) in taskDialog.extra" :key="'ex-'+idx" style="display:flex;align-items:center;gap:6px;margin-bottom:8px;flex-wrap:wrap">
        <select v-model="ex.subject" class="fill-input" style="width:68px;font-size:12px" @change="ex.code=''">
          <option value="math">数学</option>
          <option value="chi">语文</option>
          <option value="eng">英语</option>
        </select>
        <select v-model="ex.code" class="fill-input" style="flex:1;min-width:120px;font-size:12px">
          <option value="">-- 选择 --</option>
          <option v-for="t in taskDialog.subOpts[ex.subject]" :key="t.code" :value="t.code">{{t.title}}</option>
        </select>
        <input v-model.number="ex.target" type="number" min="1" max="50" class="fill-input" style="width:56px;font-size:12px" placeholder="数量" title="每天要完成的数量">
        <button class="btn btn-ghost btn-sm" @click="taskDialog.extra.splice(idx,1)" style="padding:2px 8px;font-size:12px">✕</button>
      </div>
      <button class="btn btn-ghost btn-sm" @click="taskDialog.extra.push({subject:'math',code:'',target:1})" style="margin-bottom:16px">+ 添加强制任务</button>
      <div style="font-weight:bold;margin-bottom:10px;color:#3a4a6b">可选任务（可添加多条）</div>
      <div v-for="(opt, idx) in taskDialog.optional" :key="idx" style="display:flex;align-items:center;gap:6px;margin-bottom:8px;flex-wrap:wrap">
        <select v-model="opt.subject" class="fill-input" style="width:68px;font-size:12px" @change="opt.code=''">
          <option value="math">数学</option>
          <option value="chi">语文</option>
          <option value="eng">英语</option>
        </select>
        <select v-model="opt.code" class="fill-input" style="flex:1;min-width:120px;font-size:12px">
          <option value="">-- 选择 --</option>
          <option v-for="t in taskDialog.subOpts[opt.subject]" :key="t.code" :value="t.code">{{t.title}}</option>
        </select>
        <input v-model.number="opt.target" type="number" min="1" max="50" class="fill-input" style="width:56px;font-size:12px" placeholder="数量" title="每天要完成的数量">
        <button class="btn btn-ghost btn-sm" @click="taskDialog.optional.splice(idx,1)" style="padding:2px 8px;font-size:12px">✕</button>
      </div>
      <button class="btn btn-ghost btn-sm" @click="taskDialog.optional.push({subject:'math',code:'',target:1})" style="margin-bottom:16px">+ 添加可选任务</button>
      <div style="font-weight:bold;margin:16px 0 10px;color:#3a4a6b">👪 家长自定义任务 <span class="more" style="font-weight:400">可添加多个，放入强制/可选，由家长确认完成</span></div>
      <div v-for="ct in parentCustomTasks" :key="'ct-'+ct.id" style="display:flex;align-items:center;gap:6px;margin-bottom:8px;flex-wrap:wrap">
        <span class="tag" :class="ct.subject==='数学' ? 'tag-orange' : (ct.subject==='语文' ? 'tag-green' : 'tag-blue')">{{ct.subject}}</span>
        <span class="fill-input" style="flex:1;min-width:120px;font-size:12px;display:flex;align-items:center;gap:6px">{{ct.title}}<i class="tag tag-gray" style="font-style:normal">{{ct.task_type==='mandatory'?'强制':'可选'}}</i></span>
        <button class="btn btn-ghost btn-sm" @click="deleteParentCustomTask(ct.id)" style="padding:2px 8px;font-size:12px">✕</button>
      </div>
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;flex-wrap:wrap">
        <input v-model="customTaskForm.title" class="fill-input" style="flex:1;min-width:120px;font-size:12px" placeholder="自定义任务标题（如：练字一页）">
        <select v-model="customTaskForm.subject" class="fill-input" style="width:68px;font-size:12px">
          <option value="数学">数学</option><option value="语文">语文</option><option value="英语">英语</option><option value="其他">其他</option>
        </select>
        <select v-model="customTaskForm.task_type" class="fill-input" style="width:72px;font-size:12px">
          <option value="mandatory">强制</option><option value="optional">可选</option>
        </select>
        <input v-model.number="customTaskForm.target" type="number" min="1" max="50" class="fill-input" style="width:52px;font-size:12px" title="每天完成数量">
        <button class="btn btn-ghost btn-sm" @click="addParentCustomTask()" style="padding:2px 8px;font-size:12px">+ 添加</button>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" @click="saveTaskDialog()">保存</button>
        <button class="btn btn-ghost" @click="taskDialog.show=false">取消</button>
      </div>
    </div>
  </div>
</div>

<!-- ═══════════ 60 秒挑战赛浮层（Sprint 4） ═══════════ -->
<div class="quiz-overlay overlay-pop" v-if="chalOverlay.show" @click.self="closeChal()">
  <div class="quiz-shell chal-shell">
    <div class="quiz-top">
      <span class="qname">⚡ 60 秒挑战赛</span>
      <button class="icon-btn" @click="closeChal()" title="关闭">✕</button>
    </div>
    <div class="chal-body">
      <div v-if="chalOverlay.stage==='pick'">
        <div class="chal-pick">
          <button class="btn btn-primary" @click="startChallenge('math')">🧮 口算快答</button>
          <button class="btn btn-primary" @click="startChallenge('word')">🔤 单词快答</button>
        </div>
        <p class="chal-rec">🏆 最佳纪录：口算 {{chalBest.math.best}} 题 · 单词 {{chalBest.word.best}} 题<br><span>60 秒内答对越多越好，全对连击有彩蛋 ✨</span></p>
      </div>
      <div v-else-if="chalOverlay.stage==='run'">
        <div class="chal-timer" :class="{low: chalOverlay.timeLeft<=10}">{{chalOverlay.timeLeft}}<small> 秒</small></div>
        <div class="chal-score">已答对 <b>{{chalOverlay.correct}}</b> 题 <span class="chal-combo" v-if="chalCombo>=3">🔥 连击 x{{chalCombo}}</span></div>
        <div class="chal-q">
          <h3>{{curChalQ.q}}</h3>
          <div v-if="chalOverlay.kind==='word'" class="chal-options">
            <button v-for="(o,oi) in curChalQ.options" :key="oi" class="btn btn-ghost" @click="chalAnswer(o)">{{o}}</button>
          </div>
          <div v-else class="chal-input-row">
            <input v-model="chalOverlay.input" class="fill-input" type="number" placeholder="输入答案，回车提交" @keyup.enter="chalAnswer()">
            <button class="btn btn-primary" @click="chalAnswer()">确定</button>
          </div>
        </div>
      </div>
      <div v-else>
        <div class="chal-result">
          <div class="em">{{chalOverlay.correct>=15?'🏆':(chalOverlay.correct>=8?'🎉':'💪')}}</div>
          <h3>60 秒答对 {{chalOverlay.correct}} / {{chalOverlay.total}} 题！</h3>
          <p>本场正确率 <b>{{ chalOverlay.total ? Math.round(chalOverlay.correct/chalOverlay.total*100) : 0 }}%</b>
            <span v-if="chalOverlay.total && chalOverlay.correct*5 >= chalOverlay.total*4">✅ 已达 80%，计入每日挑战任务</span>
            <span v-else>⚠️ 需 ≥80% 才算完成每日挑战任务</span>
          </p>
          <p v-if="chalOverlay.newBest">🎊 刷新个人纪录，太厉害啦！</p>
          <p v-else>最佳纪录 {{chalBest[chalOverlay.kind].best}} 题，再练练超越它</p>
        </div>
        <div class="detail-actions">
          <button class="btn btn-primary" @click="startChallenge(chalOverlay.kind)">再来一局</button>
          <button class="btn btn-ghost" @click="closeChal()">关闭</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ═══════════ 学期目标浮层（Sprint 4） ═══════════ -->
<div class="quiz-overlay overlay-pop" v-if="goalOverlay.show" @click.self="goalOverlay.show=false">
  <div class="quiz-shell goal-shell">
    <div class="quiz-top">
      <span class="qname">🎯 学期目标</span>
      <button class="icon-btn" @click="goalOverlay.show=false" title="关闭">✕</button>
    </div>
    <div class="goal-body">
      <div class="goal-list" v-if="goals.length">
        <div class="goal-item" v-for="g in goals" :key="g.id">
          <div class="g-head"><b>{{g.title}}</b><span class="tag" :class="g.achieved ? 'tag-green' : 'tag-blue'">{{g.achieved ? '已达成 🎉' : g.current + ' / ' + g.target}}</span></div>
          <div class="progress" style="margin:8px 0"><i :style="{width: g.pct+'%'}"></i></div>
          <div class="g-foot">
            <span v-if="g.deadline">⏳ 还剩 {{g.days_left}} 天（{{g.deadline}} 截止）</span>
            <span v-else>长期目标 · 持续进步中</span>
            <span v-if="g.daily_step && !g.achieved" class="tag tag-blue">每日小步 ≈ {{g.daily_step}}</span>
            <span v-if="g.achieved && g.status==='active'"><button class="btn btn-success btn-sm" @click="doneGoal(g)">标记达成 🏆</button></span>
            <button class="btn btn-ghost btn-sm" @click="archiveGoal(g)">移除</button>
          </div>
        </div>
      </div>
      <p v-else class="pc-empty">还没有目标，立一个吧 👇（最多同时 2 个）</p>
      <div class="goal-form">
        <label>立下新目标</label>
        <div class="pc-row">
          <select v-model="goalOverlay.kind" class="fill-input" style="max-width:120px">
            <option value="score">分数</option><option value="wrong">消灭错题</option><option value="recite">背诵</option>
          </select>
          <input v-if="goalOverlay.kind==='score'" v-model="goalOverlay.subject" class="fill-input" maxlength="4" placeholder="学科，如：数学">
          <input v-model.number="goalOverlay.target" class="fill-input" type="number" placeholder="目标值">
          <input v-model="goalOverlay.deadline" class="fill-input" type="date">
        </div>
        <div class="detail-actions" style="margin-top:12px">
          <button class="btn btn-primary" @click="submitGoal()">立下目标 🎯</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ═══════════ 小老师浮层（Sprint 4） ═══════════ -->
<div class="quiz-overlay overlay-pop" v-if="teachOverlay.show" @click.self="closeTeach()">
  <div class="quiz-shell teach-shell">
    <div class="quiz-top">
      <span class="qname">🎓 小老师课堂 <em v-if="teachOverlay.cards.length>1" class="ts-prog">{{teachOverlay.idx+1}} / {{teachOverlay.cards.length}}</em></span>
      <button class="icon-btn" @click="closeTeach()" title="关闭">✕</button>
    </div>
    <div class="teach-body">
      <div class="teach-step" v-if="teachOverlay.step===1">
        <div class="ts-tag">第 1 步 · 你来讲</div>
        <h3 class="ts-q">{{teachOverlay.card.question}}</h3>
        <details class="ts-answer"><summary>🔍 参考答案</summary><p>{{teachOverlay.card.answer}}</p></details>
        <p class="ts-hint">把这道题的思路讲给家长听，讲明白了再出题考考 TA 👇</p>
        <div class="detail-actions"><button class="btn btn-primary" @click="teachOverlay.step=2">讲好啦，考考家长 →</button></div>
      </div>
      <div class="teach-step" v-else-if="teachOverlay.step===2">
        <div class="ts-tag">第 2 步 · 家长作答</div>
        <h3 class="ts-q">{{teachOverlay.card.question}}</h3>
        <input v-model="teachOverlay.answerText" class="fill-input" placeholder="家长把答案写在这里" style="margin-top:14px">
        <div class="detail-actions" style="margin-top:14px"><button class="btn btn-primary" @click="submitTeachAnswer()">提交答案</button></div>
      </div>
      <div class="teach-step" v-else-if="teachOverlay.step===3">
        <div class="ts-tag">第 3 步 · 你来批改</div>
        <h3 class="ts-q">{{teachOverlay.card.question}}</h3>
        <div class="ts-pair">
          <div class="ts-ans-box"><span>家长的答案</span><b>{{teachOverlay.card.answer_text || '（未填写）'}}</b></div>
          <div class="ts-ans-box right"><span>正确答案</span><b>{{teachOverlay.card.answer}}</b></div>
        </div>
        <div class="detail-actions" style="margin-top:14px">
          <button class="btn btn-success" @click="gradeTeach(true)">✅ 讲对了</button>
          <button class="btn btn-danger" @click="gradeTeach(false)">❌ 没讲对</button>
        </div>
      </div>
      <div class="teach-step" v-else>
        <div class="em">🎉</div>
        <h3>{{teachOverlay.result}}</h3>
        <p class="ts-hint">{{teachOverlay.hint}}</p>
        <div class="detail-actions">
          <button v-if="teachOverlay.idx < teachOverlay.cards.length-1" class="btn btn-primary" @click="nextTeach()">讲下一道 →</button>
          <button v-else class="btn btn-primary" @click="closeTeach()">全部讲完，完成 🎓</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ═══════════ 7 天复习验证浮层（Sprint 4） ═══════════ -->
<div class="quiz-overlay overlay-pop" v-if="recheckOverlay.show" @click.self="recheckOverlay.show=false">
  <div class="quiz-shell teach-shell">
    <div class="quiz-top">
      <span class="qname">🔁 复习验证</span>
      <button class="icon-btn" @click="recheckOverlay.show=false" title="关闭">✕</button>
    </div>
    <div class="teach-body">
      <p class="ts-hint">7 天前讲给家长的题，现在还记得怎么做吗？</p>
      <h3 class="ts-q">{{recheckOverlay.card.question}}</h3>
      <input v-model="recheckOverlay.answerText" class="fill-input" placeholder="写出你的答案" style="margin-top:14px">
      <div class="detail-actions" style="margin-top:14px"><button class="btn btn-primary" @click="submitRecheck()">提交</button></div>
    </div>
  </div>
</div>

<!-- ═══════════ 全屏答题（通用状态机） ═══════════ -->
<div class="quiz-overlay" v-if="quiz.active" :class="{turbo}">
  <div class="float-fx" v-if="floatFx.show" :class="{no: !floatFx.ok}">{{floatFx.text}}</div>
  <template v-if="!quiz.done">
    <div class="quiz-shell">
      <div class="quiz-top">
        <span class="qname">{{quiz.title}}</span>
        <div class="progress"><i :style="{width: quizPct+'%'}"></i></div>
        <span class="combo-badge" v-if="combo>=2">🔥 {{combo}}</span>
        <span class="qcount">{{quiz.i+1}} / {{quiz.items.length}}</span>
        <button class="icon-btn" @click="closeQuiz()" title="退出">✕</button>
      </div>
      <div class="quiz-card" style="max-width:760px">
        <template v-if="quiz.items.length">
          <div class="quiz-q">{{quiz.items[quiz.i].question}}</div>
          <div class="quiz-sub" v-if="quiz.items[quiz.i].sub">{{quiz.items[quiz.i].sub}}</div>
          <div v-if="quiz.items[quiz.i].options && quiz.items[quiz.i].options.length">
            <button v-for="(o,oi) in quiz.items[quiz.i].options" :key="oi" class="option" :class="qOptClass(quiz.items[quiz.i], oi)" @click="pickOption(oi)" :disabled="quiz.items[quiz.i].answered">
              <span class="o-let">{{'ABCDEFGH'[oi]}}</span>{{o}}
            </button>
          </div>
          <div v-else class="fill-wrap">
            <input v-model="quiz.fillText" class="fill-input" :placeholder="quiz.items[quiz.i].placeholder||'请输入答案'" @keyup.enter="submitFill()" :disabled="quiz.items[quiz.i].answered" style="margin-top:0">
            <button class="btn btn-primary" @click="submitFill()" :disabled="quiz.items[quiz.i].answered">提交</button>
          </div>
          <div class="feedback" :class="{on: quiz.items[quiz.i].answered, ok: quiz.items[quiz.i].answered && quiz.items[quiz.i].correct, no: quiz.items[quiz.i].answered && !quiz.items[quiz.i].correct}">
            <template v-if="quiz.items[quiz.i].answered">
              <h4 v-if="quiz.items[quiz.i].correct">✔ 回答正确！<span v-if="combo>=2" class="fb-combo">🔥 连击 x{{combo}}</span></h4>
              <h4 v-else>差一点！没关系</h4>
              <p v-if="!quiz.items[quiz.i].correct">正确答案：<b style="color:var(--success)">{{quiz.items[quiz.i].answer}}</b></p>
              <p v-if="!quiz.items[quiz.i].correct" class="fb-gentle">每一次错题都是进步的机会，订正一次就多掌握一个知识点 ✨</p>
              <div class="cause-pills" v-if="!quiz.items[quiz.i].correct && quiz.items[quiz.i].qid && !quiz.items[quiz.i].cause">
                <span class="pill-label">这次是哪里没弄明白？</span>
                <button v-for="(c,ci) in causeOptions" :key="ci" class="cause-pill" @click="pickCause(c.code)">{{c.label}}</button>
              </div>
              <!-- 孩子申诉：判错 → 「我做对了」→ 家长二次确认 -->
              <div class="appeal-row" v-if="!quiz.items[quiz.i].correct && quiz.source && (quiz.source.mode==='exam' || quiz.source.mode==='retry')">
                <button v-if="!quiz.items[quiz.i].appealed" class="btn btn-ghost btn-sm" @click="appealThis()" title="觉得这道题批错了？点这里，家长会来确认">🙋 我做对了</button>
                <span v-else class="fb-gentle">✋ 申诉已提交，等家长在「家长管理」里确认</span>
              </div>
              <p v-if="!quiz.items[quiz.i].correct && quiz.items[quiz.i].cause" class="fb-gentle">已记录错因：{{causeLabel(quiz.items[quiz.i].cause)}} · 进步 +1 ✨</p>
              <p v-if="quiz.items[quiz.i].explanation">📖 {{quiz.items[quiz.i].explanation}}</p>
            </template>
          </div>
          <!-- AI 讲解（内联展示在题目下方，不弹窗） -->
          <div class="inline-explain" v-if="quiz.items[quiz.i].explaining || quiz.items[quiz.i].aiText || quiz.items[quiz.i].aiError">
            <div v-if="quiz.items[quiz.i].explaining" class="explain-loading">
              <span class="explain-spin"></span>🤖 老师正在讲解…（通常 3-10 秒，请稍等）
            </div>
            <template v-else-if="quiz.items[quiz.i].aiText">
              <div class="explain-seg" v-for="(s,i) in explainSectionsOf(quiz.items[quiz.i].aiText)" :key="i" :class="{first: i===0}">
                <div class="seg-title" v-if="s.title">【{{s.title}}】</div>
                <div class="seg-body">
                  <p v-for="(line,li) in s.body.split('\n').filter(x=>x.trim())" :key="li">{{line}}</p>
                </div>
              </div>
              <p class="explain-deg" v-if="quiz.items[quiz.i].aiDegraded">（离线讲解版 · 已尽力帮到你了）</p>
              <div class="explain-actions" style="justify-content:flex-start" v-if="curWrong && curWrong.question_id===quiz.items[quiz.i].qid">
                <button class="btn btn-primary btn-sm" @click="markWrongMastered(curWrong)" title="先做 3 道同类型题，全部答对才标记已掌握">✅ 检测掌握</button>
                <button class="btn btn-ghost btn-sm" @click="startWrongRetry(curWrong)">🎯 变式重练</button>
              </div>
            </template>
            <p v-else class="explain-err">😵 {{quiz.items[quiz.i].aiError}} <button class="btn btn-ghost btn-sm" @click="askQuizExplain()">重试</button></p>
          </div>
          <div class="quiz-actions">
            <button class="btn btn-ghost" v-if="quiz.items[quiz.i].qid" :disabled="quiz.items[quiz.i].explaining" @click="askQuizExplain()" title="标记为做错并生成 AI 讲解">{{quiz.items[quiz.i].explaining ? '⏳ 讲解中…' : '🤖 AI 讲解'}}</button>
            <button class="btn btn-ghost" @click="closeQuiz()">保存退出</button>
            <button class="btn btn-primary" v-if="quiz.items[quiz.i].answered" :disabled="quiz.items[quiz.i].explaining" @click="quizNext()">{{quiz.i===quiz.items.length-1 ? '查看结果 →' : '下一题 →'}}</button>
          </div>
        </template>
        <div v-else class="empty">⏳ 题目加载中…</div>
      </div>
    </div>
  </template>
  <div v-else class="done-wrap">
    <div class="stars-row">
      <span v-for="n in 5" :key="n" class="star" :class="{on: n<=starCount}">★</span>
    </div>
    <div v-if="newStarRecord" class="new-record">🏆 新纪录！首次五星</div>
    <div class="done-illus" :class="{no: quiz.score<60}">{{quiz.score>=90?'🏆':quiz.score>=60?'🎉':'💪'}}</div>
    <h2>{{quiz.score>=90?'太棒了！':quiz.score>=60?'继续加油！':'别灰心，再来一次'}}</h2>
    <p class="sub">{{quiz.title}} · 完成<template v-if="maxCombo>=2"> · 最佳连击 🔥 x{{maxCombo}}</template></p>
    <div class="done-grid">
      <div class="done-cell"><b>{{quiz.score}}分</b><span>得分</span></div>
      <div class="done-cell"><b>{{quiz.correct}}/{{quiz.items.length}}</b><span>答对题数</span></div>
      <div class="done-cell"><b>{{quiz.wrongCount}}</b><span>错题（已入错题本）</span></div>
    </div>
    <div class="chest-box" :class="{locked: quiz.score<60}">
      <span class="chest">🎁</span>
      <p>{{quiz.score>=60 ? '宝箱开启：' + chestReward : '得分 60 分以上可开启宝箱，明天再来挑战！'}}</p>
    </div>
    <p class="sub next-preview">下一关预告：明天的 3 个新任务等你解锁 🔥</p>
    <div class="done-note" v-if="quiz.wrongCount>0">📝 {{quiz.wrongCount}} 道错题已自动加入错题本，可在「错题本」中复盘错因并变式重练</div>
    <div class="done-actions">
      <button class="btn btn-ghost" @click="quizAgain()">再来一组</button>
      <button class="btn btn-primary" @click="closeQuizGo('wrong')">去错题本复盘</button>
      <button class="btn btn-ghost" @click="closeQuizGo('home')">返回首页</button>
    </div>
  </div>
</div>

<!-- ═══════════ 单词学习浮层 ═══════════ -->
<div class="quiz-overlay" v-if="wordSession.active && (wordSession.phase==='card' || wordSession.done) && !quiz.active">
  <template v-if="!wordSession.done && wordSession.phase==='card'">
    <div class="quiz-shell">
      <div class="quiz-top">
        <span class="qname">{{wordSession.mode==='new'?'📖 学习新词':'🔁 复习单词'}}</span>
        <div class="progress"><i :style="{width: wordPct+'%'}"></i></div>
        <span class="qcount">{{wordSession.i+1}} / {{wordSession.words.length}}</span>
        <button class="icon-btn" @click="wordSession.active=false" title="退出">✕</button>
      </div>
      <div class="word-card" v-if="wordSession.words.length">
        <div class="word-big" @click="wordSpeak" style="cursor:pointer" title="点击朗读">🔊 {{curWord.word}}</div>
        <div class="word-phonetic">{{curWord.phonetic || ''}}</div>
        <transition name="fade">
          <div v-if="wordSession.revealed || wordSession.mode!=='new'" class="word-meaning-block">
            <div class="word-meaning">{{curWord.pos}} {{curWord.meaning}}</div>
            <div class="word-unit">📚 {{curWord.unit || '未分单元'}}</div>
          </div>
        </transition>
        <div class="word-btns">
          <button class="btn btn-ghost" @click="wordSpeak">🔊 听</button>
          <button v-if="wordSession.mode==='new' && !wordSession.revealed" class="btn btn-ghost btn-lg" @click="wordSession.revealed=true">👁 看释义</button>
          <button class="btn btn-primary btn-lg" @click="wordTest()">✍️ 测一测 →</button>
        </div>
      </div>
      <p class="dictate-hint">💡 听清读音、看懂意思，点「测一测」做几道小题，做对就过关！</p>
    </div>
  </template>
  <div v-else-if="wordSession.done" class="done-wrap">
    <div class="done-illus">🎉</div>
    <h2>本轮单词背诵完成！</h2>
    <p class="sub">共 {{wordSession.words.length}} 个单词 · 综合测试全部背对 ✅</p>
    <div class="done-actions"><button class="btn btn-primary" @click="wordSession.active=false; refreshAll()">完成</button></div>
  </div>
</div>

<!-- ═══════════ 古诗文背诵浮层 ═══════════ -->
<div class="quiz-overlay" v-if="textSession.active && (textSession.phase==='card' || textSession.done) && !quiz.active">
  <template v-if="!textSession.done && textSession.phase==='card'">
    <div class="quiz-shell">
      <div class="quiz-top">
        <span class="qname">{{textSession.mode==='new'?'📜 背诵新篇':'🔁 复习背诵'}}</span>
        <div class="progress"><i :style="{width: textPct+'%'}"></i></div>
        <span class="qcount">{{textSession.i+1}} / {{textSession.texts.length}}</span>
        <button class="icon-btn" @click="textSession.active=false" title="退出">✕</button>
      </div>
      <div class="word-card text-card" v-if="textSession.texts.length">
        <div class="text-title">《{{curText.title}}》<span>{{curText.author}} · {{curText.dynasty}}</span></div>
        <div class="text-lines" @click="textSpeak" style="cursor:pointer" title="点击朗读">
          <div class="text-line" v-for="(ln, idx) in textLines" :key="idx">
            <div class="text-py" v-if="curText.pinyin && curText.pinyin[idx]">{{curText.pinyin[idx]}}</div>
            <div class="text-txt">🔊 {{ln}}</div>
          </div>
        </div>
        <div class="word-btns">
          <button class="btn btn-ghost" @click="textSpeak">🔊 跟读</button>
          <button class="btn btn-primary btn-lg" @click="textTest()">✍️ 测一测 →</button>
        </div>
      </div>
      <p class="dictate-hint">💡 跟着拼音读几遍，点「测一测」填一填，做对就过关！</p>
    </div>
  </template>
  <div v-else-if="textSession.done" class="done-wrap">
    <div class="done-illus">🏮</div>
    <h2>本轮古诗文背诵完成！</h2>
    <p class="sub">共 {{textSession.texts.length}} 篇 · 综合测试全部背对 ✅</p>
    <div class="done-actions"><button class="btn btn-primary" @click="textSession.active=false; refreshAll()">完成</button></div>
  </div>
</div>

<!-- ═══════════ 篇目详情弹窗 ═══════════ -->
<div class="modal-mask" :class="{on: textDetail.show}">
  <div class="modal">
    <div class="modal-head"><h2>《{{textDetail.title}}》</h2></div>
    <div class="modal-body">
      <p class="text-detail-meta">{{textDetail.author}} · {{textDetail.dynasty}} · {{textDetail.grade}}年级 · {{textDetail.text_type==='prose'?'古文':'古诗'}}</p>
      <div class="text-detail-content">{{textDetail.content}}</div>
    </div>
    <div class="modal-foot">
      <button class="btn btn-ghost" @click="textDetail.show=false">关闭</button>
      <button class="btn btn-primary" @click="startTextQuiz(textDetail)">随机练习 →</button>
    </div>
  </div>
</div>

<!-- ═══════════ 做题记录详情弹窗 ═══════════ -->
<div class="modal-mask" :class="{on: attemptDetail.show}">
  <div class="modal modal-wide">
    <div class="modal-head"><h2>📄 {{attemptDetail.title}}</h2><span class="tag" :class="attemptDetail.score>=80?'tag-green':attemptDetail.score>=60?'tag-orange':'tag-red'">{{attemptDetail.score}}分 · 对 {{attemptDetail.correct}} / 共 {{attemptDetail.total}} 题</span></div>
    <div class="modal-body">
      <div v-if="!attemptDetail.items.length" class="empty" style="padding:20px"><div class="em">⏳</div><h3>加载中…</h3></div>
      <div v-else class="attempt-detail-list">
        <div v-for="(it, idx) in attemptDetail.items" :key="idx" class="ad-item" :class="{wrong: !it.is_correct}">
          <div class="ad-head">
            <span class="ad-flag">{{it.is_correct ? '✓' : '✗'}}</span>
            <span class="ad-q">{{idx+1}}. {{it.question}}</span>
            <span class="tag" :class="it.is_correct?'tag-green':'tag-red'">{{it.type_name}}</span>
          </div>
          <div class="ad-answers">
            <span class="ad-ua" :class="{bad: !it.is_correct}">你的答案：{{it.user_answer || '（未作答）'}}</span>
            <span class="ad-ca" v-if="!it.is_correct">正确答案：{{it.correct_answer}}</span>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn btn-ghost" @click="attemptDetail.show=false">关闭</button>
    </div>
  </div>
</div>

<div class="modal-mask" :class="{on: taskSubmitTip.show}">
  <div class="modal">
    <div class="modal-head"><h2>🎉 任务完成已提交</h2></div>
    <div class="modal-body">
      <p>请把这次完成的截图，用微信或其他方式发给家长，<br>提醒家长在首页「完成确认」里确认你就完成啦～</p>
    </div>
    <div class="modal-foot">
      <button class="btn btn-primary" @click="taskSubmitTip.show=false">我知道了</button>
    </div>
  </div>
</div>

<div class="toast" :class="{on: toast.show}">{{toast.msg}}</div>

</div>
</template>

<script>
import appOptions from './logic/appOptions.js'
import { NAV_GROUPS, TABBAR, ALL_TABS } from './nav.js'
import { useWalletStore } from './stores/wallet.js'

// 根组件：承载登录、App Shell（侧边栏/顶栏）、各业务页面切换与全部业务逻辑的「壳」。
// 绝大多数数据/方法来自 logic/appOptions.js 这个 mixin（通过展开合并），本文件只做三件事：
//   1) 合并 appOptions 的 data/methods/mounted；2) 用 vue-router 做 URL ↔ tab 同步；
//   3) 进入「钱包」tab 时拉取钱包数据。模板已用 ══ 注释分区，关键区块：登录屏、
//      首次年级弹窗、强制/可选任务（含补签 makeup_pending）、复习队列（艾宾浩斯）、
//      挑战赛浮层（答对≥80% 计入每日挑战，见模板 chalOverlay.correct*5>=total*4）。
export default {
  ...appOptions,
  data() {
    // 合并 mixin 的 data，并注入侧边栏/底部导航配置供模板渲染
    return { ...appOptions.data.call(this), NAV_GROUPS, TABBAR }
  },
  setup() {
    // 钱包 store 仅在 App 级创建一次，供钱包页与各任务卡共用
    const wallet = useWalletStore()
    return { wallet }
  },
  methods: {
    ...appOptions.methods,
    // 切换 tab：先复用 mixin 的逻辑（更新 this.tab、记录、刷新数据），
    // 进入钱包则拉取钱包；最后把当前 tab 同步进 URL，支持深链/刷新保持页面
    goTab(t) {
      appOptions.methods.goTab.call(this, t)
      if (t === 'wallet') this.wallet.load(this.user, this.makeupCards)
      this._syncRoute(t)
    },
    // URL ↔ tab 同步（vue-router 深链/刷新保持当前页）
    _syncRoute(t) {
      if (this.$route && this.$route.params.tab !== t) {
        this.$router.replace('/' + t).catch(() => {})
      }
    },
    // 今日提醒条：滚动到任务卡区域
    scrollToTasks() {
      this.$nextTick(() => {
        const el = document.querySelector('.task-card') || document.querySelector('.section-title')
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
    },
  },
  watch: {
    // 浏览器前进/后退或深链进入时，URL 中的 tab 变化要同步到界面（含钱包拉取）
    '$route.params.tab'(t) {
      if (t && ALL_TABS.includes(t) && t !== this.tab && this.user) {
        appOptions.methods.goTab.call(this, t)
        if (t === 'wallet') this.wallet.load(this.user, this.makeupCards)
      }
    },
  },
  mounted() {
    appOptions.mounted.call(this)
    // 首屏若 URL 已带合法 tab（如刷新后），直接定位到该 tab
    const t = this.$route && this.$route.params.tab
    if (t && ALL_TABS.includes(t) && t !== this.tab) {
      appOptions.methods.goTab.call(this, t)
      if (t === 'wallet') this.wallet.load(this.user, this.makeupCards)
    }
  },
}
</script>
