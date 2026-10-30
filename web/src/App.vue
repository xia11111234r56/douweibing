<template>
  <Login v-if="!authState.token" />
  <el-container v-else class="app-shell">
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo" :class="{ collapsed }">
        <img src="/logo.png" class="logo-img" alt="豆卫兵" />
        <div v-if="!collapsed" class="logo-text">豆卫兵</div>
      </div>
      <el-menu :default-active="$route.path" router class="menu" :collapse="collapsed"
               :collapse-transition="false">
        <el-menu-item v-if="isAdmin()" index="/dashboard"><el-icon><DataLine /></el-icon><template #title>概览</template></el-menu-item>
        <el-menu-item v-else index="/home"><el-icon><HomeFilled /></el-icon><template #title>科普首页</template></el-menu-item>
        <el-menu-item index="/recognize"><el-icon><Camera /></el-icon><template #title>图片识别</template></el-menu-item>
        <el-menu-item index="/recognitions"><el-icon><Histogram /></el-icon><template #title>识别记录</template></el-menu-item>
        <el-menu-item index="/diseases"><el-icon><Document /></el-icon><template #title>病害知识库</template></el-menu-item>
        <el-menu-item index="/search"><el-icon><Search /></el-icon><template #title>多维检索</template></el-menu-item>
        <el-menu-item index="/graph"><el-icon><Share /></el-icon><template #title>知识图谱</template></el-menu-item>
        <el-menu-item index="/gis"><el-icon><MapLocation /></el-icon><template #title>GIS 种植信息</template></el-menu-item>
        <el-menu-item v-if="isAdmin()" index="/stats"><el-icon><PieChart /></el-icon><template #title>数据统计</template></el-menu-item>
        <el-menu-item v-if="isAdmin()" index="/users"><el-icon><User /></el-icon><template #title>用户管理</template></el-menu-item>
        <el-menu-item v-if="isAdmin()" index="/logs"><el-icon><Tickets /></el-icon><template #title>操作日志</template></el-menu-item>
        <el-menu-item index="/about"><el-icon><InfoFilled /></el-icon><template #title>关于</template></el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div class="topbar-left">
          <el-button text class="fold-btn" @click="collapsed = !collapsed">
            <el-icon :size="18"><Expand v-if="collapsed" /><Fold v-else /></el-icon>
          </el-button>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: isAdmin() ? '/dashboard' : '/home' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ $route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="topbar-right">
          <el-tag v-if="health" size="small" :type="health.model_ready ? 'success' : 'info'" class="health-tag">
            {{ health.model_ready ? '模型就绪' : '模型未就绪' }}
          </el-tag>
          <el-tag size="small" :type="isAdmin() ? 'danger' : 'info'">
            {{ isAdmin() ? '管理员' : '使用者' }}
          </el-tag>
          <el-dropdown trigger="click">
            <span class="user-trigger">
              <img src="/logo.png" class="avatar" alt="头像" />
              <span class="username">{{ authState.user?.username }}</span>
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="openPwDialog">修改密码</el-dropdown-item>
                <el-dropdown-item divided @click="doLogout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>

      <el-footer class="footer" height="36px">
        <span>豆卫兵 · 绿豆病害智能分级与精准防治系统</span>
        <span class="footer-right">
          <a @click="router.push('/about')">关于</a>
          <span>v0.1.0</span>
        </span>
      </el-footer>
    </el-container>

    <!-- 修改密码（mustChange 时不可关闭，强制改密） -->
    <el-dialog
      v-model="pwDialog"
      :title="mustChange ? '请修改初始密码' : '修改密码'"
      width="420px"
      :close-on-click-modal="!mustChange"
      :close-on-press-escape="!mustChange"
      :show-close="!mustChange"
      :align-center="true"
    >
      <el-alert v-if="mustChange" type="warning" :closable="false" show-icon class="mb12">
        当前使用默认密码 admin123，为保障系统安全请立即修改。
      </el-alert>
      <el-form ref="pwFormRef" :model="pwForm" :rules="pwRules" label-width="80px">
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="pwForm.old_password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwForm.new_password" type="password" show-password autocomplete="new-password" placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="pwForm.confirm" type="password" show-password autocomplete="new-password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="!mustChange" @click="pwDialog = false">取消</el-button>
        <el-button type="primary" :loading="changingPw" @click="submitPw">确认修改</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowDown, Camera, DataLine, Document, Expand, Fold, Histogram, HomeFilled, InfoFilled,
  MapLocation, PieChart, Search, Share, Tickets, User,
} from '@element-plus/icons-vue'
import Login from './views/Login.vue'
import { authState, clearAuth, isAdmin } from './auth'
import { changePassword, getHealth } from './api'

