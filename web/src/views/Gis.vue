<template>
  <div>
    <h2 class="page-title">GIS 种植信息与病害风险区划</h2>

    <el-alert v-if="error" class="mb16" type="error" :closable="false" show-icon>
      {{ error }}
      <el-button size="small" text type="primary" @click="renderMap">重新加载</el-button>
    </el-alert>

    <el-row :gutter="16">
      <el-col :xs="24" :md="14">
        <el-card shadow="never" v-loading="loading">
          <template #header>
            <div class="card-head">
              <span class="title">
                {{ metric === 'risk'
                  ? `中国绿豆病害风险区划（${riskYear}）`
                  : (prodScope === 'china' ? `中国绿豆主产区产量分布（${prodYear ?? '—'}）` : `全球干豆产量分布（${prodYear ?? '—'}）`) }}
              </span>
              <div class="head-ops">
                <el-select
                  v-if="metric === 'production' && years.length"
                  v-model="prodYear"
                  size="small"
                  style="width: 100px"
                  @change="renderMap"
                >
                  <el-option v-for="y in years" :key="y" :label="y" :value="y" />
                </el-select>
                <el-radio-group v-if="metric === 'production'" v-model="prodScope" size="small" @change="onScopeChange">
                  <el-radio-button value="world">全球</el-radio-button>
                  <el-radio-button value="china">中国</el-radio-button>
                </el-radio-group>
                <el-radio-group v-model="metric" size="small" @change="renderMap">
                  <el-radio-button value="risk">风险区划</el-radio-button>
                  <el-radio-button value="production">产量分布</el-radio-button>
                </el-radio-group>
              </div>
            </div>
          </template>

          <div class="map-wrap">
            <!-- 容器永不卸载（useEcharts 复用单实例，卸载会失效） -->
            <div ref="mapRef" class="map-box" :style="{ visibility: hasData ? 'visible' : 'hidden' }"></div>
            <div v-if="!hasData" class="map-empty">
              <el-empty :description="emptyText" :image-size="90" />
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="10">
        <!-- 省份点击详情（仅风险模式） -->
        <el-card v-if="selectedRisk" shadow="never" class="mb16">
          <template #header>
            <div class="card-head">
              <span>省份详情</span>
              <el-button text type="primary" size="small" @click="selectedRisk = null">关闭</el-button>
            </div>
          </template>
          <div class="prov-head">
            <b class="prov-name">{{ selectedRisk.name }}</b>
            <el-tag :type="LEVEL_TAG[selectedRisk.level]" effect="dark">{{ selectedRisk.level }}</el-tag>
          </div>
          <el-descriptions :column="1" border size="small" class="mt12">
            <el-descriptions-item label="风险指数">{{ selectedRisk.value }}</el-descriptions-item>
            <el-descriptions-item label="6-8月均温">
              {{ selectedRisk.tavg != null ? selectedRisk.tavg + ' ℃' : '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="6-8月累计降水">
              {{ selectedRisk.prec != null ? selectedRisk.prec + ' mm' : '—' }}
            </el-descriptions-item>
          </el-descriptions>
          <p class="advice">{{ levelAdvice(selectedRisk.level) }}</p>
        </el-card>

        <!-- 说明卡：随模式切换 -->
        <el-card shadow="never" class="mb16">
          <template #header>{{ metric === 'risk' ? '风险区划说明' : '产量数据说明' }}</template>
          <template v-if="metric === 'risk'">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="数据来源">
                WorldClim 2.1（1km 栅格，1970-2000 长期气候平均）
              </el-descriptions-item>
              <el-descriptions-item label="时间窗">
                6-8 月（绿豆开花结荚关键期）均温 × 累计降水
              </el-descriptions-item>
              <el-descriptions-item label="风险指数">
                100 ×（0.5×温度适宜度 + 0.5×湿度适宜度），0-100 越大风险越高
              </el-descriptions-item>
              <el-descriptions-item label="风险等级">
                <div class="tag-row">
                  <el-tag type="success" size="small">低 &lt;40</el-tag>
                  <el-tag type="warning" size="small">中 40-60</el-tag>
                  <el-tag type="danger" size="small">较高 60-75</el-tag>
                  <el-tag type="danger" size="small">高 ≥75</el-tag>
                </div>
              </el-descriptions-item>
            </el-descriptions>
            <p class="hint">
              规则式适宜度指数，用于相对区划参考，非实证预测。
              {{ riskYear }} 为入库年份标签，气候数据为长期平均。
            </p>
          </template>
          <template v-else-if="prodScope === 'world'">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="数据来源">
                OWID / FAOSTAT（全球粮食产量统计）
              </el-descriptions-item>
              <el-descriptions-item label="口径">
                Dry beans（干豆）总量，含绿豆及其他大宗豆类，非纯绿豆
              </el-descriptions-item>
              <el-descriptions-item label="年份范围">
                2019-2024（当前展示 {{ prodYear ?? '—' }}）
              </el-descriptions-item>
              <el-descriptions-item label="单位">
                吨（tonnes），页面按需换算万吨 / 千吨
              </el-descriptions-item>
            </el-descriptions>
            <p class="hint">暂缺全球绿豆种植面积数据源，故不提供面积视图。</p>
          </template>
          <template v-else>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="数据来源">
                《中国农村统计年鉴》7-18 各地区分品种粮食作物产量（绿豆）
              </el-descriptions-item>
              <el-descriptions-item label="口径">
                绿豆（专属口径）主产区产量，2022 年
              </el-descriptions-item>
              <el-descriptions-item label="范围">
                仅全国产量前十主产省；其余省份年鉴无独立绿豆统计，如实不显示
              </el-descriptions-item>
              <el-descriptions-item label="单位">
                吨（tonnes），页面按需换算万吨 / 千吨
              </el-descriptions-item>
            </el-descriptions>
            <p class="hint">数据为年鉴口径整理，非实时统计。</p>
          </template>
        </el-card>

        <!-- 榜单：随模式切换 -->
        <el-card shadow="never">
          <template #header>
            {{ metric === 'risk'
              ? `各省风险指数（${riskYear}，Top 15）`
              : (prodScope === 'china' ? `绿豆主产省产量（${prodYear ?? '—'}，Top 10）` : `全球主要产区（${prodYear ?? '—'}，Top 10）`) }}
          </template>
          <template v-if="metric === 'risk'">
            <el-table :data="topRisk" size="small" max-height="360" @row-click="onRowClick">
              <el-table-column prop="name" label="省份" width="130" />
              <el-table-column prop="value" label="指数" width="80">
                <template #default="{ row }">{{ Number(row.value).toFixed(1) }}</template>
              </el-table-column>
              <el-table-column label="等级">
                <template #default="{ row }">
                  <el-tag :type="LEVEL_TAG[row.level]" size="small">{{ row.level }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <p class="hint">点击表格行或地图省份可查看详情。</p>
          </template>
          <template v-else>
            <el-table :data="topProd" size="small" max-height="360">
              <el-table-column prop="name" :label="prodScope === 'china' ? '省份' : '国家'" width="160" />
              <el-table-column label="产量">
                <template #default="{ row }">{{ formatTonnage(row.value) }}</template>
              </el-table-column>
            </el-table>
            <p class="hint">数据单位：吨（tonnes）。</p>
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { getGeojson, getMungbean, getRisk } from '../api'
import { useEcharts } from '../composables/useEcharts'

const mapRef = ref(null)
const metric = ref('risk')
const loading = ref(false)
const error = ref('')
const hasData = ref(false)

const riskYear = ref('—')
const riskList = ref([])
const riskSeries = ref({})           // 全量省级指标（含 JJA 气候），供详情卡查询
const prodScope = ref('world')       // 产量范围：world=全球干豆 / china=中国绿豆主产区
const prodYear = ref(null)
const years = ref([])
const prodSeries = ref([])
const selectedRisk = ref(null)       // 省份详情

const { setOption, dispose } = useEcharts(mapRef)
// 底图缓存，避免重复拉取与 registerMap
const geoLoaded = {}

const LEVEL_TAG = { 低: 'success', 中: 'warning', 较高: 'danger', 高: 'danger' }

// OWID 全名 vs world.geojson（ECharts 简称）的真实失配表（已逐一核对 geojson 要素名）
// Reunion、Taiwan 在 world.geojson 中无对应要素，无法着色，如实接受。
const WORLD_NAME_ALIAS = {
  'Bosnia and Herzegovina': 'Bosnia and Herz.',
  "Cote d'Ivoire": "Côte d'Ivoire",
  Czechia: 'Czech Rep.',
  'Democratic Republic of Congo': 'Dem. Rep. Congo',
  'Dominican Republic': 'Dominican Rep.',
  'East Timor': 'Timor-Leste',
  Eswatini: 'Swaziland',
  Laos: 'Lao PDR',
  'North Korea': 'Dem. Rep. Korea',
  'North Macedonia': 'Macedonia',
  'South Korea': 'Korea',
  'South Sudan': 'S. Sudan',
}

const topRisk = computed(() =>
  [...riskList.value].sort((a, b) => b.value - a.value).slice(0, 15)
)
const topProd = computed(() =>
  [...prodSeries.value].sort((a, b) => b.value - a.value).slice(0, 10)
)
const emptyText = computed(() => {
  if (metric.value === 'risk') return '暂无风险数据，请先在服务器执行 spatial 入库'
  if (prodScope.value === 'world') return years.value.length ? `该年份（${prodYear.value}）无产量数据` : '暂无产量数据'
  return '暂无中国绿豆产量数据（年鉴仅收录主产省）'
})

// 吨 → 可读文本
function formatTonnage(v) {
  if (v == null) return '—'
  if (v >= 1e6) return (v / 1e6).toFixed(2) + ' 百万吨'
  if (v >= 1e4) return (v / 1e4).toFixed(1) + ' 万吨'
  if (v >= 1e3) return (v / 1e3).toFixed(1) + ' 千吨'
  return Math.round(v) + ' 吨'
}

function levelAdvice(lv) {
  return {
    低: '气象条件总体不利病害流行，保持常规田间巡查即可。',
    中: '有一定发病条件，重点关注雨后田间湿度，及时排水通风。',
    较高: '高温高湿较利于叶部病害发生，建议提前喷施保护性药剂并加强监测。',
    高: '气象条件极利于病害暴发，务必加密巡查频次，提前采取预防性防治措施。',
  }[lv] || ''
}

// OWID 名 → geojson 要素名（别名表中的名字即 geojson 精确要素名）
function toMapSeries(list) {
  return list.map((d) => ({
    name: WORLD_NAME_ALIAS[d.name] || d.name,
    originName: d.name,
    value: d.value,
  }))
}

async function ensureGeo(name) {
  if (geoLoaded[name]) return
  const geo = await getGeojson(name)
  echarts.registerMap(name, geo.data || geo)
  geoLoaded[name] = true
}

async function loadRisk() {
  const res = await getRisk()
  const d = res.data
  riskYear.value = d.year
  riskList.value = d.risk || []
  riskSeries.value = d.series || {}
  hasData.value = riskList.value.length > 0
  if (!hasData.value) return
  await ensureGeo('china')
  const chart = await setOption({
    tooltip: {
      formatter: (p) => {
        const lv = riskList.value.find((r) => r.name === p.name)?.level
        return `${p.name}<br/>风险指数：${p.value ?? '—'}${lv ? `（${lv}）` : ''}`
      },
    },
    visualMap: {
      type: 'piecewise',
      pieces: [
        { gte: 75, label: '高（≥75）', color: '#c0392b' },
        { lt: 75, gte: 60, label: '较高（60-75）', color: '#e67e22' },
        { lt: 60, gte: 40, label: '中（40-60）', color: '#f5b041' },
        { lt: 40, label: '低（<40）', color: '#fff59d' },
      ],
      left: 10, bottom: 10,
    },
    series: [{
      type: 'map', map: 'china', roam: true,
      label: { show: false },
      itemStyle: { areaColor: '#eef0f3', borderColor: '#b9c0ca' },
      emphasis: { label: { show: true } },
      data: riskList.value.map((r) => ({ name: r.name, value: r.value })),
    }],
  }, { notMerge: true })
  bindClick(chart)
}

async function loadProduction() {
  // 范围决定查询层级与底图：world=country/世界地图，china=province/中国地图
  const level = prodScope.value === 'china' ? 'province' : 'country'
  const geoName = prodScope.value === 'china' ? 'china' : 'world'
  const isMung = prodScope.value === 'china'
  // 首次进入该范围：取最新年份 + 年份列表
  if (!prodYear.value) {
    const meta = await getMungbean({ level })
    years.value = meta.data?.years || []
    prodYear.value = meta.data?.year ?? null
  }
  const res = await getMungbean({ level, year: prodYear.value })
  const d = res.data
  if (d?.years?.length) years.value = d.years
  prodSeries.value = d?.series?.production || []
  hasData.value = prodSeries.value.length > 0
  if (!hasData.value) return
  await ensureGeo(geoName)
  const chart = await setOption({
    tooltip: {
      formatter: (p) => `${p.data?.originName || p.name}<br/>${isMung ? '绿豆产量' : '干豆产量'}：${formatTonnage(p.value)}`,
    },
    // 分档而非连续线性：印度 ~800 万吨巨值会拉爆线性刻度，其余国家/省全落最浅色≈白
    visualMap: {
      type: 'piecewise',
      pieces: [
        { gte: 1000000, label: '≥100万吨', color: '#1b5e20' },
        { gte: 100000, lt: 1000000, label: '10-100万吨', color: '#2e7d32' },
        { gte: 10000, lt: 100000, label: '1-10万吨', color: '#66bb6a' },
        { gte: 1000, lt: 10000, label: '1000-10000吨', color: '#a5d6a7' },
        { lt: 1000, label: '<1000吨', color: '#e8f5e9' },
      ],
      left: 10, bottom: 10,
    },
    series: [{
      type: 'map', map: geoName, roam: true,
      label: { show: false },
      itemStyle: { areaColor: '#eef0f3', borderColor: '#b9c0ca' },
      emphasis: { label: { show: true } },
      // 中国范围省份名已是 geojson 精确名，无需别名
      data: isMung
        ? prodSeries.value.map((d) => ({ name: d.name, value: d.value }))
        : toMapSeries(prodSeries.value),
    }],
  }, { notMerge: true })
  bindClick(chart)
}

// 产量范围切换：清空年份状态后重载（各范围年份集不同：全球 2019-2024 / 中国 2022）
function onScopeChange() {
  prodYear.value = null
  years.value = []
  renderMap()
}

async function renderMap() {
  loading.value = true
  error.value = ''
  selectedRisk.value = null
  // 单实例复用下 ECharts 切换 china↔world 且带 roam 时，geo 视图变换会残留/损坏
  // （切回还显示旧图、无法缩放、内部抛错）。每次渲染前销毁重建，彻底隔离地图状态。
  dispose()
  try {
    if (metric.value === 'risk') await loadRisk()
    else await loadProduction()
  } catch (e) {
    const detail = e?.response?.data?.detail
    error.value = detail || e?.message || 'GIS 数据暂不可用'
    ElMessage.warning(detail || 'GIS 数据暂不可用')
  } finally {
    loading.value = false
  }
}

function bindClick(chart) {
  chart?.off('click', onMapClick)
  chart?.on('click', onMapClick)
}

function onMapClick(params) {
  if (metric.value !== 'risk' || !params.name) {
    selectedRisk.value = null
    return
  }
  const row = riskList.value.find((r) => r.name === params.name)
  if (!row) { selectedRisk.value = null; return }
  const pick = (metricKey) => riskSeries.value[metricKey]?.find((x) => x.name === row.name)?.value
  selectedRisk.value = {
    ...row,
    tavg: pick('climate_tavg_jja'),
    prec: pick('climate_prec_jja'),
  }
}

// 表格行点击与地图点击同构
function onRowClick(row) {
  if (metric.value !== 'risk') return
  const pick = (metricKey) => riskSeries.value[metricKey]?.find((x) => x.name === row.name)?.value
  selectedRisk.value = {
    ...row,
    tavg: pick('climate_tavg_jja'),
    prec: pick('climate_prec_jja'),
  }
}

onMounted(renderMap)
</script>

<style scoped>
.page-title { margin-bottom: 16px; color: #1d2b3a; }
.mb16 { margin-bottom: 16px; }
.mt12 { margin-top: 12px; }
.card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.head-ops { display: flex; align-items: center; gap: 8px; }
/* 地图高度随视口自适应，容器永不卸载（空态用绝对定位浮层盖住） */
.map-wrap { position: relative; }
.map-box { height: calc(100vh - 320px); min-height: 440px; width: 100%; }
.map-empty {
  position: absolute; inset: 0; background: #fff;
  display: flex; align-items: center; justify-content: center;
}
.prov-head { display: flex; align-items: center; gap: 8px; }
.prov-name { font-size: 15px; color: #1d2b3a; }
.advice { margin-top: 10px; font-size: 13px; color: #4a5568; line-height: 1.7; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
.hint { margin-top: 12px; color: #8a94a6; font-size: 12px; line-height: 1.7; }
</style>
