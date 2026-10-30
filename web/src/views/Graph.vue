<template>
  <div>
    <h2 class="page-title">动态知识图谱</h2>

    <el-alert v-if="error" class="mb16" type="error" :closable="false" show-icon>
      {{ error }}
      <el-button size="small" text type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <el-row :gutter="16">
      <!-- 图谱主区：高度随视口自适应，右边界收窄给解释面板让位 -->
      <el-col :span="isAdmin() ? 16 : 18" :xs="24" :md="isAdmin() ? 16 : 18">
        <el-card shadow="never" v-loading="loading" class="graph-card">
          <template #header>
            <div class="card-head">
              <span>图谱结构（{{ nodes.length }} 节点 · {{ edgeCount }} 关系）</span>
              <el-tag size="small" type="info">可拖拽缩放 · 点击节点看解释</el-tag>
            </div>
          </template>
          <div v-if="!nodes.length" class="chart-empty">
            <el-empty description="暂无图谱数据" :image-size="100" />
          </div>
          <div v-else ref="chartRef" class="chart-box"></div>
        </el-card>
      </el-col>

      <el-col :span="isAdmin() ? 8 : 6" :xs="24" :md="isAdmin() ? 8 : 6">
        <div class="graph-right" ref="rightPanelRef">
        <!-- 防治路径推荐：图算法端点（病害→防治药剂路径，图中高亮） -->
        <el-card shadow="never" class="mb16">
          <template #header>
            <div class="card-head">
              <span>防治路径推荐</span>
              <el-button v-if="pathResult" text type="primary" size="small" @click="clearPath">清除</el-button>
            </div>
          </template>
          <el-form label-position="left" label-width="70px" size="small">
            <el-form-item label="病害">
              <el-select v-model="pathForm.disease" placeholder="选择病害" filterable style="width: 100%">
                <el-option
                  v-for="d in diseases.filter((x) => x.name !== '健康')"
                  :key="d.id"
                  :label="d.name"
                  :value="d.name"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="严重度">
              <el-select v-model="pathForm.severity" style="width: 100%">
                <el-option v-for="s in ['轻度', '中度', '重度']" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
            <el-form-item label="天气档位">
              <el-select v-model="pathForm.weather" clearable placeholder="可选" style="width: 100%">
                <el-option v-for="w in ['高温高湿', '阴雨连绵', '雨后天晴', '晴热干旱', '虫害盛发']" :key="w" :label="w" :value="w" />
              </el-select>
            </el-form-item>
            <el-button type="primary" style="width: 100%" :loading="pathLoading" @click="queryPath">
              推荐防治路径
            </el-button>
          </el-form>

          <template v-if="pathResult">
            <div class="rel-title mt12">路径（{{ pathResult.path.length }} 节点）</div>
            <div v-if="pathResult.path.length" class="path-flow">
              <template v-for="(n, i) in pathResult.path" :key="n.id">
                <span v-if="i" class="path-arrow">→</span>
                <span class="path-node" :style="{ background: CATEGORY_COLOR[n.label] || '#999' }">{{ n.name }}</span>
              </template>
            </div>
            <el-empty v-else description="无可用路径" :image-size="40" />
            <template v-if="pathResult.steps.length">
              <div class="rel-title">推理步骤</div>
              <ol class="reason-steps">
                <li v-for="s in pathResult.steps" :key="s.order" class="reason-step">
                  <span class="reason-line">
                    <b>{{ s.source }}</b>
                    <span class="reason-rel">—{{ s.relation }}→</span>
                    <b>{{ s.target }}</b>
                    <span class="reason-colon">：</span>
                    <span class="reason-text">{{ s.text }}</span>
                  </span>
                </li>
              </ol>
            </template>
            <div v-if="pathResult.note" class="path-note">⚠ {{ pathResult.note }}</div>
          </template>
        </el-card>

        <!-- 节点解释面板 -->
        <el-card ref="explainCardRef" shadow="never">
          <template #header>
            <div class="card-head">
              <span>节点解释</span>
              <el-button
                v-if="selected"
                text
                type="primary"
                size="small"
                @click="selected = null"
              >清除</el-button>
            </div>
          </template>

          <div v-if="selected" class="explain">
            <div class="explain-head">
              <span class="node-dot" :style="{ background: CATEGORY_COLOR[selected.node.label] || '#999' }"></span>
              <b class="node-name">{{ selected.node.name }}</b>
              <el-tag
                size="small"
                effect="dark"
                :style="{ background: CATEGORY_COLOR[selected.node.label] || '#999', border: 'none' }"
              >{{ selected.node.label }}</el-tag>
            </div>
            <p class="intro">{{ LABEL_META[selected.node.label]?.intro }}</p>

            <!-- 病害节点：完整知识卡 -->
            <template v-if="selected.disease">
              <el-image
                :src="getDiseaseImage(selected.disease.name)"
                fit="cover"
                class="disease-pic"
                :preview-src-list="[getDiseaseImage(selected.disease.name)]"
                preview-teleported
              >
                <template #error><div class="disease-pic-err">暂无配图</div></template>
              </el-image>
              <el-descriptions :column="1" size="small" border>
                <el-descriptions-item label="类型">{{ selected.disease.disease_type }}</el-descriptions-item>
                <el-descriptions-item label="病原">{{ selected.disease.pathogen || '—' }}</el-descriptions-item>
                <el-descriptions-item label="发病条件">{{ selected.disease.conditions || '—' }}</el-descriptions-item>
                <el-descriptions-item label="症状"><div class="pre">{{ selected.disease.symptoms || '—' }}</div></el-descriptions-item>
              </el-descriptions>
            </template>

            <!-- 关联关系（所有节点类型通用） -->
            <div class="rel-title" :class="{ 'mt12': selected.disease }">关联关系（{{ selected.rels.length }} 条）</div>
            <ul v-if="selected.rels.length" class="rel-list">
              <li v-for="(r, i) in selected.rels" :key="i" class="rel-item">
                <template v-if="r.dir === 'out'">
                  <span class="rel-node">{{ selected.node.name }}</span>
                  <span class="rel-arrow">—{{ r.relation }}→</span>
                  <span class="rel-node">{{ r.otherName }}</span>
                </template>
                <template v-else>
                  <span class="rel-node">{{ r.otherName }}</span>
                  <span class="rel-arrow">—{{ r.relation }}→</span>
                  <span class="rel-node">{{ selected.node.name }}</span>
                </template>
              </li>
            </ul>
            <el-empty v-else description="暂无关联关系" :image-size="44" />

            <!-- 病害节点：可解释推理链（寄主感染→症状→环境→防治） -->
            <el-collapse v-if="selected.node.label === '病害'" class="mt12">
              <el-collapse-item title="图谱推理链（推荐依据）" name="reason" v-loading="reasonState.loading">
                <template v-if="reasonState.data">
                  <div class="rel-title">推理链（{{ reasonState.data.engine === 'neo4j' ? 'Neo4j' : 'SQL' }} 引擎）</div>
                  <ol class="reason-steps">
                    <li v-for="s in reasonState.data.steps" :key="s.order" class="reason-step">
                      <span class="reason-line">
                        <b>{{ s.source }}</b>
                        <span class="reason-rel">—{{ s.relation }}→</span>
                        <b>{{ s.target }}</b>
                        <el-tag v-if="s.weight" size="small" type="info" class="wtag">w={{ s.weight }}</el-tag>
                        <span class="reason-colon">：</span>
                        <span class="reason-text">{{ s.text }}</span>
                      </span>
                    </li>
                  </ol>
                  <template v-if="reasonState.data.controls.length">
                    <div class="rel-title">防治用药（{{ reasonState.data.controls.length }} 种）</div>
                    <ul class="rel-list">
                      <li v-for="c in reasonState.data.controls" :key="c.name" class="rel-item">
                        <span class="rel-node">{{ c.name }}</span>
                        <el-tag size="small" type="warning" effect="plain">{{ c.severity }}</el-tag>
                      </li>
                    </ul>
                  </template>
                  <div class="reason-summary">{{ reasonState.data.summary }}</div>
                  <div v-if="reasonState.data.note" class="path-note">⚠ {{ reasonState.data.note }}</div>
                </template>
                <el-empty v-else-if="!reasonState.loading" description="暂无推理数据" :image-size="40" />
              </el-collapse-item>
            </el-collapse>
          </div>

          <el-empty v-else description="点击图谱中的节点，查看详细解释" :image-size="80" />
        </el-card>

        <!-- 管理员动态增改 -->
        <el-card v-if="isAdmin()" shadow="never" class="mt16">
          <template #header>动态增改</template>
          <el-form label-position="top" size="small">
            <el-form-item label="节点类型">
              <el-select v-model="nodeForm.label" placeholder="类型">
                <el-option label="病害" value="病害" />
                <el-option label="寄主" value="寄主" />
                <el-option label="症状" value="症状" />
                <el-option label="药剂" value="药剂" />
                <el-option label="环境" value="环境" />
              </el-select>
            </el-form-item>
            <el-form-item label="节点名称">
              <el-input v-model="nodeForm.name" placeholder="如：绿豆" />
            </el-form-item>
            <el-button type="primary" style="width: 100%" :loading="addingNode" @click="addNode">
              添加节点
            </el-button>

            <el-divider />

            <el-form-item label="起点节点">
              <el-select v-model="edgeForm.source_id" placeholder="source" filterable>
                <el-option v-for="n in nodes" :key="n.id" :label="n.name" :value="n.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="终点节点">
              <el-select v-model="edgeForm.target_id" placeholder="target" filterable>
                <el-option v-for="n in nodes" :key="n.id" :label="n.name" :value="n.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="关系">
              <el-select v-model="edgeForm.relation">
                <el-option v-for="r in ['感染', '表现为', '防治', '适宜']" :key="r" :label="r" :value="r" />
              </el-select>
            </el-form-item>
            <el-button type="warning" style="width: 100%" :loading="addingEdge" @click="addEdge">
              添加关系
            </el-button>
          </el-form>
        </el-card>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createEdge, createNode, getGraph, getGraphPath, getGraphReason, listDiseases } from '../api'
