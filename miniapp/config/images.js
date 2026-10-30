/**
 * 病害图片映射（本地静态图，10 类全覆盖，来自真实数据集的代表性叶片照片）。
 * map(name)     → 主图路径（列表/首页卡片用）
 * galleryOf(name) → 详情页「真实病例图库」多图（来自同一批真实训练数据）
 * 某类缺图返回空，页面显示占位色块兜底。
 */
module.exports = {
  diseases: {
    '健康': '/images/diseases/healthy.jpg',
    '晕疫病': '/images/diseases/halo-blight.jpg',
    '炭疽叶斑病': '/images/diseases/anthracnose.jpg',
    '轮纹叶斑病': '/images/diseases/leaf-spot.jpg',
    '枯萎病': '/images/diseases/fusarium-wilt.jpg',
    '病毒病': '/images/diseases/virus.jpg',
    '细菌性疫病': '/images/diseases/bacterial-blight.jpg',
    '叶腐病': '/images/diseases/leaf-rot.jpg',
    '细菌性萎蔫': '/images/diseases/bacterial-wilt.jpg',
    '虫食': '/images/diseases/insect.jpg'
  },
  gallery: {
    '健康': ['/images/diseases/gallery/healthy-1.jpg', '/images/diseases/gallery/healthy-2.jpg', '/images/diseases/gallery/healthy-3.jpg'],
    '晕疫病': ['/images/diseases/gallery/halo-blight-1.jpg', '/images/diseases/gallery/halo-blight-2.jpg', '/images/diseases/gallery/halo-blight-3.jpg'],
    '炭疽叶斑病': ['/images/diseases/gallery/anthracnose-1.jpg', '/images/diseases/gallery/anthracnose-2.jpg', '/images/diseases/gallery/anthracnose-3.jpg'],
    '轮纹叶斑病': ['/images/diseases/gallery/leaf-spot-1.jpg', '/images/diseases/gallery/leaf-spot-2.jpg', '/images/diseases/gallery/leaf-spot-3.jpg'],
    '枯萎病': ['/images/diseases/gallery/fusarium-wilt-1.jpg', '/images/diseases/gallery/fusarium-wilt-2.jpg', '/images/diseases/gallery/fusarium-wilt-3.jpg'],
    '病毒病': ['/images/diseases/gallery/virus-1.jpg', '/images/diseases/gallery/virus-2.jpg', '/images/diseases/gallery/virus-3.jpg'],
    '细菌性疫病': ['/images/diseases/gallery/bacterial-blight-1.jpg', '/images/diseases/gallery/bacterial-blight-2.jpg', '/images/diseases/gallery/bacterial-blight-3.jpg'],
    '叶腐病': ['/images/diseases/gallery/leaf-rot-1.jpg'],
    '细菌性萎蔫': ['/images/diseases/gallery/bacterial-wilt-1.jpg', '/images/diseases/gallery/bacterial-wilt-2.jpg', '/images/diseases/gallery/bacterial-wilt-3.jpg'],
    '虫食': ['/images/diseases/gallery/insect-1.jpg']
  },
  map: function (name) {
    return this.diseases[name] || ''
  },
  galleryOf: function (name) {
    return this.gallery[name] || []
  }
}
