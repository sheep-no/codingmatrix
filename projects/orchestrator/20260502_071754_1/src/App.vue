<template>
  <div id="app" class="app-container">
    <!-- 顶部导航栏 -->
    <header class="app-header">
      <div class="logo">五子棋大师 (Gomoku Master)</div>
      <nav class="nav-menu">
        <router-link to="/game" class="nav-item">双人对战</router-link>
        <router-link to="/history" class="nav-item">战绩展示</router-link>
        <button class="start-btn">开始游戏</button>
      </nav>
    </header>

    <!-- 主内容区域 -->
    <main class="app-main">
      <RouterView v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </RouterView>
    </main>

    <!-- 底部功能栏 -->
    <footer class="app-footer">
      <div class="footer-links">
        <a href="#">隐私政策</a>
        <a href="#">服务条款</a>
      </div>
      <p>&copy; 2026 五子棋大师. All rights reserved.</p>
    </footer>

    <!-- 全局错误边界 -->
    <div v-if="isError" class="error-overlay" style="display: none;">
      <h3>系统错误</h3>
      <p>{{ errorDetail }}</p>
    </div>
  </div>
</template>

<script setup>
  import { ref, onMounted, onErrorCaptured } from 'vue'
  import { useRouter, useRoute } from 'vue-router'
  import { createPinia } from 'pinia'
  import axios from 'axios'
  import { useFormWarningAction } from 'vue-form-state'
  
  // 初始化错误边界
  const isError = ref(false)
  const errorDetail = ref()
  
  // 初始化错误监听，捕获全局错误
  onMounted(() => {
    try {
      // 这里是 Vue App 通常挂载的地方
      const app = import.meta.env.APP피스
      // 模拟在 main.js 中加载的路由和 Store
      window.parent.postMessage({ type: 'INIT_COMPLETE' }, '*')
      
      // 错误捕获
      onErrorCaptured()
    } catch (err) {
      isError.value = true
      errorDetail.value = "应用初始化出错，请查看控制台。"
    }
  })

  // 监听 Vue Router 错误
  const router = useRouter()
  router.onError((err) => {
    isError.value = true
    errorDetail.value = err.message
  })

  // 错误边界配置
  onErrorCaptured((err) => {
    console.error('应用错误捕获:', err)
    isError.value = true
  })

  // 引用 Axios 实例配置（通常在 main.js，但此处可定义全局配置）
  const authHeader = axios
    .getDefaultConfig()
    .headers
    .Authorization
  </script>

  <style scoped>
    /* 全局应用样式 */
    #app {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background-color: #f5f5f5;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }

    /* 顶部导航栏 */
    .app-header {
      background-color: #e8f3d6;
      padding: 1rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .logo {
      font-size: 1.5rem;
      font-weight: bold;
      color: #2c3e50;
    }

    .nav-menu {
      display: flex;
      gap: 1rem;
    }

    .nav-item {
      color: #4a5568;
      text-decoration: none;
      padding: 0.5rem 1rem;
      border-radius: 4px;
      transition: background-color 0.3s;
    }

    .nav-item:hover {
      background-color: rgba(0, 0, 0, 0.05);
    }

    /* 游戏按钮 */
    .start-btn {
      background-color: #2c7a2c;
      color: white;
      padding: 0.5rem 1rem;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-weight: bold;
      transition: background-color 0.3s;
    }

    .start-btn:hover {
      background-color: #1e5c1e;
    }

    /* 主内容区域 */
    .app-main {
      flex: 1;
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 1rem;
    }

    /* 轮播动画 */
    .fade-enter-active,
    .fade-leave-active {
      transition: opacity 0.5s ease;
    }

    .fade-enter-from,
    .fade-leave-to {
      opacity: 0;
    }

    /* 底部功能栏 */
    .app-footer {
      background-color: #2d3e50;
      color: white;
      padding: 1rem 2rem;
      text-align: center;
      font-size: 0.9rem;
    }

    .footer-links {
      margin-bottom: 0.5rem;
    }

    .footer-links a {
      color: #a0aec0;
      text-decoration: none;
      margin: 0 0.5rem;
    }

    .footer-links a:hover {
      color: white;
    }
  </style>