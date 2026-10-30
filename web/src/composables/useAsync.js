import { ref } from 'vue'

// 统一的请求状态管理：loading / error + run。
// 用法：
//   const { loading, error, run } = useAsync()
//   run(async () => { ... })
// 模板中：v-loading="loading"，error 时 el-alert + 重试按钮。
export function useAsync() {
  const loading = ref(false)
  const error = ref('')

  async function run(fn) {
    loading.value = true
    error.value = ''
    try {
      await fn()
    } catch (e) {
      error.value = e?.response?.data?.detail || e?.message || '请求失败'
    } finally {
      loading.value = false
    }
  }

  return { loading, error, run }
}
