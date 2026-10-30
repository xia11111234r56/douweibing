var api = require('../../utils/api')

Page({
  data: {
    record: null,
    severityTagClass: 'tag-green',
    treatments: [],
    feedback: {
      recognitionId: null,
      canShow: false,      // 记录带 recognitionId 且未提交过 → 显示反馈卡片
      wrongMode: false,    // 点击「纠错」后展开病害/严重度修正
      submitting: false,
      submitted: false,
      submittedText: '',    // 提交后显示的纠错结果
      diseases: [],
      diseaseNames: [],
      diseaseIndex: -1,
      severities: ['轻度', '中度', '重度'],
      severityIndex: -1,   // 纠错严重度；健康时无需选择
      isHealthy: false,    // 选中的正确病害是否为「健康」
      // 识别结果作为纠错默认值：病害与严重度独立修正，默认选中识别值
      predDiseaseIndex: -1,
      predSeverityIndex: -1,
      canSubmit: false     // 至少一项与识别结果不同才可提交
    }
  },

  onLoad(options) {
    var id = options.id
    var record = id ? getApp().getRecordById(id) : (getApp().getRecords()[0] || null)
    if (!record) {
      wx.showToast({ title: '记录不存在', icon: 'none' })
      wx.navigateBack()
      return
    }
    var cls = 'tag-green'
    if (record.severity === '中度') cls = 'tag-orange'
    if (record.severity === '重度') cls = 'tag-red'

    // 防治方案按方法类型分组展示
    var treatments = (record.treatments || []).map(function (t) {
      return {
        method_type: t.method_type,
        content: t.content
      }
    })

    this.setData({
      record: record,
      severityTagClass: cls,
      treatments: treatments
    })

    this.initFeedback(record)
    // 从「我的记录」纠错入口进入时直接展开病害选择
    if (options.correct === '1' && this.data.feedback.canShow && !this.data.feedback.submitted) {
      this.setData({ 'feedback.wrongMode': true })
    }
  },

  initFeedback(record) {
    var recognitionId = record.recognitionId
    if (!recognitionId) return // 旧版本地记录无 id，不渲染反馈入口（向后兼容）

    var app = getApp()
    if (app.hasFeedback(recognitionId)) {
      this.setData({
        'feedback.recognitionId': recognitionId,
        'feedback.canShow': true,
        'feedback.submitted': true,
        'feedback.submittedText': '已提交纠错 ✓' // 重开记录时本地只存过提交标记，显示通用文案
      })
      return
    }

    // 病害与严重度独立修正：都以识别结果作为默认值（识别为健康时无严重度可默认）
    var predIsHealthy = record.diseaseName === '健康'
    var predSevIdx = predIsHealthy
      ? -1
      : this.data.feedback.severities.indexOf(record.severity)
    this.setData({
      'feedback.recognitionId': recognitionId,
      'feedback.canShow': true,
      'feedback.predSeverityIndex': predSevIdx,
      'feedback.severityIndex': predSevIdx
    })

    // 拉取 10 类病害供纠错选择；失败静默隐藏（纠错入口仍然可点）
    var that = this
    api.get('/api/diseases').then(function (list) {
      if (!list || !list.length) return
      var predIdx = -1
      for (var k = 0; k < list.length; k++) {
        if (list[k].id === record.diseaseId) { predIdx = k; break }
      }
      that.setData({
        'feedback.diseases': list,
        'feedback.diseaseNames': list.map(function (d) { return d.name }),
        'feedback.predDiseaseIndex': predIdx,
        'feedback.diseaseIndex': predIdx,
        'feedback.isHealthy': predIdx >= 0 && list[predIdx].name === '健康'
      })
      that.refreshSubmit()
    }).catch(function () {})
  },

  startCorrect() {
    this.setData({ 'feedback.wrongMode': true })
  },

  onPickDisease(e) {
    var i = Number(e.detail.value)
    var list = this.data.feedback.diseases
    var isHealthy = !!(list[i] && list[i].name === '健康')
    // 换病害：健康 → 严重度置空；非健康 → 默认回到识别出的严重度
    var sevIdx = isHealthy
      ? -1
      : (this.data.feedback.predSeverityIndex >= 0 ? this.data.feedback.predSeverityIndex : -1)
    this.setData({
      'feedback.diseaseIndex': i,
      'feedback.isHealthy': isHealthy,
      'feedback.severityIndex': sevIdx
    })
    this.refreshSubmit()
  },

  onPickSeverity(e) {
    this.setData({ 'feedback.severityIndex': Number(e.currentTarget.dataset.index) })
    this.refreshSubmit()
  },

  refreshSubmit() {
    var f = this.data.feedback
    var valid = f.diseaseIndex >= 0 && (f.isHealthy || f.severityIndex >= 0)
    // 至少一项与识别结果不同才允许提交（避免空纠错）
    var diseaseChanged = f.diseaseIndex >= 0 && f.diseaseIndex !== f.predDiseaseIndex
    var severityChanged = !f.isHealthy && f.severityIndex >= 0 && f.severityIndex !== f.predSeverityIndex
    this.setData({ 'feedback.canSubmit': valid && (diseaseChanged || severityChanged) })
  },

  // 病害与严重度各自独立修正：识别结果已默认预选，未改动无需提交
  submitCorrect() {
    var f = this.data.feedback
    var list = f.diseases
    if (f.diseaseIndex < 0 || !list[f.diseaseIndex]) {
      wx.showToast({ title: '请选择正确病害', icon: 'none' })
      return
    }
    // 健康 = 无病害，无需严重度；非健康必须选轻/中/重
    if (!f.isHealthy && (f.severityIndex < 0 || !f.severities[f.severityIndex])) {
      wx.showToast({ title: '请选择严重度', icon: 'none' })
      return
    }
    if (!f.canSubmit) {
      wx.showToast({ title: '识别结果没有改动，无需提交', icon: 'none' })
      return
    }
    var d = list[f.diseaseIndex]
    var severity = f.isHealthy ? null : f.severities[f.severityIndex]
    var diseaseChanged = f.diseaseIndex !== f.predDiseaseIndex
    var text
    if (f.isHealthy) {
      text = '已纠错：纠正为 健康'
    } else if (diseaseChanged) {
      text = '已纠错：纠正为 ' + d.name + (severity ? '（' + severity + '）' : '')
    } else {
      text = '已纠错：严重度修正为 ' + severity
    }
    this.submitFeedback(
      {
        is_correct: false,
        corrected_disease_id: d.id,
        corrected_severity: severity
      },
      text
    )
  },

  submitFeedback(body, submittedText) {
    var that = this
    var recognitionId = this.data.feedback.recognitionId
    this.setData({ 'feedback.submitting': true })
    api.post('/api/recognitions/' + recognitionId + '/feedback', body)
      .then(function () {
        getApp().saveFeedback(recognitionId)
        that.setData({
          'feedback.submitting': false,
          'feedback.submitted': true,
          'feedback.wrongMode': false,
          'feedback.submittedText': submittedText || '已提交纠错 ✓'
        })
        wx.showToast({ title: '纠错已提交', icon: 'success' })
      })
      .catch(function (err) {
        that.setData({ 'feedback.submitting': false })
        var msg = (err && err.detail) || '提交失败，请稍后重试'
        wx.showToast({ title: msg, icon: 'none' })
      })
  },

  goDiseaseDetail() {
    var id = this.data.record && this.data.record.diseaseId
    if (!id) {
      wx.showToast({ title: '暂无对应百科', icon: 'none' })
      return
    }
    wx.navigateTo({ url: '/pages/knowledge/disease-detail?id=' + id })
  },

  reDiagnose() {
    wx.redirectTo({ url: '/pages/camera/camera' })
  },

  backHome() {
    wx.switchTab({ url: '/pages/index/index' })
  },

  previewImage() {
    if (this.data.record && this.data.record.image) {
      wx.previewImage({ urls: [this.data.record.image] })
    }
  }
})
