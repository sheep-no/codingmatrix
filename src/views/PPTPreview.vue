<template>
  <div class="ppt-preview-page">
    <!-- 页面头部 -->
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="返回 PPT 生成页" @click="goBack">
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
        <button v-if="showPDFDownload" class="btn btn-secondary" type="button" @click="downloadPDF">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          下载 PDF
        </button>
        <button v-if="pptId" class="btn btn-primary" type="button" @click="downloadPPTX">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          下载 PPTX
        </button>
      </div>
    </header>

    <div v-if="pdfPreview" class="html-preview-container">
      <p>成品 PDF 预览（静态页面，动画请下载 PPTX 查看）</p>
      <iframe :src="pdfPreview" title="成品 PDF 预览" class="preview-iframe"></iframe>
    </div>
    <div v-else-if="htmlPreview" class="html-preview-container">
      <p>结构预览：用于核对内容，成品排版请下载文件查看。</p>
      <iframe
        :srcdoc="htmlPreview"
        class="preview-iframe"
        sandbox="allow-scripts"
        frameborder="0"
      ></iframe>
    </div>

    <section v-if="qualityReport" class="quality-report-card">
      <div class="quality-report-heading">
        <strong>生成质量 {{ qualityReport.overall_score }}（规则评分）</strong>
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
      <div v-if="visualReviewDegraded" class="quality-report-warning" role="alert">
        <p>视觉复审未完成，当前保留规则检查结果。请下载成品人工复核排版、文字和图片。</p>
        <p>请在设置中检查用户模型凭据与服务可用性；渲染失败请联系管理员检查 PDF 渲染依赖。修复后可重新生成并选择精修模式。</p>
        <button class="btn btn-secondary" type="button" @click="router.push('/settings')">检查模型设置</button>
        <button class="btn btn-secondary" type="button" @click="downloadPPTX">下载成品人工复核</button>
      </div>
      <ul v-if="qualityReport.issues?.length" class="quality-report-issues">
        <li v-for="(issue, index) in qualityReport.issues.slice(0, 5)" :key="`${issue.slide_id || 'deck'}-${index}`">
          <strong>{{ formatIssueType(issue.issue_type) }}</strong>
          <span>{{ issue.issue_type === 'vision_review_unavailable' ? '视觉复审未完成，请按上方提示处理。' : `${issue.slide_id ? `${issue.slide_id}: ` : ''}${issue.message || issue.issue_type}` }}</span>
          <span v-if="issue.fix_action && issue.issue_type !== 'vision_review_unavailable'" class="quality-fix-action">修复动作：{{ formatFixAction(issue.fix_action) }}</span>
        </li>
      </ul>
    </section>

    <section v-if="qualityReport?.outline_id" class="quality-report-card slide-edit-panel">
      <strong>修改指定页面</strong>
      <p>基于当前预览的大纲 v{{ qualityReport.outline_version }}，仅修改所选页面内容，保留其他页面内容和顺序。保存为新版本并重新导出整份 PPTX，旧文件仍可下载；配图和排版可能重新计算。</p>
      <p v-if="outlineError" role="alert">{{ outlineError }} <button class="btn btn-secondary" @click="loadEditableOutline">重新加载</button></p>
      <p v-else-if="!editableOutline">正在加载对应版本的大纲...</p>
      <template v-else>
        <label>目标页面
          <select v-model="selectedSlideId" :disabled="savingSlide || !!savedVersion" @change="selectSlide">
            <option v-for="page in editableOutline.slides" :key="page.id" :value="page.id">第 {{ page.position + 2 }} 页：{{ page.title }}</option>
          </select>
        </label>
        <form v-if="editedSlide" @submit.prevent="saveSlide">
          <fieldset :disabled="savingSlide || !!savedVersion">
            <label>标题<input v-model="editedSlide.title" class="slide-title-input" maxlength="300" required></label>
            <label>核心结论<textarea v-model="editedSlide.key_message" class="slide-message-input" maxlength="1000" required></textarea></label>
            <label v-for="(block, index) in editedSlide.content_blocks" :key="index">正文 {{ index + 1 }}
              <textarea v-model="block.content" class="slide-block-input" maxlength="5000"></textarea>
            </label>
            <label>演讲备注<textarea v-model="editedSlide.speaker_notes" maxlength="5000"></textarea></label>
            <label><input v-model="editOptions.auto_images" type="checkbox">自动配图</label>
            <label><input v-model="editOptions.enable_animation" type="checkbox">页面切换动画</label>
          </fieldset>
          <p v-if="editError" role="alert">{{ editError }}</p>
          <button class="btn btn-primary quality-regenerate-btn" :disabled="savingSlide" type="submit">{{ savingSlide ? '正在创建导出任务...' : savedVersion ? '重试导出已保存版本' : '保存修改并导出整份新文件' }}</button>
        </form>
      </template>
    </section>

    <!-- 传统幻灯片预览（回退） -->
    <div v-if="!pdfPreview && !htmlPreview && slides.length > 0" class="page-content">
      <p>结构预览：用于核对内容，成品排版请下载文件查看。</p>
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
            <div class="slide-content">{{ slideContent(slide) }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-else-if="!pdfPreview && !htmlPreview && isLoading" class="page-content">
      <div class="loading-state">
        <div class="loading-spinner"></div>
        <p>正在加载预览...</p>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!pdfPreview && !htmlPreview && !slides.length" class="page-content">
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
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/utils/api/index'
import { ElMessage } from 'element-plus'
import { useApiKeyStore } from '@/stores/apikey'

const route = useRoute()
const router = useRouter()
const apiKeyStore = useApiKeyStore()

const pptId = route.params.id
const slides = ref([])
const htmlPreview = ref('')
const pdfPreview = ref('')
let disposed = false
const showPDFDownload = ref(false)
const isLoading = ref(true)
const qualityReport = ref(null)
const visualReviewDegraded = computed(() => !!qualityReport.value?.degraded_stage ||
  qualityReport.value?.issues?.some(issue => issue.issue_type === 'vision_review_unavailable'))
const editableOutline = ref(null)
const outlineError = ref('')
const selectedSlideId = ref('')
const editedSlide = ref(null)
const savingSlide = ref(false)
const savedVersion = ref(null)
const editError = ref('')
const editOptions = ref({ auto_images: true, enable_animation: true })

function selectSlide() {
  const slide = editableOutline.value?.slides.find(page => page.id === selectedSlideId.value)
  editedSlide.value = slide ? JSON.parse(JSON.stringify(slide)) : null
  editError.value = ''
}

async function loadEditableOutline() {
  outlineError.value = ''
  try {
    const report = qualityReport.value
    editableOutline.value = await api.ppt.getOutline(report.outline_id, report.outline_version)
    selectedSlideId.value = editableOutline.value.slides[0]?.id || ''
    selectSlide()
  } catch (error) {
    outlineError.value = error.message
  }
}

async function saveSlide() {
  if (savingSlide.value || !editedSlide.value) return
  const slide = editedSlide.value
  if (!slide.title.trim() || !slide.key_message.trim() || !slide.content_blocks.some(block => block.content.trim())) {
    editError.value = '请填写页面标题、核心结论和正文'
    return
  }
  savingSlide.value = true
  editError.value = ''
  try {
    const report = qualityReport.value
    const options = { ...editOptions.value, api_key_token: apiKeyStore.siliconflowKey?.token || null }
    const task = savedVersion.value
      ? await api.ppt.generateFromOutline(report.outline_id, report.quality_mode, savedVersion.value, options)
      : await api.ppt.regenerateOutlineSlide(report.outline_id, slide.id, report.quality_mode, slide, report.outline_version, options)
    await router.push({ path: '/ppt-generate', query: { task_id: task.task_id } })
  } catch (error) {
    if (error.savedVersion) savedVersion.value = error.savedVersion
    editError.value = error.message
  } finally {
    savingSlide.value = false
  }
}

function slideContent(slide) {
  if (slide.content_blocks?.length) return slide.content_blocks.map(block => block.content).join('\n')
  return Array.isArray(slide.content) ? slide.content.join('\n') : slide.content
}

async function loadPdfPreview() {
  try {
    const blob = await api.ppt.downloadPDF(pptId)
    if (disposed || blob.type !== 'application/pdf') return false
    pdfPreview.value = URL.createObjectURL(blob)
    showPDFDownload.value = true
    isLoading.value = false
    return true
  } catch {
    return false
  }
}

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
  vision_review_unavailable: '视觉复审未完成',
  vision_review_low_confidence: '视觉复审需人工确认',
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
    if (qualityReport.value?.outline_id) await loadEditableOutline()
  } catch {
    qualityReport.value = null
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
    ElMessage.error('成品下载失败，请稍后重试或检查登录状态。')
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
  const quality = loadQualityReport()
  const hasPreview = await loadPdfPreview() || await loadHtmlPreview()
  if (!hasPreview) {
    await loadSlides()
  }
  await quality
})

