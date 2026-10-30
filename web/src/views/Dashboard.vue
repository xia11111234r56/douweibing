<template>
  <div>
    <h2 class="page-title">系统概览</h2>

    <el-alert v-if="error" class="mt16" type="error" :closable="false" show-icon>
      {{ error }}
      <el-button size="small" text type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <div v-loading="loading">
      <el-row :gutter="16">
        <el-col v-for="c in cards" :key="c.label" :xs="24" :sm="12" :md="8" :lg="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-num">{{ fmtNum(c.value) }}</div>
            <div class="stat-label">{{ c.label }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" class="mt16">
        <el-col :xs="24" :md="12">
          <el-card shadow="never">
            <template #header>病害分布</template>
            <div v-if="!stats?.disease_dist?.length" class="chart-empty">
              <el-empty description="暂无识别记录" :image-size="80" />
            </div>
            <div v-else ref="diseaseChart" style="height: 320px"></div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card shadow="never">
            <template #header>识别趋势</template>
            <div v-if="!stats?.daily_trend?.length" class="chart-empty">
              <el-empty description="暂无识别记录" :image-size="80" />
            </div>
            <div v-else ref="trendChart" style="height: 320px"></div>
          </el-card>
        </el-col>
      </el-row>

      <el-alert class="mt16" type="info" :closable="false" show-icon>
        本平台实现：图像智能识别（病害分类 + 严重度分级）、动态知识图谱、
        GIS 种植信息与病害风险区划、GAN 增强小样本训练。所有 AI 指标均为真实实验结果。
      </el-alert>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getStats } from '../api'
import { useEcharts } from '../composables/useEcharts'
import { fmtNum } from '../utils/format'

const cards = ref([
  { label: '识别总次数', value: null },
  { label: '病害种类', value: null },
  { label: '已录入防治方案', value: null },
  { label: '覆盖种植区域', value: null },
])
const stats = ref(null)
const loading = ref(false)
const error = ref('')

const diseaseChart = ref(null)
const trendChart = ref(null)
const { setOption: setDiseaseOpt } = useEcharts(diseaseChart)
const { setOption: setTrendOpt } = useEcharts(trendChart)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getStats()
    stats.value = res.data
    const s = res.data
    cards.value[0].value = s.total
    cards.value[1].value = s.disease_count
    cards.value[2].value = s.treatment_count
    cards.value[3].value = s.province_count ? `${s.province_count} 省` : s.province_count

    if (s.disease_dist?.length) {
      setDiseaseOpt({
        tooltip: { trigger: 'item', formatter: '{b}：{c}（{d}%）' },
        legend: { bottom: 0 },
        series: [{
          type: 'pie',
          radius: ['35%', '65%'],
          data: s.disease_dist.map((d) => ({ name: d.name, value: d.count })),
          label: { formatter: '{b}: {c}' },
        }],
      })
    }
    if (s.daily_trend?.length) {
      setTrendOpt({
        tooltip: { trigger: 'axis' },
        grid: { left: 40, right: 20, bottom: 30, top: 20 },
        xAxis: { type: 'category', data: s.daily_trend.map((d) => d.date) },
        yAxis: { type: 'value', minInterval: 1 },
        series: [{
          type: 'line', smooth: true, areaStyle: {},
          data: s.daily_trend.map((d) => d.count),
        }],
      })
    }
  } catch (e) {
    error.value = e?.response?.data?.detail || '统计接口暂不可用'
    ElMessage.warning('统计接口暂不可用，请确认后端已启动')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-title { margin-bottom: 16px; color: #1d2b3a; }
.stat-card { text-align: center; margin-bottom: 16px; transition: transform .2s ease, box-shadow .2s ease; }
.stat-card:hover { transform: translateY(-3px); box-shadow: 0 10px 24px rgba(46, 125, 50, .16); }
.stat-num {
  font-size: 30px; font-weight: 700;
  background: linear-gradient(135deg, #2e7d32, #66bb6a);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: #2e7d32;
}
.stat-label { margin-top: 6px; color: #888; font-size: 13px; }
.mt16 { margin-top: 16px; }
.chart-empty { height: 320px; display: flex; align-items: center; justify-content: center; }
</style>
