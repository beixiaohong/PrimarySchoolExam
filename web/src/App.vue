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
        <label>邮箱</label>
        <input v-model="username" placeholder="请输入邮箱" @keyup.enter="login">
      </div>
      <div class="field" v-if="isAccountCredential">
        <label>密码</label>
        <input v-model="loginPwd" type="password" placeholder="请输入密码" @keyup.enter="login">
      </div>
      <button class="btn btn-primary btn-lg login-btn" :disabled="!username.trim()" @click="login">进入学习 →</button>
      <p class="login-tip link" @click="authMode='reset'">忘记密码？</p>
    </template>

    <!-- 注册 -->
    <template v-if="authMode==='register'">
      <div class="field">
        <label>邮箱</label>
        <input v-model="regTarget" placeholder="用于接收验证码" @keyup.enter="register">
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
        <label>昵称（可选，仅作展示名）</label>
        <input v-model="regNickname" placeholder="不填则取邮箱前缀作为昵称">
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
      <div class="avatar">{{userName.charAt(0)}}</div>
      <div><b>{{userName}}</b><span>🔥 连续学习 {{streakDays}} 天</span></div>
    </div>
  </aside>

  <div class="main">
    <header class="topbar">
      <div class="subject-pills" v-if="tab==='practice' || tab==='wrong'">
        <button v-for="s in subjectOptions" :key="s" :class="{active: subject===s}" @click="switchSubject(s)">{{s}}</button>
      </div>
      <button class="icon-btn" @click="showToast('🔔 暂无新通知，加油学习！')">🔔</button>
      <div class="me">
        <div class="avatar" style="width:32px;height:32px;font-size:12px">{{userName.charAt(0)}}</div>
        <b>{{userName}}</b><span class="streak">🔥{{streakDays}}</span><span class="diamonds" title="钻石余额">💎{{diamonds}}</span>
      </div>
    </header>

    <main class="content">
      <!-- ═══════════ 今日学习首页 ═══════════ -->
<home-view v-if="tab==='home'"></home-view>

      <!-- ═══════════ 刷题中心 ═══════════ -->
      <practice-view v-if="tab==='practice'"></practice-view>

      <!-- ═══════════ 背诵中心 ═══════════ -->
      <recite-view v-if="tab==='recite'"></recite-view>

      <!-- ═══════════ 错题本 ═══════════ -->
<wrong-view v-if="tab==='wrong'"></wrong-view>

      <!-- ═══════════ 试卷中心 ═══════════ -->
<papers-view v-if="tab==='papers'"></papers-view>

      <!-- ═══════════ 学习统计 ═══════════ -->
<stats-view v-if="tab==='stats'"></stats-view>

      <!-- ═══════════ 设置 ═══════════ -->
      <!-- ═══════════ 十万个为什么 ═══════════ -->
<qa-view v-if="tab==='qa'"></qa-view>

      <!-- ═══════════ 宠物家园（P2-1 金币宠物） ═══════════ -->
<pet-view v-if="tab==='pet'"></pet-view>

      <!-- ═══════════ 成长树（P2-2 创意 7） ═══════════ -->
<tree-view v-if="tab==='tree'"></tree-view>

      <!-- ═══════════ 成就徽章墙（P2-3 创意 8） ═══════════ -->
<badges-view v-if="tab==='badges'"></badges-view>

      <!-- ═══════════ 知识卡图鉴（P2-4 创意 13） ═══════════ -->
<cards-view v-if="tab==='cards'"></cards-view>

      <!-- ═══════════ 听写磨耳朵（P2-5 创意 25） ═══════════ -->
<dict-view v-if="tab==='dict'"></dict-view>

      <!-- ═══════════ 番茄专注钟（P2-6 创意 22） ═══════════ -->
<focus-view v-if="tab==='focus'"></focus-view>

      <!-- ═══════════ AI 趣味出题（AI-2 创意 24） ═══════════ -->
<aiquiz-view v-if="tab==='aiquiz'"></aiquiz-view>

      <!-- ═══════════ AI 学习助手（AI-5） ═══════════ -->
