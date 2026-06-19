<template>
  <div class="ppt-generate-page">
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
        <span>AI PPT 生成</span>
      </div>
      <div class="header-actions">
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

        <div class="form-group">
          <label>选择模板</label>
          <div class="template-grid">
            <div
              v-for="tpl in templates"
              :key="tpl.id"
              class="template-card"
              :class="{ selected: selectedTemplate === tpl.id }"
              @click="selectedTemplate = tpl.id"
            >
              <div class="template-preview" :style="{ background: tpl.color }">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <line x1="8" y1="8" x2="16" y2="8"/>
                  <line x1="8" y1="12" x2="16" y2="12"/>
                  <line x1="8" y1="16" x2="12" y2="16"/>
                </svg>
              </div>
              <div class="template-name">{{ tpl.name }}</div>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label>高级选项</label>
          <div class="advanced-options">
            <div class="option-item">
              <label class="option-label">
                <span>幻灯片数量</span>
                <select v-model="slideCount" class="option-select">
                  <option value="5">5 页 (简洁)</option>
                  <option value="10">10 页 (标准)</option>
                  <option value="15">15 页 (详细)</option>
                  <option value="20">20 页 (完整)</option>
                  <option value="30">30 页 (深度)</option>
                  <option value="50">50 页 (全面)</option>
                </select>
              </label>
            </div>
            <div class="option-item">
              <label class="option-label">
                <input v-model="autoImages" type="checkbox" class="option-checkbox" />
                <span>自动配图</span>
              </label>
            </div>
            <div class="option-item">
              <label class="option-label">
                <input v-model="enableAnimation" type="checkbox" class="option-checkbox" />
                <span>启用动画</span>
              </label>
            </div>
          </div>
        </div>

        <button
          class="generate-btn"
          :disabled="!canGenerate || generating"
          @click="handleGenerate"
        >
          <span v-if="generating" class="loading-spinner"></span>
          {{ generating ? 'AI 正在生成...' : '一键生成 PPT' }}
        </button>

        <div v-if="generating && progressState" class="progress-section">
          <div class="progress-header">
            <span class="progress-title">生成进度</span>
            <span class="progress-percentage">{{ Math.round(progressState.progress * 100) }}%</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: `${progressState.progress * 100}%` }"></div>
          </div>
          <div class="progress-step">{{ progressState.step }}</div>
          <div class="progress-message">{{ progressState.message }}</div>
        </div>
      </aside>

      <main class="preview-panel">
        <div v-if="!generatedSlides.length && !generating" class="preview-placeholder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
          </svg>
          <p>描述您的想法，AI Agent 将自动完成大纲、排版和配图</p>
        </div>

        <div v-if="generating && !generatedSlides.length" class="loading-container">
          <div class="spinner-ring"></div>
          <p>正在生成幻灯片...</p>
        </div>

        <div v-else-if="generatedFileUrl" class="success-container">
          <h3>生成成功!</h3>
          <div class="success-actions">
            <a :href="generatedFileUrl" target="_blank" class="download-link">
              下载 PPTX 文件
            </a>
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
                  @click="handleAnalyze"
                  :disabled="isModifying"
                >
                  分析 PPT
                </button>
                <button
                  class="btn-apply"
                  @click="handleModify"
                  :disabled="!modifyInput.trim() || isModifying"
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApiKeyStore } from '@/stores/apikey'
import { api } from '@/utils/api/index'
import { ElMessage } from 'element-plus'

const router = useRouter()
const apiKeyStore = useApiKeyStore()

const topic = ref('')
const selectedTemplate = ref('modern')
const slideCount = ref('10')
const autoImages = ref(true)
const enableAnimation = ref(true)
const generating = ref(false)
const generatedSlides = ref([])
const generatedFileUrl = ref('')
const progressState = ref(null)

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

const canGenerate = computed(() => topic.value.trim().length > 0 && topic.value.length <= 2000)

function goBack() {
  router.push('/')
}

function goToPreview() {
  if (generatedFileUrl.value) {
    // 从 URL 中提取 ppt_id
    const match = generatedFileUrl.value.match(/\/pptx\/download\/(.+)$/)
    if (match) {
      router.push(`/ppt-preview/${match[1]}`)
    }
  }
}

