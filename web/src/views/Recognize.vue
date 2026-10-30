<template>
  <div>
    <h2 class="page-title">图片智能识别</h2>
    <el-row :gutter="16">
      <el-col :span="11">
        <el-card shadow="never">
          <template #header>上传叶片照片</template>
          <el-upload
            drag
            accept="image/*"
            :auto-upload="false"
            :show-file-list="false"
            :on-change="onFileChange"
          >
            <div v-if="preview" class="preview-box">
              <img :src="preview" class="preview-img" alt="预览" />
            </div>
            <template v-else>
              <el-icon :size="40" color="#a0a0a0"><UploadFilled /></el-icon>
              <div class="el-upload__text">拖拽或点击上传绿豆叶片照片</div>
            </template>
          </el-upload>

          <el-divider />
          <div class="env-form">
            <h4>环境上下文（选填，多模态融合）</h4>
            <el-form label-width="90px" size="default">
              <el-form-item label="生育期">
                <el-select v-model="env.growth_stage" placeholder="选择生育期" clearable>
                  <el-option v-for="s in stages" :key="s" :label="s" :value="s" />
                </el-select>
              </el-form-item>
              <el-form-item label="天气档位">
                <el-select v-model="env.weather" placeholder="选择近期天气" clearable>
                  <el-option v-for="w in weathers" :key="w" :label="w" :value="w" />
                </el-select>
              </el-form-item>
              <el-form-item label="种植方式">
                <el-select v-model="env.planting" placeholder="选择种植方式" clearable>
                  <el-option v-for="p in plantings" :key="p" :label="p" :value="p" />
                </el-select>
              </el-form-item>
            </el-form>
          </div>

          <el-button type="primary" size="large" :loading="loading" style="width: 100%"
                     :disabled="!preview" @click="doRecognize">
            {{ loading ? '识别中…' : '开始识别' }}
          </el-button>
        </el-card>
      </el-col>

      <el-col :span="13">
        <el-card shadow="never">
          <template #header>识别结果</template>
          <div v-if="!result" class="empty-result">
            <el-empty description="上传图片后点击「开始识别」" />
          </div>
          <template v-else>
            <div class="result-img-wrap">
              <el-image
                :src="preview"
                fit="contain"
                class="result-img"
                :preview-src-list="[preview]"
                preview-teleported
              />
            </div>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="病害名称">
                <b :style="{ color: severityColor(result.severity) }">{{ result.disease_name }}</b>
              </el-descriptions-item>
              <el-descriptions-item label="病害类型">{{ result.disease_type }}</el-descriptions-item>
              <el-descriptions-item label="危害等级">
                <el-tag :type="sevType(result.severity)">{{ result.severity || '未判定' }}</el-tag>
              </el-descriptions-item>
            </el-descriptions>

            <el-alert class="mt12" type="warning" :closable="false" show-icon>
              {{ result.severity_desc }}
            </el-alert>

            <h4 class="mt16">防治方案</h4>
            <el-table :data="result.treatments" size="small" border>
              <el-table-column prop="method_type" label="方式" width="90" />
              <el-table-column prop="content" label="方案" />
              <el-table-column prop="severity_level" label="适用等级" width="90" />
            </el-table>

            <!-- 图谱可解释推理链：识别完随响应返回；图引擎失败时为 null，自动隐藏 -->
            <el-collapse v-if="result.reasoning" class="mt12">
              <el-collapse-item title="推荐依据 · 图谱推理链（寄主→症状→环境→防治）" name="reason">
                <ol class="reason-steps">
                  <li v-for="s in result.reasoning.steps" :key="s.order" class="reason-step">
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
                <div v-if="result.reasoning.controls.length" class="reason-controls">
                  <span class="controls-label">推荐用药：</span>
                  <el-tag v-for="c in result.reasoning.controls" :key="c.name" type="warning" effect="plain" class="ctrl-tag">
                    {{ c.name }}
                  </el-tag>
                </div>
                <div class="reason-summary">{{ result.reasoning.summary }}</div>
                <div v-if="result.reasoning.note" class="reason-note">⚠ {{ result.reasoning.note }}</div>
              </el-collapse-item>
            </el-collapse>

          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { recognize } from '../api'

const stages = ['苗期', '分枝期', '开花期', '结荚期', '成熟期']
const weathers = ['高温高湿', '阴雨连绵', '雨后天晴', '晴热干旱', '虫害盛发']
const plantings = ['露地', '大棚']

const preview = ref(null)
const loading = ref(false)
const result = ref(null)
const base64 = ref(null) // 不含 data: 前缀的原始 base64
const env = reactive({ growth_stage: null, weather: null, planting: null })

const MAX_SIZE = 5 * 1024 * 1024 // 5MB

function onFileChange(file) {
  if (!file.raw) return
  // 类型 / 大小校验
  if (!file.raw.type.startsWith('image/')) {
    ElMessage.error('请上传图片文件')
    return
  }
  if (file.raw.size > MAX_SIZE) {
    ElMessage.error('图片不能超过 5MB，请压缩后重试')
    return
  }
  // 换图时释放旧预览 URL，避免内存泄漏
  if (preview.value) URL.revokeObjectURL(preview.value)
  preview.value = URL.createObjectURL(file.raw)
  const reader = new FileReader()
  reader.onload = () => {
    // 去掉 "data:image/xxx;base64," 前缀
    base64.value = String(reader.result).split(',')[1]
  }
  reader.readAsDataURL(file.raw)
  result.value = null
}

async function doRecognize() {
  if (!base64.value) return
  loading.value = true
  try {
    const res = await recognize(base64.value, env)
    result.value = res.data
    ElMessage.success('识别完成')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '识别失败，请确认后端已启动')
  } finally {
    loading.value = false
  }
}

function sevType(s) {
  return { 轻度: 'success', 中度: 'warning', 重度: 'danger' }[s] || 'info'
}
// 危害等级配色（与 sevType 一致的语义色）
const severityColor = (s) => ({
  轻度: '#2e7d32', 中度: '#e6a23c', 重度: '#e53935',
}[s] || '#2b4a63')
</script>

<style scoped>
.page-title { margin-bottom: 16px; color: #1d2b3a; }
.env-form h4, .mt16 { margin-top: 16px; }
.result-img-wrap { text-align: center; margin-bottom: 12px; }
.result-img {
  width: 140px; height: 140px; border-radius: 12px; display: inline-block;
  background: #f0f4f0;
}
/* 上传预览：固定尺寸容器完整显示所选图，不被拖拽区裁切 */
.preview-box {
  width: 100%;
  height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 8px;
  background: #f7faf8;
}
.preview-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
/* 图谱推理链 */
.reason-steps { list-style: decimal inside; margin: 0; padding: 0; }
.reason-step { margin-bottom: 6px; font-size: 13px; line-height: 1.7; color: #1d2b3a; }
.reason-line { display: inline; }
.reason-rel { color: #8a94a6; }
.reason-colon { margin: 0 2px; }
.reason-text { color: #4a5568; font-size: 12px; }
.wtag { transform: scale(0.85); }
.reason-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.controls-label { font-size: 12px; color: #4a5568; }
.ctrl-tag { font-size: 12px; }
.reason-summary {
  margin-top: 8px; padding: 8px 10px; background: #f6f8fa; border-radius: 8px;
  font-size: 12px; color: #2b4a63; line-height: 1.7;
}
.reason-note { margin-top: 8px; font-size: 12px; color: #b45309; line-height: 1.6; }
</style>
