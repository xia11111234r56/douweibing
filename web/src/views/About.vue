<template>
  <div>
    <h2 class="page-title">关于本系统</h2>

    <el-card shadow="never" class="mb16">
      <template #header>项目简介</template>
      <p class="intro">
        豆卫兵面向绿豆种植户与农技推广人员，以手机拍摄叶片照片即可完成病害智能识别、
        危害分级与精准防治建议。系统由绿豆病害图像识别小程序与 Web 管理平台两部分组成：
        小程序端面向田间一线用户，Web 端面向管理员与科研人员，提供知识管理、数据统计与用户管理能力。
      </p>
      <div class="meta-grid">
        <div class="meta-item"><span class="label">版本</span><span>v0.1.0</span></div>
        <div class="meta-item"><span class="label">模型部署</span><span>ONNX Runtime 推理</span></div>
      </div>
    </el-card>

    <el-card shadow="never" class="mb16">
      <template #header>技术栈</template>
      <div class="stack-tags">
        <el-tag v-for="t in STACK" :key="t" class="stack-tag">{{ t }}</el-tag>
      </div>
    </el-card>

    <el-card shadow="never" class="mb16">
      <template #header>系统模块</template>
      <el-table :data="MODULES" border>
        <el-table-column prop="name" label="模块" width="160" />
        <el-table-column prop="desc" label="说明" />
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>模型指标（实验实测数据）</template>
      <el-table :data="METRICS" border>
        <el-table-column prop="item" label="项目" width="190" />
        <el-table-column prop="value" label="指标" width="220" />
        <el-table-column prop="note" label="说明" />
      </el-table>
      <p class="hint">
        数据来源：自建绿豆病害图像数据集（10 类病害/状态，共 601 张，经图像增广后训练）。
        以上均为独立测试集或交叉验证结果，未做过拟合性回代统计。
      </p>
    </el-card>

    <el-card shadow="never" class="mb16">
      <template #header>实验数据可视化</template>
      <el-row :gutter="16">
        <el-col v-for="f in FIGURES" :key="f.src" :xs="24" :sm="12" :md="8">
          <figure class="fig">
            <el-image :src="f.src" fit="contain" :preview-src-list="FIGURES.map((x) => x.src)" preview-teleported />
            <figcaption>{{ f.caption }}</figcaption>
          </figure>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
const STACK = [
  'Python · FastAPI', 'ONNX Runtime', 'PyTorch · MobileNetV3',
  'Vue 3 · Element Plus', 'ECharts', 'MySQL / MariaDB', 'Nginx', '小程序原生框架',
]

const MODULES = [
  { name: '图像识别', desc: 'MobileNetV3 分类模型 Top-5 候选 + 严重度分级模型，ONNX 推理' },
  { name: '多模态融合', desc: '识别结果融合生育期、天气等环境上下文，输出防治建议' },
  { name: '病害知识库', desc: '10 类绿豆病害的病原、症状、发病条件与分级防治方案' },
  { name: '知识图谱', desc: '病害-寄主-症状-药剂-环境实体关系，支持动态增改' },
  { name: 'GIS 种植信息', desc: '基于 WorldClim 2.1 气候数据的病害风险区划' },
  { name: '数据统计', desc: '识别记录、环境模态分布与交叉分析' },
  { name: '用户管理', desc: '注册登录、角色与封禁管理、操作日志（Web 端管理员）' },
]

const METRICS = [
  { item: '病害分类（5 折交叉验证）', value: '准确率 0.8519 ± 0.022', note: '10 类 pooled 验证，达标基线（0.83）之上' },
  { item: '生产部署模型', value: '准确率 0.8315', note: 'GAN 增广 + 真实虫食样本，独立验证' },
  { item: '严重度分级（5 折交叉验证）', value: '一致率 0.844', note: '轻度/中度/重度三档，MobileNetV3 骨干 + 逻辑回归' },
  { item: '多模态消融：基线 → 高温高湿', value: '0.8315 → 0.8427', note: '引入环境模态增益 +0.0112' },
]

// 真实实验图表（docs/paper/figures）
const FIGURES = [
  { src: '/figures/fig1_dataset_dist.png', caption: '数据集类别分布' },
  { src: '/figures/fig5_cv_5fold.png', caption: '5 折交叉验证性能' },
  { src: '/figures/fig6_2x2_ablation.png', caption: '多模态消融实验' },
]
</script>

<style scoped>
.page-title { margin-bottom: 16px; color: #1d2b3a; }
.mb16 { margin-bottom: 16px; }
.intro { line-height: 1.8; color: #4a5a6a; }
.meta-grid { display: flex; flex-wrap: wrap; gap: 24px; margin-top: 16px; }
.meta-item .label { color: #8a94a6; margin-right: 8px; }
.stack-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.stack-tag { margin: 0; }
.hint { margin-top: 12px; color: #8a94a6; font-size: 12px; line-height: 1.7; }
.fig { margin: 0; text-align: center; margin-bottom: 12px; }
.fig .el-image { width: 100%; border-radius: 10px; border: 1px solid #eef1f4; }
.fig figcaption { margin-top: 6px; color: #8a94a6; font-size: 12.5px; }
</style>
