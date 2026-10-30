import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发时代理后端（FastAPI 默认 8000 端口），避免跨域
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
