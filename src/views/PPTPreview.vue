<template>
  <div class="ppt-preview-page">
    <!-- 页面头部 -->
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
        <!-- 下载按钮 -->
        <button v-if="showPDFDownload" class="btn btn-secondary" @click="downloadPDF">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          下载 PDF
        </button>
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

    <!-- 真实 HTML 预览 -->
    <div v-if="htmlPreview" class="html-preview-container">
      <iframe
        :srcdoc="htmlPreview"
        class="preview-iframe"
        sandbox="allow-scripts"
        frameborder="0"
      ></iframe>
    </div>

    <!-- 传统幻灯片预览（回退） -->
    <div v-else-if="slides.length > 0" class="page-content">
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

    <!-- 加载中 -->
    <div v-else-if="isLoading" class="page-content">
      <div class="loading-state">
        <div class="loading-spinner"></div>
        <p>正在加载预览...</p>
      </div>
    </div>

    <!-- 空状态 -->
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
import { api } from '@/utils/api/index'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()

const pptId = route.params.id
const slides = ref([])
const htmlPreview = ref('')
const downloadUrl = ref('')
const showPDFDownload = ref(false)
const isLoading = ref(true)

// 从路由状态获取幻灯片数据（如果存在）
if (route.query.slides) {
  try {
    slides.value = JSON.parse(decodeURIComponent(route.query.slides))
    isLoading.value = false
  } catch (e) {
    console.error('Failed to parse slides from route query:', e)
  }
}

// 加载 HTML 预览
async function loadHtmlPreview() {
  try {
    const html = await api.ppt.previewPPTHtml(pptId)
    if (html) {
      htmlPreview.value = html
      showPDFDownload.value = true
      isLoading.value = false
      return true
    }
  } catch (error) {
    console.error('加载 HTML 预览失败:', error)
  }
  return false
}

// 如果没有 HTML 预览，则加载传统幻灯片数据
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
  } finally {
    isLoading.value = false
  }
}

// 下载 PDF（当前回退为 PPTX）
async function downloadPDF() {
  try {
    const blob = await api.ppt.downloadPDF(pptId)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ppt-${pptId}.pptx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (error) {
    console.error('下载失败:', error)
    ElMessage.error('下载失败：' + error.message)
  }
}

function goBack() {
  router.go(-1)
}

onMounted(async () => {
  // 优先尝试加载 HTML 预览
  const hasHtmlPreview = await loadHtmlPreview()
  
  // 如果 HTML 预览加载失败，回退到传统方式
  if (!hasHtmlPreview) {
    await loadSlides()
  }
  
  // 设置下载 URL
  if (pptId && !downloadUrl.value) {
    downloadUrl.value = `/api/v1/pptx/download/${pptId}?format=pptx`
  }
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

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-actions .btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover {
  background: var(--color-primary-dark);
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover {
  background: var(--bg-secondary);
}

.btn svg {
  width: 16px;
  height: 16px;
}

/* HTML 预览容器 */
.html-preview-container {
  flex: 1;
  background: #1a1a1a;
  overflow: hidden;
}

.preview-iframe {
  width: 100%;
  height: 100%;
  border: none;
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

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-color);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 空状态 */
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
