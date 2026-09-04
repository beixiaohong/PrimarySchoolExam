<template>
  <!-- 学习配置类：每日任务设置 / 试卷最少题数 / 学习同步(含教学进度合并) / 网课设置。默认收起。 -->
  <div class="pc-fold-group">
    <details class="pc-fold">
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">📋 每日任务设置</span>
        <span class="more">管理强制任务和可选任务</span>
      </summary>
      <div class="pc-fold-body">
        <div v-if="appCtx.taskSettings" style="font-size:13px;color:#666;margin-bottom:8px">
          强制任务 {{appCtx.mandatorySummary}} · 可选任务 {{(appCtx.taskSettings.optional || []).length}} 个已配置
          <div style="margin-top:4px">打开「管理任务」可更换每科任务类型（如数学同步练、语文阅读+家庭作业、英语朗读+背单词）</div>
        </div>
        <div class="pc-row" style="margin-top:8px">
          <button class="btn btn-primary btn-sm" @click="appCtx.showTaskSettingsDialog()">管理任务</button>
        </div>
      </div>
    </details>

    <details class="pc-fold">
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">📝 试卷最少题数</span>
        <span class="more">孩子生成试卷（含每日练习）不得少于这个数</span>
      </summary>
      <div class="pc-fold-body">
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
    </details>

    <!-- 学习同步 + 教学进度合并：原 hint 就写着「课堂同步需先在下方设置教学进度」，两者强相关，并到一个区块 -->
    <details class="pc-fold">
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">📅 学习同步与教学进度</span>
        <span class="more">学期解锁 · 课堂同步 · 小升初衔接 · 英语词书单元</span>
      </summary>
      <div class="pc-fold-body">
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
        <div class="pc-subtitle">📖 教学进度 <span class="more">孩子英语当前词书/单元，课堂同步按此出题</span></div>
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
    </details>

    <details class="pc-fold">
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">🎬 网课设置</span>
        <span class="more">给孩子添加网课视频（支持 b站/腾讯视频/直链 mp4）</span>
      </summary>
      <div class="pc-fold-body">
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
    </details>
  </div>
</template>

<script>
// 家长管理·学习配置面板。仅 inject appCtx，纯模板，无自身业务 data/methods。
export default {
  name: 'ParentStudyConfig',
  inject: ['appCtx'],
}
</script>
