// static/app.js
// 全局前端脚本，初始化Vue 3应用、路由、状态管理及Element Plus组件库

import { createApp } from 'vue';
import { createPinia } from 'pinia';
import { createRouter, createWebHistory } from 'vue-router';
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import App from './App.vue'; // 假设主组件在App.vue
import routes from './router'; // 修复导入路径
import { useAuthStore } from './stores/authentication'; // 假设认证store在stores/authentication.js

// 初始化Pinia状态管理
const pinia = createPinia();

// 初始化Vue Router
const router = createRouter({
  history: createWebHistory(),
  routes
});

// 创建Vue应用实例
const app = createApp(App);

// 注册Element Plus组件库
app.use(ElementPlus);

// 注册Pinia
app.use(pinia);

// 全局axios配置
import axios from 'axios';
import { useNotification } from 'element-plus';

// 创建axios实例并设置基础URL
const apiClient = axios.create({
  baseURL: 'https://api.blogcms.dev', // 指向后端API的域名
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  }
});

// 请求拦截器（添加JWT token）
apiClient.interceptors.request.use((config) => {
  const authStore = useAuthStore();
  const token = authStore.getToken;
  
  // 如果存在token且未在刷新中，添加到请求头
  if (token && !authStore.isRefreshing) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  
  return config;
});

// 响应拦截器（处理错误和全局通知）
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    // 401错误处理：自动刷新token
    if (error.config && error.response?.status === 401) {
      const authStore = useAuthStore();
      if (!authStore.isRefreshing) {
        authStore.isRefreshing = true;
        try {
          const refreshResponse = await apiClient.post('/api/auth/refresh', {
            refresh_token: authStore.getRefreshToken
          });
          
          // 更新token和刷新时间
          authStore.setToken(refreshResponse.data.access_token);
          authStore.setRefreshToken(refreshResponse.data.refresh_token);
          authStore.setRefreshTime(Date.now());
          
          // 重新发送原始请求
          const originalRequest = error.config;
          originalRequest.headers.Authorization = `Bearer ${authStore.getToken}`;
          
          return apiClient(originalRequest);
        } catch (refreshError) {
          // 刷新失败，清除状态并跳转登录
          authStore.clearAuth();
          useNotification().create('error', '认证失败', '请重新登录');
          router.push('/login');
        }
      }
    }
    
    // 其他错误类型
    if (error.response) {
      useNotification().create('error', '请求失败', error.response.data.message || '服务器错误');
    } else if (error.request) {
      useNotification().create('error', '网络问题', '无法连接到服务器');
    } else {
      useNotification().create('error', '请求错误', error.message);
    }
    
    return Promise.reject(error);
  }
);

// 注册全局API客户端
app.config.globalProperties.$api = apiClient;

// 全局组件注册（可选）
// app.component('CommentCard', () => import('./components/UI/CommentCard.vue')); 

// 路由守卫 - 权限验证
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore();
  
  // 公共路由（不需要认证）
  if (to.meta.public) {
    return next();
  }
  
  // 需要认证的路由
  if (authStore.isAuthenticated) {
    return next();
  }
  
  // 未认证且需要权限，跳转登录
  if (to.meta.requiresAuth) {
    useNotification().create('warning', '未认证', '请先登录再访问此页面');
    return next('/login');
  }
  
  // 其他情况继续
  next();
});

// 挂载应用
app.mount('#app');