import { isAdmin } from '../auth'
import { getDiseaseImage } from '../utils/diseaseImages'
import { useEcharts } from '../composables/useEcharts'

const chartRef = ref(null)
const nodes = ref([])
const edges = ref([])
const diseases = ref([])
const edgeCount = ref(0)
const loading = ref(false)
const error = ref('')
const addingNode = ref(false)
const addingEdge = ref(false)
const nodeForm = ref({ label: '病害', name: '' })
const edgeForm = ref({ source_id: null, target_id: null, relation: '感染' })
const selected = ref(null)
const rightPanelRef = ref(null)
const explainCardRef = ref(null)
const { getChart, setOption } = useEcharts(chartRef)

// 防治路径推荐（图算法端点）
const pathForm = ref({ disease: '', severity: '中度', weather: null })
const pathResult = ref(null)
const pathLoading = ref(false)

// 图谱推理链（对选中病害自动加载）
const reasonState = ref({ loading: false, data: null })

const CATEGORY_COLOR = {
  病害: '#c0392b', 寄主: '#27ae60', 症状: '#e67e22', 药剂: '#2980b9', 环境: '#8e44ad',
}
// 各类节点的固定解释文案
const LABEL_META = {
  病害: '一种绿豆病害节点。点击可查看其病原、发病条件、典型症状与按严重度分级的防治方案。',
  寄主: '寄主作物节点（如绿豆）。病害在寄主上发生与传播，选择抗性品种是预防的第一步。',
  症状: '典型症状节点。症状是田间识别病害的主要依据，据此可快速匹配到对应病害。',
  药剂: '防治药剂节点。根据病害严重度选择合适的药剂，注意用法用量与安全间隔期。',
  环境: '环境条件节点。温湿度等环境显著影响病害的发生与流行，是预警预报的重要输入。',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [graphRes, diseaseRes] = await Promise.all([
      getGraph(),
      listDiseases({ page: 1, page_size: 100 }),
    ])
    nodes.value = graphRes.data.nodes
    edges.value = graphRes.data.edges
    edgeCount.value = edges.value.length
    diseases.value = diseaseRes.data.items || []
    selected.value = null
    if (!nodes.value.length) return

    const chart = await setOption({
      tooltip: {
        formatter: (p) => p.dataType === 'edge' ? `${p.data.source} → ${p.data.target}：${p.data.label}` : p.data.name,
      },
      legend: { bottom: 0, data: Object.keys(CATEGORY_COLOR) },
      series: [{
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        data: nodes.value.map((n) => ({
          id: String(n.id), name: n.name,
          category: n.label,
          itemStyle: { color: CATEGORY_COLOR[n.label] || '#999' },
          // 病害节点随识别热度生长（36 + min(heat,20)，图谱随使用变大）
          symbolSize: n.label === '病害' ? 36 + Math.min(n.properties?.heat || 0, 20) : 32,
        })),
        links: edges.value.map((e) => ({
          source: String(e.source_id), target: String(e.target_id), label: e.relation,
        })),
        categories: Object.keys(CATEGORY_COLOR).map((k) => ({ name: k })),
        label: { show: true, fontSize: 12 },
        force: { repulsion: 300, edgeLength: 120 },
      }],
    })
    // 点击节点展示解释；点击空白清空。重绑前先 off 避免重复监听
    chart?.off('click', onChartClick)
    chart?.on('click', onChartClick)
  } catch (e) {
    error.value = e?.response?.data?.detail || '图谱接口暂不可用'
    ElMessage.warning('图谱接口暂不可用')
  } finally {
    loading.value = false
  }
}