<assistant-view v-if="tab==='assistant'"></assistant-view>

      <!-- ═══════════ 钱包（P5 新增） ═══════════ -->
<wallet-view v-if="tab==='wallet'"></wallet-view>
      
<settings-view v-if="tab==='settings'"></settings-view>

      <SearchView v-if="tab==='search'"></SearchView>
      <SyncView v-if="tab==='sync'"></SyncView>
      <KnowledgeView v-if="tab==='kp'"></KnowledgeView>
      <ReadingView v-if="tab==='reading'"></ReadingView>
      <LearningGoalsView v-if="tab==='goals'"></LearningGoalsView>

      <!-- ═══════════ 网课（系统配置 + 家长配置） ═══════════ -->
<courses-view v-if="tab==='courses'"></courses-view>

      <!-- 网课播放弹窗 -->
      <div v-if="curCourse" class="modal-mask on" @click.self="closeCourse()">
        <div class="modal-card course-modal">
          <div class="modal-head"><b>{{curCourse.title}}</b><button class="icon-btn" @click="closeCourse()">✕</button></div>
          <div class="course-player">
            <video v-if="isMp4(curCourse.video_url)" :src="curCourse.video_url" controls autoplay style="width:100%;max-height:52vh;background:#000;border-radius:10px"></video>
            <iframe v-else :src="curCourse.video_url" frameborder="0" allowfullscreen
                    style="width:100%;height:52vh;border-radius:10px;background:#000"></iframe>
          </div>
          <p class="course-desc" v-if="curCourse.description" style="margin:12px 0 0">{{curCourse.description}}</p>
        </div>
      </div>
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
            <input v-model="chalOverlay.input" class="fill-input" type="number" placeholder="输入答案，回车提交" @keydown.enter="chalAnswer()">
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

<!-- 学期目标浮层已于二期下线：目标统一进入「学习目标」管理台（/api/learning-goals） -->

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
            <anti-cheat-input
              v-if="quiz.source && (quiz.source.mode === 'dictate' || quiz.source.mode === 'classical')"
              v-model="quiz.fillText"
              :mode="quiz.source.kind === 'word' ? 'alpha' : 'text'"
              :chars="quiz.source.kind === 'word' ? [] : quiz.candidateChars"
              :placeholder="quiz.source.kind === 'word' ? '点击字母拼出单词' : '用输入法输入'"
            ></anti-cheat-input>
            <input v-else v-model="quiz.fillText" class="fill-input" :placeholder="quiz.items[quiz.i].placeholder||'请输入答案'" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" @compositionstart="composing = true" @compositionend="composing = false" @keydown.enter="!composing && submitFill()" :disabled="quiz.items[quiz.i].answered" style="margin-top:0">
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
                <button v-if="!quiz.items[quiz.i].appealed" class="btn btn-ghost btn-sm" :disabled="rejudging" @click="aiRejudgeCurrent()" title="让 AI 重新判断，尤其当参考答案本身算错时">{{ rejudging ? '复核中…' : '🤖 用 AI 重判' }}</button>
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
            <button class="btn btn-primary" v-if="quiz.items[quiz.i].answered" :disabled="quiz.items[quiz.i].explaining" @click="quizNext()">
              <template v-if="quiz.source && quiz.source.perItem && quiz.i===quiz.items.length-1">
                {{ quiz.items[quiz.i].correct ? (quiz.source.kind==='word' ? '✓ 下一个单词 →' : '✓ 下一篇 →') : '再测一次 →' }}
              </template>
              <template v-else>{{quiz.i===quiz.items.length-1 ? '查看结果 →' : '下一题 →'}}</template>
            </button>
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
      <p>请把这次完成的截图，用微信或其他方式发给家长，<br>提醒家长在首页「🏡 家园互动」里的「完成确认」中确认你就完成啦～</p>
    </div>
    <div class="modal-foot">
      <button class="btn btn-primary" @click="taskSubmitTip.show=false">我知道了</button>
    </div>
  </div>
</div>

