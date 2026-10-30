<template>
  <div class="login-page">
    <!-- 背景大图：从顶部到页面的下 1/4 处（上 3/4），交叉淡入淡出 -->
    <div class="bg-area">
      <div
        v-for="(img, i) in images"
        :key="img"
        class="bg-img"
        :class="{ active: i === activeIndex }"
        :style="{ backgroundImage: `url(${img})` }"
      ></div>
      <div class="bg-tint"></div>
      <div class="bg-fade"></div>
    </div>

    <!-- 底部 1/4 纯净区 -->
    <div class="band"></div>

    <!-- 若有若无的优美线条 -->
    <div class="line"></div>

    <!-- 小方块：六张沿“先升后降”圆弧排布（中间大、两端小，点击切换背景） -->
    <div class="tiles">
      <div
        v-for="(i, idx) in tileIndexes"
        :key="i"
        class="tile"
        :class="{ active: i === activeIndex }"
        :title="`切换背景 ${i + 1}`"
        :style="tileStyle(idx)"
        @click="selectImage(i)"
      >
        <img :src="images[i]" alt="叶片背景" />
      </div>
    </div>

    <!-- 中央登录/注册卡（中心对齐线条，不超页面 1/2） -->
    <div class="center-card">
      <img class="logo" src="/logo.png" alt="豆卫兵" />
      <h1 class="title">豆卫兵</h1>
      <p class="sub">绿豆病害智能分级与精准防治系统</p>

      <!-- 两个按钮：登录 / 注册 -->
      <div v-show="!mode" class="btns">
        <button class="btn btn-login" @click="mode = 'login'">登 录</button>
        <button class="btn btn-register" @click="mode = 'register'">注 册</button>
      </div>

      <!-- 表单面板（滑入） -->
      <transition name="slide">
        <div v-show="mode" class="form-panel">
          <template v-if="mode === 'login'">
            <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" @keyup.enter="doLogin">
              <el-form-item prop="username">
                <el-input v-model="loginForm.username" placeholder="用户名" clearable size="large" />
              </el-form-item>
              <el-form-item prop="password">
                <el-input v-model="loginForm.password" type="password" placeholder="密码" show-password size="large" />
              </el-form-item>
              <el-button type="primary" size="large" class="btn btn-login wide" :loading="loading" @click="doLogin">
                登 录
              </el-button>
            </el-form>
          </template>
          <template v-else>
            <el-form ref="regFormRef" :model="regForm" :rules="regRules" @keyup.enter="doRegister">
              <el-form-item prop="username">
                <el-input v-model="regForm.username" placeholder="用户名（至少 2 位）" clearable size="large" />
              </el-form-item>
              <el-form-item prop="password">
                <el-input v-model="regForm.password" type="password" placeholder="密码（至少 6 位）" show-password size="large" />
              </el-form-item>
              <el-form-item prop="confirm">
                <el-input v-model="regForm.confirm" type="password" placeholder="确认密码" show-password size="large" />
              </el-form-item>
              <el-button type="primary" size="large" class="btn btn-register wide" :loading="loading" @click="doRegister">
                注 册
              </el-button>
            </el-form>
          </template>
          <p v-if="err" class="err">{{ err }}</p>
          <a class="back" @click="back">‹ 返回</a>
        </div>
      </transition>
    </div>

  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getMe, login, register } from '../api'
import { isAdmin, setAuth } from '../auth'

const router = useRouter()

// leaf-0 = d:\dc2\1.jpg（用户指定初始图）；其余为原轮播叶片图
const images = [
  '/login-imgs/leaf-0.jpg', '/login-imgs/leaf-1.jpg', '/login-imgs/leaf-2.jpg',
  '/login-imgs/leaf-3.jpg', '/login-imgs/leaf-4.jpg', '/login-imgs/leaf-5.jpg',
]
const activeIndex = ref(0)

// 六张图沿“先升后降”圆弧排布（左→右一条抛物线，中间上拱）：中间大、两端小。
// 两端保持现尺寸 88px，中间最大 128px（远小于登录卡 400px）；垂直以 75% 线条为基线，
// 两端贴线、中间上拱；水平最外沿与原来（±516px）一致，中间两张贴卡外缘避让卡片。
const TILE_SIZE = [88, 104, 128, 128, 104, 88] // 尺寸：中间大、两边小
const TILE_RISE = [0, -24, -40, -40, -24, 0]   // 相对基线的上拱量（负=上移）
const INNER_X = 282 // 中间两张中心偏移：卡半宽 200 + 半图 64 + 18px 间隙
const tileIndexes = [0, 1, 2, 3, 4, 5]

