<template>
<div class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#11998e,#38ef7d)">
          <div style="flex:1">
            <h1>🌳 成长树</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">你的每一次学习都在浇灌这棵树，只和自己比，看着它慢慢长大！</p>
          </div>
          <div class="tree-score" v-if="appCtx.treeData">
            <div class="tree-score-num">{{appCtx.treeData.score}}</div>
            <div class="tree-score-label">🌱 成长值</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="tree-stage" v-if="appCtx.treeData">
            <div class="tree-emoji">{{appCtx.treeData.stage.emoji}}</div>
            <div class="tree-name">{{appCtx.treeData.stage.name}}</div>
            <div class="tree-bar"><div class="tree-fill" :style="{width: appCtx.treeData.stage.pct + '%'}"></div></div>
            <div class="tree-bar-text" v-if="appCtx.treeData.stage.next">再攒 {{appCtx.treeData.stage.next - appCtx.treeData.score}} 成长值，长成「{{appCtx.treeStageName(appCtx.treeData.stage.stage + 1)}}」！</div>
            <div class="tree-bar-text" v-else>已经长成「森林之王」，太厉害了！</div>
            <div class="tree-path">
              <div v-for="(s, i) in appCtx.treeStages" :key="i" class="tree-path-node"
                   :class="{done: i <= (appCtx.treeData.stage.stage), cur: i === appCtx.treeData.stage.stage}">
                <span class="tree-path-emoji">{{s.emoji}}</span><span class="tree-path-name">{{s.name}}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>📈 成长值来源</b><span class="more" style="font-size:12px;color:var(--text-3)">总计 {{appCtx.treeData ? appCtx.treeData.score : 0}}</span></div>
          <div v-if="!appCtx.treeData || !appCtx.treeData.parts.length" class="empty" style="padding:24px">
            <div class="em">🌱</div><h3>成长值还是 0</h3><p>去刷一套题，或者背几个单词，小树就会发芽啦！</p>
          </div>
          <div v-else class="tree-parts">
            <div v-for="p in appCtx.treeData.parts" :key="p.key" class="tree-part-item">
              <span class="tree-part-label">{{p.label}}<em class="tree-part-val">{{p.value}} 次</em></span>
              <span class="tree-part-score">+{{p.score}}</span>
            </div>
          </div>
        </div>
</div>
</template>

<script>
// TreeView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'TreeView',
  inject: ['appCtx'],
}
</script>
