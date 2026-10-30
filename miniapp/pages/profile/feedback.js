Page({
  data: {
    content: '',
    contact: '',
    submitting: false
  },

  onContentChange(e) {
    this.setData({ content: e.detail.value })
  },

  onContactChange(e) {
    this.setData({ contact: e.detail.value })
  },

  submitFeedback() {
    if (!this.data.content.trim()) {
      wx.showToast({ title: '请输入反馈内容', icon: 'none' })
      return
    }
    if (this.data.submitting) return

    var that = this
    this.setData({ submitting: true })

    var item = {
      content: this.data.content.trim(),
      contact: this.data.contact.trim(),
      time: new Date().toLocaleString()
    }
    var list = wx.getStorageSync('feedbacks') || []
    list.unshift(item)
    if (list.length > 50) list = list.slice(0, 50)
    wx.setStorageSync('feedbacks', list)

    this.setData({ submitting: false })
    wx.showToast({ title: '已记录，感谢反馈', icon: 'success' })
    setTimeout(function () {
      wx.navigateBack()
    }, 1200)
  }
})
