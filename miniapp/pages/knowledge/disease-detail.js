var IMAGES = require('../../config/images')
var api = require('../../utils/api')

Page({
  data: {
    detail: null,
    gallery: [],
    loading: true,
    loadError: ''
  },

  onLoad(options) {
    this.setData({ targetId: options && options.id ? String(options.id) : '' })
    this.fetchDetail()
  },

  fetchDetail() {
    var that = this
    this.setData({ loading: true, loadError: '' })
    api.get('/api/diseases').then(function (list) {
      var targetId = that.data.targetId
      var found = null
      for (var i = 0; i < list.length; i++) {
        if (String(list[i].id) === targetId) {
          found = list[i]
          break
        }
      }
      if (!found) {
        that.setData({ loading: false, loadError: '没有找到该病害' })
        return
      }
      var detail = {
        id: found.id,
        name: found.name,
        name_en: found.name_en || '',
        disease_type: found.disease_type || '',
        pathogen: found.pathogen || '',
        symptoms: found.symptoms || '',
        conditions: found.conditions || '',
        image: IMAGES.map(found.name),
        char: found.name ? found.name.charAt(0) : '病',
        treatments: (found.treatments || []).map(function (t) {
          return { method_type: t.method_type, content: t.content }
        })
      }
      that.setData({
        detail: detail,
        gallery: IMAGES.galleryOf(found.name),
        loading: false
      })
    }).catch(function () {
      that.setData({ loading: false, loadError: '病害数据加载失败，请确认后端服务已启动' })
    })
  },

  previewMain() {
    var detail = this.data.detail
    if (!detail || !detail.image) return
    var urls = [detail.image].concat(this.data.gallery)
    wx.previewImage({ urls: urls, current: detail.image })
  },

  previewGallery(e) {
    var urls = this.data.gallery
    wx.previewImage({ urls: urls, current: e.currentTarget.dataset.src })
  },

  goRecognize() {
    wx.navigateTo({ url: '/pages/camera/camera' })
  },

  retry() {
    this.fetchDetail()
  }
})
