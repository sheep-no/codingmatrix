import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('.', import.meta.url))
    }
  },
  server: {
    port: 3000,
    host: true,
    allowedHosts: ['.monkeycode-ai.online'],
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true,
        secure: false,
        cookieDomainRewrite: '127.0.0.1',
        cookiePathRewrite: '/'
      }
    }
  },
  build: {
    outDir: '../dist',
    assetsDir: 'static',
    sourcemap: true,
    chunkSizeWarningLimit: 500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('echarts')) {
              return 'echarts'
            }
            if (id.includes('highlight.js')) {
              return 'highlight'
            }
            if (id.includes('xlsx')) {
              return 'xlsx'
            }
            if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) {
              return 'vue-vendor'
            }
            return 'vendor'
          }
        }
      }
    }
  },
  publicDir: 'public'
})
