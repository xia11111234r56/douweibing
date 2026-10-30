<template>
  <div class="home-page">
    <!-- ① Banner：平台简介 -->
    <div class="hero">
      <div class="hero-text">
        <h2>豆卫兵</h2>
        <p class="hero-sub">面向绿豆种植户的病害智能识别与防治参考工具</p>
        <p class="hero-desc">
          上传一张叶片照片，即可获得病害类型、危害程度与分级防治建议。
          系统融合图像识别、环境模态与领域知识规则，帮助你在田间快速判断病情、科学用药。
        </p>
        <el-button type="primary" size="large" round @click="router.push('/recognize')">
          立即识别
        </el-button>
      </div>
      <div class="hero-img" :style="{ backgroundImage: `url(${heroImg})` }"></div>
    </div>

    <!-- ② 种植科普 -->
    <h3 class="section-title">绿豆种植科普</h3>
    <el-row :gutter="16">
      <el-col v-for="k in KNOWLEDGE" :key="k.title" :xs="24" :sm="12" :md="12" :lg="6">
        <el-card shadow="hover" class="k-card">
          <div class="k-icon" :style="{ background: k.color }">
            <el-icon :size="22"><component :is="k.icon" /></el-icon>
          </div>
          <h4>{{ k.title }}</h4>
          <p>{{ k.text }}</p>
        </el-card>
      </el-col>
    </el-row>

    <!-- ③ 常见病害图鉴 -->
    <h3 class="section-title">常见病害图鉴（{{ diseases.length }} 类）</h3>
    <el-row :gutter="16" v-loading="loading">
      <el-col v-for="d in diseases" :key="d.id" :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="d-card" @click="openDetail(d)">
          <el-image :src="getDiseaseImage(d.name)" fit="cover" class="d-img">
            <template #error>
              <div class="d-img-err"><el-icon><Picture /></el-icon></div>
            </template>
          </el-image>
          <div class="d-body">
            <div class="d-name">
              {{ d.name }}
              <el-tag size="small" :type="typeTag(d.disease_type)" class="d-tag">{{ d.disease_type }}</el-tag>
            </div>
            <p class="d-symptom">{{ symptomBrief(d) }}</p>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-alert v-if="error" type="error" :closable="false" show-icon class="mt16">
      {{ error }}
      <el-button size="small" text type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <!-- ④ 使用引导 -->
    <h3 class="section-title">三步快速上手</h3>
    <el-row :gutter="16">
      <el-col v-for="(s, i) in STEPS" :key="i" :xs="24" :sm="8">
        <div class="step-card">
          <div class="step-no">{{ i + 1 }}</div>
          <h4>{{ s.title }}</h4>
          <p>{{ s.text }}</p>
        </div>
      </el-col>
    </el-row>

    <p class="disclaimer">识别结果仅供参考，具体防治请结合田间实际，必要时咨询当地农业技术部门。</p>

    <!-- 病害详情抽屉 -->
    <el-drawer v-model="drawer" :title="current?.name" size="460px">
      <template v-if="current">
        <el-image :src="getDiseaseImage(current.name)" fit="contain" class="drawer-img" />
        <el-descriptions :column="1" border class="mt12">
          <el-descriptions-item label="类型">{{ current.disease_type }}</el-descriptions-item>
          <el-descriptions-item label="病原">{{ current.pathogen || '—' }}</el-descriptions-item>
          <el-descriptions-item label="发病条件">{{ current.conditions || '—' }}</el-descriptions-item>
          <el-descriptions-item label="症状">
            <div style="white-space: pre-wrap">{{ current.symptoms || '—' }}</div>
          </el-descriptions-item>
        </el-descriptions>
        <h4 class="mt16">防治方案（按严重度分级）</h4>
        <el-table :data="current.treatments" size="small" border>
          <el-table-column prop="severity_level" label="等级" width="80" />
          <el-table-column prop="method_type" label="方式" width="80" />
          <el-table-column prop="content" label="方案" />
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Calendar, Cpu, FirstAidKit, Picture, Sunny } from '@element-plus/icons-vue'
import { listDiseases } from '../api'
import { getDiseaseImage } from '../utils/diseaseImages'

const router = useRouter()
const heroImg = '/login-imgs/leaf-1.jpg'

const KNOWLEDGE = [
  {
    title: '把握生育期',
    text: '苗期防渍水促根、分枝期控旺防徒长、开花结荚期补肥防脱肥、成熟期防贪青晚熟，每个阶段管理重点不同。',
    icon: Calendar, color: '#2e7d32',
  },
  {
    title: '通风透光',
    text: '合理密植、及时中耕除草，避免田间郁闭。高温高湿、雨后积水是叶斑类病害高发的重要诱因。',
    icon: Sunny, color: '#e6a23c',
  },
  {
    title: '预防为主',
    text: '选用无病种子、轮作倒茬、播种前药剂拌种，能显著减少初侵染源；发病初期用药效果远好于流行期。',
    icon: FirstAidKit, color: '#e53935',
  },
  {
    title: '综合防治',
    text: '农业防治为主、化学防治为辅，合理用药并注意安全间隔期。同一类药剂避免连用，防止抗药性。',
    icon: Cpu, color: '#2980b9',
  },
]

