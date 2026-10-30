var env = require('./config/env')

App({
  globalData: {
    userInfo: null
  },

  // 后端地址统一从 config/env.js 读取，上线只改那一处
  API_BASE_URL: env.API_BASE_URL,

  onLaunch() {
    this.loadLocalUser()
  },

  // ===== 本地用户信息（不依赖微信云 / 后端登录）=====
  loadLocalUser() {
    var u = wx.getStorageSync('userInfo')
    if (u) this.globalData.userInfo = u
  },

  setUser(u) {
    this.globalData.userInfo = u
    wx.setStorageSync('userInfo', u)
  },

  logout() {
    this.globalData.userInfo = null
    wx.removeStorageSync('userInfo')
  },

  // ===== 本地诊断记录（wx.setStorageSync，最新在前）=====
  saveRecord(record) {
    var list = wx.getStorageSync('diag_records') || []
    list.unshift(record)
    if (list.length > 100) list = list.slice(0, 100)
    wx.setStorageSync('diag_records', list)
  },

  getRecords() {
    return wx.getStorageSync('diag_records') || []
  },

  getRecordById(id) {
    var list = this.getRecords()
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) return list[i]
    }
    return null
  },

  // ===== 本地纠错反馈标记（按识别记录去重）=====
  saveFeedback(recognitionId) {
    var list = wx.getStorageSync('diag_feedback') || []
    if (list.indexOf(recognitionId) === -1) list.push(recognitionId)
    wx.setStorageSync('diag_feedback', list)
  },

  hasFeedback(recognitionId) {
    var list = wx.getStorageSync('diag_feedback') || []
    return list.indexOf(recognitionId) !== -1
  }
})
