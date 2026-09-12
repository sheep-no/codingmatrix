<template>
  <div class="ppt-generate-page">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="返回首页" @click="goBack">
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
        <span>AI PPT 生成</span>
      </div>
      <div class="header-actions">
         <button class="header-btn" type="button" title="生成历史" :aria-expanded="showHistoryPanel" aria-controls="ppt-history-panel" @click="toggleHistory">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
          历史
        </button>
        <span class="header-hint">Agent 驱动自然语言生成</span>
      </div>
    </header>

    <div class="page-content">
      <aside class="config-panel">
        <div class="form-group">
          <label>主题 / 描述 <span class="required">*</span></label>
          <textarea
            v-model="topic"
            placeholder="请输入 PPT 主题，例如：'帮我做一个关于 2026 年人工智能发展趋势的技术汇报'"
            rows="4"
            :disabled="generating"
          ></textarea>
          <div class="char-count">{{ topic.length }} / 2000</div>
        </div>

        <!-- 文件上传区域 -->
        <div class="form-group">
          <label>上传文件生成 <span class="optional">(可选)</span></label>
          <div
            class="file-upload-area"
            :class="{ 'has-file': uploadedFile }"
            @dragover.prevent
            @drop.prevent="handleFileDrop"
          >
            <div v-if="!uploadedFile" class="upload-placeholder" @click="triggerFileInput">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <p>拖拽文件到此处，或点击上传</p>
              <span class="upload-hint">支持 PDF、Word、TXT、Markdown、代码文件</span>
            </div>
            <div v-else class="file-info">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="24" height="24">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              <div class="file-details">
                <span class="file-name">{{ uploadedFile.name }}</span>
                <span class="file-size">{{ formatFileSize(uploadedFile.size) }}</span>
              </div>
              <button class="remove-file" title="移除文件" @click.stop="removeFile">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          </div>
          <input ref="fileInputRef" type="file" accept=".txt,.md,.pdf,.docx,.doc,.py,.js,.ts,.json,.yaml,.yml,.csv,.log" style="display:none" @change="handleFileSelect" />
        </div>

        <div class="form-group">
          <label>选择模板</label>
          <button type="button" class="template-card template-auto" :class="{ selected: selectedTemplate === 'auto' }"
            :disabled="outlineSaving || workflowStep !== 1" :aria-pressed="selectedTemplate === 'auto'" @click="selectedTemplate = 'auto'">
            自动推荐 · 根据主题与场景选择
          </button>
           <p class="template-hint">样张来自固定 PPTX 的真实 PDF/PNG 渲染；样张生成中或不可用时显示色彩示意。</p>
          <div class="template-grid">
            <button
              v-for="tpl in templates"
              :key="tpl.id"
              type="button"
              class="template-card"
              :disabled="outlineSaving || workflowStep !== 1"
              :aria-pressed="selectedTemplate === tpl.id"
              :class="{ selected: selectedTemplate === tpl.id }"
              @click="selectedTemplate = tpl.id"
            >
               <div class="template-preview" :style="{ background: tpl.color }">
                 <img v-if="tpl.sample?.status === 'available'" :src="tpl.sample.slides[0]" :alt="`${tpl.name} 封面样张`" loading="lazy">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <line x1="8" y1="8" x2="16" y2="8"/>
                  <line x1="8" y1="12" x2="16" y2="12"/>
                  <line x1="8" y1="16" x2="12" y2="16"/>
                </svg>
              </div>
              <div class="template-name">{{ tpl.name }}</div>
              <p class="template-description">{{ tpl.description || '模板描述暂缺' }}</p>
              <p class="template-description">场景：{{ tpl.scenarios?.length ? tpl.scenarios.map(scenarioLabel).join('、') : '场景信息暂缺' }}</p>
            </button>
          </div>
          <p v-if="templateListError" class="template-hint" role="status">模板注册表暂不可用，当前显示备用配色。
            <button type="button" @click="loadTemplates">重新加载模板</button>
          </p>
          <div v-if="outlineDraft?.template_id" class="template-result" role="status">
            <strong>{{ automaticSelection ? '自动选择结果' : '已采用模板' }}：{{ templateName(outlineDraft.template_id) }}</strong>
            <p>模板 ID：{{ outlineDraft.template_id }}</p>
            <p v-if="templateRecommendation">场景：{{ scenarioLabel(templateRecommendation.scenario) }}；推荐模板：{{ templateRecommendation.templates.map(templateName).join('、') }}</p>
            <p v-else-if="recommendationLoading">正在加载场景推荐...</p>
            <p v-else>推荐信息暂不可用，已采用模板保持有效。<button type="button" @click="loadRecommendation">重试推荐</button></p>
          </div>
        </div>

        <div class="form-group">
          <label>高级选项</label>
          <div class="advanced-options">
            <div class="option-item">
              <label class="option-label">
                <span>页数</span>
                <select v-model="slideCount" class="option-select">
                  <option value="auto">自动（按主题决定）</option>
                  <option value="8">约 8 页</option>
                  <option value="12">约 12 页</option>
                  <option value="16">约 16 页</option>
                  <option value="20">约 20 页</option>
                </select>
              </label>
              <p class="option-hint">默认按主题复杂度自动决定页数，也可指定大致页数作为参考。</p>
            </div>
            <div class="option-item">
              <label class="option-label">
                <span>输出格式</span>
                <select v-model="outputFormat" class="option-select">
                  <option value="pptx">PPTX (PowerPoint)</option>
                  <option value="html">HTML (在线预览)</option>
                  <option value="markdown">Markdown (文档)</option>
                </select>
              </label>
            </div>
            <div class="option-item">
              <label class="option-label">
                <input v-model="autoImages" type="checkbox" class="option-checkbox" />
                <span>自动配图（PPTX 成品）</span>
              </label>
            </div>
            <div class="option-item">
              <label class="option-label">
                <input v-model="enableAnimation" type="checkbox" class="option-checkbox" />
                <span>页面切换动画（PPTX 播放时生效）</span>
              </label>
            </div>
          </div>
        </div>

        <div v-if="workflowStep === 3" class="quality-mode-panel">
          <div class="workflow-heading"><span>第 3 步：选择质量模式</span></div>
          <label v-for="mode in qualityModes" :key="mode.id" class="quality-mode-option">
            <input v-model="qualityMode" type="radio" :value="mode.id" />
            <span><strong>{{ mode.name }}</strong><small>{{ mode.description }}</small></span>
          </label>
          <button class="generate-btn" :disabled="generating" @click="generateApprovedOutline">开始生成 PPT</button>
        </div>

        <button
          v-if="!generating && workflowStep === 1"
          class="generate-btn"
          :disabled="outlineSaving || !canGenerate"
          @click="handleGenerate"
        >
          {{ outlineSaving ? '正在生成大纲...' : uploadedFile ? '根据文件生成 PPT' : '一键生成 PPT' }}
        </button>
        <button
          v-else-if="generating"
          class="generate-btn cancel-btn"
          @click="handleCancel"
        >
          <span class="loading-spinner"></span>
          取消生成
        </button>

        <TaskFeedbackPanel
          :feedback="taskFeedbackState"
          :connection-status="taskFeedbackConnection"
          :visible="hasTaskFeedback"
          :actions="taskFeedbackActions"
          @action="handleTaskFeedbackAction"
        />
      </aside>

      <main class="preview-panel">
        <div v-if="outlineDrafting" class="outline-drafting" role="status">
          <div class="spinner-ring"></div>
          <h3>正在生成大纲</h3>
          <p>{{ outlineStages[outlineStageIndex] }}</p>
          <ol class="stage-list">
            <li v-for="(stage, index) in outlineStages" :key="stage" :class="{ done: index < outlineStageIndex, current: index === outlineStageIndex }">
              {{ stage }}
            </li>
          </ol>
          <ol v-if="outlineSlides.length" class="generation-slide-list">
            <li v-for="(slide, index) in outlineSlides" :key="slide.id || index" class="done">
              <span>{{ index + 1 }}</span>
              <strong>{{ slide.title || `第 ${index + 1} 页` }}</strong>
            </li>
          </ol>
        </div>

        <div v-else-if="workflowStep >= 2 && !generating && !generatedFileUrl" class="outline-review-panel">
          <div class="workflow-heading">
            <span>第 2 步：审阅大纲</span>
            <div class="workflow-heading-actions">
              <span class="outline-total">当前 {{ outlineSlides.length }} 页内容（另加封面）</span>
              <span class="workflow-version">v{{ outlineDraft?.version || 1 }}</span>
              <button class="outline-add-btn" type="button" :disabled="outlineSlides.length >= 49" @click="addOutlineSlide">新增页面</button>
            </div>
          </div>
          <div class="outline-board">
            <div v-for="(slide, index) in outlineSlides" :key="slide.id" class="outline-slide-editor">
              <span class="outline-index">{{ index + 1 }}</span>
              <div class="outline-fields">
                <select v-model="slide.slide_type" class="outline-type-select" aria-label="页面类型">
                  <option value="key_points">要点页</option>
                  <option value="comparison">对比页</option>
                  <option value="timeline">时间线</option>
                  <option value="data_chart">数据图表</option>
                  <option value="closing">结论页</option>
                </select>
                <input v-model="slide.title" class="outline-title-input" placeholder="页面标题" />
                <input v-model="slide.key_message" class="outline-message-input" placeholder="页面核心结论" />
                <textarea v-model="slide.content_blocks[0].content" class="outline-content-input" rows="3" placeholder="页面内容"></textarea>
                <div v-if="slideValidationMessages(slide).length" class="outline-validation">
                  {{ slideValidationMessages(slide).join('；') }}
                </div>
              </div>
              <div class="outline-slide-actions">
                <button class="outline-move-up" type="button" :disabled="index === 0" :aria-label="`上移第 ${index + 1} 页`" @click="moveOutlineSlide(index, -1)">上移</button>
                <button class="outline-move-down" type="button" :disabled="index === outlineSlides.length - 1" :aria-label="`下移第 ${index + 1} 页`" @click="moveOutlineSlide(index, 1)">下移</button>
                <button class="outline-remove" type="button" :disabled="outlineSlides.length === 1" :aria-label="`删除第 ${index + 1} 页`" @click="removeOutlineSlide(index)">删除</button>
              </div>
            </div>
          </div>
          <button class="generate-btn outline-approve-btn" :disabled="outlineSaving || !outlineCanApprove" @click="approveOutline">
            {{ outlineSaving ? '正在保存...' : '批准大纲并继续' }}
          </button>
        </div>

        <div v-else-if="!generatedSlides.length && !generating && !generatedFileUrl" class="preview-placeholder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
          </svg>
          <p>描述您的想法，AI Agent 将自动完成大纲、排版和配图</p>
        </div>

        <div v-else-if="generating && !generatedFileUrl" class="generation-live">
          <div class="progress-section">
            <div class="progress-header">
              <span class="progress-title">正在生成 PPT</span>
              <span class="progress-percentage">{{ generationPercent }}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: generationPercent + '%' }"></div>
            </div>
            <p class="progress-step">{{ progressState?.step || 'starting' }}</p>
            <p class="progress-message">{{ progressState?.message || '正在准备生成任务...' }}</p>
          </div>
          <ol class="generation-slide-list">
            <li
              v-for="(slide, index) in outlineSlides"
              :key="slide.id"
              :class="{ current: currentRenderingIndex === index, done: currentRenderingIndex > index }"
            >
              <span>{{ index + 1 }}</span>
              <strong>{{ slide.title || `第 ${index + 1} 页` }}</strong>
            </li>
          </ol>
        </div>

        <div v-else-if="generatedFileUrl" class="success-container">
          <h3>生成成功!</h3>
          <div class="success-actions">
            <button class="download-link" @click="downloadPpt">
              下载 PPTX 文件
            </button>
            <button v-if="currentTaskId" class="download-link pdf-link" @click="downloadPdf">
              下载 PDF
            </button>
            <button class="preview-btn" @click="goToPreview">
              在线预览
            </button>
            <button class="modify-btn" @click="showModifyPanel = !showModifyPanel">
              {{ showModifyPanel ? '收起修改' : '修改 PPT' }}
            </button>
          </div>

          <!-- 修改面板 -->
          <div v-if="showModifyPanel" class="modify-panel">
            <div class="modify-input-group">
              <textarea
                v-model="modifyInput"
                placeholder="输入修改需求，例如：&#10;- 把第三页的标题改成 XXX&#10;- 将背景色改成蓝色&#10;- 添加一页关于...的内容"
                rows="3"
                :disabled="isModifying"
              ></textarea>
              <div class="modify-actions">
                <button
                  class="btn-analyze"
                  :disabled="isModifying"
                  @click="handleAnalyze"
                >
                  分析 PPT
                </button>
                <button
                  class="btn-apply"
                  :disabled="!modifyInput.trim() || isModifying"
                  @click="handleModify"
                >
                  {{ isModifying ? '修改中...' : '应用修改' }}
                </button>
              </div>
            </div>

            <!-- 修改历史 -->
            <div v-if="modifyHistory.length > 0" class="modify-history">
              <h4>修改历史</h4>
              <div
                v-for="(item, index) in modifyHistory"
                :key="index"
                class="history-item"
              >
                <span class="history-index">{{ index + 1 }}.</span>
                <span class="history-input">{{ item.input }}</span>
                <span class="history-time">{{ formatTime(item.timestamp) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-else-if="generatedSlides.length" class="slides-preview">
          <div v-for="(slide, index) in generatedSlides" :key="index" class="slide-card">
            <div class="slide-header">
              <span class="slide-number">Slide {{ index + 1 }}</span>
              <span class="slide-type">{{ slide.type || 'content' }}</span>
            </div>
            <h3>{{ slide.title }}</h3>
            <ul v-if="slide.bullets && slide.bullets.length">
              <li v-for="bullet in slide.bullets" :key="bullet">{{ bullet }}</li>
            </ul>
            <p v-else>{{ slide.content }}</p>
          </div>
        </div>
      </main>
    </div>

    <!-- 历史记录面板 -->
    <div v-if="showHistoryPanel" class="history-panel-overlay" @click.self="showHistoryPanel = false">
          <div id="ppt-history-panel" class="history-panel" role="dialog" aria-modal="true" aria-label="生成历史">
        <div class="history-panel-header">
          <h3>生成历史</h3>
          <button class="close-btn" @click="showHistoryPanel = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="history-panel-body">
          <div v-if="loadingHistory" class="history-loading">加载中...</div>
          <div v-else-if="historyError" class="history-empty" role="alert">
            <p>{{ historyError }}</p>
            <button type="button" class="history-action-btn" @click="loadHistory">重新加载</button>
          </div>
          <div v-else-if="historyList.length === 0" class="history-empty">暂无历史记录</div>
          <div v-else class="history-list">
            <div v-for="item in historyList" :key="item.task_id" class="history-card">
              <div class="history-card-header">
                <span class="history-card-title">{{ historyTitle(item) }}</span>
                <span class="history-card-time">{{ historyTime(item) }}</span>
              </div>
              <div class="history-card-meta">
                <span>{{ item.slide_count || '-' }} 页</span>
                <span>{{ item.has_file === false ? '无成品文件' : '可预览' }}</span>
              </div>
              <div class="history-card-actions">
                <button class="history-action-btn history-preview-btn" type="button" :disabled="item.has_file === false" @click="previewHistory(item)">预览</button>
                <button class="history-action-btn history-load-btn" type="button" @click="loadFromHistory(item)">加载</button>
                <button class="history-action-btn" type="button" :disabled="item.has_file === false" @click="downloadHistory(item.task_id)">下载</button>
                <button class="history-action-btn delete" type="button" @click="deleteHistory(item.task_id)">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApiKeyStore } from '@/stores/apikey'
import { api } from '@/utils/api/index'
import { ElMessage } from 'element-plus'
import { useTokenManager } from '@/utils/tokenManager'
import { useTaskFeedback } from '@/composables/useTaskFeedback'
import TaskFeedbackPanel from '@/components/TaskFeedbackPanel.vue'

const router = useRouter()
const route = useRoute()
const apiKeyStore = useApiKeyStore()
const { getToken } = useTokenManager()

const topic = ref('')
const selectedTemplate = ref('modern')
const automaticSelection = ref(false)
const templateRecommendation = ref(null)
const recommendationLoading = ref(false)
const recommendationTopic = ref('')
const templateListError = ref(false)
const scenarioNames = { business: '商务汇报', data_report: '数据报告', product_pitch: '产品路演', academic: '学术研究', education: '教育培训', general: '通用' }
const scenarioLabel = scenario => scenarioNames[scenario] || scenario
const templateName = id => templates.value.find(template => template.id === id)?.name || id
const slideCount = ref('auto')
const outputFormat = ref('pptx')
const autoImages = ref(true)
const enableAnimation = ref(true)
const workflowStep = ref(1)
const outlineDraft = ref(null)
const outlineSlides = ref([])
const outlineSaving = ref(false)
const outlineDrafting = ref(false)
const qualityMode = ref('standard')
const qualityModes = [
  { id: 'standard', name: '标准模式', description: '规则质检和自动重排，速度更快' },
  { id: 'refined', name: '精修模式', description: '增加逐页视觉复审，适合正式交付' },
]
const generating = ref(false)
const generatedSlides = ref([])
const generatedFileUrl = ref('')
const progressState = ref(null)
const PPT_SESSION_KEY = 'ppt-generate-session-v1'
const outlineStages = ['分析主题与受众', '检索参考资料', '起草页面结构', '整理可编辑大纲']
const outlineStageIndex = ref(0)
let outlineStageTimer = null
let outlineAbort = null
let outlineRequestId = 0
const taskFeedback = useTaskFeedback('ppt')
const taskFeedbackState = taskFeedback.feedback
const taskFeedbackConnection = taskFeedback.connectionStatus
const hasTaskFeedback = taskFeedback.hasFeedback
const taskFeedbackActions = computed(() => {
  const status = taskFeedbackState.value.status
  if (status === 'running') return [{ key: 'cancel', label: '取消生成', variant: 'danger' }]
  if (status === 'failed' || status === 'paused') return [{ key: 'retry', label: '重新生成', variant: 'primary' }]
  if (status === 'completed') return [{ key: 'preview', label: '在线预览', variant: 'primary' }, { key: 'download', label: '下载 PPTX' }]
  return []
})

function handleTaskFeedbackAction(action) {
  if (action === 'cancel') handleCancel()
  if (action === 'retry') {
    if (workflowStep.value === 3) generateApprovedOutline()
    else handleGenerate()
  }
  if (action === 'preview') goToPreview()
  if (action === 'download') downloadPpt()
}

// 文件上传相关
const uploadedFile = ref(null)
const uploadedMaterialId = ref(null)
const fileInputRef = ref(null)

// 历史记录相关
const showHistoryPanel = ref(false)
const historyList = ref([])
const loadingHistory = ref(false)
const historyError = ref('')

// 增量修改相关状态
const currentTaskId = ref('')
const showModifyPanel = ref(false)
const modifyInput = ref('')
const isModifying = ref(false)
const modifyHistory = ref([])

const templates = ref([
  { id: 'modern', name: '现代简约', color: 'linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)' },
  { id: 'business', name: '商务专业', color: 'linear-gradient(135deg, #1e40af 0%, #3b82f6 100%)' },
  { id: 'tech', name: '科技蓝调', color: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)' },
  { id: 'creative', name: '创意设计', color: 'linear-gradient(135deg, #dc2626 0%, #ea580c 100%)' },
  { id: 'elegant', name: '优雅商务', color: 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)' },
  { id: 'minimal', name: '极简主义', color: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)' },
  { id: 'academic', name: '学术研究', color: 'linear-gradient(135deg, #0369a1 0%, #0c4a6e 100%)' },
  { id: 'education', name: '教育培训', color: 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)' },
  { id: 'medical', name: '医疗健康', color: 'linear-gradient(135deg, #059669 0%, #047857 100%)' }
])

let ws = null
let reconnectTimer = null
let reconnectAttempts = 0
let intentionalSocketClose = false
const MAX_RECONNECT_ATTEMPTS = 3

async function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

async function downloadPpt() {
  if (!currentTaskId.value) return
  try {
    await downloadBlob(await api.ppt.downloadPPT(currentTaskId.value), `presentation_${currentTaskId.value}.pptx`)
  } catch (error) {
    ElMessage.error('PPTX 下载失败: ' + error.message)
  }
}

async function downloadHistory(taskId) {
  try {
    await downloadBlob(await api.ppt.downloadPPT(taskId), `presentation_${taskId}.pptx`)
  } catch (error) {
    ElMessage.error('下载失败: ' + error.message)
  }
}

const canGenerate = computed(() => {
  return (topic.value.trim().length > 0 || uploadedFile.value) && topic.value.length <= 2000
})

const outlineCanApprove = computed(() => outlineSlides.value.length > 0 && outlineSlides.value.every(isOutlineSlideValid))

const generationPercent = computed(() => {
  const raw = progressState.value?.progress
  if (raw == null) return 8
  const value = raw <= 1 ? raw * 100 : raw
  return Math.max(8, Math.min(100, Math.round(value)))
})

const currentRenderingIndex = computed(() => {
  const message = progressState.value?.message || ''
  const match = message.match(/第\s*(\d+)\s*页/)
  return match ? Number(match[1]) - 1 : -1
})

let localSlideSequence = 0

function normalizeOutlineSlides(slides) {
  return (slides || []).map((slide, position) => ({
    ...slide,
    position,
    slide_type: slide.slide_type || 'key_points',
    narrative_role: slide.narrative_role || 'opportunity_map',
    content_blocks: slide.content_blocks?.length
      ? slide.content_blocks.map(block => ({ type: 'text', metadata: {}, ...block }))
      : [{ type: 'text', content: '', metadata: {} }],
  }))
}

function isOutlineSlideValid(slide) {
  return Boolean(
    slide.title?.trim()
    && slide.key_message?.trim()
    && slide.content_blocks?.some(block => block.content?.trim())
  )
}

function slideValidationMessages(slide) {
  const messages = []
  if (!slide.title?.trim()) messages.push('请填写页面标题')
  if (!slide.key_message?.trim()) messages.push('请填写页面核心结论')
  if (!slide.content_blocks?.some(block => block.content?.trim())) messages.push('请填写有效页面内容')
  return messages
}

function reindexOutlineSlides() {
  outlineSlides.value.forEach((slide, position) => {
    slide.position = position
  })
}

function addOutlineSlide() {
  if (outlineSlides.value.length >= 49) return
  outlineSlides.value.push({
    id: `draft-slide-${Date.now()}-${localSlideSequence++}`,
    position: outlineSlides.value.length,
    slide_type: 'key_points',
    narrative_role: 'opportunity_map',
    evidence_sources: [],
    title: '',
    key_message: '',
    content_blocks: [{ type: 'text', content: '', metadata: {} }],
    asset_intent: null,
    speaker_notes: '',
  })
}

function removeOutlineSlide(index) {
  if (outlineSlides.value.length <= 1) return
  outlineSlides.value.splice(index, 1)
  reindexOutlineSlides()
}

function moveOutlineSlide(index, direction) {
  const target = index + direction
  if (target < 0 || target >= outlineSlides.value.length) return
  const [slide] = outlineSlides.value.splice(index, 1)
  outlineSlides.value.splice(target, 0, slide)
  reindexOutlineSlides()
}

function goBack() {
  router.push('/')
}

function goToPreview() {
  const fromUrl = String(generatedFileUrl.value || '').match(/\/pptx\/download\/([^/?#]+)/)
  const pptId = currentTaskId.value || fromUrl?.[1] || ''
  if (pptId) router.push(`/ppt-preview/${pptId}`)
}

async function downloadPdf() {
  if (!currentTaskId.value) return
  try {
    const blob = await api.ppt.downloadPDF(currentTaskId.value)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `presentation_${currentTaskId.value}.pdf`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('PDF 下载失败:', e)
    ElMessage.error('PDF 下载失败: ' + e.message)
  }
}

async function loadTemplates() {
  templateListError.value = false
  try {
    const result = await api.ppt.getTemplates()
    if (result.templates && result.templates.length > 0) {
      templates.value = result.templates.map(t => ({
        id: t.id,
        name: t.name_zh || t.name,
        description: t.description,
        scenarios: t.scenarios,
        color: `linear-gradient(135deg, ${t.primary_color || '#667eea'} 0%, ${t.primary_color || '#764ba2'}80 100%)`
      }))
    } else templateListError.value = true
  } catch {
    templateListError.value = true
  }
}

async function loadRecommendation() {
  if (recommendationLoading.value) return
  recommendationLoading.value = true
  try {
    const result = await api.ppt.getTemplates(null, { topic: recommendationTopic.value, scenario: outlineDraft.value?.scenario })
    templateRecommendation.value = result.scenario && Array.isArray(result.templates) && result.templates.length
      ? result : null
  } catch {
    templateRecommendation.value = null
  } finally {
    recommendationLoading.value = false
  }
}

// 文件上传相关函数
function triggerFileInput() {
  fileInputRef.value?.click()
}

function handleFileSelect(e) {
  const file = e.target.files?.[0]
  if (file) setUploadedFile(file)
}

function handleFileDrop(e) {
  const file = e.dataTransfer.files?.[0]
  if (file) setUploadedFile(file)
}

function setUploadedFile(file) {
  const maxSize = 50 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.error('文件过大，最大支持 50MB')
    return
  }
  uploadedFile.value = file
  uploadedMaterialId.value = null
}

function removeFile() {
  uploadedFile.value = null
  uploadedMaterialId.value = null
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

// 历史记录相关函数
function historyTitle(item) {
  return item?.title || item?.topic || '未命名'
}

function historyTime(item) {
  if (!item?.created_at) return ''
  const date = new Date(item.created_at)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN')
}

async function toggleHistory() {
  showHistoryPanel.value = !showHistoryPanel.value
  if (showHistoryPanel.value) await loadHistory()
}

async function loadHistory() {
  loadingHistory.value = true
  historyError.value = ''
  try {
    const result = await api.ppt.getHistory(1, 20)
    historyList.value = result.records || []
  } catch (e) {
    historyList.value = []
    historyError.value = e.message || '加载历史失败'
  } finally {
    loadingHistory.value = false
  }
}

function loadFromHistory(item) {
  topic.value = item.topic || item.title || ''
  if (item.template || item.template_id) {
    selectedTemplate.value = item.template || item.template_id
  }
  slideCount.value = item.slide_count ? String(item.slide_count) : 'auto'
  if (item.task_id && item.has_file !== false) {
    currentTaskId.value = item.task_id
    generatedFileUrl.value = `/api/v1/pptx/download/${item.task_id}`
    generating.value = false
  }
  showHistoryPanel.value = false
  ElMessage.success('已加载历史记录')
}

function previewHistory(item) {
  if (!item?.task_id || item.has_file === false) return
  showHistoryPanel.value = false
  router.push(`/ppt-preview/${item.task_id}`)
}

async function deleteHistory(taskId) {
  if (!window.confirm('删除后无法恢复，确定删除这份 PPT？')) return
  try {
    const result = await api.ppt.deleteHistory(taskId)
    if (!result?.success) {
      ElMessage.error('删除失败')
      return
    }
    historyList.value = historyList.value.filter(h => h.task_id !== taskId)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败: ' + e.message)
  }
}

function clearReconnectTimer() {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function closeWebSocket() {
  intentionalSocketClose = true
  clearReconnectTimer()
  if (ws) {
    ws.close(1000)
    ws = null
  }
}

function scheduleWebSocketReconnect(taskId) {
  if (!generating.value || intentionalSocketClose || reconnectTimer !== null) return
  reconnectAttempts += 1
  if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
    generating.value = false
    taskFeedback.markDisconnected('任务连接恢复失败，生成上下文和已接收进度已保留')
    return
  }

  taskFeedback.markReconnecting(`连接中断，正在进行第 ${reconnectAttempts} 次恢复`)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connectWebSocket(taskId)
  }, Math.min(4000, 500 * (2 ** (reconnectAttempts - 1))))
}

function resultFromPptEvent(data) {
  return data.result ?? data.payload?.result ?? data.payload ?? data.state?.result ?? null
}

function applyPptResult(rawResult) {
  if (!rawResult) return
  try {
    const resultData = typeof rawResult === 'string' ? JSON.parse(rawResult) : rawResult
    if (resultData.slides) generatedSlides.value = resultData.slides
    if (resultData.ppt_id || resultData.filename) {
      const pid = resultData.ppt_id || resultData.filename.replace('.pptx', '')
      currentTaskId.value = pid
      generatedFileUrl.value = `/api/v1/pptx/download/${pid}`
    }
  } catch (error) {
    console.warn('解析结果数据失败:', error)
  }
}

function connectWebSocket(taskId) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = getToken()
  const params = new URLSearchParams({ token: token || '' })
  if (taskFeedback.lastSequence.value !== null) {
    params.set('after_sequence', String(taskFeedback.lastSequence.value))
  }
  const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/ppt/${taskId}?${params}`

  intentionalSocketClose = false
  ws = new WebSocket(wsUrl)

  ws.onopen = () => taskFeedback.markConnected()

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      const updateResult = taskFeedback.update(data)
      if (updateResult.gap) {
        ws?.close(4000, 'event sequence gap')
        return
      }
      if (!updateResult.applied) return
      reconnectAttempts = 0
      const normalized = taskFeedback.feedback.value
      progressState.value = {
        progress: normalized.progress === null ? 0 : normalized.progress / 100,
        step: normalized.stage,
        message: data.message ?? data.payload?.message ?? ''
      }

      if (normalized.status === 'completed') {
        taskFeedback.complete({ stage: 'PPT 生成完成', progress: 100, nextAction: '预览或下载演示文稿' })
        generating.value = false
        applyPptResult(resultFromPptEvent(data))
        closeWebSocket()
        ElMessage.success('PPT 生成完成!')
      } else if (normalized.status === 'failed') {
        taskFeedback.fail(normalized.error || '生成失败', { stage: 'PPT 生成失败', nextAction: '检查内容后重新生成' })
        generating.value = false
        closeWebSocket()
        ElMessage.error('生成失败: ' + (data.error || data.message || '未知错误'))
      } else if (normalized.status === 'paused' && ['cancelled', 'canceled', 'stopped'].includes(
        String(data.status ?? data.step ?? data.payload?.status ?? data.payload?.step ?? '').toLowerCase()
      )) {
        taskFeedback.update({ status: 'cancelled', step: 'cancelled', nextAction: '调整内容后重新生成' })
        generating.value = false
        closeWebSocket()
      }
    } catch (error) {
      console.error('WebSocket 消息解析失败:', error)
    }
  }

  ws.onerror = () => {
    if (generating.value && !intentionalSocketClose) taskFeedback.markReconnecting('PPT 进度连接中断，正在恢复')
  }
  ws.onclose = (event) => {
    ws = null
    if (event.code !== 1000 && generating.value && !intentionalSocketClose) scheduleWebSocketReconnect(taskId)
  }
}

function applyOutlineStreamEvent(event) {
  if (!event || typeof event !== 'object') return
  if (event.type === 'stage') {
    const index = typeof event.index === 'number' ? event.index : outlineStages.indexOf(event.label)
    if (index >= 0) {
      outlineStageIndex.value = index
      stopOutlineStages()
    }
    return
  }
  if (event.type === 'retry') {
    outlineSlides.value = []
    return
  }
  if (event.type === 'slide' && event.slide) {
    const existing = outlineSlides.value || []
    const next = existing.some(slide => slide.id && slide.id === event.slide.id)
      ? existing.map(slide => (slide.id === event.slide.id ? { ...slide, ...event.slide } : slide))
      : [...existing, event.slide]
    outlineSlides.value = normalizeOutlineSlides(next)
  }
}

function isOutlineRequestCanceled(error) {
  return error?.name === 'AbortError' || error?.isCanceled || error?.code === 'REQUEST_ABORTED'
}

async function handleGenerate({ resume = false } = {}) {
  if (!canGenerate.value || generating.value) return
  if (!apiKeyStore.hasSiliconflowKey) {
    ElMessage.error('请先配置 API Key 后再使用')
    router.push('/settings')
    return
  }

  if (workflowStep.value === 1) {
    const requestId = ++outlineRequestId
    startOutlineStages()
    outlineDrafting.value = true
    outlineSaving.value = true
    if (!resume) outlineSlides.value = []
    try {
      if (uploadedFile.value && !uploadedMaterialId.value) {
        const uploaded = await api.uploadFile(uploadedFile.value)
        uploadedMaterialId.value = uploaded.id
      }
      const outlinePayload = {
        topic: topic.value.trim() || uploadedFile.value?.name || '未命名演示',
        description: topic.value.trim(),
        template_id: selectedTemplate.value,
        api_key_token: apiKeyStore.siliconflowKey?.token || null,
        material_file_ids: uploadedMaterialId.value ? [uploadedMaterialId.value] : [],
      }
      if (slideCount.value !== 'auto') outlinePayload.num_slides = parseInt(slideCount.value, 10)
      outlineAbort?.abort()
      outlineAbort = typeof AbortController === 'function' ? new AbortController() : null
      persistSession()
      const draft = await api.ppt.createOutline(outlinePayload, {
        signal: outlineAbort?.signal,
        onEvent: applyOutlineStreamEvent,
      })
      outlineDraft.value = draft
      automaticSelection.value = selectedTemplate.value === 'auto'
      if (draft.template_id) selectedTemplate.value = draft.template_id
      recommendationTopic.value = topic.value.trim() || uploadedFile.value?.name || '未命名演示'
      templateRecommendation.value = null
      loadRecommendation()
      outlineSlides.value = normalizeOutlineSlides(draft.slides)
      workflowStep.value = 2
      ElMessage.success('大纲已生成，请审阅页面结构')
    } catch (e) {
      if (isOutlineRequestCanceled(e)) return
      ElMessage.error('大纲生成失败: ' + e.message)
    } finally {
      if (requestId === outlineRequestId) {
        stopOutlineStages()
        outlineDrafting.value = false
        outlineSaving.value = false
      }
    }
    return
  }
}

async function approveOutline() {
  if (!outlineDraft.value || !outlineCanApprove.value) return
  outlineSaving.value = true
  try {
    reindexOutlineSlides()
    const updated = await api.ppt.updateOutline(outlineDraft.value.id, { slides: outlineSlides.value })
    const approved = await api.ppt.approveOutline(updated.id)
    outlineDraft.value = approved
    outlineSlides.value = normalizeOutlineSlides(approved.slides)
    workflowStep.value = 3
    ElMessage.success('大纲已批准，请选择质量模式')
  } catch (e) {
    ElMessage.error('大纲审批失败: ' + e.message)
  } finally {
    outlineSaving.value = false
  }
}

async function generateApprovedOutline() {
  if (!outlineDraft.value || generating.value) return
  generating.value = true
  generatedSlides.value = []
  generatedFileUrl.value = ''
  progressState.value = { progress: 0, step: 'starting', message: '正在创建任务...' }
  reconnectAttempts = 0
  intentionalSocketClose = false
  taskFeedback.reset()
  taskFeedback.start({ status: 'running', step: '正在创建 PPT 任务', progress: 0 })

  try {
    let result

    if (outlineDraft.value) {
      result = await api.ppt.generateFromOutline(
        outlineDraft.value.id,
        qualityMode.value,
        outlineDraft.value.version,
        {
          output_format: outputFormat.value,
          auto_images: autoImages.value,
          enable_animation: enableAnimation.value,
          api_key_token: apiKeyStore.siliconflowKey?.token || null,
        },
      )
    } else {

    if (uploadedFile.value) {
      // 文件上传模式：使用 FormData
      const formData = new FormData()
      formData.append('file', uploadedFile.value)
      formData.append('template', selectedTemplate.value)
      formData.append('slide_count', parseInt(slideCount.value))
      formData.append('output_format', outputFormat.value)
      formData.append('extra_prompt', topic.value.trim())
      formData.append('api_key_token', apiKeyStore.siliconflowKey?.token || '')

      const token = getToken() || ''
      const resp = await fetch('/api/v1/pptx/generate_from_file', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      })
      result = await resp.json()
      if (!resp.ok) throw new Error(result.detail || '上传失败')
    } else {
      // 文本模式
      const fullPrompt = buildFullPrompt()
      result = await api.ppt.createPptTask(fullPrompt, null, apiKeyStore.siliconflowKey?.token, {
        template_id: selectedTemplate.value,
        slide_count: parseInt(slideCount.value),
        auto_images: autoImages.value,
        enable_animation: enableAnimation.value,
        output_format: outputFormat.value,
      })
    }
    }

    if (result && result.task_id) {
      currentTaskId.value = result.task_id
      connectWebSocket(result.task_id)
      ElMessage.success('任务已创建，正在生成中...')
    } else {
      ElMessage.error('创建 PPT 任务失败，请稍后重试')
      taskFeedback.fail('创建 PPT 任务失败，请稍后重试', { stage: '任务创建失败', nextAction: '检查内容后重新生成' })
      generating.value = false
    }
  } catch (e) {
    console.error('PPT 生成失败:', e)
    ElMessage.error('生成失败: ' + e.message)
    taskFeedback.fail(e, { stage: '任务创建失败', nextAction: '检查内容后重新生成' })
    progressState.value = null
    generating.value = false
  }
}

async function handleCancel() {
  if (!generating.value) return
  try {
    await api.ppt.cancelPptTask(currentTaskId.value)
    closeWebSocket()
    generating.value = false
    progressState.value = null
    taskFeedback.update({ status: 'cancelled', step: 'cancelled', nextAction: '调整内容后重新生成' })
    ElMessage.info('已取消生成')
  } catch {
    generating.value = false
  }
}

function buildFullPrompt() {
  const tpl = templates.value.find(t => t.id === selectedTemplate.value)
  const features = []
  if (autoImages.value) features.push('自动配图')
  if (enableAnimation.value) features.push('动画效果')

  let prompt = `${topic.value.trim()}\n\n`
  prompt += `模板风格：${tpl?.name || '默认'}\n`
  prompt += slideCount.value === 'auto' ? '幻灯片数量：按主题自动决定\n' : `幻灯片数量：${slideCount.value}页\n`
  if (features.length > 0) prompt += `特殊要求：${features.join('、')}\n`
  return prompt
}

// 分析 PPT 状态
async function handleAnalyze() {
  if (!currentTaskId.value) return

  try {
    const result = await api.ppt.analyzePpt(currentTaskId.value)
    if (result) {
      ElMessage.success('分析完成，可在下方输入修改需求')
    }
  } catch (e) {
    ElMessage.error('分析失败: ' + e.message)
  }
}

// 应用修改
async function handleModify() {
  if (!modifyInput.value.trim() || !currentTaskId.value) return

  isModifying.value = true
  try {
    const result = await api.ppt.modifyPpt(
      currentTaskId.value,
      modifyInput.value.trim(),
      apiKeyStore.siliconflowKey?.token,
      true
    )

    if (result.success) {
      currentTaskId.value = result.task_id
      generatedFileUrl.value = result.download_url

      modifyHistory.value.push({
        input: modifyInput.value.trim(),
        message: result.message,
        timestamp: new Date()
      })

      modifyInput.value = ''
      ElMessage.success('修改成功!')
    } else {
      ElMessage.warning(result.message || '修改失败')
    }
  } catch (e) {
    ElMessage.error('修改失败: ' + e.message)
  } finally {
    isModifying.value = false
  }
}

function formatTime(date) {
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function startOutlineStages() {
  stopOutlineStages()
  outlineStageIndex.value = 0
  outlineStageTimer = setInterval(() => {
    if (outlineStageIndex.value < outlineStages.length - 1) outlineStageIndex.value += 1
  }, 1600)
}

function stopOutlineStages() {
  if (outlineStageTimer !== null) {
    clearInterval(outlineStageTimer)
    outlineStageTimer = null
  }
}

function persistSession() {
  try {
    sessionStorage.setItem(PPT_SESSION_KEY, JSON.stringify({
      workflowStep: workflowStep.value,
      topic: topic.value,
      slideCount: slideCount.value,
      selectedTemplate: selectedTemplate.value,
      automaticSelection: automaticSelection.value,
      outputFormat: outputFormat.value,
      autoImages: autoImages.value,
      enableAnimation: enableAnimation.value,
      qualityMode: qualityMode.value,
      outlineDraft: outlineDraft.value,
      outlineSlides: outlineSlides.value,
      outlineDrafting: outlineDrafting.value,
      outlineStageIndex: outlineStageIndex.value,
      uploadedMaterialId: uploadedMaterialId.value,
      generating: generating.value,
      generatedFileUrl: generatedFileUrl.value,
      generatedSlides: generatedSlides.value,
      currentTaskId: currentTaskId.value,
      progressState: progressState.value,
    }))
  } catch (error) {
    console.warn('保存 PPT 会话失败:', error)
  }
}

function restoreSession() {
  try {
    const raw = sessionStorage.getItem(PPT_SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function applySession(saved) {
  if (!saved || typeof saved !== 'object') return
  workflowStep.value = saved.workflowStep || 1
  topic.value = saved.topic || ''
  slideCount.value = saved.slideCount || 'auto'
  selectedTemplate.value = saved.selectedTemplate || selectedTemplate.value
  automaticSelection.value = Boolean(saved.automaticSelection)
  outputFormat.value = saved.outputFormat || 'pptx'
  autoImages.value = saved.autoImages !== false
  enableAnimation.value = saved.enableAnimation !== false
  qualityMode.value = saved.qualityMode || 'standard'
  outlineDraft.value = saved.outlineDraft || null
  outlineSlides.value = normalizeOutlineSlides(saved.outlineSlides || [])
  uploadedMaterialId.value = saved.uploadedMaterialId || null
  outlineStageIndex.value = Number.isInteger(saved.outlineStageIndex) ? saved.outlineStageIndex : 0
  outlineDrafting.value = Boolean(saved.outlineDrafting && !saved.outlineDraft)
  generatedFileUrl.value = saved.generatedFileUrl || ''
  generatedSlides.value = saved.generatedSlides || []
  currentTaskId.value = saved.currentTaskId || ''
  progressState.value = saved.progressState || null
  generating.value = Boolean(saved.generating && saved.currentTaskId && !saved.generatedFileUrl)
}

watch(
  [workflowStep, topic, slideCount, selectedTemplate, outlineDraft, outlineSlides, outlineDrafting, outlineStageIndex, uploadedMaterialId, generating, generatedFileUrl, generatedSlides, currentTaskId, progressState, qualityMode, outputFormat, autoImages, enableAnimation, automaticSelection],
  persistSession,
  { deep: true },
)

onMounted(() => {
  loadTemplates()
  if (typeof route.query.task_id === 'string' && route.query.task_id) {
    currentTaskId.value = route.query.task_id
    generating.value = true
    taskFeedback.reset()
    taskFeedback.start({ status: 'running', step: '正在恢复 PPT 导出进度', progress: 0 })
    connectWebSocket(currentTaskId.value)
    return
  }
  const saved = restoreSession()
  if (saved) applySession(saved)
  if (generating.value && currentTaskId.value) {
    taskFeedback.reset()
    taskFeedback.start({
      status: 'running',
      step: progressState.value?.step || '正在恢复 PPT 生成进度',
      progress: generationPercent.value,
    })
    connectWebSocket(currentTaskId.value)
    return
  }
  if (outlineDrafting.value && canGenerate.value) {
    handleGenerate({ resume: true })
  }
})

onUnmounted(() => {
  outlineRequestId += 1
  outlineAbort?.abort()
  stopOutlineStages()
  closeWebSocket()
})
</script>

<style scoped>
.ppt-generate-page {
  flex: 1;
  min-height: 0;
  height: 100%;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  color: var(--text-primary);
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  cursor: pointer;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
}

.header-title svg { width: 20px; height: 20px; }
.header-actions { margin-left: auto; }
.header-hint { font-size: 13px; color: var(--text-secondary); }

.page-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.config-panel {
  width: min(340px, 30vw);
  min-width: 280px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
}

.form-group { display: flex; flex-direction: column; gap: 8px; }
.form-group label { font-size: 14px; font-weight: 500; }
.required { color: #ef4444; }

.form-group textarea {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 14px;
  resize: vertical;
  font-family: inherit;
}

.char-count { text-align: right; font-size: 12px; color: var(--text-tertiary); }

.template-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.template-card {
  padding: 0;
  min-width: 0;
  color: var(--text-primary);
  background: var(--bg-tertiary);
  font: inherit;
  border: 2px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
}

.template-card:hover { border-color: var(--color-primary); transform: translateY(-1px); }
.template-card.selected { border-color: var(--color-primary); box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2); }
.template-card:disabled { cursor: default; }
.template-auto { width: 100%; padding: 10px; }
.template-description, .template-hint, .template-result { font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
.template-description { margin: 6px 8px; text-align: left; }
.template-result { margin-top: 12px; padding: 10px; border: 1px solid var(--border-color); border-radius: 8px; }

.template-preview {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.template-preview svg { width: 24px; height: 24px; color: rgba(255,255,255,0.9); }

.template-name {
  padding: 6px 8px;
  font-size: 12px;
  font-weight: 500;
  text-align: center;
  background: var(--bg-tertiary);
}

.advanced-options {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
}

.option-item { margin-bottom: 10px; }
.option-item:last-child { margin-bottom: 0; }

.option-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: var(--text-primary);
  cursor: pointer;
}

.option-select {
  padding: 4px 8px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.option-checkbox {
  width: 16px;
  height: 16px;
  margin-right: 8px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.option-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.outline-review-panel,
.quality-mode-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-tertiary);
}

.workflow-heading,
.workflow-heading-actions,
.outline-slide-actions {
  display: flex;
  align-items: center;
}

.workflow-heading {
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 14px;
  font-weight: 600;
}

.workflow-heading-actions,
.outline-slide-actions {
  gap: 6px;
}

.workflow-version,
.outline-total {
  color: var(--text-secondary);
  font-size: 12px;
}

.outline-add-btn,
.outline-slide-actions button {
  padding: 5px 8px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
}

.outline-add-btn:disabled,
.outline-slide-actions button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.outline-slide-editor {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.preview-panel .outline-review-panel {
  min-height: 100%;
  background: transparent;
  border: none;
  padding: 0;
}

.outline-board {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}

.outline-approve-btn {
  align-self: flex-start;
  min-width: 220px;
}

.outline-drafting,
.generation-live {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 720px;
}

.outline-drafting h3 {
  margin: 0;
  font-size: 20px;
}

.stage-list,
.generation-slide-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stage-list li,
.generation-slide-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.stage-list li.current,
.generation-slide-list li.current {
  border-color: var(--color-primary);
  color: var(--text-primary);
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.25);
}

.stage-list li.done,
.generation-slide-list li.done {
  color: var(--text-primary);
  opacity: 0.75;
}

.generation-slide-list li span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  font-size: 12px;
  font-weight: 700;
}

.outline-index {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--color-primary);
  color: white;
  font-size: 12px;
  font-weight: 700;
}

.outline-fields {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.outline-fields input,
.outline-fields select,
.outline-fields textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 9px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font: inherit;
}

.outline-slide-actions {
  grid-column: 2;
  justify-content: flex-end;
}

.outline-remove {
  color: #dc2626 !important;
}

.outline-validation {
  color: #b91c1c;
  font-size: 12px;
  line-height: 1.4;
}

.quality-mode-option {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.quality-mode-option span {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.quality-mode-option small {
  color: var(--text-secondary);
}

.generate-btn {
  padding: 12px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--color-primary) 0%, #3b82f6 100%);
  color: white;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.generate-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3); }
.generate-btn:disabled { background: var(--border-color); cursor: not-allowed; }

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.progress-section {
  padding: 14px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.progress-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.progress-title { font-size: 13px; font-weight: 600; }
.progress-percentage { font-size: 16px; font-weight: 700; color: var(--color-primary); }

.progress-bar { height: 6px; background: var(--bg-primary); border-radius: 3px; overflow: hidden; margin-bottom: 8px; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--color-primary), #3b82f6); border-radius: 3px; transition: width 0.3s ease; }
.progress-step { font-size: 12px; font-weight: 600; color: var(--color-primary); margin-bottom: 2px; }
.progress-message { font-size: 12px; color: var(--text-secondary); }

.preview-panel {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  background: var(--bg-primary);
}

.preview-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  gap: 16px;
}

.preview-placeholder svg { width: 60px; height: 60px; opacity: 0.5; }

.loading-container, .success-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.spinner-ring {
  width: 40px;
  height: 40px;
  border: 4px solid var(--border-color);
  border-top: 4px solid var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.success-container a { color: var(--color-primary); text-decoration: underline; }

.slides-preview {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.slide-card {
  background: var(--bg-secondary);
  padding: 16px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.slide-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.slide-number { font-size: 12px; color: var(--text-secondary); }
.slide-type { font-size: 12px; color: var(--color-primary); text-transform: capitalize; }
.slide-card h3 { font-size: 16px; margin-bottom: 8px; }
.slide-card ul { list-style-position: inside; font-size: 14px; color: var(--text-secondary); }

/* 修改面板样式 */
.success-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
}

.download-link {
  padding: 10px 20px;
  background: linear-gradient(135deg, var(--color-primary) 0%, #3b82f6 100%);
  color: white;
  border-radius: 8px;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.download-link:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.preview-btn, .modify-btn {
  padding: 10px 20px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.preview-btn:hover, .modify-btn:hover {
  background: var(--hover-bg);
  border-color: var(--color-primary);
}

.modify-btn {
  background: var(--bg-tertiary);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.modify-panel {
  width: 100%;
  max-width: 600px;
  margin-top: 24px;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  text-align: left;
}

.modify-input-group textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  transition: border-color 0.2s;
}

.modify-input-group textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}

.modify-input-group textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.modify-actions {
  display: flex;
  gap: 12px;
  margin-top: 12px;
}

.btn-analyze {
  padding: 8px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-analyze:hover:not(:disabled) {
  background: var(--hover-bg);
  border-color: var(--color-primary);
}

.btn-apply {
  padding: 8px 16px;
  background: linear-gradient(135deg, var(--color-primary) 0%, #3b82f6 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-apply:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.btn-apply:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.modify-history {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.modify-history h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.history-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 0;
  font-size: 13px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-color);
}

.history-item:last-child {
  border-bottom: none;
}

.history-index {
  font-weight: 600;
  color: var(--color-primary);
  min-width: 20px;
}

.history-input {
  flex: 1;
}

.history-time {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 文件上传区域 */
.optional { color: var(--text-tertiary); font-weight: 400; }

.file-upload-area {
  border: 2px dashed var(--border-color);
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-tertiary);
}

.file-upload-area:hover { border-color: var(--color-primary); background: var(--bg-primary); }
.file-upload-area.has-file { border-style: solid; border-color: var(--color-primary); }

.upload-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
}

.upload-placeholder svg { opacity: 0.5; }
.upload-placeholder p { font-size: 14px; margin: 0; }
.upload-hint { font-size: 12px; color: var(--text-tertiary); }

.file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
}

.file-info svg { color: var(--color-primary); flex-shrink: 0; }
.file-details { flex: 1; text-align: left; }
.file-name { display: block; font-size: 14px; font-weight: 500; color: var(--text-primary); }
.file-size { font-size: 12px; color: var(--text-tertiary); }

.remove-file {
  padding: 4px;
  border: none;
  background: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 4px;
}

.remove-file:hover { color: #ef4444; background: rgba(239,68,68,0.1); }

/* 取消按钮 */
.cancel-btn {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%) !important;
}

/* PDF 下载按钮 */
.pdf-link {
  background: linear-gradient(135deg, #059669 0%, #047857 100%) !important;
}

/* 头部按钮 */
.header-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.header-btn:hover { border-color: var(--color-primary); }

/* 历史记录面板 */
.history-panel-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.history-panel {
  width: 400px;
  height: 100%;
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 20px rgba(0,0,0,0.2);
}

.history-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}

.history-panel-header h3 { margin: 0; font-size: 16px; }

.close-btn {
  padding: 4px;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 4px;
}

.close-btn:hover { background: var(--bg-tertiary); }

.history-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.history-loading, .history-empty {
  text-align: center;
  padding: 40px 0;
  color: var(--text-tertiary);
}

.history-list { display: flex; flex-direction: column; gap: 12px; }

.history-card {
  padding: 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.history-card-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
}

.history-card-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: min(220px, 55%);
}

.history-card-time { font-size: 12px; color: var(--text-tertiary); }

.history-card-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.history-card-actions {
  display: flex;
  gap: 8px;
}

.history-action-btn {
  padding: 4px 10px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.2s;
}

.history-action-btn:hover { border-color: var(--color-primary); }
.history-action-btn.delete { color: #ef4444; border-color: #fca5a5; }
.history-action-btn.delete:hover { background: rgba(239,68,68,0.1); }
 .history-action-btn:disabled { opacity: 0.45; cursor: not-allowed; }
button:focus-visible, textarea:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 3px; }
.file-details { min-width: 0; }
.file-name { overflow-wrap: anywhere; }
@media (max-width: 900px) {
  .page-header { padding: 14px 16px; flex-wrap: wrap; }
  .header-hint { display: none; }
  .page-content { display: flex; flex-direction: column; overflow: auto; }
  .config-panel { width: 100%; min-width: 0; border-right: 0; border-bottom: 1px solid var(--border-color); padding: 20px 16px; overflow: visible; }
  .result-panel { min-height: 420px; padding: 20px 16px; }
  .template-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 480px) {
  .template-grid { grid-template-columns: 1fr; }
  .workflow-heading { align-items: flex-start; flex-direction: column; }
  .workflow-heading-actions, .outline-slide-actions, .modify-actions { flex-wrap: wrap; }
  .history-panel { width: min(400px, 100vw); }
}
</style>
