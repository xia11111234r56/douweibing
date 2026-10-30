<template>
  <div>
    <h2 class="page-title">用户管理</h2>

    <el-alert v-if="error" class="mb16" type="error" :closable="false" show-icon>
      {{ error }}
      <el-button size="small" text type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="card-head">
          <span>共 {{ total }} 个账号</span>
          <div>
            <el-input v-model="keyword" placeholder="按用户名搜索" clearable style="width: 200px" @keyup.enter="search1" @clear="search1" />
            <el-button type="primary" class="ml8" @click="search1">搜索</el-button>
          </div>
        </div>
      </template>
      <el-table :data="users" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="roleTag(row.role)" size="small">{{ roleName(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="190">
          <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="280">
          <template #default="{ row }">
            <template v-if="isSelf(row)">
              <el-tag size="small" type="info">当前账号</el-tag>
            </template>
            <template v-else>
              <el-select
                :model-value="row.role"
                size="small"
                style="width: 100px; margin-right: 8px"
                @change="(role) => changeRole(row, role)"
              >
                <el-option label="管理员" value="admin" />
                <el-option label="普通用户" value="user" />
                <el-option label="已封禁" value="banned" />
              </el-select>
              <el-button size="small" text type="warning" @click="resetPwd(row)">重置密码</el-button>
              <el-button size="small" text :type="row.role === 'banned' ? 'success' : 'danger'" @click="toggleBan(row)">
                {{ row.role === 'banned' ? '解封' : '封禁' }}
              </el-button>
            </template>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无用户" :image-size="80" />
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { getUsers, resetUserPassword, updateUserRole } from '../api'
import { authState } from '../auth'
import { fmtDate } from '../utils/format'

const users = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const keyword = ref('')
const loading = ref(false)
const error = ref('')

const roleName = (r) => ({ admin: '管理员', user: '普通用户', banned: '已封禁' }[r] || r)
const roleTag = (r) => ({ admin: 'danger', user: 'primary', banned: 'info' }[r] || 'info')
const isSelf = (row) => row.id === authState.user?.id

function search1() {
  page.value = 1
  load()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    const res = await getUsers(params)
    users.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    error.value = e?.response?.data?.detail || '用户接口暂不可用'
    ElMessage.warning('用户接口暂不可用')
  } finally {
    loading.value = false
  }
}

async function changeRole(row, role) {
  try {
    await updateUserRole(row.id, role)
    ElMessage.success(`已将 ${row.username} 设为「${roleName(role)}」`)
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '修改角色失败')
    await load() // 回滚下拉显示
  }
}

async function resetPwd(row) {
  let val
  try {
    const { value } = await ElMessageBox.prompt(`为「${row.username}」设置新密码（至少 6 位）`, '重置密码', {
      inputPattern: /^.{6,128}$/,
      inputErrorMessage: '密码长度需在 6-128 位之间',
    })
    val = value
  } catch {
    return
  }
  try {
    await resetUserPassword(row.id, val)
    ElMessage.success('密码已重置')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '重置失败')
  }
}

async function toggleBan(row) {
  const toBan = row.role !== 'banned'
  try {
    await ElMessageBox.confirm(
      toBan ? `确认封禁「${row.username}」？封禁后其将无法登录。` : `确认解封「${row.username}」？`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await updateUserRole(row.id, toBan ? 'banned' : 'user')
    ElMessage.success(toBan ? '已封禁' : '已解封')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page-title { margin-bottom: 16px; color: #1d2b3a; }
.mb16 { margin-bottom: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.ml8 { margin-left: 8px; }
.pager { margin-top: 16px; justify-content: flex-end; }
</style>