function onChartClick(params) {
  if (params.dataType !== 'node') {
    selected.value = null
    return
  }
  const node = nodes.value.find((n) => String(n.id) === String(params.data.id))
  if (node) selected.value = buildExplain(node)
}

// 组装节点解释：类别文案 + 病害知识卡（仅病害节点）+ 关联关系
function buildExplain(node) {
  const rels = edges.value
    .filter((e) => e.source_id === node.id || e.target_id === node.id)
    .map((e) => {
      const out = e.source_id === node.id
      const otherId = out ? e.target_id : e.source_id
      const other = nodes.value.find((n) => n.id === otherId)
      return {
        otherName: other?.name || String(otherId),
        relation: e.relation,
        dir: out ? 'out' : 'in',
      }
    })
  const disease = node.label === '病害'
    ? diseases.value.find((d) => d.name === node.name) || null
    : null
  return { node, rels, disease }
}

async function addNode() {
  if (!nodeForm.value.name) return ElMessage.warning('请填写节点名称')
  addingNode.value = true
  try {
    await createNode(nodeForm.value)
    nodeForm.value.name = ''
    ElMessage.success('节点已添加')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '添加节点失败')
  } finally {
    addingNode.value = false
  }
}

async function addEdge() {
  if (!edgeForm.value.source_id || !edgeForm.value.target_id) return ElMessage.warning('请选择两端节点')
  addingEdge.value = true
  try {
    await createEdge(edgeForm.value)
    ElMessage.success('关系已添加')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '添加关系失败')
  } finally {
    addingEdge.value = false
  }
}

