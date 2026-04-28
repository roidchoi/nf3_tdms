import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  // --- [Phase 7] 백엔드 API 연동 프록시 설정 ---
  server: {
    proxy: {
      // 1. 일반 REST API 프록시 (http -> http)
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      // 2. WebSocket 로그 스트리밍 프록시 (ws -> ws)
      '/api/v1/admin/logs/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        changeOrigin: true
      }
    }
  }
  // ------------------------------------------------
})