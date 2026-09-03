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
        <button v-if="pptId" class="btn btn-primary" @click="downloadPPTX">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          下载 PPTX
        </button>
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

    <section v-if="qualityReport" class="quality-report-card">
      <div class="quality-report-heading">
        <strong>生成质量 {{ qualityReport.overall_score }}</strong>
        <span>{{ qualityReport.quality_mode === 'refined' ? '精修模式' : '标准模式' }}</span>
      </div>
      <div class="quality-report-meta">
        大纲版本 v{{ qualityReport.outline_version }} · {{ qualityReport.issues?.length || 0 }} 个问题 ·
        {{ Object.keys(qualityReport.reflow_attempts || {}).length }} 页执行过重排
      </div>
      <div v-if="Object.keys(qualityReport.slide_scores || {}).length" class="quality-slide-scores">
        <span v-for="(score, slideId) in qualityReport.slide_scores" :key="slideId">{{ slideId }} {{ score }} 分</span>
      </div>
      <div v-if="manualReviewSlides.length" class="quality-manual-review">
        需人工复核：{{ manualReviewSlides.join('、') }}
      </div>
      <div v-if="qualityReport.degraded_stage" class="quality-report-warning">视觉复审已降级：{{ qualityReport.degraded_stage }}</div>
      <ul v-if="qualityReport.issues?.length" class="quality-report-issues">
        <li v-for="(issue, index) in qualityReport.issues.slice(0, 5)" :key="`${issue.slide_id || 'deck'}-${index}`">
          <strong>{{ formatIssueType(issue.issue_type) }}</strong>
          <span>{{ issue.slide_id ? `${issue.slide_id}: ` : '' }}{{ issue.message || issue.issue_type }}</span>
          <span v-if="issue.fix_action" class="quality-fix-action">修复动作：{{ formatFixAction(issue.fix_action) }}</span>
          <button v-if="issue.slide_id && qualityReport.outline_id" class="quality-regenerate-btn" @click="regenerateSlide(issue.slide_id)">重新生成此页</button>
        </li>
      </ul>
    </section>

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
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/utils/api/index'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()

const pptId = route.params.id
const slides = ref([])
const htmlPreview = ref('')
const showPDFDownload = ref(false)
const isLoading = ref(true)
const qualityReport = ref(null)

const manualReviewSlides = computed(() => {
  if (qualityReport.value?.manual_review_slides?.length) {
    return qualityReport.value.manual_review_slides
  }
  const attempts = qualityReport.value?.reflow_attempts || {}
  return [...new Set((qualityReport.value?.issues || [])
    .filter(issue => issue.slide_id && issue.severity === 'high' && attempts[issue.slide_id] >= 2)
    .map(issue => issue.slide_id))]
})

const issueTypeLabels = {
  text_overflow: '文本溢出',
  element_overlap: '元素重叠',
  low_contrast: '对比度不足',
  unsafe_margin: '超出安全区',
  image_distortion: '图片变形',
  layout_repetition: '布局重复',
}

const fixActionLabels = {
  reduce_text_or_switch_layout: '缩减文本或切换布局',
  reposition_elements: '重新定位元素',
  adjust_text_color: '调整文字或背景颜色',
  move_into_safe_area: '移入页面安全区',
  preserve_aspect_ratio: '保持图片宽高比',
  switch_layout: '切换页面布局',
}

function formatIssueType(issueType) {
  return issueTypeLabels[issueType] || issueType || '质量问题'
}

function formatFixAction(action) {
  return fixActionLabels[action] || action
}

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
    const data = await api.ppt.getPPTSlides(pptId)
    if (data && data.slides) {
      slides.value = data.slides
    }
  } catch (error) {
    console.error('加载幻灯片失败:', error)
  } finally {
    isLoading.value = false
  }
}

async function loadQualityReport() {
  try {
    qualityReport.value = await api.ppt.getQualityReport(pptId)
  } catch {
    qualityReport.value = null
  }
}

async function regenerateSlide(slideId) {
  try {
    const task = await api.ppt.regenerateOutlineSlide(
      qualityReport.value.outline_id,
      slideId,
      qualityReport.value.quality_mode
    )
    ElMessage.success('页面再生成任务已创建')
    router.push(`/ppt/generate?task_id=${task.task_id}`)
  } catch (error) {
    ElMessage.error('页面再生成失败：' + error.message)
  }
}

// 下载 PPTX
async function downloadPPTX() {
  try {
    const blob = await api.ppt.downloadPPT(pptId, 'pptx')
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

// 下载 PDF
async function downloadPDF() {
  try {
    const blob = await api.ppt.downloadPDF(pptId)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ppt-${pptId}.pdf`
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
  await loadQualityReport()
})
</script>

<style scoped>
.quality-report-card {
  margin: 16px 24px 0;
  padding: 16px 20px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--bg-secondary);
}

.quality-report-heading,
.quality-report-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.quality-report-meta {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.quality-report-warning {
  margin-top: 8px;
  color: #b45309;
  font-size: 13px;
}

.quality-slide-scores {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.quality-slide-scores span {
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 12px;
}

.quality-manual-review {
  margin-top: 10px;
  padding: 8px 10px;
  border-left: 3px solid #dc2626;
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
  font-size: 13px;
  font-weight: 600;
}

.quality-report-issues li {
  margin-top: 8px;
}

.quality-report-issues li > span {
  margin-left: 8px;
}

.quality-fix-action {
  color: var(--text-secondary);
  font-size: 12px;
}

.quality-regenerate-btn {
  margin-left: 10px;
  border: 0;
  background: transparent;
  color: var(--primary-color, #2563eb);
  cursor: pointer;
}

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
