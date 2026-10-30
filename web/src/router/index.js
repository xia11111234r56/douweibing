import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  // 按角色分流：管理员→系统概览，普通用户→科普首页
  {
    path: '/',
    redirect: () => {
      try {
        const user = JSON.parse(localStorage.getItem('dc2_user'))
        return user?.role === 'admin' ? '/dashboard' : '/home'
      } catch {
        return '/home'
      }
    },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/home',
    name: 'home',
    component: () => import('../views/Home.vue'),
    meta: { title: '科普首页' },
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { title: '概览', admin: true },
  },
  {
    path: '/recognize',
    name: 'recognize',
    component: () => import('../views/Recognize.vue'),
    meta: { title: '图片识别' },
  },
  {
    path: '/diseases',
    name: 'diseases',
    component: () => import('../views/Diseases.vue'),
    meta: { title: '病害知识库' },
  },
  {
    path: '/search',
    name: 'search',
    component: () => import('../views/Search.vue'),
    meta: { title: '多维检索' },
  },
  {
    path: '/graph',
    name: 'graph',
    component: () => import('../views/Graph.vue'),
    meta: { title: '知识图谱' },
  },
  {
    path: '/gis',
    name: 'gis',
    component: () => import('../views/Gis.vue'),
    meta: { title: 'GIS 种植信息' },
  },
  {
    path: '/stats',
    name: 'stats',
    component: () => import('../views/Stats.vue'),
    meta: { title: '数据统计', admin: true },
  },
  {
    path: '/recognitions',
    name: 'recognitions',
    component: () => import('../views/Recognitions.vue'),
    meta: { title: '识别记录' },
  },
  {
    path: '/users',
    name: 'users',
    component: () => import('../views/Users.vue'),
    meta: { title: '用户管理', admin: true },
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('../views/Logs.vue'),
    meta: { title: '操作日志', admin: true },
  },
  {
    path: '/about',
    name: 'about',
    component: () => import('../views/About.vue'),
    meta: { title: '关于' },
  },
  { path: '/:pathMatch(.*)*', name: 'notfound', component: () => import('../views/NotFound.vue'), meta: { title: '页面不存在' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 未登录访问任何页面 → /login；已登录访问 /login → 按角色回首页
// admin 专属页面：非管理员跳回科普首页
function homeOfRole() {
  try {
    const user = JSON.parse(localStorage.getItem('dc2_user'))
    return user?.role === 'admin' ? '/dashboard' : '/home'
  } catch {
    return '/home'
  }
}
router.beforeEach((to) => {
  const token = localStorage.getItem('dc2_token')
  if (to.path !== '/login' && !token) return '/login'
  if (to.path === '/login' && token) return homeOfRole()
  if (to.meta?.admin && token) {
    try {
      const user = JSON.parse(localStorage.getItem('dc2_user'))
      if (user?.role !== 'admin') return '/home'
    } catch {
      return '/home'
    }
  }
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 豆卫兵` : '豆卫兵'
})

export default router
