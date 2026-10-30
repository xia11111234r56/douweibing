var api = require('../../utils/api')

var GROWTH_STAGES = ['不填写', '苗期', '分枝期', '开花期', '结荚期', '成熟期']
var WEATHERS = ['不填写', '高温高湿', '阴雨连绵', '雨后天晴', '晴热干旱', '虫害盛发'] // 与后端 5 档一致
var PLANTINGS = ['不填写', '露地', '大棚']

Page({
  data: {
    selectedImage: '',
    cameraOpen: false,
    diagnosing: false,
    growthStages: GROWTH_STAGES,
    weathers: WEATHERS,
    plantings: PLANTINGS,
    growthStageIndex: 0,
    weatherIndex: 0,
    plantingIndex: 0
  },

  openCamera() {
    this.setData({ cameraOpen: true, selectedImage: '' })
  },

  closeCamera() {
    this.setData({ cameraOpen: false })
  },

  onCameraInit() {},

  onCameraError() {
    wx.showToast({ title: '相机初始化失败', icon: 'none' })
    this.setData({ cameraOpen: false })
  },

  takePhoto() {
    var that = this
    wx.createCameraContext().takePhoto({
      quality: 'high',
      success: function (res) {
        that.setData({ selectedImage: res.tempImagePath, cameraOpen: false })
      },
      fail: function () {
        wx.showToast({ title: '拍照失败', icon: 'none' })
      }
    })
  },

  chooseAlbum() {
    var that = this
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album'],
      success: function (res) {
        that.setData({ selectedImage: res.tempFiles[0].tempFilePath, cameraOpen: false })
      }
    })
  },

  previewImage() {
    if (this.data.selectedImage) {
      wx.previewImage({ urls: [this.data.selectedImage] })
    }
  },

  onGrowthStage(e) {
    this.setData({ growthStageIndex: Number(e.detail.value) })
  },
  onWeather(e) {
    this.setData({ weatherIndex: Number(e.detail.value) })
  },
  onPlanting(e) {
    this.setData({ plantingIndex: Number(e.detail.value) })
  },

  buildEnv() {
    var d = this.data
    var env = {}
    if (d.growthStageIndex > 0) env.growth_stage = GROWTH_STAGES[d.growthStageIndex]
    if (d.weatherIndex > 0) env.weather = WEATHERS[d.weatherIndex]
    if (d.plantingIndex > 0) env.planting = PLANTINGS[d.plantingIndex]
    return env
  },

  diagnose() {
    if (!this.data.selectedImage) {
      wx.showToast({ title: '请先选择图片', icon: 'none' })
      return
    }
    var that = this
    this.setData({ diagnosing: true })
    wx.showLoading({ title: '识别中', mask: true })

    wx.compressImage({
      src: this.data.selectedImage,
      quality: 50,
      success: function (compressRes) {
        that._compressedPath = compressRes.tempFilePath // 记录图用压缩版，省空间
        var fs = wx.getFileSystemManager()
        fs.readFile({
          filePath: compressRes.tempFilePath,
          encoding: 'base64',
          success: function (fileRes) {
            api.post('/api/recognize', {
              image_base64: fileRes.data,
              env: that.buildEnv()
            }).then(function (body) {
              wx.hideLoading()
              that.setData({ diagnosing: false })
              if (!body || !body.disease_name) {
                wx.showToast({ title: '识别服务未就绪', icon: 'none' })
                return
              }
              that.finishAndGoResult(body)
            }).catch(function (err) {
              wx.hideLoading()
              that.setData({ diagnosing: false })
              var msg = (err && err.detail) || '网络异常，请稍后重试'
              wx.showToast({ title: msg, icon: 'none' })
            })
          },
          fail: function () {
            wx.hideLoading()
            that.setData({ diagnosing: false })
            wx.showToast({ title: '图片读取失败', icon: 'none' })
          }
        })
      },
      fail: function () {
        wx.hideLoading()
        that.setData({ diagnosing: false })
        wx.showToast({ title: '图片压缩失败', icon: 'none' })
      }
    })
  },

  finishAndGoResult(body) {
    var now = new Date()
    function pad(n) { return n < 10 ? '0' + n : '' + n }
    var id = 'diag_' + Date.now()
    var record = {
      id: id,
      recognitionId: body.id || null, // 后端识别记录 id，用于纠错反馈；旧记录为 null 时不渲染反馈入口
      image: this.data.selectedImage,
      diseaseId: body.disease_id,
      diseaseName: body.disease_name,
      diseaseType: body.disease_type || '',
      severity: body.severity || '未知',
      severityText: body.severity_desc || '',
      confidence: body.confidence ? Math.round(body.confidence * 100) : 0,
      candidates: (body.candidates || []).slice(0, 3),
      treatments: body.treatments || [],
      time: now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate()) +
        ' ' + pad(now.getHours()) + ':' + pad(now.getMinutes())
    }
    // 压缩图拷贝到用户数据目录，避免临时文件被回收导致识别记录图片失效
    var src = this._compressedPath || this.data.selectedImage
    var dst = wx.env.USER_DATA_PATH + '/rec_' + Date.now() + '.jpg'
    try {
      wx.getFileSystemManager().copyFileSync(src, dst)
      record.image = dst
    } catch (e) {
      record.image = src
    }
    getApp().saveRecord(record)
    wx.redirectTo({ url: '/pages/result/result?id=' + id })
  }
})