const vw = ref(window.innerWidth)
function onResize() {
  vw.value = window.innerWidth
}

function tileStyle(idx) {
  const half = Math.min(470, (vw.value - 100) / 2) // 两侧各留 50px，随视口伸缩
  const mid = Math.round((half + INNER_X) / 2)
  const xs = [-half, -mid, -INNER_X, INNER_X, mid, half]
  return {
    '--tile-x': `${xs[idx]}px`,
    '--tile-rise': `${TILE_RISE[idx]}px`,
    '--tile-size': `${TILE_SIZE[idx]}px`,
  }
}

function selectImage(i) {
  activeIndex.value = i
  resetTimer()
}

let timer = null
function resetTimer() {
  clearInterval(timer)
  timer = setInterval(() => {
    activeIndex.value = (activeIndex.value + 1) % images.length
  }, 8000)
}

// ---------------- 表单 ----------------
const mode = ref('') // '' 显示两按钮；'login' / 'register' 显示表单
const loading = ref(false)
const err = ref('')

const loginFormRef = ref(null)
const regFormRef = ref(null)
const loginForm = reactive({ username: '', password: '' })
const regForm = reactive({ username: '', password: '', confirm: '' })

const loginRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}
const regRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 64, message: '用户名至少 2 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 128, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_, value, cb) => (value === regForm.password ? cb() : cb(new Error('两次输入不一致'))),
      trigger: 'blur',
    },
  ],
}

function back() {
  err.value = ''
  mode.value = ''
}

async function afterAuth(token, username) {
  const me = await getMe()
  setAuth(token, me.data)
  ElMessage.success(`欢迎回来，${username}`)
  router.push(isAdmin() ? '/dashboard' : '/home')
}

