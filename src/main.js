import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'

import App from './App.vue'
import router from './router'
import { useUserStore } from './stores/user'
import { initApiClient } from './utils/api/index'
import ToastContainer from './components/ToastContainer.vue'

// 导入全局样式
import './styles/index.css'

const app = createApp(App)

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

app.use(pinia)
app.use(router)
app.component('ToastContainer', ToastContainer)

// 创建 userStore 实例并初始化 API 客户端
const userStore = useUserStore()
initApiClient(userStore)

app.mount('#app')
