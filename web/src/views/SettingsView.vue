<template>
<div class="fade-enter">
        <div class="card" style="max-width:640px">
          <div class="card-head"><b>👤 个人信息</b></div>
          <div class="form-grid" style="margin-top:16px">
            <div class="form-item"><label>用户名</label><input :value="appCtx.user" disabled style="background:var(--bg)"></div>
            <div class="form-item"><label>年级</label><select v-model="appCtx.grade" @change="appCtx.onGradeChange"><option v-for="g in [1,2,3,4,5,6,7,8,9]" :key="'set-'+g" :value="g">{{g}}年级</option></select></div>
            <div class="form-item"><label>默认学科</label><select v-model="appCtx.subject" @change="appCtx.onSubjectChange"><option v-for="s in appCtx.subjectOptions" :key="'def-'+s">{{s}}</option></select></div>
          </div>
          <p class="card-desc">当前年级：{{appCtx.grade}}年级 · 每年9月自动升一年级 · 学习数据按用户名保存在本地服务器</p>
        </div>
        <div class="card" style="max-width:640px;margin-top:16px">
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
        <div class="card" style="max-width:640px;margin-top:16px">
          <div class="card-head"><b>🏙️ 我的城市</b><span class="more">用于首页天气展示</span></div>
          <div class="pc-row">
            <input v-model="appCtx.cityInput" placeholder="如：杭州" maxlength="50" style="flex:1;padding:9px 12px;border:1px solid #E5E1F5;border-radius:10px;font-size:14px">
            <button class="btn btn-primary" @click="appCtx.saveCity" style="padding:9px 20px">保存</button>
          </div>
        </div>
        <div class="card" style="max-width:640px;margin-top:16px">
          <div class="card-head"><b>🔐 账号安全</b><span class="more">绑定邮箱后可跨设备登录与找回密码</span></div>
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
        <div class="card" style="max-width:640px;margin-top:16px">
          <div class="card-head"><b>📚 学习数据</b></div>
          <div class="info-row"><span>连续学习</span><b>🔥 {{appCtx.streakDays}} 天</b></div>
          <div class="info-row"><span>累计单词</span><b>{{appCtx.vocabStats.learned_count||0}} / {{appCtx.vocabStats.total_words||0}}</b></div>
          <div class="info-row"><span>累计古诗文</span><b>{{appCtx.classicalStats.learned||0}} / {{appCtx.classicalStats.total||0}}</b></div>
          <div class="info-row"><span>错题总数</span><b>{{appCtx.wrongAnalysis.total||0}}（已掌握 {{appCtx.wrongAnalysis.mastered||0}}）</b></div>
        </div>
        <div class="card" style="max-width:640px;margin-top:16px">
          <div class="card-head"><b>⚙️ 其他</b></div>
          <div class="info-row"><span>极速模式（答题动画加速）</span><button class="btn btn-sm" :class="appCtx.turbo ? 'btn-primary' : 'btn-ghost'" @click="appCtx.toggleTurbo()">{{appCtx.turbo ? '已开启' : '已关闭'}}</button></div>
          <div class="detail-actions" style="margin-top:14px">
            <button class="btn btn-ghost" @click="appCtx.showToast('已是最新版本 v2.0')">检查更新</button>
            <button class="btn btn-danger" @click="appCtx.logout()">退出登录</button>
          </div>
        </div>

        <!-- 家长管理（密码保护 + 任务设置 + 兑换券/心愿 + 留言/学习数据/题数设置） -->
        <div class="card parent-card" style="max-width:640px;margin-top:16px">
          <div class="card-head"><b>👨‍👩‍👧 家长管理</b><span class="more">家长密码保护 · 孩子进不来</span></div>

          <!-- ① 首次使用：设置家长密码 -->
          <div v-if="appCtx.parentPhase==='unset'" class="pc-sec">
            <div class="pc-title">🔒 设置家长密码 <span class="more">设置后进入家长管理需要输密码，防止孩子乱动</span></div>
            <div class="pc-row">
              <input v-model="appCtx.pwdForm.pwd" type="password" class="fill-input" maxlength="32" placeholder="家长密码（4-32 位）" style="max-width:180px">
              <input v-model="appCtx.pwdForm.pwd2" type="password" class="fill-input" maxlength="32" placeholder="再输一次" style="max-width:180px">
            </div>
            <div class="pc-row" style="margin-top:8px">
              <input v-model="appCtx.pwdForm.hintQ" class="fill-input" maxlength="100" placeholder="密保问题（忘记密码时用，如：孩子的小名是？）">
            </div>
            <div class="pc-row" style="margin-top:8px">
              <input v-model="appCtx.pwdForm.hintA" class="fill-input" maxlength="50" placeholder="密保答案（家长才能答对哦）" style="max-width:240px">
              <button class="btn btn-primary btn-sm" @click="appCtx.setupParentPwd()">设置并进入</button>
            </div>
          </div>

          <!-- ② 已设密码：输入密码解锁 -->
          <div v-else-if="appCtx.parentPhase==='locked' || appCtx.parentPhase==='reset'" class="pc-sec">
            <div class="pc-title">🔑 家长验证</div>
            <template v-if="appCtx.parentPhase==='locked'">
              <div class="pc-row">
                <input v-model="appCtx.pwdForm.unlock" type="password" class="fill-input" maxlength="32" placeholder="输入家长密码" style="max-width:200px" @keyup.enter="appCtx.unlockParent()">
                <button class="btn btn-primary btn-sm" @click="appCtx.unlockParent()">解锁</button>
                <button class="btn btn-ghost btn-sm" @click="appCtx.parentPhase='reset'">忘记密码？</button>
              </div>
              <p class="pc-hint">孩子完成每日任务、兑换券、心愿都由家长在这里管理</p>
            </template>
            <template v-else>
              <div class="pc-row">
                <span class="more" style="font-size:13px">密保问题：{{appCtx.pwdForm.hintQ}}</span>
              </div>
              <div class="pc-row" style="margin-top:8px">
                <input v-model="appCtx.pwdForm.resetA" class="fill-input" maxlength="50" placeholder="密保答案" style="max-width:200px">
                <input v-model="appCtx.pwdForm.resetPwd" type="password" class="fill-input" maxlength="32" placeholder="新密码" style="max-width:180px">
                <button class="btn btn-primary btn-sm" @click="appCtx.resetParentPwd()">重置</button>
                <button class="btn btn-ghost btn-sm" @click="appCtx.parentPhase='locked'">返回</button>
              </div>
              <p class="pc-hint">答对密保问题即可重置密码（家长预设的问题）</p>
            </template>
          </div>

          <!-- ③ 已解锁：家长管理全部功能 -->
          <template v-else-if="appCtx.parentPhase==='open'">
          <div class="pc-row" style="justify-content:space-between;margin-bottom:8px">
            <span class="more" style="font-size:13px">🔓 家长模式已解锁</span>
            <button class="btn btn-ghost btn-sm" @click="appCtx.exitParentMode()">退出家长模式 →</button>
          </div>
          <div class="pc-sec">
            <div class="pc-title">🎯 今日任务确认 <span class="more">讲题/朗读/听写由家长确认完成，数量可在下方设置</span></div>
            <div class="pc-row" v-for="t in appCtx.dailyTasks" :key="t.id" style="justify-content:space-between;flex-wrap:wrap">
              <span style="font-size:13px;color:#3a4a6b">{{t.subject}} · {{t.title}}</span>
              <span style="display:inline-flex;align-items:center;gap:8px">
                <span v-if="t.status==='done'" class="tag tag-green">✅ 已完成</span>
                <template v-else-if="t.manual && t.status==='pending_confirm'">
                  <span class="tag tag-orange">孩子已提交</span>
                  <button class="btn btn-primary btn-sm" @click="appCtx.parentConfirmTask(t)">确认完成 ✓</button>
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
            <div class="pc-title">🎫 补签卡待确认 <span class="more">孩子用补签卡完成的任务，需家长确认生效，拒绝则退回</span><span v-if="appCtx.pendingMakeups.length" class="tag tag-orange">{{appCtx.pendingMakeups.length}} 条待处理</span></div>
            <div class="pc-list" v-if="appCtx.pendingMakeups.length">
              <div class="pc-item" v-for="m in appCtx.pendingMakeups" :key="m.log_id" style="flex-wrap:wrap">
                <div class="c-body" style="flex:1;min-width:200px">
                  <b>{{m.task_title || '任务'}}</b>
                  <span class="more">提交于 {{m.used_at}}</span>
                </div>
                <button class="btn btn-success btn-sm" @click="appCtx.confirmMakeup(m.log_id, 'confirm')">确认生效 ✓</button>
                <button class="btn btn-ghost btn-sm" @click="appCtx.confirmMakeup(m.log_id, 'reject')">拒绝退回</button>
              </div>
            </div>
            <p v-else class="pc-empty">没有待确认的补签申请</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">✋ 孩子的申诉 <span class="more">孩子觉得题判错了，请家长二次确认</span><span v-if="appCtx.pendingAppeals.length" class="tag tag-orange">{{appCtx.pendingAppeals.length}} 条待处理</span></div>
            <div class="pc-list" v-if="appCtx.pendingAppeals.length">
              <div class="pc-item" v-for="a in (appCtx.showAllPending ? appCtx.pendingAppeals : appCtx.pendingAppeals.slice(0,30))" :key="a.id" style="flex-wrap:wrap">
                <div class="c-body" style="flex:1;min-width:220px">
                  <b class="appeal-q" @click="appCtx.toggleAppeal(a.id)" title="点击查看完整题目">
                    [{{a.subject || '未分科'}}]
                    <template v-if="!appCtx.appealExpanded[a.id]">{{ (a.question || '').length > 60 ? (a.question || '').slice(0,60)+'…' : (a.question || '') }}</template>
                    <template v-else>{{ a.question || '' }}</template>
                    <span class="q-toggle">{{ appCtx.appealExpanded[a.id] ? '收起 ▴' : '查看完整题目 ▾' }}</span>
                  </b>
                  <span>孩子答案：{{a.user_answer}} · 参考答案：{{a.correct_answer}}</span>
                  <span class="more">{{a.created_at}} 提交</span>
                  <input class="fill-input appeal-note" v-model="appCtx.appealNotes[a.id]" placeholder="判题备注（可选）：可填写判对/判错的理由" />
                </div>
                <button class="btn btn-primary btn-sm" :disabled="appCtx.recheckingId===a.id" @click="appCtx.aiRecheckAppeal(a)" title="让 AI 重判该题，参考答案有误会自动修正并直接通过申诉">{{ appCtx.recheckingId===a.id ? '复核中…' : '🤖 AI 复核' }}</button>
                <button class="btn btn-success btn-sm" :disabled="a._deciding" @click="appCtx.decideAppeal(a, true)" title="确认后该题改判正确、本卷得分重算">{{ a._deciding ? '处理中…' : '确认做对了 ✓' }}</button>
                <button class="btn btn-ghost btn-sm" :disabled="a._deciding" @click="appCtx.decideAppeal(a, false)">{{ a._deciding ? '处理中…' : '维持判错' }}</button>
              </div>
              <button v-if="appCtx.pendingAppeals.length > 30" class="link-btn" @click="appCtx.showAllPending = !appCtx.showAllPending">{{ appCtx.showAllPending ? '收起 ▴' : '查看全部 ' + appCtx.pendingAppeals.length + ' 条 ▾' }}</button>
            </div>
            <p v-else class="pc-empty">没有待处理的申诉</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">📋 每日任务设置 <span class="more">管理强制任务和可选任务</span></div>
            <div v-if="appCtx.taskSettings" style="font-size:13px;color:#666;margin-bottom:8px">
              强制任务 {{appCtx.mandatorySummary}} · 可选任务 {{(appCtx.taskSettings.optional || []).length}} 个已配置
              <div style="margin-top:4px">打开「管理任务」可更换每科任务类型（如数学同步练、语文阅读+家庭作业、英语朗读+背单词）</div>
            </div>
            <div class="pc-row" style="margin-top:8px">
              <button class="btn btn-primary btn-sm" @click="appCtx.showTaskSettingsDialog()">管理任务</button>
            </div>
          </div>

          <div class="pc-sec">
            <div class="pc-title">🎬 网课设置 <span class="more">给孩子添加网课视频（支持 b站/腾讯视频/直链 mp4）</span></div>
            <div class="pc-row" style="flex-wrap:wrap;gap:8px">
              <input v-model="appCtx.courseForm.title" class="fill-input" placeholder="课程标题（必填）" style="flex:1;min-width:150px">
              <input v-model="appCtx.courseForm.video_url" class="fill-input" placeholder="视频链接（必填）" style="flex:2;min-width:220px">
            </div>
            <div class="pc-row" style="flex-wrap:wrap;gap:8px;margin-top:8px">
              <select v-model="appCtx.courseForm.subject" class="fill-input" style="max-width:110px">
                <option value="">不限学科</option>
                <option v-for="s in appCtx.subjectOptions" :key="s" :value="s">{{s}}</option>
              </select>
              <select v-model.number="appCtx.courseForm.grade" class="fill-input" style="max-width:130px">
                <option :value="0">不限年级</option>
                <option v-for="g in [1,2,3,4,5,6,7,8,9]" :key="g" :value="g">{{g}}年级</option>
              </select>
              <button class="btn btn-primary btn-sm" @click="appCtx.addParentCourse()">添加网课</button>
            </div>
            <div v-if="appCtx.parentCourses.length" style="margin-top:10px">
              <div v-for="c in appCtx.parentCourses" :key="c.id" class="pc-row" style="justify-content:space-between">
                <span style="font-size:13px">▶ {{c.title}}<span class="more" v-if="c.subject && c.subject!=='不限'"> · {{c.subject}}</span></span>
                <button class="btn btn-danger btn-sm" @click="appCtx.removeParentCourse(c)">删除</button>
              </div>
            </div>
            <p v-else class="pc-empty" style="margin-top:8px">还没有添加网课</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">📝 试卷最少题数 <span class="more">孩子生成试卷（含每日练习）不得少于这个数</span></div>
            <div class="pc-row" style="gap:12px">
              <span class="more" style="font-size:13px">数学</span>
              <input v-model.number="appCtx.examMin.math_min" type="number" min="1" max="50" class="fill-input" style="max-width:70px">
              <span class="more" style="font-size:13px">语文</span>
              <input v-model.number="appCtx.examMin.chi_min" type="number" min="1" max="50" class="fill-input" style="max-width:70px">
              <span class="more" style="font-size:13px">英语</span>
              <input v-model.number="appCtx.examMin.eng_min" type="number" min="1" max="50" class="fill-input" style="max-width:70px">
              <button class="btn btn-primary btn-sm" @click="appCtx.saveExamSettings()">保存</button>
            </div>
            <p class="pc-hint">范围 1-50 题。比如数学设 20，孩子怎么选都不会少于 20 题</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">📅 学习同步设置 <span class="more">学期解锁 · 课堂同步 · 小升初衔接</span></div>
            <div class="pc-row" style="justify-content:space-between">
              <span style="font-size:13px;color:#3a4a6b">预习下学期（提前解锁下学期词书/古诗文）</span>
              <button class="btn btn-sm" :class="appCtx.studyFlags.include_next ? 'btn-primary' : 'btn-ghost'" @click="appCtx.toggleStudyFlag('include_next')">{{appCtx.studyFlags.include_next ? '已开启' : '已关闭'}}</button>
            </div>
            <div class="pc-row" style="justify-content:space-between">
              <span style="font-size:13px;color:#3a4a6b">课堂同步（背单词/听写按教学进度的当前单元）</span>
              <button class="btn btn-sm" :class="appCtx.studyFlags.sync_mode ? 'btn-primary' : 'btn-ghost'" @click="appCtx.toggleStudyFlag('sync_mode')">{{appCtx.studyFlags.sync_mode ? '已开启' : '已关闭'}}</button>
            </div>
            <div class="pc-row" style="justify-content:space-between" v-if="appCtx.grade===6">
              <span style="font-size:13px;color:#3a4a6b">小升初衔接（六年级新学批次混入 30% 七年级内容）</span>
              <button class="btn btn-sm" :class="appCtx.studyFlags.xsc_bridge ? 'btn-primary' : 'btn-ghost'" @click="appCtx.toggleStudyFlag('xsc_bridge')">{{appCtx.studyFlags.xsc_bridge ? '已开启' : '已关闭'}}</button>
            </div>
            <p class="pc-hint">预习：提前学下学期内容；课堂同步需先在下方设置教学进度；衔接仅六年级生效</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">📖 教学进度 <span class="more">孩子英语当前词书/单元，课堂同步按此出题</span></div>
            <div class="pc-row" style="flex-wrap:wrap;gap:8px">
              <select v-model.number="appCtx.teachProgress.book_id" class="fill-input" style="max-width:220px" @change="appCtx.onTeachBookChange()">
                <option :value="0">选择词书</option>
                <option v-for="b in appCtx.teachBooks" :key="b.book_id" :value="b.book_id">{{b.book_name}}（{{b.semester}}学期）</option>
              </select>
              <select v-model="appCtx.teachProgress.chapter" class="fill-input" style="max-width:130px">
                <option value="">选择单元</option>
                <option v-for="u in appCtx.teachUnitOptions" :key="u">{{u}}</option>
              </select>
              <button class="btn btn-primary btn-sm" @click="appCtx.saveTeachProgress()">保存进度</button>
            </div>
            <p class="pc-hint" v-if="appCtx.teachProgressText">当前进度：{{appCtx.teachProgressText}}</p>
            <p class="pc-hint" v-else>尚未设置；开启「课堂同步」后，背单词/听写只出当前单元的词汇，额度不足时回退全量</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">📊 孩子学习数据 <span class="more">本周概况</span></div>
            <div class="stats-grid">
              <div class="sg"><b>{{appCtx.childStats.week_attempts}}</b><span>本周做题(套)</span></div>
              <div class="sg"><b>{{appCtx.childStats.week_avg_score}}%</b><span>平均正确率</span></div>
              <div class="sg"><b>{{appCtx.childStats.unmastered_wrong}}</b><span>未消灭错题</span></div>
              <div class="sg"><b>{{appCtx.childStats.streak_days}}</b><span>连续学习(天)</span></div>
              <div class="sg"><b>{{appCtx.childStats.week_tasks_done}}</b><span>本周完成任务</span></div>
            </div>
          </div>

          <div class="pc-sec">
            <div class="pc-title">💬 留言给孩子 <span class="more">孩子一登录就能看到，未读有提醒</span></div>
            <div class="pc-row">
              <input v-model="appCtx.parentMsg" class="fill-input" maxlength="300" placeholder="写句悄悄话：如 今天数学做得不错，继续保持！" @compositionstart="appCtx.composing = true" @compositionend="appCtx.composing = false" @keydown.enter="!appCtx.composing && appCtx.sendParentMsg()">
              <button class="btn btn-primary btn-sm" @click="appCtx.sendParentMsg()">发送</button>
            </div>
            <div class="pc-list" v-if="appCtx.sentMsgs.length">
              <div class="pc-item" v-for="m in appCtx.sentMsgs.slice(0,5)" :key="m.id">
                <div class="c-body"><b>💌 {{m.content}}</b><span>{{m.created_at}}</span></div>
              </div>
            </div>
          </div>

          <div class="pc-sec">
            <div class="pc-title">💌 给孩子写悄悄话（周报寄语）</div>
            <div class="pc-row">
              <input v-model="appCtx.parentNote" class="fill-input" maxlength="200" placeholder="写一句鼓励的话，会出现在孩子的成长周报里">
              <button class="btn btn-primary btn-sm" @click="appCtx.saveParentNote()">保存</button>
            </div>
          </div>

          <div class="pc-sec">
            <div class="pc-title">🎫 兑换券管理 <span class="more">可设全勤天数门槛，孩子达成即获得；家长核销兑现 · 成长奖励记录只展示已获取的券</span></div>
            <div class="pc-row" style="flex-wrap:wrap">
              <input v-model="appCtx.newCoupon.title" class="fill-input" maxlength="30" placeholder="如：周末看动画半小时" style="min-width:150px">
              <select v-model="appCtx.newCoupon.kind" class="fill-input" style="min-width:140px">
                <option value="cartoon">动画时间</option><option value="snack">零食券</option>
                <option value="sticker">贴纸券</option><option value="toy">玩具券</option>
                <option value="outing">外出券</option><option value="custom">自定义</option>
              </select>
              <input v-model.number="appCtx.newCoupon.requiredDays" type="number" min="0" max="30" class="fill-input" style="width:120px" placeholder="全勤几天">
              <span class="more">0=添加即获得</span>
              <input v-model.number="appCtx.newCoupon.requiredWithinDays" type="number" min="0" max="365" :disabled="!appCtx.newCoupon.requiredDays" class="fill-input" style="width:120px" placeholder="限几天内">
              <span class="more">0=不限期</span>
              <input v-model="appCtx.newCoupon.reason" class="fill-input" maxlength="50" placeholder="奖励理由（选填）" style="min-width:150px">
              <button class="btn btn-primary btn-sm" @click="appCtx.createCoupon()">添加</button>
            </div>
            <div class="pc-list" v-if="appCtx.allCoupons.length">
              <div class="pc-item" v-for="c in appCtx.allCoupons" :key="c.id" style="flex-wrap:wrap">
                <span class="ci">{{appCtx.couponIcon(c.kind)}}</span>
                <div class="c-body">
                  <b>{{c.title}}</b>
                  <span>{{c.kind_label}}<template v-if="c.required_days>0"> · 三科全勤 {{c.required_days}} 天得 1 张<template v-if="c.required_within_days>0"> · 限 {{c.required_within_days}} 天内<span class="more" style="font-size:11px"> · 超时进度清零重启</span></template><template v-else><span class="more" style="font-size:11px"> · 7天内最多缺1天，超出从头计算</span></template></template><template v-if="c.reason"> · 🎯 {{c.reason}}</template></span>
                  <span v-if="c.status==='active'">已获得 {{c.granted_count}} 张 · 剩余 {{c.left}} 张</span>
                  <span v-else>已停用（历史获得 {{c.granted_count}} 张）</span>
                </div>
                <button v-if="c.status==='active' && c.left>0" class="btn btn-success btn-sm" @click="appCtx.redeemCoupon(c)">核销 1 张</button>
                <button class="btn btn-sm" :class="c.status==='active' ? 'btn-ghost' : 'btn-primary'" @click="appCtx.toggleCoupon(c)">{{c.status==='active' ? '停用' : '启用'}}</button>
              </div>
            </div>
          </div>

          <div class="pc-sec">
            <div class="pc-title">🌟 心愿确认 <span class="more">孩子的心愿需要家长确认才能开始，达标后由家长兑现</span></div>
            <div class="pc-list" v-if="appCtx.pendingWishes.length">
              <div class="pc-item" v-for="w in appCtx.pendingWishes" :key="w.id" style="flex-wrap:wrap">
                <div class="c-body" style="flex:1"><b>{{w.title}}</b><span>{{w.status==='pending' ? '待确认' : '已完成，待兑现'}} · 进度 {{w.progress}}/{{w.target}}{{w.deadline ? ' · 截止 '+w.deadline : ''}}</span></div>
                <input v-if="w.status==='pending_redeem'" v-model="w.redeemReason" class="fill-input" maxlength="50" placeholder="兑现理由（选填）" style="max-width:150px">
                <button class="btn btn-success btn-sm" @click="appCtx.confirmWish(w)">{{w.status==='pending' ? '确认开始' : '确认兑现'}}</button>
                <button class="btn btn-ghost btn-sm" @click="appCtx.archiveWish(w)">移除</button>
              </div>
            </div>
            <p v-else class="pc-empty">没有待处理的心愿</p>
          </div>

          <div class="pc-sec">
            <div class="pc-title">🔐 修改家长密码 <span class="more">需验证当前密码</span></div>
            <div class="pc-row" style="flex-wrap:wrap">
              <input v-model="appCtx.pwdForm.old" type="password" class="fill-input" maxlength="32" placeholder="当前密码" style="max-width:140px">
              <input v-model="appCtx.pwdForm.new1" type="password" class="fill-input" maxlength="32" placeholder="新密码" style="max-width:140px">
              <input v-model="appCtx.pwdForm.new2" type="password" class="fill-input" maxlength="32" placeholder="再输一次" style="max-width:140px">
              <button class="btn btn-primary btn-sm" @click="appCtx.changeParentPwd()">修改</button>
            </div>
          </div>
          </template>

          <!-- ④ 加载/校验中：避免首屏 parentPhase='' 误落入「已解锁」面板造成闪烁 -->
          <template v-else>
            <div class="pc-sec">
              <div class="pc-title">🔄 正在校验家长密码…</div>
              <p class="pc-hint">请稍候，正在确认家长管理模式</p>
            </div>
          </template>
        </div>
</div>
</template>

<script>
// SettingsView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'SettingsView',
  inject: ['appCtx'],
}
</script>