async function doLogin() {
  try {
    await loginFormRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  err.value = ''
  try {
    const res = await login(loginForm.username, loginForm.password)
    setAuth(res.data.access_token, null)
    await afterAuth(res.data.access_token, loginForm.username)
  } catch (e) {
    err.value = e.response?.data?.detail || '登录失败，请检查用户名或密码'
  } finally {
    loading.value = false
  }
}

async function doRegister() {
  try {
    await regFormRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  err.value = ''
  try {
    await register(regForm.username, regForm.password)
    // 注册成功：切回登录表单，用户名保留，密码留空由用户手动输入
    loginForm.username = regForm.username
    loginForm.password = ''
    regForm.password = ''
    regForm.confirm = ''
    mode.value = 'login'
    ElMessage.success('注册成功，请登录')
  } catch (e) {
    err.value = e.response?.data?.detail || '注册失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  window.addEventListener('resize', onResize)
  resetTimer()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  clearInterval(timer)
})
</script>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  overflow: hidden;
  background: #eaf6ec;
  font-family: 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ---------- 背景大图：上 3/4 ---------- */
.bg-area {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 75%;
  overflow: hidden;
}
.bg-img {
  position: absolute; inset: 0;
  background-size: cover; background-position: center;
  opacity: 0; transition: opacity 1.2s ease;
}
.bg-img.active { opacity: 1; }
.bg-tint {
  position: absolute; inset: 0;
  background: linear-gradient(180deg, rgba(46,125,50,.16), rgba(46,125,50,.06));
}
/* 底部淡出，融入纯净区 */
.bg-fade {
  position: absolute; left: 0; right: 0; bottom: 0; height: 90px;
  background: linear-gradient(180deg, rgba(234,246,236,0), rgba(234,246,236,.88));
}

/* ---------- 底部 1/4 纯净区 ---------- */
.band {
  position: absolute; left: 0; right: 0; bottom: 0; height: 25%;
  background: linear-gradient(180deg, rgba(234,246,236,.42), #eaf6ec 42%, #f7fbf7);
}

/* ---------- 若有若无的优美线条 ---------- */
.line {
  position: absolute;
  left: 20%; right: 20%; bottom: 25%;
  z-index: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(46,125,50,.30), transparent);
}
.line::after {
  content: '';
  position: absolute; left: 0; right: 0; top: -3px; height: 7px;
  background: linear-gradient(90deg, transparent, rgba(46,125,50,.12), transparent);
  filter: blur(4px);
}

/* ---------- 小方块：圆弧排布（先升后降，中间大两端小） ---------- */
.tiles {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
}
.tile {
  --tile-x: 0px;      /* 相对页面中心的水平偏移 */
  --tile-rise: 0px;   /* 相对 75% 基线的上拱量（负=上移） */
  --tile-size: 88px;
  position: absolute;
  left: calc(50% + var(--tile-x));
  top: 75%;
  width: var(--tile-size);
  height: var(--tile-size);
  border-radius: 16px;
  overflow: hidden;
  cursor: pointer;
  pointer-events: auto;
  border: 2px solid rgba(255, 255, 255, .8);
  box-shadow: 0 8px 20px rgba(0, 0, 0, .16);
  transition: transform .3s ease, box-shadow .3s ease, border-color .3s ease;
  transform: translate(-50%, calc(-50% + var(--tile-rise)));
}
.tile img {
  width: 100%; height: 100%; object-fit: cover;
  display: block;
}
.tile:hover {
  transform: translate(-50%, calc(-50% + var(--tile-rise))) scale(1.09);
  box-shadow: 0 12px 26px rgba(0, 0, 0, .24);
  z-index: 3;
}
.tile.active {
  border-color: #2e7d32;
  box-shadow: 0 0 0 3px rgba(46, 125, 50, .28), 0 12px 26px rgba(0, 0, 0, .22);
}
/* 轻微旋转增加灵动感（作用于 img，不干扰定位/缩放的 transform） */
.tiles .tile:nth-child(1) img { transform: rotate(-5deg); }
.tiles .tile:nth-child(2) img { transform: rotate(3deg); }
.tiles .tile:nth-child(3) img { transform: rotate(-2deg); }
.tiles .tile:nth-child(4) img { transform: rotate(2deg); }
.tiles .tile:nth-child(5) img { transform: rotate(-3deg); }
.tiles .tile:nth-child(6) img { transform: rotate(5deg); }

/* ---------- 中央卡（跨线条居中，不超页面 1/2） ---------- */
.center-card {
  position: absolute;
  left: 50%;
  bottom: 25%;
  transform: translate(-50%, 50%);
  z-index: 3;
  width: 400px;
  max-height: 46vh;
  overflow-y: auto;
  padding: 24px 36px 20px;
  text-align: center;
  background: rgba(255, 255, 255, .58);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, .65);
  box-shadow: 0 14px 44px rgba(46, 125, 50, .20);
}
.logo {
  width: 60px; height: 60px;
  border-radius: 50%;
  object-fit: cover;
  margin: 0 auto 10px;
  border: 2.5px solid #fff;
  box-shadow: 0 5px 14px rgba(46, 125, 50, .32);
}
.title { font-size: 23px; color: #1d2b3a; letter-spacing: 2px; }
.sub { color: #7d8a7d; font-size: 12.5px; margin-top: 4px; }

/* 两按钮 */
.btns { display: flex; gap: 14px; margin-top: 22px; }
.btn {
  flex: 1;
  padding: 11px 0;
  border-radius: 999px;
  border: none;
  font-size: 15px;
  letter-spacing: 6px;
  text-indent: 6px;
  cursor: pointer;
  transition: transform .22s ease, box-shadow .22s ease, background .22s ease, color .22s ease;
}
.btn-login {
  background: linear-gradient(135deg, #2e7d32, #66bb6a);
  color: #fff;
  box-shadow: 0 8px 20px rgba(46, 125, 50, .36);
}
.btn-login:hover { transform: translateY(-2px); box-shadow: 0 12px 26px rgba(46, 125, 50, .44); }
.btn-register {
  background: rgba(255, 255, 255, .92);
  color: #2e7d32;
  border: 1.5px solid #43a047;
}
.btn-register:hover { background: #43a047; color: #fff; transform: translateY(-2px); box-shadow: 0 10px 22px rgba(67, 160, 71, .38); }
.btn.wide { width: 100%; margin-top: 4px; }

/* 表单面板 */
.form-panel { margin-top: 20px; text-align: left; }
.form-panel :deep(.el-form-item) { margin-bottom: 14px; }
.form-panel :deep(.el-input__wrapper) {
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(67, 160, 71, .28) inset;
}
.form-panel :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1.5px #43a047 inset; }
.err { color: #e53935; font-size: 13px; margin-top: 8px; text-align: center; }
.back {
  display: block;
  text-align: center;
  margin-top: 10px;
  color: #7d8a7d;
  font-size: 13px;
  cursor: pointer;
  transition: color .2s;
}
.back:hover { color: #2e7d32; }

/* 面板滑入 */
.slide-enter-active { transition: all .3s ease; }
.slide-leave-active { transition: all .18s ease; }
.slide-enter-from { opacity: 0; transform: translateY(14px); }
.slide-leave-to { opacity: 0; transform: translateY(-10px); }

/* 小屏适配 */
@media (max-width: 900px) {
  .tiles { display: none; }
  .center-card { width: min(400px, 92vw); padding: 20px 24px 16px; max-height: 52vh; }
}
</style>
