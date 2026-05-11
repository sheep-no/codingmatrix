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
        <span>AI 生成 PPT</span>
      </div>
      <div class="header-actions">
        <div class="header-hint">生成后在任务队列查看进度</div>
      </div>
    </header>

    <div class="page-content">
      <div class="form-card">
        <div class="form-section">
          <label class="form-label">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
            </svg>
            PPT 主题 <span class="required">*</span>
          </label>
          <textarea
            v-model="pptPrompt"
            class="form-textarea"
            placeholder="请输入 PPT 主题或内容大纲，例如：&#10;关于人工智能的介绍，包含以下章节：&#10;1. 人工智能概述&#10;2. 主要技术方向&#10;3. 应用场景&#10;4. 未来发展趋势"
            rows="8"
            :disabled="isGenerating"
          ></textarea>
          <div class="char-count">{{ pptPrompt.length }} / 2000</div>
        </div>

        <div class="form-section">
          <label class="form-label">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
            </svg>
            选择模板
          </label>
          <div class="template-grid">
            <div
              v-for="template in templates"
              :key="template.id"
              class="template-card"
              :class="{ selected: selectedTemplate === template.id }"
              @click="selectedTemplate = template.id"
            >
              <div class="template-preview" :style="{ background: template.color }">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <line x1="8" y1="8" x2="16" y2="8"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="16" x2="12" y2="16"/>
                </svg>
              </div>
              <div class="template-info">
                <div class="template-name">{{ template.name }}</div>
                <div class="template-desc">{{ template.desc }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="form-section">
          <label class="form-label">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
            高级选项
          </label>
          <div class="advanced-options">
            <div class="option-item">
              <label class="option-label">
                <span>幻灯片数量</span>
                <select v-model="slideCount" class="option-select" :disabled="isGenerating">
                  <option value="5">5 页 (简洁)</option>
                  <option value="10">10 页 (标准)</option>
                  <option value="15">15 页 (详细)</option>
                  <option value="20">20 页 (完整)</option>
                </select>
              </label>
            </div>
            <label class="option-item option-checkbox-item">
              <input v-model="autoImages" type="checkbox" :disabled="isGenerating" />
              <span>自动配图</span>
            </label>
          </div>
        </div>

        <div class="form-actions">
          <button
            class="btn-generate"
            :disabled="!canGenerate || isGenerating"
            @click="generatePPT"
          >
            <svg v-if="isGenerating" class="loading-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" stroke-dasharray="60" stroke-dashoffset="60">
                <animate attributeName="stroke-dashoffset" from="60" to="0" dur="1s" repeatCount="indefinite" />
              </circle>
            </svg>
            <span>{{ isGenerating ? '生成中...' : '开始生成' }}</span>
          </button>
          <p class="generate-hint">生成时间约 2-5 分钟，完成后自动跳转到任务队列</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed } from 'vue'
  import { useRouter } from 'vue-router'
  import { api } from '@/utils/api/index'

  const router = useRouter()

  const pptPrompt = ref('')
  const selectedTemplate = ref('default')
  const slideCount = ref('10')
  const autoImages = ref(true)
  const isGenerating = ref(false)

  const templates = [
    { id: 'default', name: '默认模板', desc: '简洁通用', color: 'linear-gradient(135deg, #0d9488 0%, #14b8a6 100%)' },
    { id: 'business', name: '商务风格', desc: '专业正式', color: 'linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)' },
    { id: 'tech', name: '科技风格', desc: '现代创新', color: 'linear-gradient(135deg, #00c6ff 0%, #0072ff 100%)' },
    { id: 'simple', name: '极简风格', desc: '清新淡雅', color: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)' },
    { id: 'creative', name: '创意设计', desc: '活泼生动', color: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' },
    { id: 'elegant', name: '优雅经典', desc: '高贵典雅', color: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)' }
  ]

  const canGenerate = computed(() => {
    return pptPrompt.value.trim().length > 0 && pptPrompt.value.length <= 2000
  })

  const goBack = () => router.push('/')

  const buildFullPrompt = () => {
    const template = templates.find(t => t.id === selectedTemplate.value)
    const features = []
    if (autoImages.value) features.push('自动配图')
    let fullPrompt = `${pptPrompt.value.trim()}\n\n`
    fullPrompt += `模板风格：${template?.name || '默认'}\n`
    fullPrompt += `幻灯片数量：${slideCount.value}页\n`
    if (features.length > 0) fullPrompt += `特殊要求：${features.join('、')}\n`
    return fullPrompt
  }

  const generatePPT = async () => {
    if (!canGenerate.value || isGenerating.value) return
    isGenerating.value = true
    try {
      const fullPrompt = buildFullPrompt()
      const result = await api.createPptTask(fullPrompt)
      if (result && result.task_id) {
        window.open('/task-queue', '_blank')
      } else {
        alert('创建 PPT 任务失败，请稍后重试')
      }
    } catch (error) {
      alert('生成失败：' + (error.message || '未知错误'))
    } finally {
      isGenerating.value = false
    }
  }
</script>

<style scoped>
  .ppt-generate-page {
    min-height: 100vh;
    background: var(--bg-primary);
    color: var(--text-primary);
    display: flex;
    flex-direction: column;
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

  .header-title {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 18px;
    font-weight: 600;
  }

  .header-title svg { width: 28px; height: 28px; color: var(--teal-hover); }
  .header-hint { font-size: 13px; color: var(--text-tertiary); }

  .page-content {
    flex: 1;
    display: flex;
    justify-content: center;
    padding: 32px 24px;
  }

  .form-card {
    width: 100%;
    max-width: 800px;
    display: flex;
    flex-direction: column;
    gap: 32px;
  }

  .form-section { display: flex; flex-direction: column; gap: 12px; }

  .form-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .form-label svg { width: 18px; height: 18px; color: var(--teal-hover); }
  .required { color: var(--color-danger-500); }

  .form-textarea {
    width: 100%;
    padding: 14px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    color: var(--text-primary);
    font-size: 14px;
    font-family: inherit;
    resize: vertical;
  }

  .form-textarea:focus { outline: none; border-color: var(--teal-hover); box-shadow: 0 0 0 3px var(--primary-100); }
  .form-textarea:disabled { opacity: 0.5; cursor: not-allowed; }

  .char-count { font-size: 12px; color: var(--text-tertiary); text-align: right; }

  .template-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
  }

  .template-card {
    padding: 12px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .template-card:hover { background: var(--hover-bg); }
  .template-card.selected { border-color: var(--teal-hover); background: var(--primary-100); }

  .template-preview {
    aspect-ratio: 16 / 10;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 8px;
  }

  .template-preview svg { width: 32px; height: 32px; color: var(--text-secondary); }
  .template-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
  .template-desc { font-size: 11px; color: var(--text-tertiary); }

  .advanced-options { display: flex; gap: 16px; }

  .option-item {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    background: var(--bg-tertiary);
    border-radius: 8px;
  }

  .option-label { display: flex; align-items: center; gap: 12px; flex: 1; }
  .option-label span { font-size: 14px; color: var(--text-primary); }

  .option-select {
    padding: 6px 12px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 13px;
  }

  .option-select:disabled { opacity: 0.5; }

  .option-checkbox-item input[type="checkbox"] {
    width: 18px;
    height: 18px;
    accent-color: var(--teal-hover);
  }

  .form-actions { display: flex; flex-direction: column; align-items: center; gap: 12px; margin-top: 8px; }

  .btn-generate {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 14px 40px;
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
  .generate-hint { font-size: 13px; color: var(--text-tertiary); margin: 0; }
</style>
