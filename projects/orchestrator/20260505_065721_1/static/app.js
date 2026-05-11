import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import store from './store';
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import { createPinia } from 'pinia';
import axios from 'axios';
import 'axios/dist/axios.min.css';

// 配置 axios
axios.defaults.baseURL = 'http://localhost:8000/api'; // 假设后端 API 地址
axios.defaults.withCredentials = true;

// 创建 Vite 实例并初始化应用
const app = createApp(App);

// 挂载 Element Plus
app.use(ElementPlus);

// 挂载 Pinia 状态管理库
const pinia = createPinia();
app.use(pinia);

// 挂载 Vue Router
app.use(router);

// 挂载 Axios
app.config.globalProperties.axios = axios;

// 使 router 能够使用 store 和 axios
router.beforeEach((to, from, next) => {
  if (to.matched.some(record => record.meta.requiresAuth)) {
    // 要求用户认证
    if (!store.state.user.isAuthenticated) {
      next('/login');
    } else {
      next();
    }
  } else {
    next();
  }
});

// 应用挂载
app.mount('#app');