// 防治路径推荐：调图算法端点，图中高亮路径节点/边 + 渲染推理步骤
async function queryPath() {
  if (!pathForm.value.disease) return ElMessage.warning('请选择病害')
  pathLoading.value = true
  try {
    const res = await getGraphPath({
      disease: pathForm.value.disease,
      severity: pathForm.value.severity || undefined,
      weather: pathForm.value.weather || undefined,
    })
    pathResult.value = res.data
    if (res.data.path.length) {
      highlightPath(res.data.highlight.node_ids || [], res.data.highlight.edge_ids || [])
    } else {
      getChart()?.dispatchAction({ type: 'downplay', seriesIndex: 0 })
    }
    scrollPanelTop()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '路径推荐失败')
  } finally {
    pathLoading.value = false
  }
}

// 清除路径推荐：清空结果、取消图中高亮、滚回面板顶部
function clearPath() {
  pathResult.value = null
  getChart()?.dispatchAction({ type: 'downplay', seriesIndex: 0 })
  scrollPanelTop()
}

// 右侧面板内部滚动到顶部（页面整体不动，左图常驻）
function scrollPanelTop() {
  const panel = rightPanelRef.value
  if (panel) panel.scrollTo({ top: 0, behavior: 'smooth' })
}

// 通过 ECharts dispatchAction 高亮路径（dataIndex = nodes/edges 数组下标，与 series 顺序一致）
function highlightPath(nodeIds, edgeIds) {
  const chart = getChart()
  if (!chart) return
  chart.dispatchAction({ type: 'downplay', seriesIndex: 0 })
  nodeIds.forEach((id) => {
    const i = nodes.value.findIndex((n) => n.id === id)
    if (i >= 0) chart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: i })
  })
  edgeIds.forEach((id) => {
    const i = edges.value.findIndex((e) => e.id === id)
    if (i >= 0) chart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: i })
  })
}

