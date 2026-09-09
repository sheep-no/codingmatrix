import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import { useUserStore } from './stores/user'
import { initApiClient } from './utils/api/index'
import { installPerformanceMetrics } from './utils/performanceMetrics'
import ToastContainer from './components/ToastContainer.vue'

// 导入全局样式
import './styles/index.css'
import './styles/agent-layout.css'

const app = createApp(App)

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

app.use(pinia)
const performanceMetrics = installPerformanceMetrics(router)
app.use(router)
app.component('ToastContainer', ToastContainer)

// 创建 userStore 实例并初始化 API 客户端（必须在 use(pinia) 之后）
const userStore = useUserStore()
initApiClient(userStore)

// 将首屏初始化暴露为可重建的 Promise，让 AppLoading 绑定真实生命周期。
const initializeUser = () => Promise.resolve().then(() => userStore.restoreUser())
window.__appInitialization = initializeUser()
window.__retryAppInitialization = () => {
  window.__appInitialization = initializeUser()
  return window.__appInitialization
}

if (import.meta.hot) import.meta.hot.dispose(() => performanceMetrics.stop())

app.mount('#app')
