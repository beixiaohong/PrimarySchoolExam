import axios from 'axios'

// 后端同源托管，baseURL 留空即可命中 /api/admin/*（由 FastAPI 路由提供）。
const api = axios.create({ baseURL: '' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  if (token) {
    config.headers.Authorization = 'Bearer ' + token
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response && err.response.status
    if (status === 401) {
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_username')
      if (location.hash.indexOf('login') === -1) {
        location.hash = '#/login'
      }
    }
    return Promise.reject(err)
  }
)

export default api
