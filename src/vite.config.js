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
  css: {
    devSourcemap: false,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: ['node_modules/', 'src/test/', '**/*.spec.js']
    }
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    allowedHosts: true,
    cors: true,
    hmr: {
      protocol: 'wss',
    },
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
        secure: false,
        cookieDomainRewrite: '127.0.0.1',
        cookiePathRewrite: '/'
      },
      '/api/v2': {
        target: 'http://localhost:8000',
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
    cssCodeSplit: false,
  },
  publicDir: 'public'
})
