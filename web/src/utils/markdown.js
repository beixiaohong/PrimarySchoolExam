// utils/markdown.js：极简 Markdown → HTML 渲染器（Blog 详情与编辑预览共用）。
//
// 为什么不引第三方库：项目 requirements/web 依赖里没有任何 markdown 解析器，
// 而 temp/blog.md §55 明确「不要为了架构先进引入当前项目完全没有使用的新框架」；
// 账本侧又有「新增依赖必须同步 requirements，否则线上启动 ImportError → 全站 502」的铁律。
// 因此自研一个覆盖常用语法的小渲染器，够用且零依赖。
//
// 安全：先做 HTML 转义再解析，输出里不会出现用户可控的裸标签（防 XSS）。

/** 转义 HTML 特殊字符（必须最先做，之后所有正则都在「已转义」文本上工作） */
function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** 行内语法：**粗体** *斜体* `代码` [链接](url) ![图片](url) */
function inline(s) {
  let t = escapeHtml(s);
  t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, url) => `<img class="md-img" src="${url}" alt="${alt}">`);
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, text, url) => `<a href="${url}" target="_blank" rel="noopener">${text}</a>`);
  t = t.replace(/`([^`]+)`/g, '<code class="md-code">$1</code>');
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  return t;
}

/**
 * Markdown → HTML。
 * 支持：围栏代码块、# / ## / ### 标题、- 无序列表、1. 有序列表、> 引用、
 *       --- 分隔线、行内粗体/斜体/代码/链接/图片，其余按段落处理。
 */
export function renderMarkdown(md) {
  const src = String(md == null ? '' : md).replace(/\r\n/g, '\n');
  if (!src.trim()) return '';

  const lines = src.split('\n');
  const out = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 围栏代码块：原样保留（内部不再做行内解析）
    const fence = line.match(/^```(\w*)\s*$/);
    if (fence) {
      const buf = [];
      i += 1;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) { buf.push(lines[i]); i += 1; }
      i += 1; // 跳过收尾围栏（缺失时到末尾也安全）
      out.push(`<pre class="md-pre"><code>${escapeHtml(buf.join('\n'))}</code></pre>`);
      continue;
    }

    // 标题
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      const lv = h[1].length;
      out.push(`<h${lv} class="md-h md-h${lv}">${inline(h[2])}</h${lv}>`);
      i += 1;
      continue;
    }

    // 分隔线
    if (/^(-{3,}|\*{3,})\s*$/.test(line)) {
      out.push('<hr class="md-hr">');
      i += 1;
      continue;
    }

    // 引用
    if (/^>\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^>\s?/, '')); i += 1; }
      out.push(`<blockquote class="md-quote">${inline(buf.join(' '))}</blockquote>`);
      continue;
    }

    // 无序列表
    if (/^\s*[-*+]\s+/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) { buf.push(lines[i].replace(/^\s*[-*+]\s+/, '')); i += 1; }
      out.push(`<ul class="md-ul">${buf.map(x => `<li>${inline(x)}</li>`).join('')}</ul>`);
      continue;
    }

    // 有序列表
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { buf.push(lines[i].replace(/^\s*\d+[.)]\s+/, '')); i += 1; }
      out.push(`<ol class="md-ol">${buf.map(x => `<li>${inline(x)}</li>`).join('')}</ol>`);
      continue;
    }

    // 空行
    if (!line.trim()) { i += 1; continue; }

    // 普通段落：连续非空行合并为一段（行内换行转 <br>）
    const buf = [];
    while (i < lines.length && lines[i].trim()
           && !/^```/.test(lines[i]) && !/^#{1,4}\s/.test(lines[i])
           && !/^\s*[-*+]\s+/.test(lines[i]) && !/^\s*\d+[.)]\s+/.test(lines[i])
           && !/^>\s?/.test(lines[i]) && !/^(-{3,}|\*{3,})\s*$/.test(lines[i])) {
      buf.push(lines[i]);
      i += 1;
    }
    if (buf.length) out.push(`<p class="md-p">${inline(buf.join('\n')).replace(/\n/g, '<br>')}</p>`);
  }
  return out.join('\n');
}

/** 取纯文本摘要（列表卡片用；截断到 n 字） */
export function plainSummary(md, n = 80) {
  const t = String(md == null ? '' : md)
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*`\-_![\]()]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return t.length > n ? t.slice(0, n) + '…' : t;
}
