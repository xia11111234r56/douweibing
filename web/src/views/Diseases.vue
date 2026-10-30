<template>
  <div>
    <div class="head-row">
      <h2 class="page-title">病害知识库</h2>
      <el-button v-if="isAdmin()" type="primary" @click="openCreate">新增病害</el-button>
    </div>

    <el-alert v-if="error" class="mb16" type="error" :closable="false" show-icon>
      {{ error }}
      <el-button size="small" text type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <el-card shadow="never" v-loading="loading">
      <el-table :data="diseases" border stripe>
        <el-table-column label="图片" width="84">
          <template #default="{ row }">
            <el-image
              :src="getDiseaseImage(row.name)"
              fit="cover"
              class="thumb"
              :preview-src-list="[getDiseaseImage(row.name)]"
              preview-teleported
            >
              <template #error>
                <div class="thumb-err"><el-icon><Picture /></el-icon></div>
              </template>
            </el-image>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="病害名称" width="140" />
        <el-table-column prop="disease_type" label="类型" width="110">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.disease_type)" size="small">{{ row.disease_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="name_en" label="英文名" width="160" />
        <el-table-column prop="pathogen" label="病原" min-width="180" />
        <el-table-column prop="conditions" label="发病条件" min-width="200" />
        <el-table-column label="操作" :width="isAdmin() ? 190 : 110" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="openDetail(row)">详情</el-button>
            <template v-if="isAdmin()">
              <el-button size="small" text @click="openEdit(row)">编辑</el-button>
              <el-button size="small" type="danger" text @click="remove(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无病害数据" :image-size="80" />
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

    <el-drawer v-model="drawer" :title="current?.name" size="520px">
      <template v-if="current">
        <el-image
          :src="getDiseaseImage(current.name)"
          fit="contain"
          class="drawer-img"
          :preview-src-list="[getDiseaseImage(current.name)]"
          preview-teleported
        />
        <el-descriptions :column="1" border class="mt12">
          <el-descriptions-item label="类型">{{ current.disease_type }}</el-descriptions-item>
          <el-descriptions-item label="英文名">{{ current.name_en || '—' }}</el-descriptions-item>
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

    <el-dialog v-model="dialog" :title="form.id ? '编辑病害' : '新增病害'" width="540px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：绿豆叶斑病" />
        </el-form-item>
        <el-form-item label="类型" prop="disease_type">
          <el-select v-model="form.disease_type" style="width: 100%">
            <el-option v-for="t in TYPES" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="英文名">
          <el-input v-model="form.name_en" />
        </el-form-item>
        <el-form-item label="病原">
          <el-input v-model="form.pathogen" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="症状">
          <el-input v-model="form.symptoms" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="发病条件">
          <el-input v-model="form.conditions" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import { createDisease, deleteDisease, listDiseases, updateDisease } from '../api'
import { isAdmin } from '../auth'
import { getDiseaseImage } from '../utils/diseaseImages'

const TYPES = ['真菌性病害', '细菌性病害', '病毒性病害', '生理性病害', '虫害', '健康']

const diseases = ref([])
const drawer = ref(false)
const current = ref(null)
const dialog = ref(false)
const saving = ref(false)
const loading = ref(false)
const error = ref('')
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const formRef = ref(null)
const form = ref(emptyForm())

const formRules = {
  name: [{ required: true, message: '请填写病害名称', trigger: 'blur' }],
  disease_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
}

function emptyForm() {
  return { id: null, name: '', disease_type: '真菌性病害', name_en: '', pathogen: '', symptoms: '', conditions: '' }
}

function typeTag(t) {
  return { 真菌性病害: 'danger', 细菌性病害: 'warning', 病毒性病害: 'info', 虫害: 'primary' }[t] || 'success'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await listDiseases({ page: page.value, page_size: pageSize.value })
    diseases.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    error.value = e?.response?.data?.detail || '病害知识库接口暂不可用'
    ElMessage.warning('病害知识库接口暂不可用')
  } finally {
    loading.value = false
  }
}

function openDetail(row) {
  current.value = row
  drawer.value = true
}

function openCreate() {
  form.value = emptyForm()
  formRef.value?.clearValidate()
  dialog.value = true
}

function openEdit(row) {
  form.value = {
    id: row.id, name: row.name, disease_type: row.disease_type,
    name_en: row.name_en || '', pathogen: row.pathogen || '',
    symptoms: row.symptoms || '', conditions: row.conditions || '',
  }
  formRef.value?.clearValidate()
  dialog.value = true
}

async function save() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const body = {
      name: form.value.name, disease_type: form.value.disease_type,
      name_en: form.value.name_en, pathogen: form.value.pathogen,
      symptoms: form.value.symptoms, conditions: form.value.conditions,
    }
    if (form.value.id) {
      await updateDisease(form.value.id, body)
    } else {
      await createDisease({ ...body, host_id: 1 }) // 1 = 绿豆
    }
    ElMessage.success('已保存')
    dialog.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除病害「${row.name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteDisease(row.id)
    ElMessage.success('已删除')
    if (diseases.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page-title { margin-bottom: 16px; color: #1d2b3a; }
.head-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.head-row .page-title { margin-bottom: 0; }
.mt16 { margin-top: 16px; }
.mt12 { margin-top: 12px; }
.mb16 { margin-bottom: 16px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.thumb { width: 48px; height: 48px; border-radius: 8px; display: block; }
.thumb-err {
  width: 48px; height: 48px; border-radius: 8px;
  background: #f0f2f5; color: #a0a0a0;
  display: flex; align-items: center; justify-content: center;
}
.drawer-img { width: 100%; height: 260px; border-radius: 10px; }
</style>
