<template>
  <div class="ppt-preview-page">
    <header class="page-header">
      <button class="back-btn" @click="goBack">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        返回
      </button>
      <div class="header-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
        <span>PPT 预览</span>
      </div>
      <div class="header-actions">
        <a v-if="downloadUrl" :href="downloadUrl" class="btn btn-primary">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          下载 PPT
        </a>
      </div>
    </header>

    <div v-if="slides.length > 0" class="page-content">
      <div class="slides-container">
        <div 
          v-for="(slide, index) in slides" 
          :key="index" 
          class="slide-card"
        >
          <div class="slide-header">
            <div class="slide-number">幻灯片 {{ index + 1 }}</div>
            <div class="slide-type">{{ slide.type || '内容' }}</div>
          </div>
          <div class="slide-body">
            <div class="slide-title">{{ slide.title }}</div>
            <div class="slide-content">{{ slide.content }}</div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="page-content">
      <div class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
        <p>暂无幻灯片数据</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const pptId = route.params.id
const slides = ref([])
const downloadUrl = ref('')

// 从路由状态获取幻灯片数据（如果存在）
if (route.query.slides) {
  try {
    slides.value = JSON.parse(decodeURIComponent(route.query.slides))
  } catch (e) {
    console.error('Failed to parse slides from route query:', e)
  }
}

// 如果没有路由状态数据，则从API获取
async function loadSlides() {
  if (slides.value.length > 0) return
  
  try {
    const response = await fetch(`/api/v1/pptx/${pptId}/slides`)
    if (response.ok) {
      const data = await response.json()
      if (data.slides) {
        slides.value = data.slides
        downloadUrl.value = `/api/v1/pptx/download/${pptId}?format=pptx`
      }
    }
  } catch (error) {
    console.error('加载幻灯片失败:', error)
  }
}

function goBack() {
  router.go(-1)
}

onMounted(() => {
  loadSlides()
})
</script>

<style scoped>
.ppt-preview-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.back-btn {
  background: none;
  border: none;
  color: var(--text-primary);
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  transition: background 0.2s;
}

.back-btn:hover {
  background: var(--hover-bg);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-title svg {
  width: 24px;
  height: 24px;
}

.header-actions .btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 500;
}

.page-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}

.slides-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
  gap: 24px;
}

.slide-card {
  background: var(--bg-secondary);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px var(--shadow-color);
}

.slide-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--teal-hover);
  color: white;
}

.slide-number {
  font-weight: 600;
  font-size: 14px;
}

.slide-type {
  font-size: 12px;
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
}

.slide-body {
  padding: 20px;
}

.slide-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.slide-content {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-line;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
}

.empty-state svg {
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  color: var(--text-tertiary);
}
</style>