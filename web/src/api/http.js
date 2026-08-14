// 统一请求封装（移植自旧版 app.js 的 api()）：
// 家长解锁期间自动携带 X-Parent-Pwd 头，服务端敏感接口据此校验。
export function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' }
  try {
    // 家长解锁后台期间，sessionStorage 存有家长密码；此处自动附加到请求头，
    // 服务端据此授权访问/操作敏感数据（如补签、转账），避免每次手动传参
    const pp = sessionStorage.getItem('zx_parent_pwd')
    if (pp) headers['X-Parent-Pwd'] = pp
    // 登录会话 token：后端业务接口要求 Bearer 鉴权
    const tk = localStorage.getItem('zx_token')
    if (tk) headers['Authorization'] = 'Bearer ' + tk
  } catch (e) { /* 隐私模式等异常忽略 */ }
  return fetch(path, Object.assign({ headers }, opts)).then(async r => {
    // 401：登录态失效，清除本地会话并回到登录页
    if (r.status === 401) {
      const hadSession = !!localStorage.getItem('zx_user')
      try { localStorage.removeItem('zx_user'); localStorage.removeItem('zx_token') } catch (e) {}
      if (path.indexOf('/api/auth/') === -1) {
        // 业务接口 401：清会话 + 跳登录页（仅首次有 session 时跳）。
        // 返回永不 resolve 的 Promise，阻止各业务 .catch 弹出重复的"登录已过期" toast
        if (hadSession) location.href = '/'
        return new Promise(() => {})
      }
      throw new Error('登录已过期，请重新登录')
    }
    const t = await r.text()
    let d = t
    try { d = JSON.parse(t) } catch (e) { /* 非 JSON（如纯文本响应）原样返回 */ }
    // 统一错误封装：优先取后端 detail 字段作为错误信息
    if (!r.ok) throw new Error(typeof d === 'object' && d ? (d.detail || '请求失败') : String(d))
    return d
  })
}

export default api
