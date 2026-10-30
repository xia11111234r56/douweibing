var IMAGES = require('../../config/images')
var api = require('../../utils/api')

Page({
  data: {
    all: [],
    filtered: [],
    tabs: ['全部', '真菌性', '细菌性', '病毒性', '虫害', '健康'],
    currentTab: 0,
    keyword: '',
    loading: true,
    loadError: ''
  },

  onLoad() {
    this.fetchDiseases()
  },

  fetchDiseases() {
    var that = this
    this.setData({ loading: true, loadError: '' })
    api.get('/api/diseases').then(function (list) {
      var all = list.map(function (d) {
        return {
          id: d.id,
          name: d.name,
          char: d.name ? d.name.charAt(0) : '病',
          disease_type: d.disease_type || '',
          symptoms: d.symptoms || '',
          image: IMAGES.map(d.name)
        }
      })
      that.setData({ all: all, loading: false })
      that.applyFilter()
    }).catch(function () {
      that.setData({ loading: false, loadError: '病害数据加载失败，请确认后端服务已启动' })
    })
  },

  switchTab(e) {
    this.setData({ currentTab: e.currentTarget.dataset.index })
    this.applyFilter()
  },

  onSearch(e) {
    this.setData({ keyword: e.detail.value })
    this.applyFilter()
  },

  clearSearch() {
    this.setData({ keyword: '' })
    this.applyFilter()
  },

  applyFilter() {
    var that = this
    var tab = this.data.tabs[this.data.currentTab]
    var kw = this.data.keyword.trim()
    var list = this.data.all.filter(function (d) {
      if (tab !== '全部' && d.disease_type.indexOf(tab) === -1) return false
      if (kw && d.name.indexOf(kw) === -1 && d.symptoms.indexOf(kw) === -1) return false
      return true
    })
    this.setData({ filtered: list })
  },

  goDetail(e) {
    wx.navigateTo({ url: '/pages/knowledge/disease-detail?id=' + e.currentTarget.dataset.id })
  },

  retry() {
    this.fetchDiseases()
  }
})
