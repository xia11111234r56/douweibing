<template>
  <div>
    <h2 class="page-title">数据统计</h2>

    <el-alert v-if="error" class="mt16" type="error" :closable="false" show-icon>
      {{ error }}
      <el-button size="small" text type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <div v-loading="loading">
      <el-row :gutter="16">
        <el-col :xs="24" :md="12">
          <el-card shadow="never">
            <template #header>识别记录 · 严重度分布</template>
            <div v-if="!stats?.severity_dist?.length" class="chart-empty">
              <el-empty description="暂无识别记录" :image-size="80" />
            </div>
            <div v-else ref="severityChart" style="height: 320px"></div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card shadow="never">
            <template #header>识别记录 · 病害分布</template>
            <div v-if="!stats?.disease_dist?.length" class="chart-empty">
              <el-empty description="暂无识别记录" :image-size="80" />
            </div>
            <div v-else ref="diseaseChart" style="height: 320px"></div>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="mt16">
        <template #header>识别记录 · 每日趋势</template>
        <div v-if="!stats?.daily_trend?.length" class="chart-empty tall">
          <el-empty description="暂无识别记录" :image-size="80" />
        </div>
        <div v-else ref="trendChart" style="height: 300px"></div>
      </el-card>

      <el-row :gutter="16" class="mt16">
        <el-col :xs="24" :md="12">
          <el-card shadow="never">
            <template #header>环境模态 · 生育期分布</template>
            <div v-if="!envStats?.growth_stage_dist?.length" class="chart-empty">
              <el-empty description="暂无环境上下文" :image-size="80" />
            </div>
            <div v-else ref="stageChart" style="height: 300px"></div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card shadow="never">
            <template #header>环境模态 · 天气档位 × 严重度</template>
            <div v-if="!cross?.severity_x_weather?.length" class="chart-empty">
              <el-empty description="暂无交叉数据" :image-size="80" />
            </div>
            <div v-else ref="crossChart" style="height: 300px"></div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getStats, getStatsCross, getStatsEnv } from '../api'
import { useEcharts } from '../composables/useEcharts'

const loading = ref(false)
const error = ref('')
const stats = ref(null)
const envStats = ref(null)
const cross = ref(null)

const severityChart = ref(null)
const diseaseChart = ref(null)
const trendChart = ref(null)
const stageChart = ref(null)
const crossChart = ref(null)
const { setOption: setSeverity } = useEcharts(severityChart)
const { setOption: setDisease } = useEcharts(diseaseChart)
const { setOption: setTrend } = useEcharts(trendChart)
const { setOption: setStage } = useEcharts(stageChart)
const { setOption: setCross } = useEcharts(crossChart)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, env, cx] = await Promise.all([getStats(), getStatsEnv(), getStatsCross()])
    stats.value = s.data
    envStats.value = env.data
    cross.value = cx.data

    if (s.data.severity_dist?.length) {
      setSeverity({
        tooltip: { trigger: 'item', formatter: '{b}：{c}（{d}%）' },
        legend: { bottom: 0 },
        series: [{ type: 'pie', radius: '60%', data: s.data.severity_dist.map((d) => ({ name: d.severity, value: d.count })) }],
      })
    }
    if (s.data.disease_dist?.length) {
      setDisease({
        tooltip: { trigger: 'item', formatter: '{b}：{c}（{d}%）' },
        series: [{ type: 'pie', roseType: 'radius', data: s.data.disease_dist.map((d) => ({ name: d.name, value: d.count })) }],
      })
    }
    if (s.data.daily_trend?.length) {
      setTrend({
        tooltip: { trigger: 'axis' },
        grid: { left: 40, right: 20, bottom: 30, top: 20 },
        xAxis: { type: 'category', data: s.data.daily_trend.map((d) => d.date) },
        yAxis: { type: 'value', minInterval: 1 },
        series: [{ type: 'bar', barMaxWidth: 40, data: s.data.daily_trend.map((d) => d.count), itemStyle: { color: '#2b4a63' } }],
      })
    }
    if (env.data.growth_stage_dist?.length) {
      setStage({
        tooltip: { trigger: 'item', formatter: '{b}：{c}（{d}%）' },
        legend: { bottom: 0 },
        series: [{ type: 'pie', radius: '60%', data: env.data.growth_stage_dist.map((d) => ({ name: d.name, value: d.count })) }],
      })
    }
    if (cx.data.severity_x_weather?.length) {
      const sevLevels = ['轻度', '中度', '重度', '未知']
      setCross({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        legend: { bottom: 0, data: sevLevels },
        grid: { left: 40, right: 20, bottom: 40, top: 20 },
        xAxis: { type: 'category', data: cx.data.severity_x_weather.map((d) => d.weather) },
        yAxis: { type: 'value', minInterval: 1 },
        series: sevLevels.map((lv) => ({
          name: lv, type: 'bar', stack: 'total',
          data: cx.data.severity_x_weather.map((d) => d[lv] || 0),
        })),
      })
    }
  } catch (e) {
    error.value = e?.response?.data?.detail || '统计接口暂不可用'
    ElMessage.warning('统计接口暂不可用')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-title { margin-bottom: 16px; color: #1d2b3a; }
.mt16 { margin-top: 16px; }
.chart-empty { height: 320px; display: flex; align-items: center; justify-content: center; }
.chart-empty.tall { height: 300px; }
</style>
