<template>
  <div>
    <h2 class="page-title">多维多条件检索</h2>

    <el-alert v-if="error" class="mb16" type="error" :closable="false" show-icon>
      {{ error }}
      <el-button size="small" text type="primary" @click="doSearch">重新加载</el-button>
    </el-alert>

    <el-card shadow="never">
      <el-form inline>
        <el-form-item label="关键词">
          <el-input v-model="f.keyword" placeholder="病害名/症状/病原" clearable style="width: 180px" @keyup.enter="search1" />
        </el-form-item>
        <el-form-item label="病害类型">
          <el-select v-model="f.disease_type" placeholder="全部" clearable style="width: 130px" @change="search1">
            <el-option v-for="t in ['真菌性病害', '细菌性病害', '病毒性病害', '生理性病害', '虫害']" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="药剂">
          <el-input v-model="f.pesticide" placeholder="药剂名" clearable style="width: 120px" @keyup.enter="search1" />
        </el-form-item>
        <el-form-item label="严重度">
          <el-select v-model="f.severity" placeholder="全部" clearable style="width: 100px" @change="search1">
            <el-option v-for="s in ['轻度', '中度', '重度']" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search1">检索</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="mt16" v-loading="loading">
      <template #header>结果（{{ total }} 条）</template>
      <el-table :data="diseases" border stripe>
        <el-table-column label="图片" width="72">
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
        <el-table-column prop="name" label="病害" width="140" />
        <el-table-column prop="disease_type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.disease_type)" size="small">{{ row.disease_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="host_name" label="寄主" width="90" />
        <el-table-column prop="pathogen" label="病原" min-width="180" />
        <el-table-column prop="conditions" label="发病条件" min-width="200" />
        <el-table-column label="可用方案" width="100">
          <template #default="{ row }">{{ row.treatments.length }} 条</template>
        </el-table-column>
        <template #empty>
          <el-empty description="未检索到符合条件的病害" :image-size="80" />
        </template>
      </el-table>
      <el-pagination
        v-if="total > pageSize"
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="(p) => { page = p; doSearch() }"
      />
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import { searchDiseases } from '../api'
import { getDiseaseImage } from '../utils/diseaseImages'

const f = reactive({ keyword: '', disease_type: '', pesticide: '', severity: '' })
const diseases = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const error = ref('')

// 条件变化时回到第 1 页
function search1() {
  page.value = 1
  doSearch()
}

async function doSearch() {
  loading.value = true
  error.value = ''
  try {
    const params = { ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)), page: page.value, page_size: pageSize.value }
    const res = await searchDiseases(params)
    diseases.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    error.value = e?.response?.data?.detail || '检索接口暂不可用'
    ElMessage.warning('检索接口暂不可用')
  } finally {
    loading.value = false
  }
}

function reset() {
  Object.assign(f, { keyword: '', disease_type: '', pesticide: '', severity: '' })
  search1()
}

function typeTag(t) {
  return { 真菌性病害: 'danger', 细菌性病害: 'warning', 病毒性病害: 'info', 虫害: 'primary' }[t] || 'success'
}

onMounted(doSearch)
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
</style>
