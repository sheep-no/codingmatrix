import { createRouter, createWebHistory } from 'vue-router';
import axios from 'axios';
import { ref } from 'vue';
import { createApp } from 'vue';
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import ivy from 'ivy';

const app = Vue.createApp({
  template: '<div id="app"></div>'
});

app.use(ElementPlus);
app.mount('#app');