import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite dev server. /api is proxied to the Python backend so the frontend
// can call relative paths and avoid CORS during local testing.
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
})
