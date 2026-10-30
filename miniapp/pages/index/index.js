var api = require('../../utils/api')
var IMAGES = require('../../config/images')

Page({
  data: {
    diseases: []
  },

  onShow() {
    this.loadDiseases()
  },

  // 常见病害：从后端 /api/diseases 拉取真实 10 类（按 id 前 6 个展示）
  loadDiseases() {
    var that = this
    api.get('/api/diseases').then(function (list) {
      var items = (list || []).slice(0, 6).map(function (d) {
        return {
          id: d.id,
          name: d.name,
          disease_type: d.disease_type,
          image: IMAGES.map(d.name),
          initial: d.name.charAt(0)
        }
      })
      that.setData({ diseases: items })
    }).catch(function (err) {
      console.warn('加载常见病害失败:', err)
    })
  },

  openCamera() {
    wx.navigateTo({ url: '/pages/camera/camera' })
  },

  goToRecords() {
    wx.navigateTo({ url: '/pages/profile/records' })
  },

  goToDiseaseKnowledge() {
    wx.navigateTo({ url: '/pages/knowledge/disease' })
  },

  goToOverview() {
    wx.navigateTo({ url: '/pages/knowledge/overview' })
  },

  goToPlantingKnowledge() {
    wx.navigateTo({ url: '/pages/knowledge/planting' })
  },

  viewDisease(e) {
    var id = e.currentTarget.dataset.id
    wx.navigateTo({ url: '/pages/knowledge/disease-detail?id=' + id })
  }
})