<!-- ═══════════ 购买钻石弹窗 ═══════════ -->
<div class="modal-mask" :class="{on: rechargeOpen}">
  <div class="modal modal-recharge">
    <div class="modal-head"><h2>💎 购买钻石</h2><span class="tag tag-blue">1 元 = 1 钻石</span></div>
    <div class="modal-body">
      <p class="rc-tip">选择充值数量，扫码付款后请在<strong>转账留言 / 备注</strong>中填写你的账号，客服核对后为你发放钻石。</p>
      <div class="recharge-pkgs">
        <button v-for="p in [10,30,50,100,200]" :key="p" class="rc-pkg" :class="{on: rechargePkg===p}" @click="selectRechargePkg(p)">
          <span class="rc-pkg-num">{{p}}</span>
          <span class="rc-pkg-price">¥{{p * (rechargeCfg ? rechargeCfg.rate : 1)}}</span>
        </button>
      </div>

      <div class="recharge-account">
        <span class="rc-acc-label">付款留言请填写账号：</span>
        <code class="rc-acc-value">{{user}}</code>
        <button class="btn btn-ghost btn-sm" @click="copyRechargeAccount()">{{rechargeCopied ? '已复制 ✓' : '复制'}}</button>
      </div>

      <div class="recharge-cs">
        <div class="cs-head" @click="toggleRechargeQr()">
          <span v-if="rechargeCfg && rechargeCfg.cs_contact">📞 客服微信：<b>{{rechargeCfg.cs_contact}}</b></span>
          <span v-else>📞 付款后请联系客服，提供「付款截图 + 账号」即可发放钻石。</span>
          <span class="cs-toggle">{{ rechargeQrOpen ? '收起 ▴' : '查看收款二维码 ▾' }}</span>
        </div>
        <div class="cs-detail" v-if="rechargeQrOpen">
          <div class="recharge-qrs" v-if="rechargePkg">
            <div class="rc-qr">
              <div class="rc-qr-title">💚 微信支付</div>
              <img v-if="rechargeCfg && rechargeCfg.wechat_qr" :src="rechargeCfg.wechat_qr" alt="微信收款码" class="rc-qr-img">
              <div v-else class="rc-qr-empty">请联系客服获取微信收款码</div>
            </div>
            <div class="rc-qr">
              <div class="rc-qr-title">🔵 支付宝</div>
              <img v-if="rechargeCfg && rechargeCfg.alipay_qr" :src="rechargeCfg.alipay_qr" alt="支付宝收款码" class="rc-qr-img">
              <div v-else class="rc-qr-empty">请联系客服获取支付宝收款码</div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn btn-primary" @click="closeRecharge()">我知道了</button>
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
    return { ...appOptions.data.call(this), NAV_GROUPS, TABBAR, homeGoals: [] }
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
    // 二期 C1：首页「今日目标」卡 —— 联动学习目标管理台，展示各目标今日建议量与进度
    loadHomeGoals() {
      this.api('/api/learning-goals')
        .then(d => { this.homeGoals = (d && d.goals) || []; })
        .catch(() => { this.homeGoals = []; })
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
    // 二期 C1：进入首页「今日」子页时拉取今日目标
    tab(t) {
      if (t === 'home') this.$nextTick(() => { if (this.homeSub === 'today') this.loadHomeGoals() })
    },
    homeSub(s) {
      if (s === 'today' && this.tab === 'home') this.loadHomeGoals()
    },
  },
  // B1 组件化：把壳实例暴露给抽出的各业务视图，视图通过 inject('appCtx') 访问壳的
  // 响应式状态(data/computed)与方法(methods)，无需把 3603 行的 appOptions mixin 搬到每个视图。
  provide() {
    return { appCtx: this }
  },
  mounted() {
    appOptions.mounted.call(this)
    // 首屏若 URL 已带合法 tab（如刷新后），直接定位到该 tab
    const t = this.$route && this.$route.params.tab
    if (t && ALL_TABS.includes(t) && t !== this.tab) {
      appOptions.methods.goTab.call(this, t)
      if (t === 'wallet') this.wallet.load(this.user, this.makeupCards)
    }
    // 二期 C1：默认在首页「今日」时加载今日目标卡
    if (this.tab === 'home' && this.homeSub === 'today') this.loadHomeGoals()
  },
}
</script>