onBeforeUnmount(() => {
  disposed = true
  if (pdfPreview.value) URL.revokeObjectURL(pdfPreview.value)
})
</script>

<style scoped>
.slide-edit-panel label { display: block; margin: 10px 0; }
.slide-edit-panel fieldset { padding: 0; border: 0; min-width: 0; }
.slide-edit-panel input:not([type="checkbox"]),
.slide-edit-panel textarea,
.slide-edit-panel select { display: block; box-sizing: border-box; width: 100%; padding: 8px; color: var(--text-primary); background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; }
.slide-edit-panel textarea { min-height: 70px; resize: vertical; }
.slide-edit-panel p { line-height: 1.6; overflow-wrap: anywhere; }

.quality-report-card {
  margin: 16px 24px 0;
  padding: 16px 20px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--bg-secondary);
  overflow-wrap: anywhere;
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
  overflow-y: auto;
  background: var(--bg-primary);
  color: var(--text-primary);
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
  display: flex;
  flex-direction: column;
  min-height: 320px;
  background: #1a1a1a;
  overflow: hidden;
  min-width: 0;
}

.html-preview-container > p {
  margin: 0;
  padding: 10px 16px;
  color: #f3f4f6;
  font-size: 13px;
}

.preview-iframe {
  width: 100%;
  flex: 1;
  min-height: 0;
  border: none;
}

.page-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  min-width: 0;
}

.slides-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(500px, 100%), 1fr));
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
  overflow-wrap: anywhere;
}

@media (max-width: 600px) {
  .page-header {
    flex-wrap: wrap;
    gap: 12px;
  }

  .quality-report-heading,
  .quality-report-meta {
    flex-wrap: wrap;
  }

  .page-header { padding: 12px 16px; }
  .header-title { font-size: 16px; }
  .header-actions { width: 100%; justify-content: flex-end; gap: 8px; }
  .header-actions .btn { flex: 1; justify-content: center; padding: 10px 8px; }
  .html-preview-container { min-height: 280px; }
  .page-content { padding: 16px; }
  .quality-report-card { margin: 12px 16px 0; padding: 14px 16px; }
  .quality-report-meta { line-height: 1.6; }
  .quality-regenerate-btn { margin: 8px 0 0; width: 100%; }
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
