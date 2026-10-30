// 病害配图：病名 → 静态图路径（图片来自 miniapp/images/diseases 已压缩缩略图）
// slug 与文件名一一对应；未命中的病害（如管理员自建）返回占位图。
const DISEASE_IMAGES = {
  健康: '/disease-imgs/healthy.jpg',
  晕疫病: '/disease-imgs/halo-blight.jpg',
  炭疽叶斑病: '/disease-imgs/anthracnose.jpg',
  轮纹叶斑病: '/disease-imgs/leaf-spot.jpg',
  枯萎病: '/disease-imgs/fusarium-wilt.jpg',
  病毒病: '/disease-imgs/virus.jpg',
  细菌性疫病: '/disease-imgs/bacterial-blight.jpg',
  叶腐病: '/disease-imgs/leaf-rot.jpg',
  细菌性萎蔫: '/disease-imgs/bacterial-wilt.jpg',
  虫食: '/disease-imgs/insect.jpg',
}

const PLACEHOLDER = '/disease-imgs/healthy.jpg'

export function getDiseaseImage(name) {
  return DISEASE_IMAGES[name] || PLACEHOLDER
}

export { DISEASE_IMAGES }
