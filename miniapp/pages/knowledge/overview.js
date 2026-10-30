var api = require('../../utils/api')
var IMAGES = require('../../config/images')

Page({
  data: {
    navs: ['生长周期', '认识绿豆', '防治思路', '病害速查'],
    activeNav: 0,
    intro: {
      title: '认识绿豆',
      paragraphs: [
        '绿豆是我国主要食用豆类之一，富含蛋白质、膳食纤维与多种维生素，既是粮食又是重要的经济作物。',
        '绿豆生育期约 60-90 天，适应性强、管理相对省工。把握好各阶段的重点，是保证产量与品质的关键。'
      ]
    },
    growth: [
      { stage: '苗期', days: '约 15 天', points: ['出苗扎根', '保持湿润', '查苗补苗'] },
      { stage: '分枝期', days: '约 15 天', points: ['适当控水', '中耕培土', '追施磷钾肥'] },
      { stage: '开花结荚期', days: '约 30 天', points: ['需水高峰', '防虫防病', '雨后排水'] },
      { stage: '成熟期', days: '约 20 天', points: ['控水促籽', '防炸荚落粒', '分批采收'] }
    ],
    principles: [
      {
        title: '农业防治',
        content: '轮作倒茬、选用抗病品种、种子消毒、合理密植、排水降湿、清除病残体，是成本最低也最有效的预防手段。'
      },
      {
        title: '药剂防治',
        content: '抓住发病初期用药，对症下药、轮换用药，严格遵守安全间隔期，避免盲目加大用量。'
      },
      {
        title: '生物防治',
        content: '利用瓢虫、草蛉等天敌和枯草芽孢杆菌等生物制剂，减少化学农药依赖，兼顾防治效果与食品安全。'
      }
    ],
    diseases: [],
    loading: true,
    loadError: ''
  },

  onLoad() {
    this.fetchDiseases()
  },

  onReady() {
    var that = this
    var win = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync()
    this._navPx = Math.round(win.windowWidth / 750 * 108)
    wx.createSelectorQuery()
      .selectAll('.anchor-section')
      .boundingClientRect(function (rects) {
        // 页面初始滚动为 0，rect.top 即各区块相对文档顶部的位置
        that._sectionTops = (rects || []).map(function (r) {
          return Math.round(r.top)
        })
      })
      .exec()
  },

  onShow() {
    this._syncActiveNav()
  },

  onPageScroll(e) {
    this._scrollTop = e.scrollTop
    if (this._navJumping || !this._sectionTops) return
    var tops = this._sectionTops
    var navPx = this._navPx || 0
    var active = 0
    for (var i = 0; i < tops.length; i++) {
      if (tops[i] - navPx <= e.scrollTop) active = i
    }
    if (active !== this.data.activeNav) {
      this.setData({ activeNav: active })
    }
  },

  _syncActiveNav() {
    var that = this
    wx.createSelectorQuery()
      .selectAll('.anchor-section')
      .boundingClientRect(function (rects) {
        if (!rects || !rects.length) return
        var navPx = that._navPx || 0
        var active = 0
        for (var i = 0; i < rects.length; i++) {
          if (rects[i].top <= navPx) active = i
        }
        if (active !== that.data.activeNav) {
          that.setData({ activeNav: active })
        }
      })
      .exec()
  },

  scrollToNav(e) {
    var index = e.currentTarget.dataset.index
    var that = this
    this.setData({ activeNav: index })
    this._navJumping = true
    setTimeout(function () { that._navJumping = false }, 340)
    wx.createSelectorQuery()
      .select('#section-' + index)
      .boundingClientRect(function (rect) {
        if (!rect) return
        var scrollTop = (that._scrollTop || 0) + rect.top - that._navPx - 8
        if (scrollTop < 0) scrollTop = 0
        wx.pageScrollTo({ scrollTop: scrollTop, duration: 280 })
      })
      .exec()
  },

  fetchDiseases() {
    var that = this
    this.setData({ loading: true, loadError: '' })
    api.get('/api/diseases').then(function (list) {
      var diseases = list.map(function (d) {
        return {
          id: d.id,
          name: d.name,
          disease_type: d.disease_type || '',
          image: IMAGES.map(d.name),
          char: d.name ? d.name.charAt(0) : '病'
        }
      })
      that.setData({ diseases: diseases, loading: false })
    }).catch(function () {
      that.setData({ loading: false, loadError: '病害数据加载失败，请确认后端服务已启动' })
    })
  },

  goDetail(e) {
    wx.navigateTo({ url: '/pages/knowledge/disease-detail?id=' + e.currentTarget.dataset.id })
  },

  retry() {
    this.fetchDiseases()
  }
})
