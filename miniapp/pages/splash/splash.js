Page({
  onLoad() {
    // 进入首页前仅停留 1 秒
    setTimeout(function () {
      wx.switchTab({ url: '/pages/index/index' })
    }, 1000)
  }
})
