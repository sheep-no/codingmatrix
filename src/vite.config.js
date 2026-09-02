import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

function configureSseProxy(proxy) {
  proxy.on('proxyRes', (proxyRes, req, res) => {
    const contentType = proxyRes.headers['content-type'] || ''
    if (contentType.includes('text/event-stream')) {
      proxyRes.headers['cache-control'] = 'no-cache'
      proxyRes.headers['x-accel-buffering'] = 'no'
      res.writeHead(proxyRes.statusCode, proxyRes.headers)
      proxyRes.on('data', (chunk) => {
        res.write(chunk)
        if (res.flush) res.flush()
      })
      proxyRes.on('end', () => res.end())
    } else {
      res.writeHead(proxyRes.statusCode, proxyRes.headers)
      proxyRes.pipe(res)
    }
  })
}

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
    // P2 清理：allowedHosts 改为显式列表，部署到 *.monkeycode-ai.online 时不会被 Vite 拒
    // 之前 allowedHosts: true 等价于允许所有 Host 头（不安全）
    // 现在明确列出：本地开发 + 线上预览域名
    allowedHosts: ['localhost', '127.0.0.1', '.monkeycode-ai.online'],
    cors: true,
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
        secure: false,
        selfHandleResponse: true,
        cookieDomainRewrite: '127.0.0.1',
        cookiePathRewrite: '/',
        configure: configureSseProxy
      },
      '/api/v2': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
        secure: false,
        selfHandleResponse: true,
        cookieDomainRewrite: '127.0.0.1',
        cookiePathRewrite: '/',
        configure: configureSseProxy
      }
    }
  },
  build: {
    outDir: '../dist',
    assetsDir: 'static',
    sourcemap: process.env.VITE_BUILD_SOURCEMAP === 'true',
    chunkSizeWarningLimit: 500,
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-vue': ['vue', 'vue-router', 'pinia'],
          'vendor-element': ['element-plus'],
          'vendor-echarts': ['echarts'],
          'vendor-markdown': ['markdown-it', 'marked', 'highlight.js'],
          'vendor-files': ['jszip', 'xlsx'],
          'vendor-utils': ['axios', 'dompurify']
        }
      }
    }
  },
  publicDir: 'public'
})