async function loadTemplates() {
  try {
    const result = await api.ppt.getTemplates()
    if (result.templates && result.templates.length > 0) {
      templates.value = result.templates.map(t => ({
        id: t.id,
        name: t.name,
        color: `linear-gradient(135deg, ${t.primary_color || '#667eea'} 0%, ${t.primary_color || '#764ba2'}80 100%)`
      }))
    }
  } catch {
    // 静默使用硬编码模板列表，不打扰用户
  }
}

function connectWebSocket(taskId) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/ws/ppt/${taskId}`

  ws = new WebSocket(wsUrl)

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'progress') {
        progressState.value = { progress: data.progress, step: data.step, message: data.message }
      } else if (data.type === 'complete') {
        progressState.value = { progress: 1, step: 'completed', message: '任务完成' }
        generating.value = false
        // 获取结果
        if (data.result) {
          try {
            const resultData = typeof data.result === 'string' ? JSON.parse(data.result) : data.result
            if (resultData.slides) {
              generatedSlides.value = resultData.slides
            }
            if (resultData.ppt_id || resultData.filename) {
              const pid = resultData.ppt_id || resultData.filename.replace('.pptx', '')
              currentTaskId.value = pid
              generatedFileUrl.value = `/api/v1/pptx/download/${pid}`
            }
          } catch (e) {
            console.warn('解析结果数据失败:', e)
          }
        }
        ElMessage.success('PPT 生成完成!')
      } else if (data.type === 'error') {
        progressState.value = { progress: progressState.value?.progress || 0, step: 'error', message: data.error || data.message }
        generating.value = false
        ElMessage.error('生成失败: ' + (data.error || data.message || '未知错误'))
      }
    } catch (error) {
      console.error('WebSocket 消息解析失败:', error)
    }
  }

  ws.onerror = () => {
    ws = null
    if (generating.value) {
      ElMessage.warning('连接中断，请刷新页面查看结果')
      generating.value = false
    }
  }
  ws.onclose = (event) => {
    ws = null
    // 非正常关闭且仍在生成中
    if (event.code !== 1000 && generating.value) {
      ElMessage.warning('连接已断开，请刷新页面查看结果')
      generating.value = false
    }
  }
}

async function handleGenerate() {
  if (!canGenerate.value || generating.value) return
  if (!apiKeyStore.hasSiliconflowKey) {
    ElMessage.error('请先配置 API Key 后再使用')
    router.push('/settings')
    return
  }

  generating.value = true
  generatedSlides.value = []
  generatedFileUrl.value = ''
  progressState.value = { progress: 0, step: 'starting', message: '正在创建任务...' }

  try {
    const fullPrompt = buildFullPrompt()
    const result = await api.ppt.createPptTask(fullPrompt, null, apiKeyStore.siliconflowKey?.token, {
      template_id: selectedTemplate.value,
      slide_count: parseInt(slideCount.value),
      auto_images: autoImages.value,
      enable_animation: enableAnimation.value,
    })

    if (result && result.task_id) {
      connectWebSocket(result.task_id)
      ElMessage.success('任务已创建，正在生成中...')
      // 不跳转，留在当前页面等待 WebSocket 进度
    } else {
      ElMessage.error('创建 PPT 任务失败，请稍后重试')
      generating.value = false
    }
  } catch (e) {
    console.error('PPT 生成失败:', e)
    ElMessage.error('生成失败: ' + e.message)
    progressState.value = null
    generating.value = false
  }
  // 注意：不在 finally 中设置 generating = false，由 WebSocket complete/error 事件控制
}

function buildFullPrompt() {
  const tpl = templates.value.find(t => t.id === selectedTemplate.value)
  const features = []
  if (autoImages.value) features.push('自动配图')
  if (enableAnimation.value) features.push('动画效果')

  let prompt = `${topic.value.trim()}\n\n`
  prompt += `模板风格：${tpl?.name || '默认'}\n`
  prompt += `幻灯片数量：${slideCount.value}页\n`
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

// 格式化时间
function formatTime(date) {
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

onMounted(() => { loadTemplates() })

onUnmounted(() => {
  if (ws) { ws.close(); ws = null }
})
</script>

<style scoped>
.ppt-generate-page {
  min-height: 100vh;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
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
}

.config-panel {
  width: 420px;
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
  border: 2px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
}

.template-card:hover { border-color: var(--color-primary); transform: translateY(-1px); }
.template-card.selected { border-color: var(--color-primary); box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2); }

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
</style>