// 图谱推理链：选中病害节点时自动加载（严重度/天气沿用防治路径表单选择）
async function loadReason() {
  const node = selected.value?.node
  if (!node || node.label !== '病害') return
  reasonState.value.loading = true
  try {
    const res = await getGraphReason({
      disease: node.name,
      severity: pathForm.value.severity || '中度',
      weather: pathForm.value.weather || undefined,
    })
    reasonState.value.data = res.data
  } catch (e) {
    reasonState.value.data = null
  } finally {
    reasonState.value.loading = false
  }
}
watch(selected, async () => {
  reasonState.value.data = null
  if (selected.value?.node?.label === '病害') loadReason()
  // 选中节点后把右侧面板滚到「节点解释」卡片：页面整体不动，左图常驻
  await nextTick()
  const panel = rightPanelRef.value
  const card = explainCardRef.value
  if (panel && card && selected.value) {
    const panelTop = panel.getBoundingClientRect().top
    const cardTop = card.getBoundingClientRect().top
    panel.scrollTo({ top: panel.scrollTop + (cardTop - panelTop), behavior: 'smooth' })
  }
})

onMounted(load)
</script>

<style scoped>
.page-title { margin-bottom: 16px; color: #1d2b3a; }
.mb16 { margin-bottom: 16px; }
.mt16 { margin-top: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
/* 左卡与右列同一高度公式 calc(100vh - 150px)：两框底部精确齐平。
   顶栏 56 + 底部 36 + 页标题 + 卡片头/内边距 ≈ 150。 */
.graph-card {
  height: calc(100vh - 150px);
  display: flex;
  flex-direction: column;
}
.graph-card :deep(.el-card__header) { flex-shrink: 0; }
.graph-card :deep(.el-card__body) { flex: 1 1 auto; min-height: 0; display: flex; padding: 12px 20px 20px; }
/* 右列固定高度、面板内独立滚动：页面整体不滚，左列图常驻可见 */
.graph-right {
  height: calc(100vh - 150px);
  min-height: 420px;
  overflow-y: auto;
  padding-right: 6px;
  scrollbar-width: thin;
}
/* 图占满卡片 body，随视口自适应 */
.chart-box { flex: 1 1 auto; min-height: 0; }
.chart-empty {
  flex: 1 1 auto; min-height: 0;
  display: flex; align-items: center; justify-content: center;
}
.explain-head { display: flex; align-items: center; gap: 8px; }
.node-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.node-name { font-size: 16px; color: #1d2b3a; }
.intro { margin-top: 10px; font-size: 13px; color: #4a5568; line-height: 1.7; }
.disease-pic {
  width: 100%; height: 150px; border-radius: 8px;
  margin: 10px 0 12px; display: block; background: #f0f2f5;
}
.disease-pic-err {
  width: 100%; height: 150px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  background: #f0f2f5; color: #a0a0a0; font-size: 12px;
}
.pre { white-space: pre-wrap; }
.rel-title { font-weight: 600; color: #1d2b3a; font-size: 13px; margin-top: 12px; margin-bottom: 6px; }
.rel-list { list-style: none; margin: 0; padding: 0; }
.rel-item {
  padding: 5px 0;
  border-bottom: 1px dashed #eef1f4;
  font-size: 13px;
  line-height: 1.7;
}
.rel-item:last-child { border-bottom: none; }
.rel-node { font-weight: 600; color: #2b4a63; }
.rel-arrow { color: #8a94a6; }
/* 防治路径推荐 */
.path-flow { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 4px; }
.path-node {
  color: #fff; font-size: 12px; padding: 3px 10px; border-radius: 12px;
  white-space: nowrap; max-width: 140px; overflow: hidden; text-overflow: ellipsis;
}
.path-arrow { color: #8a94a6; }
.path-note { margin-top: 8px; font-size: 12px; color: #b45309; line-height: 1.6; }
/* 推理链步骤 */
.reason-steps { list-style: decimal inside; margin: 0; padding: 0; }
.reason-step { margin-bottom: 6px; font-size: 13px; line-height: 1.7; color: #1d2b3a; }
.reason-line { display: inline; }
.reason-rel { color: #8a94a6; }
.reason-colon { margin: 0 2px; }
.reason-text { color: #4a5568; font-size: 12px; }
.wtag { transform: scale(0.85); }
.reason-summary {
  margin-top: 8px; padding: 8px 10px; background: #f6f8fa; border-radius: 8px;
  font-size: 12px; color: #2b4a63; line-height: 1.7;
}
</style>
