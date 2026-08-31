<template>
<div class="fade-enter">
        <div class="hero">
          <div style="flex:1">
            <h1>{{appCtx.greeting}}，{{appCtx.userName}} 👋 <span class="title-badge" v-if="appCtx.titleInfo" :title="appCtx.titleInfo.next ? '再做 '+appCtx.titleInfo.next.need+' 项学习升级' : '已是最高称号'">{{appCtx.titleInfo.icon}} {{appCtx.titleInfo.name}}</span></h1>
            <p v-if="appCtx.taskRemain>0">今天还差 <b style="color:#fff">{{appCtx.taskRemain}}</b> 项任务完成全勤<template v-if="appCtx.dailyTaskStats.streak_days"> · 🔥 已连续 {{appCtx.dailyTaskStats.streak_days}} 天</template>，点击任务卡即可开始</p>
            <p v-else>🎉 三科任务全部完成，今天全勤！<template v-if="appCtx.dailyTaskStats.streak_days">已连续 {{appCtx.dailyTaskStats.streak_days}} 天 🔥</template></p>
          </div>
          <div class="hero-right">
            <div class="hero-ring">
              <svg width="74" height="74" viewBox="0 0 74 74">
                <circle cx="37" cy="37" r="32" fill="none" stroke="rgba(255,255,255,.25)" stroke-width="7"/>
                <circle cx="37" cy="37" r="32" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-dasharray="201" stroke-dashoffset="201" :style="{strokeDashoffset: 201-(201*appCtx.taskPct/100)}"/>
              </svg>
              <div class="num">{{appCtx.dailyTaskStats.done_count}}/{{appCtx.dailyTaskStats.total || 3}}<small>今日任务</small></div>
            </div>
            <div class="hero-stats">
              <div><b>{{appCtx.streakDays}}<small style="font-size:11px">天</small></b><span>连续学习</span></div>
              <div><b>{{appCtx.avgScore}}%</b><span>平均正确率</span></div>
              <div><b>{{appCtx.masteredTotal}}</b><span>已掌握错题</span></div>
            </div>
          </div>
        </div>

        <!-- 首页子导航：今日 / 奖励激励 / 家园互动 -->
        <div class="home-subnav">
          <button class="hs-btn" :class="{active: appCtx.homeSub==='today'}" @click="appCtx.homeSub='today'">📅 今日</button>
          <button class="hs-btn" :class="{active: appCtx.homeSub==='reward'}" @click="appCtx.homeSub='reward'">🎁 奖励激励</button>
          <button class="hs-btn" :class="{active: appCtx.homeSub==='family'}" @click="appCtx.homeSub='family'">🏡 家园互动</button>
        </div>

        <template v-if="appCtx.homeSub==='today'">
        <!-- 今日提醒条（P5：聚合待办提醒，点击直达） -->
        <div class="today-remind" v-if="appCtx.taskRemain>0 || appCtx.wrongBadge>0">
          <span class="tr-ico"><app-icon name="focus" :size="18"></app-icon></span>
          <button v-if="appCtx.taskRemain>0" class="tr-item" @click="appCtx.scrollToTasks">📋 还差 <b>{{appCtx.taskRemain}}</b> 项任务全勤</button>
          <button v-if="appCtx.wrongBadge>0" class="tr-item tr-warn" @click="appCtx.goTab('wrong')">📕 <b>{{appCtx.wrongBadge}}</b> 道错题待消灭</button>
        </div>

        <!-- 绑定引导：未绑定邮箱时提醒 -->
        <div class="bind-guide" v-if="appCtx.authInfo && !appCtx.authInfo.email">
          <span>🔒 绑定邮箱，可跨设备登录与找回密码</span>
          <button class="bg-btn" @click="appCtx.goTab('settings')">去绑定 →</button>
        </div>

        <!-- 天气卡片（P3：实时天气 + 3 日预报，4h 缓存） -->
        <div class="card weather-card" v-if="appCtx.weather">
          <div class="card-head"><b>🌤️ {{appCtx.weather.city}}</b><span class="more">{{appCtx.weather.cached ? '缓存数据' : '实时数据'}} · 更新于 {{(appCtx.weather.update_time || '').slice(11, 16)}}</span></div>
          <div v-if="!appCtx.weather.now" class="wx-empty">{{appCtx.weather.error || '天气数据暂不可用'}}</div>
          <div v-else>
            <div class="wx-now">
              <div class="wx-temp">{{appCtx.weather.now.temp}}°</div>
              <div class="wx-desc"><b>{{appCtx.weather.now.text}}</b><span>体感 {{appCtx.weather.now.feelsLike}}° · 湿度 {{appCtx.weather.now.humidity}}% · {{appCtx.weather.now.windDir}}{{appCtx.weather.now.windScale}}级</span></div>
            </div>
            <div class="wx-forecast">
              <div class="wx-day" v-for="d in appCtx.weather.forecast" :key="d.fxDate">
                <span class="wd-date">{{appCtx.wxDayLabel(d.fxDate)}}</span>
                <span class="wd-text">{{d.textDay}}</span>
                <span class="wd-temp">{{d.tempMin}}° ~ {{d.tempMax}}°</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 我的称号（Sprint 4） -->
        <div class="card title-card" v-if="appCtx.titleInfo">
          <div class="card-head"><b>{{appCtx.titleInfo.icon}} 我的称号：{{appCtx.titleInfo.name}}</b><span class="more" v-if="appCtx.titleInfo.next">再完成 {{appCtx.titleInfo.next.need}} 项学习 → 升级「{{appCtx.titleInfo.next.icon}} {{appCtx.titleInfo.next.name}}」</span><span class="more" v-else>👑 已是最高称号！</span></div>
          <div class="badge-row">
            <div class="badge-item" v-for="b in appCtx.titleBadges" :key="b.code" :class="{unlocked: b.unlocked}" :title="b.name">
              <span class="bi">{{b.unlocked ? b.icon : '🔒'}}</span>
              <div><b>{{b.name}}</b><i>{{b.unlocked ? '已解锁' : b.progress + ' / ' + b.target}}</i></div>
            </div>
          </div>
        </div>

        <!-- 家长提醒条（未读留言 / 心愿待办） -->
        <div class="notice-bar" v-if="appCtx.notices && (appCtx.notices.unread_messages>0 || appCtx.notices.pending_wishes>0 || appCtx.notices.pending_redeem>0)">
          <span v-if="appCtx.notices.unread_messages>0" class="nb-item nb-msg" @click="appCtx.openMessages()">✉️ 家长留言 {{appCtx.notices.unread_messages}} 条未读</span>
          <span v-if="appCtx.notices.pending_wishes>0" class="nb-item">🌟 心愿在等家长确认</span>
          <span v-if="appCtx.notices.pending_redeem>0" class="nb-item nb-hot">🎉 心愿达标啦，快找家长兑现！</span>
        </div>

        <!-- 强制任务：三科各1条，完成即全勤 -->
        <div class="section-title">✅ 每日强制任务 <span class="more">三科全完成 = 今日全勤 · 🔥连续 {{appCtx.dailyTaskStats.streak_days}} 天</span></div>
        <div class="grid-3" v-if="appCtx.dailyTasks">
          <div class="card dtask" :class="{done: t.status==='done'}" v-for="t in appCtx.mandatoryTasks" :key="'m-'+t.subject+'-'+t.task_code">
            <div class="dtask-head">
              <span class="tag" :class="t.subject==='数学' ? 'tag-orange' : (t.subject==='语文' ? 'tag-green' : 'tag-blue')">{{t.subject}}</span>
              <span class="dtask-state" :class="{ok: t.status==='done'}">{{t.status==='done' ? '✅ 已完成' : t.progress + ' / ' + t.target}}</span>
            </div>
            <div class="dtask-ico">{{t.ico}}</div>
            <b class="dtask-title">{{t.title}}</b>
            <div class="dtask-desc">{{t.desc}}</div>
            <div class="dtask-actions">
              <button v-if="t.status!=='done'" class="btn btn-primary btn-sm" @click="appCtx.gotoTaskCode(t)">去做 →</button>
              <button v-if="t.manual && t.status==='pending'" class="btn btn-primary btn-sm" @click="appCtx.childSubmitTask(t.id)">我完成了 ✓</button>
              <span v-else-if="t.manual && t.status==='pending_confirm'" class="tag tag-orange">已提交，待家长确认</span>
              <span v-else-if="t.status==='done'" class="tag tag-green">全勤 +1</span>
              <button v-if="t.status!=='done' && !t.makeup_pending && appCtx.makeupCards>0" class="btn btn-ghost btn-sm" style="margin-left:6px;font-size:11px" @click="appCtx.makeupCompleteTask(t.id)">🎫补签</button>
              <span v-else-if="t.makeup_pending" class="tag tag-orange" style="margin-left:6px;font-size:11px">🎫 待家长确认</span>
            </div>
            <div class="dtask-bar"><div class="dtask-bar-in" :style="{width: (t.target ? Math.min(100, t.progress / t.target * 100) : 0) + '%'}"></div></div>
          </div>
        </div>
        <div v-else class="card"><div class="empty"><div class="em">🎯</div><h3>加载今日任务中…</h3></div></div>

        <!-- 可选任务：系统每日生成3条，全完成获得补签卡 -->
        <div class="section-title" style="margin-top:20px">🎯 每日可选任务 <span class="more">系统每日自动分配 · 全部完成获 🎫补签卡×1</span>
          <span v-if="appCtx.makeupCards>0" style="margin-left:12px;font-size:12px;color:#8B7CF6;font-weight:600">🎫 补签卡 ×{{appCtx.makeupCards}}</span>
        </div>
        <div class="grid-3" v-if="appCtx.dailyTasks">
          <div class="card dtask" :class="{done: t.status==='done'}" v-for="(t,i) in appCtx.optionalTasks" :key="'o-'+i+'-'+t.task_code">
            <div class="dtask-head">
              <span class="tag" :class="t.subject==='数学' ? 'tag-orange' : (t.subject==='语文' ? 'tag-green' : 'tag-blue')">{{t.subject}}</span>
              <span class="dtask-state" :class="{ok: t.status==='done'}">{{t.status==='done' ? '✅ 已完成' : t.progress + ' / ' + t.target}}</span>
            </div>
            <div class="dtask-ico">{{t.ico}}</div>
            <b class="dtask-title">{{t.title}}</b>
            <div class="dtask-desc">{{t.desc}}</div>
            <div class="dtask-actions">
              <button v-if="t.status!=='done'" class="btn btn-primary btn-sm" @click="appCtx.gotoTaskCode(t)">去做 →</button>
              <button v-if="t.manual && t.status==='pending'" class="btn btn-primary btn-sm" @click="appCtx.childSubmitTask(t.id)">我完成了 ✓</button>
              <span v-else-if="t.manual && t.status==='pending_confirm'" class="tag tag-orange">已提交，待家长确认</span>
              <span v-else-if="t.status==='done'" class="tag tag-green">已完成</span>
              <button v-if="t.status!=='done' && !t.makeup_pending && appCtx.makeupCards>0" class="btn btn-ghost btn-sm" style="margin-left:6px;font-size:11px" @click="appCtx.makeupCompleteTask(t.id)">🎫补签</button>
              <span v-else-if="t.makeup_pending" class="tag tag-orange" style="margin-left:6px;font-size:11px">🎫 待家长确认</span>
            </div>
            <div class="dtask-bar"><div class="dtask-bar-in" :style="{width: (t.target ? Math.min(100, t.progress / t.target * 100) : 0) + '%'}"></div></div>
          </div>
        </div>

        <!-- 今日任务包（点击卡片直接开始，无确认弹窗） -->
        <div class="section-title">🗂️ 今日任务包 <span class="more">点击卡片立即开始，按遗忘曲线自动安排</span></div>
        <div class="grid-3" v-if="appCtx.dashboard">
          <template v-for="t in appCtx.todayTasks" :key="t.key">
            <button class="card task-card" :class="{done: t.done}" @click="appCtx.startTask(t)">
              <div class="task-ico" :class="t.icoCls"><app-icon :name="t.ico" :size="22"></app-icon></div>
              <div class="task-info">
                <b>{{t.title}}</b>
                <div class="meta"><span>{{t.subject}}</span><span class="dot">·</span><span>{{t.detail}}</span></div>
                <div class="meta" v-if="t.tag"><span class="tag" :class="t.tagCls">{{t.tag}}</span></div>
              </div>
              <span class="btn" :class="t.done ? 'btn-ghost btn-sm' : 'btn-primary btn-sm'" @click.stop="appCtx.startTask(t)">{{t.done ? '已完成 ✓' : '开始'}}</span>
            </button>
          </template>
        </div>
        <div v-else class="card"><div class="empty"><div class="em">⏳</div><h3>加载今日任务中…</h3></div></div>

        <!-- 复习队列 -->
        <div class="section-title">🧭 复习队列 <span class="more">艾宾浩斯遗忘曲线 · 自动安排</span></div>
        <div class="timeline">
          <div class="tl-node today"><b>今天</b><span>{{appCtx.queueToday}} 项到期</span><span class="count">{{appCtx.queueTodayNames}}</span></div>
          <div class="tl-node"><b>明天</b><span>{{appCtx.queueTomorrow}} 项到期</span><span class="count">按曲线节奏自动安排</span></div>
          <div class="tl-node"><b>后天</b><span>{{appCtx.queueDayAfter}} 项到期</span><span class="count">单词 · 古诗文</span></div>
          <div class="tl-node"><b>3 天后</b><span>{{appCtx.queueLater}} 项到期</span><span class="count">坚持每天来复习</span></div>
        </div>
        <div class="card" style="margin-top:12px" v-if="appCtx.reviewQueue">
          <div v-for="it in appCtx.reviewQueue.items.slice(0,6)" :key="it.type+it.id" class="queue-item">
            <div class="qi-ico" :class="it.type==='vocab' ? 't-blue' : 't-green'"><app-icon :name="it.type==='vocab' ? 'abc' : 'scroll'" :size="20"></app-icon></div>
            <div class="qi-body"><b>{{it.title}}</b><span>{{it.subtitle}} · {{it.type==='vocab' ? '单词' : '古诗文'}}复习</span></div>
            <span class="tag" :class="it.overdue_days>0 ? 'tag-red' : 'tag-orange'" style="flex-shrink:0">{{it.overdue_days>0 ? '已逾期'+it.overdue_days+'天' : '今天到期'}}</span>
          </div>
          <div v-if="!appCtx.reviewQueue.items.length" class="empty" style="padding:24px"><div class="em">🌱</div><h3>今天没有到期复习</h3><p>记忆保鲜中，明天再来巩固</p></div>
        </div>

        <!-- 今日心情（Sprint 2） -->
        <div class="card mood-card" style="margin-top:14px" v-if="appCtx.moodTrend">
          <div class="card-head"><b>🌈 今日心情</b><span class="more">打个卡，爸爸妈妈会更懂你</span></div>
          <div class="mood-7">
            <div class="mood-day" v-for="d in appCtx.moodTrend.days" :key="d.date" :class="{today: d.date===appCtx.moodTodayStr, neg: d.negative}">
              <span class="md-week">{{d.weekday}}</span>
              <span class="md-face">{{d.mood ? appCtx.moodFace(d.mood) : '·'}}</span>
              <span class="md-note" v-if="d.note">{{d.note}}</span>
            </div>
          </div>
          <template v-if="!appCtx.moodTrend.today_mood || appCtx.moodPicking">
            <div class="mood-pick">
              <button v-for="m in appCtx.moodOptions" :key="m.code" class="mood-btn" @click="appCtx.doMoodCheckin(m.code)">
                <span class="mf">{{m.face}}</span><b>{{m.label}}</b>
              </button>
            </div>
            <div class="mood-note-row">
              <input v-model="appCtx.moodNote" class="fill-input" maxlength="50" placeholder="一句话说说今天的感受（选填，先点上面的表情）" style="max-width:360px">
            </div>
          </template>
          <div v-else class="mood-done">
            <span class="md-face big">{{appCtx.moodFace(appCtx.moodTrend.today_mood)}}</span>
            <span>今天已打卡：{{appCtx.moodLabel(appCtx.moodTrend.today_mood)}}<template v-if="appCtx.moodTrend.days[6].note"> · {{appCtx.moodTrend.days[6].note}}</template></span>
            <button class="btn btn-ghost btn-sm" @click="appCtx.resetMoodPick()">换个心情</button>
          </div>
        </div>

        </template>

        <template v-if="appCtx.homeSub==='family'">
        <!-- 完成确认（孩子提交完成 → 家长确认/拒绝），显示在奖励小屋上方 -->
        <div class="card confirm-card" style="margin-top:14px">
          <div class="card-head">
            <b>📋 完成确认</b>
            <span class="more">孩子提交完成，家长在首页确认</span>
          </div>
          <div v-if="appCtx.taskConfirms.length" class="confirm-list">
            <div class="confirm-item" v-for="c in (appCtx.showAllConfirms ? appCtx.taskConfirms : appCtx.taskConfirms.slice(0,5))" :key="c.id">
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
              <div v-if="c.status==='pending' && appCtx.parentPhase==='open'" class="ci-actions">
                <button class="btn btn-success btn-sm" @click="appCtx.resolveTaskConfirm(c.id,'approve')">通过 ✓</button>
                <button class="btn btn-ghost btn-sm" @click="appCtx.openReject(c.id)">拒绝</button>
              </div>
              <div v-if="appCtx.taskReject.id===c.id" class="ci-reject-box">
                <input v-model="appCtx.taskReject.reason" class="fill-input" maxlength="100" placeholder="请填写拒绝理由（必填）">
                <button class="btn btn-primary btn-sm" @click="appCtx.resolveTaskConfirm(c.id,'reject')">提交拒绝</button>
                <button class="btn btn-ghost btn-sm" @click="appCtx.cancelReject()">取消</button>
              </div>
            </div>
          </div>
          <button v-if="appCtx.taskConfirms.length>5" class="link-btn" @click="appCtx.showAllConfirms=!appCtx.showAllConfirms">{{appCtx.showAllConfirms ? '收起 ▴' : '查看全部 '+appCtx.taskConfirmsTotal+' 条 ▾'}}</button>
          <p v-else class="pc-empty">家长反馈激励展示</p>
          <!-- 错题申诉结果：家长判对/判错，反馈到首页家长反馈区 -->
          <div v-if="appCtx.decidedAppeals.length" class="confirm-appeals">
            <div class="ca-head">📨 错题申诉结果 <span class="more">家长对申诉的判对 / 判错</span></div>
            <div class="ca-item" v-for="a in (appCtx.showAllAppeals ? appCtx.decidedAppeals : appCtx.decidedAppeals.slice(0,5))" :key="a.id">
              <div class="ci-row">
                <b class="appeal-q" @click="appCtx.toggleAppeal(a.id)" title="点击查看完整题目">
                  [{{a.subject || '未分科'}}]
                  <template v-if="!appCtx.appealExpanded[a.id]">{{ (a.question || '').length > 50 ? (a.question || '').slice(0,50)+'…' : (a.question || '') }}</template>
                  <template v-else>{{ a.question || '' }}</template>
                  <span class="q-toggle">{{ appCtx.appealExpanded[a.id] ? '收起 ▴' : '查看完整题目 ▾' }}</span>
                </b>
              </div>
              <div class="ci-row ci-sub">
                <span class="more">孩子答案 {{a.user_answer}} · 参考 {{a.correct_answer}}</span>
                <span class="tag" :class="a.status==='approved' ? 'tag-green' : 'tag-red'">
                  {{ a.status==='approved' ? '判对 ✓' : '判错（维持）' }}
                </span>
              </div>
              <div class="ci-row ci-sub"><span class="more">{{a.created_at}} 提交 · {{a.decided_at}} 裁决</span></div>
              <div class="ci-row ci-sub" v-if="a.note"><span class="appeal-note-text">📝 备注：{{a.note}}</span></div>
            </div>
          </div>
          <button v-if="appCtx.decidedAppeals.length>5" class="link-btn" @click="appCtx.showAllAppeals=!appCtx.showAllAppeals">{{appCtx.showAllAppeals ? '收起 ▴' : '查看全部 '+appCtx.decidedAppealsTotal+' 条 ▾'}}</button>
        </div>

        </template>

        <template v-if="appCtx.homeSub==='reward'">
        <!-- 奖励闭环（Sprint 3） -->
        <div class="card reward-card" style="margin-top:14px" v-if="appCtx.rewards">
          <div class="card-head"><b>🎁 奖励小屋</b><span class="more" v-if="appCtx.rewards.wish && appCtx.rewards.wish.status==='pending'">心愿待家长确认中</span><span class="more" v-else-if="appCtx.rewards.wish && appCtx.rewards.wish.status==='pending_redeem'">心愿达标啦！快找家长兑现</span></div>
          <div v-if="appCtx.rewards.wish" class="wish-box">
            <div class="wish-head">
              <b>🌟 {{appCtx.rewards.wish.title}}</b>
              <span class="tag" :class="appCtx.rewards.wish.status==='pending' ? 'tag-orange' : (appCtx.rewards.wish.status==='pending_redeem' ? 'tag-red' : 'tag-blue')">{{appCtx.wishStatusLabel(appCtx.rewards.wish.status)}}</span>
            </div>
            <div class="progress" style="margin:8px 0"><i :style="{width: Math.min(100, appCtx.rewards.wish.progress/appCtx.rewards.wish.target*100)+'%'}"></i></div>
            <div class="wish-foot">
              <span v-if="appCtx.rewards.wish.wish_type === 'optional_streak'">{{appCtx.rewards.wish.progress}} / {{appCtx.rewards.wish.target}} 天 · 每天完成 {{appCtx.rewards.wish.daily_target || 3}} 个可选任务</span>
              <span v-else>{{appCtx.rewards.wish.progress}} / {{appCtx.rewards.wish.target}} · 每完成 1 个可选任务 +1</span>
              <span v-if="appCtx.rewards.wish.deadline" class="more" style="font-size:11px">截止 {{appCtx.rewards.wish.deadline}}</span>
              <button v-if="appCtx.rewards.wish.status==='pending_redeem'" class="btn btn-primary btn-sm" @click="appCtx.showToast('去找家长兑现吧，家长可在「设置-家长管理」确认 🎉')">找家长兑现 →</button>
            </div>
          </div>
          <div v-else class="wish-box wish-empty">
            <div class="wish-head"><b>🌟 还没有心愿？</b><button class="btn btn-ghost btn-sm" @click="appCtx.startWish()">许一个心愿 →</button></div>
            <p>写下想要的小奖励，完成每日任务就能让它成真</p>
          </div>
          <div class="coupon-list" v-if="appCtx.rewards.coupons.length">
            <div class="coupon-item" v-for="c in appCtx.rewards.coupons" :key="c.id">
              <span class="ci">{{appCtx.couponIcon(c.kind)}}</span>
              <div class="c-body">
                <b>{{c.title}}</b>
                <span v-if="c.required_days>0">{{c.kind_label}}<template v-if="c.granted_count>0"> · ✅ 已获得 {{c.granted_count}} 张，剩余 {{c.left}} 张</template><template v-else> · 三科任务全勤 {{c.required_days}} 天可得<template v-if="c.required_within_days>0">，限 {{c.required_within_days}} 天内（剩 {{c.days_left>=0 ? c.days_left : 0}} 天，截止 {{c.cycle_deadline}}）</template>，当前 {{c.progress_days}}/{{c.required_days}} 天</template><template v-if="c.required_within_days>0"><span class="more" style="font-size:11px"> · 超时进度清零重启</span></template><template v-else><span class="more" style="font-size:11px"> · 7天内最多缺1天，超出从头计算</span></template></span>
                <span v-else>{{c.kind_label}} · 可直接使用，剩余 {{c.left}} 张</span>
                <span v-if="c.reason" class="c-reason">🎯 {{c.reason}}</span>
              </div>
              <span class="tag" :class="c.left>0 ? 'tag-green' : 'tag-blue'">{{c.left>0 ? '可用' : (c.required_days>0 ? '待达成' : '已用完')}}</span>
            </div>
          </div>
          <div class="timeline-box" v-if="appCtx.rewardTimeline.length">
            <div class="tl-title">🏆 成长奖励记录</div>
            <div class="tl-item" v-for="(it,i) in (appCtx.showAllRewards ? appCtx.rewardTimeline : appCtx.rewardTimeline.slice(0,6))" :key="i">
              <span class="tl-ico" :class="it.kind==='wish' ? 't-gold' : 't-blue'">{{it.kind==='wish' ? '🌟' : '🎫'}}</span>
              <div class="tl-body"><b>{{it.title}}</b><span>{{it.reason}}<template v-if="it.at"> · {{it.at}}</template></span></div>
            </div>
          </div>
          <button v-if="appCtx.rewardTimeline.length>6" class="link-btn" @click="appCtx.showAllRewards=!appCtx.showAllRewards">{{appCtx.showAllRewards ? '收起 ▴' : '查看全部 '+appCtx.rewardTimeline.length+' 条 ▾'}}</button>
        </div>

        </template>

        <template v-if="appCtx.homeSub==='family'">
        <!-- 家长留言（孩子端） -->
        <div class="card msg-card" style="margin-top:14px">
          <div class="card-head">
            <b>✉️ 家长留言</b>
            <span class="more" v-if="appCtx.parentMsgs.unread>0" @click="appCtx.markMsgsRead()">点开即已读，共 {{appCtx.parentMsgs.unread}} 条未读</span>
            <span class="more" v-else>家长写给你的悄悄话</span>
          </div>
          <div v-if="appCtx.parentMsgs.messages && appCtx.parentMsgs.messages.length" class="msg-list">
            <div class="msg-item" :class="{unread: !m.read}" v-for="m in appCtx.parentMsgs.messages.slice(0,6)" :key="m.id">
              <span class="msg-ico">💌</span>
              <div class="msg-body"><p>{{m.content}}</p><span>{{m.created_at}}<template v-if="!m.read"> · 未读</template></span></div>
            </div>
          </div>
          <div v-else class="empty" style="padding:18px">
            <p style="color:#8a97b0;font-size:13px">还没有留言，等爸爸妈妈来说悄悄话吧</p>
          </div>
        </div>

        </template>

        <template v-if="appCtx.homeSub==='today'">
        <!-- 成长周报入口（Sprint 3） -->
        <div class="card weekly-entry" style="margin-top:14px" @click="appCtx.openWeekly()">
          <div class="w-ico">📮</div>
          <div class="w-body">
            <b>上周成长周报</b>
            <span>AI 为你总结一周亮点，还有家长的悄悄话</span>
          </div>
          <span class="btn btn-ghost btn-sm">查看 →</span>
        </div>

        <!-- 挑战赛 + 学期目标（Sprint 4） -->
        <div class="grid-2" style="margin-top:14px">
          <div class="card chal-entry" @click="appCtx.openChal()">
            <div class="w-ico">⚡</div>
            <div class="w-body">
              <b>60 秒挑战赛</b>
              <span>口算 / 单词快答，刷新纪录赢徽章</span>
            </div>
            <span class="btn btn-ghost btn-sm">开战 →</span>
          </div>
          <div class="card goal-entry" @click="appCtx.goTab('goals')">
            <div class="w-ico">🎯</div>
            <div class="w-body">
              <b>今日学习目标</b>
              <template v-if="appCtx.homeGoals.length">
                <span class="gt-line" v-for="g in appCtx.homeGoals.slice(0,3)" :key="g.id" style="display:block;font-size:12px;color:#6b7180;margin-top:3px">
                  <i :style="{display:'inline-block',width:'7px',height:'7px',borderRadius:'50%',marginRight:'5px',background: g.card_kind==='rest' ? '#F5A623' : (g.card_kind ? '#F2604C' : '#34C77B')}"></i>{{g.name}} 建议 {{g.daily_suggestion}} {{g.unit}} · {{g.pct}}%
                </span>
              </template>
              <span v-else>还没目标？立一个有终点、有总量的小目标</span>
            </div>
            <span class="btn btn-primary btn-sm">打卡 →</span>
          </div>
        </div>

        <!-- 学习概览 -->
        <div class="section-title">📈 学习概览</div>
        <div class="grid-3">
          <div class="card stat-card"><div class="ico"><app-icon name="reading" :size="22"></app-icon></div><b>{{appCtx.vocabTotal ? appCtx.vocabLearned+'/'+appCtx.vocabTotal : 0}}</b><span>已学单词</span></div>
          <div class="card stat-card highlight"><div class="ico"><app-icon name="goals" :size="22"></app-icon></div><b>{{appCtx.avgScore}}%</b><span>平均正确率</span></div>
          <div class="card stat-card"><div class="ico"><app-icon name="badges" :size="22"></app-icon></div><b>{{appCtx.masteredTotal}}</b><span>已掌握错题</span></div>
        </div>
      </template>
</div>
</template>

<script>
// HomeView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'HomeView',
  inject: ['appCtx'],
}
</script>