const router = useRouter()
const collapsed = ref(false)
const health = ref(null)
const mustChange = ref(!!authState.user?.must_change_password)

const pwDialog = ref(false)
const pwFormRef = ref(null)
const changingPw = ref(false)
const pwForm = reactive({ old_password: '', new_password: '', confirm: '' })

const pwRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_, value, cb) => (value === pwForm.new_password ? cb() : cb(new Error('两次输入不一致'))),
      trigger: 'blur',
    },
  ],
}

function openPwDialog() {
  Object.assign(pwForm, { old_password: '', new_password: '', confirm: '' })
  pwFormRef.value?.clearValidate()
  pwDialog.value = true
}

async function submitPw() {
  try {
    await pwFormRef.value.validate()
  } catch {
    return
  }
  changingPw.value = true
  try {
    await changePassword(pwForm.old_password, pwForm.new_password)
    ElMessage.success('密码已更新')
    mustChange.value = false
    if (authState.user) authState.user.must_change_password = false
    pwDialog.value = false
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '修改失败')
  } finally {
    changingPw.value = false
  }
}

async function doLogout() {
  try {
    await ElMessageBox.confirm('确认退出登录？', '提示', { type: 'warning' })
  } catch {
    return
  }
  clearAuth()
  router.push('/login')
}

let healthTimer = null
async function refreshHealth() {
  try {
    health.value = (await getHealth()).data
  } catch {
    health.value = null
  }
}

onMounted(() => {
  if (window.innerWidth < 768) collapsed.value = true
  refreshHealth()
  healthTimer = setInterval(refreshHealth, 30000)
  if (mustChange.value) openPwDialog()
})

// 登录完成后 me 返回 must_change_password=true 时触发强制改密
watch(
  () => authState.user?.must_change_password,
  (v) => {
    mustChange.value = !!v
    if (v) openPwDialog()
  },
)

onBeforeUnmount(() => clearInterval(healthTimer))
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; }
body { font-family: 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif; }
/* 全局卡片观感统一 */
.el-card { border-radius: 12px; }
.el-card__header { font-weight: 600; color: #1d2b3a; }
.app-shell { height: 100%; }
.sidebar { background: #1d2b3a; color: #fff; transition: width 0.2s; }
.logo {
  display: flex; align-items: center; gap: 10px;
  padding: 18px 20px; color: #fff; font-weight: 700; font-size: 18px;
  white-space: nowrap; overflow: hidden;
}
.logo.collapsed { padding: 18px 15px; }
.logo-img {
  width: 34px; height: 34px; border-radius: 8px; object-fit: cover;
  flex-shrink: 0; border: 1px solid rgba(255, 255, 255, .35);
}
.menu { border-right: none; background: transparent; }
.menu .el-menu-item { color: #c8d2dc; }
.menu .el-menu-item.is-active { color: #fff; background: #2b4a63; }
.main { background: #f5f7fa; padding: 20px; overflow-y: auto; }
.topbar {
  background: #fff; border-bottom: 1px solid #e4e7ed;
  display: flex; align-items: center; justify-content: space-between;
  height: 56px;
}
.topbar-left { display: flex; align-items: center; gap: 10px; }
.fold-btn { color: #1d2b3a; }
.topbar-right { display: flex; align-items: center; gap: 12px; }
.health-tag { margin-right: 2px; }
.user-trigger {
  display: flex; align-items: center; gap: 6px; cursor: pointer; color: #1d2b3a; outline: none;
}
.avatar {
  width: 28px; height: 28px; border-radius: 50%; object-fit: cover;
  border: 1.5px solid #43a047;
}
.username { color: #1d2b3a; font-size: 14px; }
.footer {
  background: #fff; border-top: 1px solid #e4e7ed; color: #8a94a6; font-size: 12px;
  display: flex; align-items: center; justify-content: space-between; padding: 0 20px;
}
.footer-right { display: flex; gap: 16px; }
.footer a { cursor: pointer; color: #2b4a63; }
.mb12 { margin-bottom: 12px; }

/* 页面过渡 */
.fade-enter-active, .fade-leave-active { transition: opacity 0.18s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