const STEPS = [
  { title: '上传叶片照片', text: '拍摄或选择一张清晰的绿豆叶片照片（尽量拍病斑明显部位）。' },
  { title: '智能识别', text: '系统融合图像分类与环境上下文，给出病害类型与危害等级。' },
  { title: '获取防治建议', text: '按严重度分级查看对应防治方案，科学用药、精准防控。' },
]

const diseases = ref([])
const loading = ref(false)
const error = ref('')
const drawer = ref(false)
const current = ref(null)

function typeTag(t) {
  return { 真菌性病害: 'danger', 细菌性病害: 'warning', 病毒性病害: 'info', 虫害: 'primary' }[t] || 'success'
}
function symptomBrief(d) {
  const s = d.symptoms || ''
  return s.length > 42 ? s.slice(0, 42) + '…' : s
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await listDiseases({ page: 1, page_size: 50 })
    diseases.value = res.data.items || []
  } catch (e) {
    error.value = e?.response?.data?.detail || '病害知识库接口暂不可用'
  } finally {
    loading.value = false
  }
}

function openDetail(d) {
  current.value = d
  drawer.value = true
}

onMounted(load)
</script>

<style scoped>
.home-page { max-width: 1120px; margin: 0 auto; }

/* Banner */
.hero {
  position: relative;
  border-radius: 18px;
  overflow: hidden;
  background: linear-gradient(120deg, #2e7d32 0%, #43a047 55%, #66bb6a 100%);
  color: #fff;
  padding: 44px 48px;
  min-height: 240px;
  display: flex;
  align-items: center;
}
.hero-text { position: relative; z-index: 1; max-width: 620px; }
.hero h2 { font-size: 30px; letter-spacing: 2px; margin-bottom: 10px; }
.hero-sub { font-size: 16px; opacity: .95; margin-bottom: 12px; }
.hero-desc { font-size: 13.5px; line-height: 1.8; opacity: .88; margin-bottom: 22px; }
.hero-img {
  position: absolute;
  right: 0; top: 0; bottom: 0;
  width: 46%;
  background-size: cover;
  background-position: center;
  opacity: .35;
}
.hero :deep(.el-button) {
  --el-button-bg-color: #fff;
  --el-button-border-color: #fff;
  --el-button-text-color: #2e7d32;
  --el-button-hover-bg-color: #e8f5e9;
  --el-button-hover-border-color: #e8f5e9;
  --el-button-hover-text-color: #1b5e20;
  font-weight: 600;
}

.section-title { margin: 30px 0 16px; color: #1d2b3a; font-size: 20px; }

/* 科普卡 */
.k-card { margin-bottom: 16px; border-radius: 14px; }
.k-icon {
  width: 46px; height: 46px; border-radius: 12px;
  color: #fff; display: flex; align-items: center; justify-content: center;
  margin-bottom: 12px;
}
.k-card h4 { color: #1d2b3a; margin-bottom: 8px; }
.k-card p { color: #667; font-size: 13px; line-height: 1.7; }

/* 病害卡 */
.d-card { margin-bottom: 16px; cursor: pointer; border-radius: 14px; overflow: hidden; transition: transform .2s; }
.d-card:hover { transform: translateY(-3px); }
.d-img { width: 100%; height: 132px; display: block; }
.d-img-err {
  height: 132px; display: flex; align-items: center; justify-content: center;
  background: #f0f2f5; color: #a0a0a0;
}
.d-body { padding: 10px 12px 12px; }
.d-name { display: flex; align-items: center; gap: 8px; color: #1d2b3a; font-weight: 600; }
.d-tag { flex-shrink: 0; }
.d-symptom {
  color: #667; font-size: 12.5px; line-height: 1.6; margin-top: 6px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

/* 步骤 */
.step-card {
  background: #fff; border-radius: 14px; padding: 26px 24px; text-align: center;
  border: 1px solid #eef1f4; margin-bottom: 16px;
}
.step-no {
  width: 40px; height: 40px; border-radius: 50%; margin: 0 auto 12px;
  background: linear-gradient(135deg, #2e7d32, #66bb6a); color: #fff;
  font-size: 18px; font-weight: 700; line-height: 40px;
}
.step-card h4 { color: #1d2b3a; margin-bottom: 8px; }
.step-card p { color: #667; font-size: 13px; line-height: 1.7; }

.disclaimer { margin: 20px 0 6px; color: #999; font-size: 12.5px; text-align: center; }

.drawer-img { width: 100%; border-radius: 10px; }
.mt12 { margin-top: 12px; }
.mt16 { margin-top: 16px; }
.mt16 h4 { margin-bottom: 10px; color: #1d2b3a; }

@media (max-width: 900px) {
  .hero { padding: 30px 26px; }
  .hero-img { width: 30%; opacity: .25; }
}
</style>
