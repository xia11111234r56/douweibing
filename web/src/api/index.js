import axios from 'axios'
import { authState, clearAuth } from '../auth'

const http = axios.create({
  baseURL: '/api',
  timeout: 60000, // 识别/图谱可能较慢
})

// 请求自动带 token；401 时清空登录态并跳回登录页
http.interceptors.request.use((config) => {
  if (authState.token) config.headers.Authorization = `Bearer ${authState.token}`
  return config
})
http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response && err.response.status === 401) {
      clearAuth()
      if (window.location.pathname !== '/login') window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

// ---- 认证 ----
export const register = (username, password) => http.post('/auth/register', { username, password })
export const login = (username, password) => http.post('/auth/login', { username, password })
export const getMe = () => http.get('/users/me')
export const changePassword = (oldPassword, newPassword) =>
  http.post('/auth/change-password', { old_password: oldPassword, new_password: newPassword })

// ---- 用户管理（管理员）----
export const getUsers = (params) => http.get('/users', { params })
export const updateUserRole = (id, role) => http.patch(`/users/${id}/role`, { role })
export const resetUserPassword = (id, newPassword) =>
  http.patch(`/users/${id}/password`, { new_password: newPassword })

// ---- 识别 ----
export const recognize = (imageBase64, env = null) =>
  http.post('/recognize', { image_base64: imageBase64, env })

// ---- 识别记录 ----
export const getRecognitions = (params) => http.get('/recognitions', { params })

// ---- 识别纠错反馈 ----
export const submitRecognitionFeedback = (id, body) =>
  http.post(`/recognitions/${id}/feedback`, body)
export const getFeedbacks = (params) => http.get('/feedback', { params })
export const exportFeedbacks = () =>
  http.get('/feedback/export', { responseType: 'blob' })

// ---- 病害知识 ----
export const listDiseases = (params) => http.get('/diseases', { params })
export const getDisease = (id) => http.get(`/diseases/${id}`)
export const createDisease = (body) => http.post('/diseases', body)
export const updateDisease = (id, body) => http.put(`/diseases/${id}`, body)
export const deleteDisease = (id) => http.delete(`/diseases/${id}`)

// ---- 多维检索 ----
export const searchDiseases = (params) => http.get('/search', { params })

// ---- 知识图谱 ----
export const getGraph = () => http.get('/graph')
export const createNode = (body) => http.post('/graph/nodes', body)
export const createEdge = (body) => http.post('/graph/edges', body)
// 图引擎状态 + 图算法端点（防治路径推荐 / 可解释推理链）
export const getGraphEngine = () => http.get('/graph/engine')
export const getGraphPath = (params) => http.get('/graph/path', { params })
export const getGraphReason = (params) => http.get('/graph/reason', { params })

// ---- GIS ----
export const getMungbean = (params) => http.get('/gis/mungbean', { params })
export const getGeojson = (name) => http.get(`/gis/geojson/${name}`)
export const getRisk = (params) => http.get('/gis/risk', { params })

// ---- 统计 ----
export const getStats = () => http.get('/stats/overview')
export const getStatsEnv = () => http.get('/stats/env')
export const getStatsCross = () => http.get('/stats/cross')

// ---- 系统健康 ----
export const getHealth = () => http.get('/health')

// ---- 操作日志（管理员）----
export const getLogs = (params) => http.get('/logs', { params })

export default http
