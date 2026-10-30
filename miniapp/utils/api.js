/**
 * 后端 API 轻封装（wx.request → Promise）。
 * baseURL 取 app.js 的 API_BASE_URL，正式上线时只改那一处。
 */
function base() {
  var app = getApp()
  return (app && app.API_BASE_URL) || 'http://127.0.0.1:8000'
}

function request(method, path, data) {
  return new Promise(function (resolve, reject) {
    wx.request({
      url: base() + path,
      method: method,
      data: data || {},
      header: { 'content-type': 'application/json' },
      timeout: 60000,
      success: function (res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          reject({
            statusCode: res.statusCode,
            detail: (res.data && res.data.detail) || '服务异常'
          })
        }
      },
      fail: function (err) {
        reject(err)
      }
    })
  })
}

module.exports = {
  get: function (path) { return request('GET', path) },
  post: function (path, data) { return request('POST', path, data) }
}
