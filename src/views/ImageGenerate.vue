<template>
  <div class="image-generate-page">
    <header class="page-header">
      <button class="back-btn" @click="goBack">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        返回
      </button>
      <div class="header-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
        </svg>
        <span>AI 绘画</span>
      </div>
      <div class="header-actions">
        <span class="header-hint">基于 Kolors 模型</span>
      </div>
    </header>

    <div class="page-content">
      <!-- 左侧配置面板 -->
      <aside class="config-panel">
        <!-- 模式切换 -->
        <div class="mode-tabs">
          <button :class="['mode-tab', { active: mode === 'text2img' }]" @click="mode = 'text2img'">文生图</button>
          <button :class="['mode-tab', { active: mode === 'img2img' }]" @click="mode = 'img2img'">图生图</button>
        </div>

        <!-- 图生图 - 上传图片 -->
        <div v-if="mode === 'img2img'" class="form-section">
          <label class="form-label">参考图片</label>
          <div class="upload-area" @click="$refs.fileInput.click()" @dragover.prevent @drop.prevent="onDrop">
            <img v-if="previewUrl" :src="previewUrl" class="upload-preview" />
            <div v-else class="upload-placeholder">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
              </svg>
              <span>点击或拖拽上传图片</span>
              <span class="upload-hint">支持 JPG/PNG/WEBP，最大 10MB</span>
            </div>
            <input ref="fileInput" type="file" accept="image/*" class="file-input" @change="onFileSelect" />
          </div>
        </div>

        <!-- Prompt 输入 -->
        <div class="form-section">
          <label class="form-label">
            描述 <span class="required">*</span>
          </label>
          <textarea
            v-model="prompt"
            class="form-textarea"
            placeholder="描述你想要生成的画面..."
            rows="5"
            :disabled="isGenerating"
          ></textarea>
          <div class="char-count">{{ prompt.length }} / 2000</div>
        </div>

        <!-- 风格选择 -->
        <div class="form-section">
          <label class="form-label">画面风格</label>
          <div class="style-grid">
            <div
              v-for="s in styles"
              :key="s.value"
              class="style-card"
              :class="{ selected: style === s.value }"
              @click="style = s.value"
            >
              <div class="style-preview" :style="{ background: s.color }"></div>
              <span class="style-name">{{ s.name }}</span>
            </div>
          </div>
        </div>

        <!-- 分辨率 -->
        <div class="form-section">
          <label class="form-label">分辨率</label>
          <select v-model="resolution" class="form-select" :disabled="isGenerating">
            <option v-if="mode === 'img2img'" value="keep">保持原图</option>
            <option value="512x512">512 x 512</option>
            <option value="768x768">768 x 768</option>
            <option value="1024x1024">1024 x 1024</option>
            <option value="512x768">512 x 768 (竖)</option>
            <option value="768x512">768 x 512 (横)</option>
          </select>
        </div>

        <!-- 高级选项 -->
        <div class="form-section">
          <label class="form-label">高级选项</label>
          <div class="advanced-group">
            <div class="slider-item">
              <div class="slider-header">
                <span>步数</span>
                <span class="slider-value">{{ steps }}</span>
              </div>
              <input v-model.number="steps" type="range" min="10" max="50" :disabled="isGenerating" />
            </div>
            <div v-if="mode === 'text2img'" class="slider-item">
              <div class="slider-header">
                <span>CFG Scale</span>
                <span class="slider-value">{{ cfgScale }}</span>
              </div>
              <input v-model.number="cfgScale" type="range" min="1" max="20" step="0.5" :disabled="isGenerating" />
            </div>
            <div v-if="mode === 'img2img'" class="slider-item">
              <div class="slider-header">
                <span>降噪强度</span>
                <span class="slider-value">{{ denoising }}</span>
              </div>
              <input v-model.number="denoising" type="range" min="0.1" max="1" step="0.05" :disabled="isGenerating" />
            </div>
            <div class="slider-item">
              <div class="slider-header">
                <span>种子 (-1 随机)</span>
                <button class="btn-random" @click="seed = Math.floor(Math.random() * 999999999)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                    <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                  </svg>
                </button>
              </div>
              <input v-model.number="seed" type="number" class="seed-input" :disabled="isGenerating" />
            </div>
          </div>
        </div>

        <!-- 生成按钮 -->
        <button
          class="btn-generate"
          :disabled="!canGenerate || isGenerating"
          @click="handleGenerate"
        >
          <svg v-if="isGenerating" class="loading-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" stroke-dasharray="60" stroke-dashoffset="60">
              <animate attributeName="stroke-dashoffset" from="60" to="0" dur="1s" repeatCount="indefinite" />
            </circle>
          </svg>
          <span>{{ isGenerating ? '生成中...' : '开始生成' }}</span>
        </button>

        <!-- 错误提示 -->
        <div v-if="error" class="error-message">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
          <span>{{ error }}</span>
        </div>
      </aside>

      <!-- 右侧结果展示 -->
      <main class="result-panel">
        <div v-if="generatedImages.length === 0 && !isGenerating" class="empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
          </svg>
          <h3>等待生成</h3>
          <p>在左侧输入描述，选择风格，点击生成</p>
        </div>

        <div v-if="isGenerating" class="loading-state">
          <div class="loading-dots">
            <span></span><span></span><span></span>
          </div>
          <p>AI 正在创作中...</p>
        </div>

        <div v-if="generatedImages.length > 0" class="images-grid">
          <div v-for="(img, idx) in generatedImages" :key="idx" class="image-card">
            <img :src="img.url" class="generated-image" />
            <div class="image-actions">
              <button class="btn-icon" title="下载" @click="downloadImage(img)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
              </button>
              <button class="btn-icon" title="作为参考图" @click="useAsReference(img)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="15 10 20 15 15 20"/><path d="M4 4v7a4 4 0 0 0 4 4h12"/>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- 历史记录 -->
        <div v-if="history.length > 0" class="history-section">
          <div class="history-header">
            <h4>历史记录</h4>
            <button class="btn-clear" @click="clearHistory">清空</button>
          </div>
          <div class="history-grid">
            <div v-for="item in history" :key="item.id" class="history-item">
              <img :src="item.url" />
              <div class="history-overlay">
                <button class="btn-icon-sm" title="删除" @click="deleteHistory(item.id)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                </button>
              </div>
            </div>
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
  import { useUserStore } from '@/stores/user'

  const router = useRouter()
  const apiKeyStore = useApiKeyStore()
  const userStore = useUserStore()
  const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

  const mode = ref('text2img')
  const prompt = ref('')
  const style = ref('realistic')
  const resolution = ref('1024x1024')
  const steps = ref(25)
  const cfgScale = ref(7.5)
  const denoising = ref(0.7)
  const seed = ref(-1)
  const uploadedFile = ref(null)
  const previewUrl = ref('')
  const isGenerating = ref(false)
  const error = ref('')
  const generatedImages = ref([])
  const history = ref([])

  const styles = [
    { value: 'realistic', name: '写实', color: 'linear-gradient(135deg, #0d9488, #14b8a6)' },
    { value: 'anime', name: '动漫', color: 'linear-gradient(135deg, #ec4899, #ef4444)' },
    { value: 'digital_art', name: '数字艺术', color: 'linear-gradient(135deg, #3b82f6, #06b6d4)' },
    { value: 'oil_painting', name: '油画', color: 'linear-gradient(135deg, #f472b6, #fbbf24)' },
    { value: 'watercolor', name: '水彩', color: 'linear-gradient(135deg, #6ee7b7, #fda4af)' },
    { value: 'sketch', name: '素描', color: 'linear-gradient(135deg, #94a3b8, #3b82f6)' },
    { value: 'cyberpunk', name: '赛博朋克', color: 'linear-gradient(135deg, #e11d48, #7c3aed)' },
    { value: 'fantasy', name: '奇幻', color: 'linear-gradient(135deg, #06b6d4, #10b981)' }
  ]

  const canGenerate = computed(() => {
    if (!prompt.value.trim()) return false
    if (mode.value === 'img2img' && !uploadedFile.value) return false
    return true
  })

  const goBack = () => router.push('/')

  function onFileSelect(e) {
    const file = e.target.files?.[0]
    if (file) setFile(file)
  }

  function onDrop(e) {
    const file = e.dataTransfer.files?.[0]
    if (file) setFile(file)
  }

  function setFile(file) {
    if (file.size > 10 * 1024 * 1024) {
      error.value = '图片大小不能超过 10MB'
      return
    }
    uploadedFile.value = file
    previewUrl.value = URL.createObjectURL(file)
    error.value = ''
  }

  async function handleGenerate() {
    if (!canGenerate.value || isGenerating.value) return
    
    // 检查 API Key 配置
    if (!apiKeyStore.hasSiliconflowKey) {
      error.value = '请先配置 API Key 后再使用'
      return
    }
    
    isGenerating.value = true
    error.value = ''
    generatedImages.value = []

    const token = userStore.getAccessToken() || localStorage.getItem('access_token') || ''
    const headers = { Authorization: token ? `Bearer ${token}` : '' }

    try {
      if (mode.value === 'text2img') {
        const [w, h] = resolution.value.split('x').map(Number)
        const res = await fetch(`${API_BASE}/kolors/text-to-image`, {
          method: 'POST',
          headers: { ...headers, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt: prompt.value.trim(),
            style: style.value,
            width: w,
            height: h,
            steps: steps.value,
            cfg_scale: cfgScale.value,
            seed: seed.value === -1 ? undefined : seed.value,
            api_key_token: apiKeyStore.siliconflowKey?.token
          })
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: '请求失败' }))
          throw new Error(err.detail || err.message || '生成失败')
        }
        const data = await res.json()
        if (data.images && data.images.length > 0) {
          generatedImages.value = data.images.map(url => ({ url }))
        } else if (data.paths && data.paths.length > 0) {
          generatedImages.value = data.paths.map(url => ({ url }))
        } else {
          throw new Error('返回数据格式异常')
        }
      } else {
        const formData = new FormData()
        formData.append('image', uploadedFile.value)
        formData.append('prompt', prompt.value.trim())
        formData.append('denoising_strength', denoising.value)
        formData.append('steps', steps.value)
        if (seed.value !== -1) formData.append('seed', seed.value)
        if (resolution.value !== 'keep') {
          const [w, h] = resolution.value.split('x').map(Number)
          formData.append('width', w)
          formData.append('height', h)
        }
        formData.append('api_key_token', apiKeyStore.siliconflowKey?.token || '')
        const res = await fetch(`${API_BASE}/kolors/image-to-image`, {
          method: 'POST',
          headers,
          body: formData
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: '请求失败' }))
          throw new Error(err.detail || err.message || '生成失败')
        }
        const data = await res.json()
        if (data.images && data.images.length > 0) {
          generatedImages.value = data.images.map(url => ({ url }))
        } else if (data.paths && data.paths.length > 0) {
          generatedImages.value = data.paths.map(url => ({ url }))
        } else {
          throw new Error('返回数据格式异常')
        }
      }
    } catch (e) {
      error.value = e.message || '生成失败'
    } finally {
      isGenerating.value = false
    }
  }

  function downloadImage(img) {
    const a = document.createElement('a')
    a.href = img.url
    a.download = `ai-image-${Date.now()}.png`
    a.click()
  }

  function useAsReference(img) {
    if (previewUrl.value) {
      URL.revokeObjectURL(previewUrl.value)
    }
    mode.value = 'img2img'
    previewUrl.value = img.url
    // 从 URL 获取 blob 作为文件
    fetch(img.url).then(r => r.blob()).then(blob => {
      uploadedFile.value = new File([blob], 'reference.png', { type: 'image/png' })
    }).catch(() => {
      // fetch 失败时回退到纯文本模式
      error.value = '无法加载参考图片，请重新上传'
      mode.value = 'text2img'
      if (previewUrl.value) {
        URL.revokeObjectURL(previewUrl.value)
        previewUrl.value = ''
      }
    })
  }

  async function loadHistory() {
    try {
      const token = userStore.getAccessToken() || localStorage.getItem('access_token') || ''
      const res = await fetch(`${API_BASE}/kolors/history?page=1&page_size=20`, {
        headers: { Authorization: token ? `Bearer ${token}` : '' }
      })
      if (res.ok) {
        const data = await res.json()
        history.value = (data.items || []).map(item => ({
          id: item.image_id || item.id,
          url: (item.image_urls && item.image_urls[0]) || ''
        }))
      }
    } catch { /* ignore */ }
  }

  async function deleteHistory(id) {
    try {
      const token = userStore.getAccessToken() || localStorage.getItem('access_token') || ''
      await fetch(`${API_BASE}/kolors/history/${id}`, {
        method: 'DELETE',
        headers: { Authorization: token ? `Bearer ${token}` : '' }
      })
      history.value = history.value.filter(h => h.id !== id)
    } catch { /* ignore */ }
  }

  async function clearHistory() {
    try {
      const token = userStore.getAccessToken() || localStorage.getItem('access_token') || ''
      await fetch(`${API_BASE}/kolors/history`, {
        method: 'DELETE',
        headers: { Authorization: token ? `Bearer ${token}` : '' }
      })
      history.value = []
    } catch { /* ignore */ }
  }

  onMounted(() => {
    loadHistory()
  })

  onUnmounted(() => {
    if (previewUrl.value) {
      URL.revokeObjectURL(previewUrl.value)
    }
  })

  function setFile(file) {
    if (file.size > 10 * 1024 * 1024) {
      error.value = '图片大小不能超过 10MB'
      return
    }
    if (previewUrl.value) {
      URL.revokeObjectURL(previewUrl.value)
    }
    uploadedFile.value = file
    previewUrl.value = URL.createObjectURL(file)
    error.value = ''
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
    backdrop-filter: blur(20px);
  }

  .back-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    color: var(--text-secondary);
    font-size: 14px;
    cursor: pointer;
  }

  .back-btn:hover { background: var(--hover-bg); color: var(--text-primary); }
  .back-btn svg { width: 16px; height: 16px; }

  .header-title { display: flex; align-items: center; gap: 12px; font-size: 18px; font-weight: 600; }
  .header-title svg { width: 28px; height: 28px; color: var(--teal-hover); }
  .header-hint { font-size: 13px; color: var(--text-tertiary); }

  .page-content {
    flex: 1;
    display: grid;
    grid-template-columns: 420px 1fr;
    gap: 0;
    overflow: hidden;
  }

  .config-panel {
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
    padding: 24px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .mode-tabs { display: flex; gap: 8px; }

  .mode-tab {
    flex: 1;
    padding: 10px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: transparent;
    color: var(--text-secondary);
    font-size: 14px;
    cursor: pointer;
  }

  .mode-tab:hover { background: var(--hover-bg); }
  .mode-tab.active { background: var(--primary-100); border-color: var(--teal-hover); color: var(--teal-hover); }

  .form-section { display: flex; flex-direction: column; gap: 12px; }

  .form-label { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
  .required { color: var(--color-danger-500); }

  .form-textarea {
    width: 100%;
    padding: 12px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 14px;
    font-family: inherit;
    resize: vertical;
  }

  .form-textarea:focus { outline: none; border-color: var(--teal-hover); }
  .form-textarea:disabled { opacity: 0.5; }

  .char-count { font-size: 12px; color: var(--text-tertiary); text-align: right; }

  .upload-area {
    border: 2px dashed var(--border-color);
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
  }

  .upload-area:hover { border-color: var(--teal-hover); background: var(--primary-50); }

  .upload-preview { max-width: 100%; max-height: 200px; border-radius: 8px; }

  .upload-placeholder { display: flex; flex-direction: column; align-items: center; gap: 8px; color: var(--text-tertiary); }
  .upload-placeholder svg { width: 40px; height: 40px; opacity: 0.5; }
  .upload-hint { font-size: 12px; }

  .file-input { display: none; }

  .style-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }

  .style-card {
    padding: 8px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .style-card:hover { background: var(--hover-bg); }
  .style-card.selected { border-color: var(--teal-hover); background: var(--primary-100); }

  .style-preview { aspect-ratio: 1; border-radius: 6px; margin-bottom: 6px; }
  .style-name { font-size: 12px; color: var(--text-secondary); }

  .form-select {
    width: 100%;
    padding: 10px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 14px;
  }

  .form-select:focus { outline: none; border-color: var(--teal-hover); }

  .advanced-group {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 12px;
    background: var(--bg-tertiary);
    border-radius: 8px;
  }

  .slider-item { display: flex; flex-direction: column; gap: 8px; }

  .slider-header { display: flex; justify-content: space-between; align-items: center; font-size: 13px; color: var(--text-secondary); }
  .slider-value { font-weight: 600; color: var(--text-primary); }

  .slider-item input[type="range"] {
    width: 100%;
    accent-color: var(--teal-hover);
  }

  .btn-random {
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 4px;
    background: var(--hover-bg);
    color: var(--text-secondary);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-random:hover { background: var(--bg-tertiary); }

  .seed-input {
    width: 100%;
    padding: 8px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 13px;
  }

  .btn-generate {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 14px;
    background: var(--gradient-primary);
    border: none;
    border-radius: 10px;
    color: white;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
  }

  .btn-generate:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 20px var(--shadow-color); }
  .btn-generate:disabled { opacity: 0.5; cursor: not-allowed; }

  .loading-spinner { width: 20px; height: 20px; }

  .error-message {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px;
    background: var(--color-danger-50);
    border-radius: 8px;
    color: var(--color-danger-500);
    font-size: 13px;
  }

  .error-message svg { width: 16px; height: 16px; flex-shrink: 0; }

  .result-panel {
    padding: 24px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  .empty-state, .loading-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    color: var(--text-tertiary);
  }

  .empty-state svg, .loading-state svg { width: 64px; height: 64px; opacity: 0.3; }
  .empty-state h3 { font-size: 20px; color: var(--text-secondary); }

  .loading-dots { display: flex; gap: 8px; }
  .loading-dots span {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--teal-hover);
    animation: loading 1.4s infinite;
  }

  .loading-dots span:nth-child(2) { animation-delay: 0.2s; }
  .loading-dots span:nth-child(3) { animation-delay: 0.4s; }

  @keyframes loading {
    0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
    40% { opacity: 1; transform: scale(1); }
  }

  .images-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }

  .image-card {
    border-radius: 12px;
    overflow: hidden;
    background: var(--bg-secondary);
    position: relative;
  }

  .image-card:hover .image-actions { opacity: 1; }

  .generated-image { width: 100%; display: block; }

  .image-actions {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    display: flex;
    gap: 8px;
    padding: 12px;
    background: linear-gradient(transparent, rgba(0, 0, 0, 0.7));
    opacity: 0;
    transition: opacity 0.2s;
  }

  .btn-icon {
    width: 36px;
    height: 36px;
    border: none;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.15);
    color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-icon:hover { background: rgba(255, 255, 255, 0.25); }
  .btn-icon svg { width: 18px; height: 18px; }

  .history-section { margin-top: 32px; }

  .history-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
  .history-header h4 { margin: 0; font-size: 15px; color: var(--text-secondary); }

  .btn-clear {
    padding: 6px 12px;
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 6px;
    background: transparent;
    color: var(--color-danger-500);
    font-size: 12px;
    cursor: pointer;
  }

  .btn-clear:hover { background: var(--color-danger-50); }

  .history-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }

  .history-item {
    position: relative;
    border-radius: 8px;
    overflow: hidden;
    aspect-ratio: 1;
  }

  .history-item img { width: 100%; height: 100%; object-fit: cover; }

  .history-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.5);
    opacity: 0;
    transition: opacity 0.2s;
  }

  .history-item:hover .history-overlay { opacity: 1; }

  .btn-icon-sm {
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 6px;
    background: rgba(239, 68, 68, 0.8);
    color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-icon-sm svg { width: 16px; height: 16px; }
</style>
