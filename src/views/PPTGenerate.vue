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
        <span class="header-hint">基于 AI 自动生成幻灯片</span>
      </div>
    </header>

    <div class="page-content">
      <aside class="config-panel">
        <div class="form-group">
          <label for="topic">主题</label>
          <input
            id="topic"
            v-model="topic"
            type="text"
            placeholder="请输入 PPT 主题..."
            :disabled="generating"
          />
        </div>

        <div class="form-group">
          <label for="outline">大纲（可选）</label>
          <textarea
            id="outline"
            v-model="outline"
            placeholder="每行一个幻灯片标题，留空则自动生成..."
            rows="6"
            :disabled="generating"
          ></textarea>
        </div>

        <div class="form-group">
          <label for="slideCount">幻灯片数量</label>
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
          class="generate-btn"
          :disabled="!canGenerate || generating"
          @click="handleGenerate"
        >
          <span v-if="generating" class="loading-spinner"></span>
          {{ generating ? '生成中...' : '开始生成' }}
        </button>
      </aside>

      <main class="preview-panel">
        <div v-if="!generatedSlides.length" class="preview-placeholder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
          </svg>
          <p>配置参数后点击生成按钮</p>
        </div>

        <div v-else class="slides-preview">
          <div v-for="slide in generatedSlides" :key="slide.id" class="slide-card">
            <div class="slide-number">Slide {{ slide.id }}</div>
            <h3>{{ slide.title }}</h3>
            <p>{{ slide.content }}</p>
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
const topic = ref('')
const outline = ref('')
const slideCount = ref(10)
const generating = ref(false)
const generatedSlides = ref([])

const canGenerate = computed(() => topic.value.trim().length > 0)

function goBack() {
  router.push('/')
}

async function handleGenerate() {
  if (!canGenerate.value || generating.value) return
  
  // 检查 API Key 配置
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
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 24px;
  padding: 24px;
  flex: 1;
}

.config-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-group input,
.form-group textarea {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 14px;
}

.form-group textarea {
  resize: vertical;
  font-family: inherit;
}

.generate-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  border: none;
  border-radius: 8px;
  background: var(--accent-color);
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  margin-top: 8px;
}

.generate-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.preview-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 24px;
  overflow-y: auto;
}

.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--text-secondary);
}

.preview-placeholder svg {
  width: 64px;
  height: 64px;
  opacity: 0.4;
}

.slides-preview {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.slide-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
}

.slide-number {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.slide-card h3 {
  font-size: 15px;
  margin: 0 0 8px;
}

.slide-card p {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.preview-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 8px;
}

@media (max-width: 768px) {
  .page-content {
    grid-template-columns: 1fr;
  }
}
</style>
