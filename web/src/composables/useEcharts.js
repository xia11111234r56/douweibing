import { nextTick, onBeforeUnmount, onMounted } from 'vue'
import * as echarts from 'echarts'

// 安全的 echarts 实例管理：复用同一实例（防重复 init 泄漏）、
// 统一 window.resize 监听与卸载时 dispose。
// 用法：
//   const chartEl = ref(null)
//   const { setOption } = useEcharts(chartEl)
//   setOption({...})
export function useEcharts(elRef) {
  let chart = null

  async function ensureChart() {
    // 容器若是 v-if/v-else 条件渲染，首次 setOption 时 DOM 可能还没挂载，
    // 等一帧再 init，避免图表空白。
    if (!chart) {
      if (elRef.value) {
        chart = echarts.init(elRef.value)
      } else {
        await nextTick()
        if (elRef.value) chart = echarts.init(elRef.value)
      }
    }
    return chart
  }

  function getChart() {
    return chart
  }

  async function setOption(option, opts) {
    const c = await ensureChart()
    if (c) c.setOption(option, opts)
    return c
  }

  function dispose() {
    if (chart) {
      chart.dispose()
      chart = null
    }
  }

  function onResize() {
    if (chart) chart.resize()
  }

  onMounted(() => window.addEventListener('resize', onResize))
  onBeforeUnmount(() => {
    window.removeEventListener('resize', onResize)
    dispose()
  })

  return { getChart, setOption, dispose }
}
