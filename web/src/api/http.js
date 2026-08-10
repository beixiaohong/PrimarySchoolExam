// 统一请求封装（移植自旧版 app.js 的 api()）：
// 家长解锁期间自动携带 X-Parent-Pwd 头，服务端敏感接口据此校验。
export function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' }
  try {
    const pp = sessionStorage.getItem('zx_parent_pwd')
    if (pp) headers['X-Parent-Pwd'] = pp
  } catch (e) { /* 隐私模式等异常忽略 */ }
  return fetch(path, Object.assign({ headers }, opts)).then(async r => {
    const t = await r.text()
    let d = t
    try { d = JSON.parse(t) } catch (e) { /* 非 JSON */ }
    if (!r.ok) throw new Error(typeof d === 'object' && d ? (d.detail || '请求失败') : String(d))
    return d
  })
}

export default api
