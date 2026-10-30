Page({
  data: {
    records: []
  },

  onShow() {
    this.loadRecords()
  },

  loadRecords() {
    var app = getApp()
    var records = app.getRecords().map(function (r) {
      var cls = 'tag-green'
      if (r.severity === '中度') cls = 'tag-orange'
      if (r.severity === '重度') cls = 'tag-red'
      // 纠错入口：有 recognitionId 且本地未提交过才显示；已提交过则显示「已纠错」
      var hasFed = !!(r.recognitionId && app.hasFeedback(r.recognitionId))
      return {
        id: r.id,
        image: r.image || '',
        diseaseName: r.diseaseName || '未知',
        severity: r.severity || '—',
        severityClass: cls,
        confidence: r.confidence || 0,
        time: r.time || '',
        hasFed: hasFed,
        canCorrect: !!r.recognitionId && !hasFed
      }
    })
    this.setData({ records: records })
  },

  viewRecord(e) {
    var id = e.currentTarget.dataset.id
    wx.navigateTo({ url: '/pages/result/result?id=' + id })
  },

  // 列表直接纠错：进入结果页，反馈卡片自动展开病害选择（未提交过才会显示入口）
  goCorrect(e) {
    var id = e.currentTarget.dataset.id
    wx.navigateTo({ url: '/pages/result/result?id=' + id + '&correct=1' })
  },

  goToDiagnose() {
    wx.switchTab({ url: '/pages/index/index' })
  }
})
