/* static/app.js */
import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import { createPinia } from 'pinia';
import { ElMessage } from 'element-plus';
import axios from 'axios';
import MarkdownIt from 'markdown-it';
import mdRenderer from 'vue-markdown-render';
import 'element-plus/lib/theme-chalk/index.css';

// 创建 Vue 应用
const app = createApp(App);

// 创建并使用 Pinia 状态管理
const pinia = createPinia();
app.use(pinia);

// 创建 Axios 实例
axios.defaults.baseURL = process.env.VUE_APP_API_URL;
app.config.globalProperties.axios = axios;

// 创建并使用 Vue Router
app.use(router);

// 初始化 Markdown 渲染器
app.config.globalProperties.$markdownIt = new MarkdownIt();

// 挂载 Markdown 渲染器为全局方法
app.config.globalProperties.$markdownRenderer = (content) => {
  return mdRenderer.renderSync({ source: content, extension: [require('markdown-it-mark').default(), require('markdown-it-footnote').default()] });
};

// 定义全局 non-data-API 委托
app.config.errorHandler = (err, vm, info) => {
  // 在控制台显示错误信息
  console.error(`非数据 API 处理程序捕获了错误：${info}`, err);
  // 弹窗显示错误信息
  ElMessage({
    message: `非数据 API 处理程序捕获了错误：${info}`,
    type: 'error',
    duration: 5 * 1000
  });
};

// 使用 Element Plus 组件库
app.use(ElementPlus);

// 挂载应用
app.mount('#app');