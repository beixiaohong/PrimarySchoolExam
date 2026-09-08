// 验证新 Vue 文件模板与脚本能否编译
// 用 node + @vue/compiler-sfc（项目本地 node_modules/web/node_modules/@vue/compiler-sfc@3.5.41）
const path = require('path');
const fs = require('fs');

// 绝对路径：项目根 + web/node_modules/@vue/compiler-sfc
const PROJECT_ROOT = process.cwd();
const compilerSfcPath = path.join(PROJECT_ROOT, 'web/node_modules/@vue/compiler-sfc/dist/compiler-sfc.cjs.js');
const { parse, compileTemplate, compileScript } = require(compilerSfcPath);

// 待验证文件
const targets = [
  'web/src/App.vue',
  'web/src/views/LedgerView.vue',
  'web/src/views/ImView.vue',
  'web/src/views/WalletView.vue',
  'web/src/components/ledger/LedgerRecord.vue',
  'web/src/components/ledger/LedgerBills.vue',
  'web/src/components/ledger/LedgerAnalysis.vue',
  'web/src/components/ledger/LedgerSettings.vue',
  'web/src/components/im/ImChats.vue',
  'web/src/components/im/ImMessages.vue',
  'web/src/components/im/ImContacts.vue',
  'web/src/components/im/ImSettings.vue',
  'web/src/components/im/ImGroupInfo.vue',
];

let totalErrors = 0;
const summary = [];

for (const rel of targets) {
  const fp = path.join(PROJECT_ROOT, rel);
  if (!fs.existsSync(fp)) {
    console.log(`[SKIP] ${rel} (not found)`);
    continue;
  }
  const source = fs.readFileSync(fp, 'utf-8');
  const filename = path.basename(fp);
  const errs = [];

  // 1) 解析 SFC 结构
  const { descriptor, errors: parseErrors } = parse(source, { filename });
  if (parseErrors && parseErrors.length) {
    errs.push(`parse: ${parseErrors.map(e => e.message || e).join('; ')}`);
  }

  // 2) 编译模板（如果存在）
  if (descriptor.template) {
    try {
      const tpl = compileTemplate({
        source: descriptor.template.content,
        filename,
        id: filename,
        scoped: descriptor.styles.some(s => s.scoped),
      });
      if (tpl.errors && tpl.errors.length) {
        errs.push(`template: ${tpl.errors.map(e => e.message || e).join('; ')}`);
      }
    } catch (e) {
      errs.push(`template-throw: ${e.message || e}`);
    }
  }

  // 3) 编译脚本（如果存在）
  if (descriptor.script || descriptor.scriptSetup) {
    try {
      const scriptResult = compileScript(descriptor, { id: filename });
      if (scriptResult.errors && scriptResult.errors.length) {
        errs.push(`script: ${scriptResult.errors.map(e => e.message || e).join('; ')}`);
      }
    } catch (e) {
      errs.push(`script-throw: ${e.message || e}`);
    }
  }

  if (errs.length === 0) {
    summary.push(`  ✓ ${rel.replace('web/src/', '')}`);
  } else {
    totalErrors += errs.length;
    summary.push(`  ✗ ${rel.replace('web/src/', '')}`);
    for (const e of errs) summary.push(`     - ${e}`);
  }
}

console.log('=== Vue SFC 编译验证 ===');
console.log(summary.join('\n'));
console.log(`\n总计错误: ${totalErrors}`);
process.exit(totalErrors === 0 ? 0 : 1);