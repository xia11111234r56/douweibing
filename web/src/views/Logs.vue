<template>
  <div>
    <h2 class="page-title">操作日志</h2>

    <el-alert v-if="error" class="mb16" type="error" :closable="false" show-icon>
      {{ error }}
      <el-button size="small" text type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="card-head">
          <span>共 {{ total }} 条</span>
          <el-select v-model="action" placeholder="按操作过滤" clearable style="width: 200px" @change="(v) => { page = 1; action = v; load() }">
            <el-option v-for="a in ACTIONS" :key="a" :label="a" :value="a" />
          </el-select>
        </div>
      </template>
      <el-table :data="logs" border stripe size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="时间" width="190">
          <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="action" label="操作" width="190">
          <template #default="{ row }">
            <el-tag size="small">{{ row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" min-width="240" />
        <el-table-column prop="user_id" label="用户 ID" width="80" />
        <template #empty>
          <el-empty description="暂无操作日志" :image-size="80" />
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
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getLogs } from '../api'
import { fmtDate } from '../utils/format'

const ACTIONS = ['auth.login', 'auth.register', 'auth.change_password', 'disease.create', 'disease.update', 'disease.delete', 'graph.node.create', 'graph.edge.create', 'user.update_role', 'user.reset_password']

const logs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const action = ref('')
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (action.value) params.action = action.value
    const res = await getLogs(params)
    logs.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    error.value = e?.response?.data?.detail || '日志接口暂不可用'
    ElMessage.warning('日志接口暂不可用')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-title { margin-bottom: 16px; color: #1d2b3a; }
.mb16 { margin-bottom: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.pager { margin-top: 16px; justify-content: flex-end; }
</style>
