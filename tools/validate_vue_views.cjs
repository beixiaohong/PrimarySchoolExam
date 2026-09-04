/**
 * 校验 admin/src/views 下全部 Vue 单文件组件（不依赖 vite build）。
 *
 * 为什么需要它：本沙箱 `vite build` 间歇失败（esbuild 派生子进程被拦），
 * 但前端改动又必须保证可构建。用 @vue/compiler-sfc 直接解析是更稳的替代方案。
 *
 * 三级校验：
 *   1. parse           —— 整体 SFC 结构
 *   2. compileScript   —— <script setup> 语法（能抓出重复声明、非法解构等）
 *   3. compileTemplate —— 模板语法
 *
 * 用法（需带 NODE_PATH=admin/node_modules，或由 tools/run_node_check.py 驱动）：
 *   node tools/validate_vue_views.cjs
 *   python tools/run_node_check.py tools/validate_vue_views.cjs
 */
const { parse, compileTemplate, compileScript } = require('@vue/compiler-sfc')
const fs = require('fs')
const path = require('path')

const dir = path.resolve(__dirname, '../admin/src/views')
const files = fs.readdirSync(dir).filter((f) => f.endsWith('.vue')).sort()

let bad = 0
const out = []

for (const f of files) {
  const src = fs.readFileSync(path.join(dir, f), 'utf8')
  const { descriptor, errors } = parse(src, { filename: f })
  if (errors && errors.length) {
    out.push(`X ${f}  PARSE: ${errors.map((e) => e.message).join('; ')}`)
    bad++
    continue
  }
  if (descriptor.scriptSetup || descriptor.script) {
    try {
      compileScript(descriptor, { id: f })
    } catch (e) {
      out.push(`X ${f}  SCRIPT: ${e.message}`)
      bad++
      continue
    }
  }
  if (descriptor.template) {
    const r = compileTemplate({
      source: descriptor.template.content,
      filename: f,
      id: f,
    })
    if (r.errors && r.errors.length) {
      out.push(`X ${f}  TEMPLATE: ${r.errors.map((e) => e.message).join('; ')}`)
      bad++
      continue
    }
  }
  out.push(`OK ${f}`)
}

out.push('')
out.push(bad === 0 ? `全部 ${files.length} 个组件校验通过` : `${bad} / ${files.length} 个组件有问题`)
// 用 ASCII 标记，避免 Windows 控制台代码页吞掉非 ASCII 字符
console.log(out.join('\n'))
process.exit(bad ? 1 : 0)
