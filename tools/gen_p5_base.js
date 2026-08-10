// 一次性生成 P5 Vite 工程的基础文件：
// 1) web/src/logic/appOptions.js  ← frontend/static/app.js（转为可导入的 options 对象）
// 2) web/src/App.vue              ← frontend/index.html 主体（包进 <template>）
// 3) web/src/styles/style.css     ← frontend/static/style.css（原样复制）
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const read = p => fs.readFileSync(path.join(ROOT, p), 'utf8')
const write = (p, c) => {
  const full = path.join(ROOT, p)
  fs.mkdirSync(path.dirname(full), { recursive: true })
  fs.writeFileSync(full, c, 'utf8')
  console.log('wrote', p, '(' + c.length + ' chars)')
}

// ---- 1) appOptions.js ----
let js = read('frontend/static/app.js')
js = js.replace(/^const\s*\{\s*createApp\s*\}\s*=\s*Vue;\s*/, '')
js = js.replace(/createApp\(\s*\{/, 'const appOptions = {')
js = js.replace(/\}\s*\)\s*\.mount\(\s*['"]#app['"]\s*\)\s*;?\s*$/, '}\n\nexport default appOptions\n')
write('web/src/logic/appOptions.js', js)

// ---- 2) App.vue（先原样生成，分组导航/TabBar/钱包等随后用 SearchReplace 叠加）----
const html = read('frontend/index.html')
const startMark = '<div id="app">'
const start = html.indexOf(startMark) + startMark.length
const end = html.indexOf('<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas')
let body = html.slice(start, end).trimEnd()
body = body.slice(0, body.lastIndexOf('</div>'))  // 去掉 #app 的闭合标签
const appVue = `<template>
<div class="app-root">
${body}
</div>
</template>

<script>
import appOptions from './logic/appOptions.js'
export default { ...appOptions }
<\/script>
`
write('web/src/App.vue', appVue)

// ---- 3) style.css ----
write('web/src/styles/style.css', read('frontend/static/style.css'))

console.log('done')
