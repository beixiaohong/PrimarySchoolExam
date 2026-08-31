<template>
  <div class="fade-enter">
    <div class="sub-tabs">
      <button class="pill" :class="{active: appCtx.reciteSub==='words'}" @click="appCtx.switchRecite('words')">📖 背单词</button>
      <button class="pill" :class="{active: appCtx.reciteSub==='classical'}" @click="appCtx.switchRecite('classical')">📜 古诗文</button>
    </div>

    <!-- 背单词 -->
    <div v-if="appCtx.reciteSub==='words'">
      <div class="grid-2">
        <div class="card recite-card">
          <div class="card-head"><b>📖 今日新词</b><span class="tag tag-blue">{{appCtx.vocabToday.stats.new_remaining}} 个待学</span></div>
          <p class="card-desc">每轮学 {{appCtx.vocabToday.stats.new_remaining}} 个新单词，学完可再来一轮，不限次数</p>
          <button class="btn btn-primary btn-lg recite-btn" :disabled="appCtx.vocabToday.stats.new_remaining<=0" @click="appCtx.startWordSession('new')">开始学习新词 →</button>
        </div>
        <div class="card recite-card">
          <div class="card-head"><b>🔁 今日复习</b><span class="tag tag-orange">{{appCtx.vocabToday.stats.due_today}} 个待复习</span></div>
          <p class="card-desc">到期的单词现在复习，记忆效果最好</p>
          <button class="btn btn-warning btn-lg recite-btn" :disabled="appCtx.vocabToday.stats.due_today<=0" @click="appCtx.startWordSession('review')">开始复习 →</button>
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-head"><b>学习进度</b><span class="more">{{appCtx.vocabToday.stats.learned}} / {{appCtx.vocabToday.stats.total_words}} 已学</span></div>
        <div class="progress" style="margin:14px 0 18px"><i :style="{width: appCtx.vocabPct+'%'}"></i></div>
        <div class="recite-stats">
          <div><b>{{appCtx.vocabToday.stats.learned}}</b><span>已学单词</span></div>
          <div><b>{{appCtx.vocabToday.stats.mastered}}</b><span>已掌握</span></div>
          <div><b>{{appCtx.vocabToday.stats.streak_days}}</b><span>连续天数</span></div>
          <div><b>{{appCtx.vocabToday.stats.new_today}}</b><span>今日新学</span></div>
        </div>
      </div>
    </div>

    <!-- 古诗文 -->
    <div v-if="appCtx.reciteSub==='classical'">
      <div class="grid-2">
        <div class="card recite-card">
          <div class="card-head"><b>📜 今日新篇</b><span class="tag tag-blue">{{appCtx.classicalToday.stats.new_remaining}} 篇待背</span></div>
          <p class="card-desc">每轮背 {{appCtx.classicalToday.stats.new_remaining}} 篇古诗文，背完可再来一轮，不限次数</p>
          <button class="btn btn-primary btn-lg recite-btn" :disabled="appCtx.classicalToday.stats.new_remaining<=0" @click="appCtx.startTextSession('new')">开始背诵 →</button>
        </div>
        <div class="card recite-card">
          <div class="card-head"><b>🔁 今日复习</b><span class="tag tag-orange">{{appCtx.classicalToday.stats.due_today}} 篇待复习</span></div>
          <p class="card-desc">按记忆曲线复习，背过的篇目要定期巩固</p>
          <button class="btn btn-warning btn-lg recite-btn" :disabled="appCtx.classicalToday.stats.due_today<=0" @click="appCtx.startTextSession('review')">开始复习 →</button>
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-head"><b>📚 篇目列表</b><span class="more">已背 {{appCtx.classicalToday.stats.learned}} / {{appCtx.classicalToday.stats.total}} 篇</span></div>
        <div class="text-list" style="margin-top:6px">
          <div v-for="t in appCtx.classicalTexts" :key="t.id" class="text-item">
            <div class="t-main"><b>《{{t.title}}》</b><span>{{t.author}} · {{t.dynasty}} · {{t.grade}}年级</span></div>
            <span class="tag tag-gray">{{t.text_type==='prose'?'古文':'古诗'}}</span>
            <button class="btn btn-ghost btn-sm" @click="appCtx.openTextDetail(t)">查看</button>
          </div>
          <div v-if="!appCtx.classicalTexts.length" class="empty"><div class="em">📜</div><h3>暂无篇目</h3><p>当前年级还没有古诗文数据，换个年级试试</p></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// 背诵中心（B1 组件化第一批验证块）。
// 业务逻辑仍由 App.vue 壳通过 appOptions mixin 统一持有（壳 mounted 加载数据、壳方法处理交互），
// 本组件仅通过 inject 的 appCtx 访问壳的响应式状态与方法，自身零 data/methods。
// 后续批次按此模式把其余内联块逐一抽为 views/*.vue；真正解耦（状态下沉到 Pinia）留作 B1 后期。
export default {
  name: 'ReciteView',
  inject: ['appCtx'],
}
</script>
