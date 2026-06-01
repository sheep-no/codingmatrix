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
          <rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
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
          <label for="topic">主题 / 描述</label>
          <textarea
            id="topic"
            v-model="topic"
            type="text"
            placeholder="请输入您的 PPT 主题，例如：'帮我做一个关于 2026 年人工智能发展趋势的技术汇报'"
            rows="4"
            :disabled="generating"
          ></textarea>
        </div>

        <div class="form-group">
          <label>生成模式</label>
          <div class="mode-selector">
            <button 
              class="mode-btn" 
              :class="{ active: mode === 'agent' }" 
              :disabled="generating"
              @click="mode = 'agent'"
            >
              AI Agent 生成
            </button>
            <button 
              class="mode-btn" 
              :class="{ active: mode === 'manual' }" 
              :disabled="generating"
              @click="mode = 'manual'"
            >
              手动输入大纲
            </button>
          </div>
        </div>

        <div v-if="mode === 'manual'" class="form-group">
          <label for="outline">手动大纲（可选）</label>
          <textarea
            id="outline"
            v-model="outline"
            placeholder="每行一个标题..."
            rows="6"
            :disabled="generating"
          ></textarea>
        </div>

        <div class="form-group">
          <label for="slideCount">期望页数</label>
          <input
            id="slideCount"
            v-model.number="slideCount"
            type="number"
            min="1"
            max="30"
            :disabled="generating"
          />
        </div>

        <button
          v-if="mode === 'agent'"
          class="ai-generate-btn"
          :disabled="!canAgentGenerate || generating"
          @click="handleAgentGenerate"
        >
          <span v-if="generating" class="loading-spinner"></span>
          {{ generating ? 'AI 正在生成...' : '一键生成 PPT' }}
        </button>

        <button
          v-else
          class="generate-btn"
          :disabled="!canGenerate || generating"
          @click="handleGenerate"
        >
          <span v-if="generating" class="loading-spinner"></span>
          {{ generating ? '生成中...' : '开始生成' }}
        </button>
      </aside>

      <main class="preview-panel">
        <div v-if="!generatedSlides.length && !generating" class="preview-placeholder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
          </svg>
          <p>描述您的想法，AI Agent 将自动完成大纲、排版和配图</p>
        </div>

        <div v-if="generating" class="loading-container">
          <div class="spinner-ring"></div>
          <p>正在生成幻灯片...</p>
        </div>

        <div v-else-if="generatedFileUrl" class="success-container">
          <h3>生成成功!</h3>
          <a :href="generatedFileUrl" target="_blank" class="download-link">
            点击此处下载 PPTX 文件
          </a>
        </div>

        <div v-else-if="generatedSlides.length" class="slides-preview">
          <div v-for="(slide, index) in generatedSlides" :key="index" class="slide-card">
            <div class="slide-number">Slide {{ index + 1 }}</div>
            <div class="slide-type">{{ slide.type || 'content' }}</div>
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
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useApiKeyStore } from '@/stores/apikey'

const router = useRouter()
const apiKeyStore = useApiKeyStore()
const mode = ref('agent') // 'agent' | 'manual'
const topic = ref('')
const outline = ref('')
const slideCount = ref(10)
const generating = ref(false)
const generatedSlides = ref([])
const generatedFileUrl = ref('')

const canAgentGenerate = computed(() => topic.value.trim().length > 0)
const canGenerate = computed(() => mode.value === 'manual' && topic.value.trim().length > 0)

function goBack() {
  router.push('/')
}

async function handleAgentGenerate() {
  if (!canAgentGenerate.value || generating.value) return
  if (!apiKeyStore.hasSiliconflowKey) {
    alert('请先配置 API Key 后再使用')
    router.push('/settings')
    return
  }

  generating.value = true
  generatedSlides.value = []
  generatedFileUrl.value = ''

  try {
    const token = localStorage.getItem('access_token')
    const res = await fetch('/api/v1/ppt/generate-from-text', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : ''
      },
      body: JSON.stringify({
        topic: topic.value.trim(),
        num_slides: slideCount.value,
        api_key_token: apiKeyStore.siliconflowKey?.token
      })
    })

    if (!res.ok) {
      throw new Error(`生成失败 (${res.status})`)
    }

    const data = await res.json()
    generatedSlides.value = data.slides || []
    if (data.file_url) {
      generatedFileUrl.value = data.file_url
    }
  } catch (e) {
    console.error('PPT Agent 生成失败:', e)
    alert('生成失败: ' + e.message)
  } finally {
    generating.value = false
  }
}

async function handleGenerate() {
  if (!canGenerate.value || generating.value) return
  if (!apiKeyStore.hasSiliconflowKey) {
    alert('请先配置 API Key 后再使用')
    router.push('/settings')
    return
  }

  generating.value = true

  try {
    const token = localStorage.getItem('access_token')
    const res = await fetch('/api/v1/ppt/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : ''
      },
      body: JSON.stringify({
        topic: topic.value.trim(),
        outline: outline.value.trim() || undefined,
        slide_count: slideCount.value,
        api_key_token: apiKeyStore.siliconflowKey?.token
      })
    })

    if (!res.ok) {
      throw new Error(`生成失败 (${res.status})`)
    }

    const data = await res.json()
    generatedSlides.value = data.slides || []
  } catch (e) {
    console.error('PPT 生成失败:', e)
    alert('生成失败: ' + e.message)
  } finally {
    generating.value = false
  }
}
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

.header-title svg {
  width: 20px;
  height: 20px;
}

.header-actions {
  margin-left: auto;
}

.header-hint {
  font-size: 13px;
  color: var(--text-secondary);
}

.page-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.config-panel {
  width: 400px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
}

.form-group input,
.form-group textarea {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 14px;
}

.mode-selector {
  display: flex;
  gap: 4px;
  background: var(--bg-tertiary);
  padding: 4px;
  border-radius: 8px;
}

.mode-btn {
  flex: 1;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.2s;
}

.mode-btn.active {
  background: var(--bg-primary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  font-weight: 500;
}

.generate-btn,
.ai-generate-btn {
  padding: 12px;
  border: none;
  border-radius: 6px;
  background: var(--accent-color);
  color: white;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.generate-btn:disabled,
.ai-generate-btn:disabled {
  background: var(--border-color);
  cursor: not-allowed;
}

.ai-generate-btn {
  background: linear-gradient(135deg, #6ee7b7, #3b82f6);
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

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

.preview-placeholder svg {
  width: 60px;
  height: 60px;
  opacity: 0.5;
}

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

.slide-number {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.slide-type {
  font-size: 12px;
  color: var(--accent-color);
  margin-bottom: 4px;
  text-transform: capitalize;
}

.slide-card h3 {
  font-size: 16px;
  margin-bottom: 8px;
}

.slide-card ul {
  list-style-position: inside;
  font-size: 14px;
  color: var(--text-secondary);
}

.loading-container,
.success-container {
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
  border: 4px solid #f3f3f3;
  border-top: 4px solid var(--accent-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.success-container a {
  color: var(--accent-color);
  text-decoration: underline;
}
</style>
