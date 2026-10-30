<template>
  <div>
    <h2 class="page-title">识别记录</h2>

    <el-alert v-if="error" class="mb16" type="error" :closable="false" show-icon>
      {{ error }}
      <el-button size="small" text type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <el-card shadow="never">
      <el-form inline>
        <el-form-item label="病害">
          <el-select v-model="f.disease_id" placeholder="全部" clearable filterable style="width: 150px" @change="search1">
            <el-option v-for="d in diseases" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="严重度">
          <el-select v-model="f.severity" placeholder="全部" clearable style="width: 110px" @change="search1">
            <el-option v-for="s in ['轻度', '中度', '重度']" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="range"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 260px"
            @change="search1"
          />
        </el-form-item>
        <el-form-item label="纠错状态">
          <el-select v-model="f.has_feedback" placeholder="全部" clearable style="width: 110px" @change="search1">
            <el-option label="已纠错" :value="true" />
            <el-option label="未纠错" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="mt16" v-loading="loading">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>共 {{ total }} 条识别记录 · 已纠错 {{ correctedCount }} 条</span>
          <el-button v-if="isAdmin()" size="small" type="primary" plain @click="exportCsv">
            导出反馈 CSV
          </el-button>
        </div>
      </template>
      <el-table :data="rows" border stripe>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="disease_name" label="病害" min-width="130">
          <template #default="{ row }">{{ row.disease_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="图片" width="72">
          <template #default="{ row }">
            <el-image
              :src="recImgSrc(row)"
              fit="cover"
              class="thumb"
              :preview-src-list="[recImgSrc(row)]"
              preview-teleported
            >
              <template #error>
                <div class="thumb-err"><el-icon><Picture /></el-icon></div>
              </template>
            </el-image>
          </template>
        </el-table-column>
        <el-table-column label="严重度" width="90">
          <template #default="{ row }">
            <el-tag :type="sevTag(row.severity)" size="small">{{ row.severity || '未判定' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_anonymous ? 'info' : 'success'">
              {{ row.is_anonymous ? '小程序/匿名' : '网页' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="纠错" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.has_feedback" type="warning" size="small">已纠错</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="openDetail(row)">详情</el-button>
            <el-button size="small" type="warning" text @click="openFeedback(row)">纠错</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无识别记录" :image-size="80" />
        </template>
      </el-table>
      <el-pagination
        v-if="total > pageSize"
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="(p) => { page = p; load() }"
      />
    </el-card>

    <el-drawer v-model="drawer" title="识别详情" size="540px">
      <template v-if="current">
        <el-image
          :src="recImgSrc(current)"
          fit="contain"
          class="drawer-img"
          :preview-src-list="[recImgSrc(current)]"
          preview-teleported
        />
        <el-descriptions :column="2" border class="mt12">
          <el-descriptions-item label="病害">
            <b>{{ current.disease_name || '—' }}</b>
          </el-descriptions-item>
          <el-descriptions-item label="类型">{{ current.disease_type || '—' }}</el-descriptions-item>
          <el-descriptions-item label="严重度">
            <el-tag :type="sevTag(current.severity)" size="small">{{ current.severity || '未判定' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="识别时间" :span="2">{{ fmtDate(current.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="纠错反馈" :span="2">
            <el-tag v-if="current.has_feedback" type="warning" size="small">已纠错</el-tag>
            <span v-else class="muted">未反馈</span>
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="mt16">环境上下文</h4>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="生育期">{{ env.growth_stage || '—' }}</el-descriptions-item>
          <el-descriptions-item label="天气">{{ env.weather || '—' }}</el-descriptions-item>
          <el-descriptions-item label="种植方式">{{ env.planting || '—' }}</el-descriptions-item>
          <el-descriptions-item label="拍摄月份">{{ env.capture_month || '—' }}</el-descriptions-item>
          <el-descriptions-item label="GPS">{{ gpsText }}</el-descriptions-item>
          <el-descriptions-item label="气候(均温/降水)">
            {{ env.clim?.tavg != null ? `${env.clim.tavg}℃` : '—' }} /
            {{ env.clim?.prec != null ? `${env.clim.prec}mm` : '—' }}
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="mt16">防治建议</h4>
        <div v-loading="loadingTreat">
          <el-table v-if="treatments.length" :data="treatments" size="small" border>
            <el-table-column prop="severity_level" label="等级" width="80" />
            <el-table-column prop="method_type" label="方式" width="90" />
            <el-table-column prop="content" label="建议" />
          </el-table>
          <el-empty v-else description="暂无可参考的防治方案" :image-size="60" />
        </div>
      </template>
    </el-drawer>

    <el-dialog v-model="fbDialog" title="识别纠错" width="480px" :close-on-click-modal="false">
      <p class="fb-hint">已按识别结果预选，只修正不对的项即可。</p>
      <el-form label-width="80px">
        <el-form-item label="正确病害" required>
          <el-select v-model="fbForm.corrected_disease_id" placeholder="选择正确病害" style="width: 100%">
            <el-option v-for="d in diseases" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!fbHealthy" label="严重度" required>
          <el-radio-group v-model="fbForm.corrected_severity">
            <el-radio :label="'轻度'">轻度</el-radio>
            <el-radio :label="'中度'">中度</el-radio>
            <el-radio :label="'重度'">重度</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="fbForm.remark"
            type="textarea"
            :rows="2"
            maxlength="500"
            show-word-limit
            placeholder="可填写补充说明（选填）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="fbDialog = false">取消</el-button>
        <el-button type="primary" :loading="fbSubmitting" :disabled="!canSubmitFeedback" @click="submitFeedback">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import { isAdmin } from '../auth'
import {
  exportFeedbacks,
  getDisease,
  getRecognitions,
  listDiseases,
  submitRecognitionFeedback,
} from '../api'
import { getDiseaseImage } from '../utils/diseaseImages'
import { fmtDate } from '../utils/format'

const rows = ref([])
const total = ref(0)
const correctedCount = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const error = ref('')
const f = reactive({ disease_id: null, severity: '', has_feedback: null })
const range = ref(null)
const diseases = ref([])

const drawer = ref(false)
const current = ref(null)
const treatments = ref([])
const loadingTreat = ref(false)

// 纠错反馈弹窗（纯纠错：选正确病害 + 严重度，健康无需严重度）
const fbDialog = ref(false)
const fbSubmitting = ref(false)
const fbTarget = ref(null)
const fbForm = reactive({ corrected_disease_id: null, corrected_severity: null, remark: '' })

const fbHealthy = computed(() => {
  if (fbForm.corrected_disease_id == null) return false
  return diseases.value.find((d) => d.id === fbForm.corrected_disease_id)?.name === '健康'
})
// 识别结果作为纠错默认值：预测严重度（识别为健康时无严重度可默认）
const fbPredSeverity = computed(() => {
  const t = fbTarget.value
  if (!t) return null
  if (t.disease_name === '健康') return null
  return ['轻度', '中度', '重度'].includes(t.severity) ? t.severity : null
})
// 病害与严重度独立修正：至少一项与识别结果不同才可提交（避免空纠错）
const canSubmitFeedback = computed(() => {
  if (fbForm.corrected_disease_id == null) return false
  if (!fbHealthy.value && fbForm.corrected_severity == null) return false
  const t = fbTarget.value
  const diseaseChanged = fbForm.corrected_disease_id !== (t?.disease_id ?? null)
  const severityChanged = fbHealthy.value ? false : fbForm.corrected_severity !== fbPredSeverity.value
  return diseaseChanged || severityChanged
})

const env = computed(() => current.value?.env_metadata || {})
const gpsText = computed(() => {
  const e = env.value
  if (e.gps_lat != null && e.gps_lon != null) return `${e.gps_lat.toFixed(4)}, ${e.gps_lon.toFixed(4)}`
  return '—'
})

const sevTag = (s) => ({ 轻度: 'success', 中度: 'warning', 重度: 'danger' }[s] || 'info')

// 识别记录原图：有 image_path 时返回公开 UUID 接口（img 标签不带鉴权头），否则退回病害示意图
function recImgSrc(r) {
  return r && r.image_path ? `/api/recognitions/image/${r.image_path}` : getDiseaseImage(r?.disease_name)
}

function search1() {
  page.value = 1
  load()
}

function reset() {
  f.disease_id = null
  f.severity = ''
  f.has_feedback = null
  range.value = null
  search1()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (f.disease_id) params.disease_id = f.disease_id
    if (f.severity) params.severity = f.severity
    if (f.has_feedback !== null) params.has_feedback = f.has_feedback
    if (range.value?.length === 2) {
      params.start_date = range.value[0]
      params.end_date = range.value[1]
    }
    const res = await getRecognitions(params)
    rows.value = res.data.items
    total.value = res.data.total
    correctedCount.value = res.data.corrected_count ?? 0
  } catch (e) {
    error.value = e?.response?.data?.detail || '识别记录接口暂不可用'
    ElMessage.warning('识别记录接口暂不可用')
  } finally {
    loading.value = false
  }
}

async function loadDiseases() {
  try {
    const res = await listDiseases({ page: 1, page_size: 100 })
    diseases.value = res.data.items
  } catch {
    diseases.value = []
  }
}

async function openDetail(row) {
  current.value = row
  treatments.value = []
  drawer.value = true
  if (!row.disease_id) return
  loadingTreat.value = true
  try {
    const res = await getDisease(row.disease_id)
    treatments.value = res.data.treatments || []
  } catch {
    treatments.value = []
  } finally {
    loadingTreat.value = false
  }
}

function openFeedback(row) {
  fbTarget.value = row
  // 默认预选识别结果：病害与严重度独立修正，只改不对的项即可
  const sevValid = ['轻度', '中度', '重度'].includes(row.severity)
  fbForm.corrected_disease_id = row.disease_id ?? null
  fbForm.corrected_severity = row.disease_name === '健康' || !sevValid ? null : row.severity
  fbForm.remark = ''
  fbDialog.value = true
}

async function submitFeedback() {
  if (fbForm.corrected_disease_id == null) {
    ElMessage.warning('请选择正确的病害')
    return
  }
  if (!fbHealthy.value && fbForm.corrected_severity == null) {
    ElMessage.warning('请选择严重度')
    return
  }
  if (!canSubmitFeedback.value) {
    ElMessage.warning('识别结果没有改动，无需提交')
    return
  }
  fbSubmitting.value = true
  try {
    await submitRecognitionFeedback(fbTarget.value.id, {
      is_correct: false,
      corrected_disease_id: fbForm.corrected_disease_id,
      corrected_severity: fbHealthy.value ? null : fbForm.corrected_severity,
      remark: fbForm.remark || null,
    })
    ElMessage.success('已提交纠错')
    fbDialog.value = false
    load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交纠错失败')
  } finally {
    fbSubmitting.value = false
  }
}

async function exportCsv() {
  try {
    const res = await exportFeedbacks()
    const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'feedback_export.csv'
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出反馈 CSV')
  } catch {
    ElMessage.error('导出失败，请确认有管理员权限')
  }
}

onMounted(() => {
  load()
  loadDiseases()
})
</script>

<style scoped>
.page-title { margin-bottom: 16px; color: #1d2b3a; }
.mb16 { margin-bottom: 16px; }
.mt16 { margin-top: 16px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.thumb { width: 44px; height: 44px; border-radius: 8px; display: block; }
.thumb-err {
  width: 44px; height: 44px; border-radius: 8px;
  background: #f0f2f5; color: #a0a0a0;
  display: flex; align-items: center; justify-content: center;
}
.muted { color: #a0a0a0; }
.drawer-img { width: 100%; height: 260px; border-radius: 10px; }
.mt12 { margin-top: 12px; }
.fb-hint { font-size: 13px; color: #8a8f99; margin: 0 0 12px; }
</style>
