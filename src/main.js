import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import { useUserStore } from './stores/user'
import { initApiClient } from './utils/api/index'
import ToastContainer from './components/ToastContainer.vue'

// 导入全局样式
import './styles/index.css'
import './styles/agent-layout.css'

const app = createApp(App)

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

app.use(pinia)
app.use(router)
app.use(ElementPlus)
app.component('ToastContainer', ToastContainer)

// 创建 userStore 实例并初始化 API 客户端（必须在 use(pinia) 之后）
const userStore = useUserStore()
initApiClient(userStore)

// 恢复用户状态（刷新页面后保持登录）
userStore.restoreUser()

app.mount('#app')
