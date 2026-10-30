var env = require('../../config/env')

Page({
  data: {
    userInfo: null,
    stats: {
      diagnosisCount: 0,
      daysUsed: 0,
      lastDisease: ''
    },
    showEditModal: false,
    tempAvatarUrl: '',
    tempNickname: '',
    webUrl: env.API_BASE_URL
  },

  onShow() {
    this.loadUser()
    this.loadStats()
  },

  loadUser() {
    var u = getApp().globalData.userInfo || wx.getStorageSync('userInfo') || null
    this.setData({ userInfo: u })
  },

  loadStats() {
    var records = getApp().getRecords()
    var count = records.length
    var daysUsed = 0
    var lastDisease = ''
    if (count > 0) {
      lastDisease = records[0].diseaseName || ''
      var firstId = records[count - 1].id || ''
      var ts = parseInt(firstId.split('_')[1], 10)
      if (ts) {
        daysUsed = Math.ceil((Date.now() - ts) / (1000 * 60 * 60 * 24))
        if (daysUsed < 1) daysUsed = 1
      }
    }
    this.setData({
      stats: {
        diagnosisCount: count,
        daysUsed: daysUsed,
        lastDisease: lastDisease
      }
    })
  },

  // ===== 资料编辑（本地存储）=====
  openEdit() {
    var u = this.data.userInfo || {}
    this.setData({
      showEditModal: true,
      tempAvatarUrl: u.avatarUrl || '',
      tempNickname: u.nickName || ''
    })
  },

  closeEdit() {
    this.setData({
      showEditModal: false,
      tempAvatarUrl: '',
      tempNickname: ''
    })
  },

  stopPropagation() {},

  onChooseAvatar(e) {
    this.setData({ tempAvatarUrl: e.detail.avatarUrl })
  },

  onNicknameInput(e) {
    this.setData({ tempNickname: e.detail.value })
  },

  completeEdit(e) {
    // 以表单提交读到的原生输入值为准（微信昵称快速填入不触发 input/blur 也能拿到），再兜底 data
    var nickname = (e && e.detail && e.detail.value && e.detail.value.nickname) || this.data.tempNickname || ''
    if (!this.data.tempAvatarUrl || !nickname.trim()) {
      wx.showToast({ title: '请选择头像并填写昵称', icon: 'none' })
      return
    }
    var userInfo = {
      nickName: nickname.trim(),
      avatarUrl: this.data.tempAvatarUrl
    }
    getApp().setUser(userInfo)
    this.setData({ userInfo: userInfo, showEditModal: false })
    wx.showToast({ title: '已保存', icon: 'success' })
  },

  clearUser() {
    var that = this
    wx.showModal({
      title: '清除资料',
      content: '将清除本机保存的昵称与头像，识别记录不受影响。确定继续吗？',
      success: function (res) {
        if (res.confirm) {
          getApp().logout()
          that.setData({ userInfo: null })
          wx.showToast({ title: '已清除', icon: 'none' })
        }
      }
    })
  },

  // ===== 页面跳转 =====
  goToRecords() {
    wx.navigateTo({ url: '/pages/profile/records' })
  },

  goToAbout() {
    wx.navigateTo({ url: '/pages/profile/about' })
  },

  goToFeedback() {
    wx.navigateTo({ url: '/pages/profile/feedback' })
  },

  // 复制 Web 平台网址
  copyWebUrl() {
    wx.setClipboardData({
      data: this.data.webUrl,
      success: function () {
        wx.showToast({ title: '网址已复制', icon: 'none' })
      }
    })
  }
})
