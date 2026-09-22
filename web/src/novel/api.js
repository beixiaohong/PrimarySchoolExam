// 小说站 API 封装（同源 /api/novel/*，游客可读；书架与进度需登录）
//
// 登录态复用主站的 zx_token（与主站 App 一致），未登录时书架/进度接口会返回 401，
// 由调用方降级处理（不阻塞阅读）。
const TOKEN_KEY = 'zx_token'

function authHeaders() {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: 'Bearer ' + token } : {}
}

function buildUrl(path, params) {
  const qs = new URLSearchParams()
  Object.keys(params || {}).forEach((k) => {
    const v = params[k]
    if (v !== undefined && v !== null && v !== '') qs.append(k, v)
  })
  const s = qs.toString()
  return s ? `${path}?${s}` : path
}

async function request(path, params, options = {}) {
  const res = await fetch(buildUrl(path, params), {
    headers: { ...authHeaders(), ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    let msg = `请求失败(${res.status})`
    try {
      const d = await res.json()
      msg = d.message || d.detail || msg
    } catch (e) { /* 非 JSON 响应沿用默认文案 */ }
    const err = new Error(msg)
    err.status = res.status
    throw err
  }
  return res.json()
}

export const api = {
  // ── 书城 ──
  categories: () => request('/api/novel/categories'),
  list: (params) => request('/api/novel/list', params),
  detail: (id) => request(`/api/novel/${id}`),
  chapters: (id, params) => request(`/api/novel/${id}/chapters`, params),
  // 下滑增量加载核心：from=起始段号，limit=本次段数
  read: (id, from, limit = 1) => request(`/api/novel/${id}/read`, { from, limit }),
  // ── 需登录 ──
  shelf: () => request('/api/novel/shelf'),
  toggleShelf: (id, inShelf) => request(`/api/novel/${id}/shelf`, {}, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ in_shelf: inShelf }),
  }),
  saveProgress: (id, chapterIdx) => request(`/api/novel/${id}/progress`, {}, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chapter_idx: chapterIdx }),
  }),
  // ── 书签（需登录）──
  bookmarks: (id) => request(`/api/novel/${id}/bookmarks`),
  addBookmark: (id, chapterIdx, note = '') => request(`/api/novel/${id}/bookmarks`, {}, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chapter_idx: chapterIdx, note }),
  }),
  deleteBookmark: (id, bid) => request(`/api/novel/${id}/bookmarks/${bid}`, {}, {
    method: 'DELETE',
  }),
}

export const isLogin = () => !!localStorage.getItem(TOKEN_KEY)
