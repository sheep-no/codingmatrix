<template>
  <div v-if="visible" class="ppt-generator-modal" @click.self="close">
    <div class="ppt-generator-container">
      <!-- 头部 -->
      <div class="ppt-header">
        <div class="ppt-title">
          <svg
            class="ppt-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
            <polyline points="10 9 9 9 8 9"></polyline>
          </svg>
          <h2>AI 生成 PPT</h2>
        </div>
        <button class="close-btn" @click="close">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>

      <!-- 内容区 -->
      <div class="ppt-content">
        <!-- 主题输入 -->
        <div class="form-section">
          <label class="form-label">
            <svg
              class="label-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            PPT 主题 <span class="required">*</span>
          </label>
          <textarea
            v-model="pptPrompt"
            class="form-textarea"
            placeholder="请输入 PPT 主题或内容大纲，例如：&#10;关于人工智能的介绍，包含以下章节：&#10;1. 人工智能概述&#10;2. 主要技术方向&#10;3. 应用场景&#10;4. 未来发展趋势"
            rows="6"
            :disabled="isGenerating"
          ></textarea>
          <div class="char-count">{{ pptPrompt.length }} / 2000</div>
        </div>

        <!-- 模板选择 -->
        <div class="form-section">
          <label class="form-label">
            <svg
              class="label-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
              <circle cx="8.5" cy="8.5" r="1.5"></circle>
              <polyline points="21 15 16 10 5 21"></polyline>
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
                  <rect x="3" y="3" width="18" height="18" rx="2"></rect>
                  <line x1="8" y1="8" x2="16" y2="8"></line>
                  <line x1="8" y1="12" x2="16" y2="12"></line>
                  <line x1="8" y1="16" x2="12" y2="16"></line>
                </svg>
              </div>
              <div class="template-info">
                <div class="template-name">{{ template.name }}</div>
                <div class="template-desc">{{ template.desc }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 高级选项 -->
        <div class="form-section">
          <label class="form-label">
            <svg
              class="label-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="3"></circle>
              <path
                d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"
              ></path>
            </svg>
            高级选项
          </label>
          <div class="advanced-options">
            <div class="option-item">
              <label class="option-label">
                <span>幻灯片数量</span>
                <select v-model="slideCount" class="option-select">
                  <option value="5">5 页 (简洁)</option>
                  <option value="10">10 页 (标准)</option>
                  <option value="15">15 页 (详细)</option>
                  <option value="20">20 页 (完整)</option>
                </select>
              </label>
            </div>
            <div class="option-item">
              <label class="option-label">
                <input v-model="autoImages" type="checkbox" class="option-checkbox" />
                <span>自动配图</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部操作栏 -->
      <div class="ppt-footer">
        <div class="footer-info">
          <svg
            class="info-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="16" x2="12" y2="12"></line>
            <line x1="12" y1="8" x2="12.01" y2="8"></line>
          </svg>
          <span class="info-text">生成时间约 2-5 分钟，完成后在任务队列查看</span>
        </div>
        <div class="footer-actions">
          <button class="cancel-btn" :disabled="isGenerating" @click="close">取消</button>
          <button
            class="generate-btn"
            :disabled="!canGenerate || isGenerating"
            @click="generatePPT"
          >
            <svg
              v-if="isGenerating"
              class="loading-spinner"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" stroke-dasharray="60" stroke-dashoffset="60">
                <animate
                  attributeName="stroke-dashoffset"
                  from="60"
                  to="0"
                  dur="1s"
                  repeatCount="indefinite"
                />
              </circle>
            </svg>
            <span>{{ isGenerating ? '生成中...' : '开始生成' }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed } from 'vue'
  import { api } from '@/utils/api/index'
  import { useNavigationStore } from '@/stores/navigation'

  const props = defineProps({
    visible: {
      type: Boolean,
      default: false
    }
  })

  const emit = defineEmits(['close', 'generated'])

  const navigationStore = useNavigationStore()

  // 表单状态
  const pptPrompt = ref('')
  const selectedTemplate = ref('default')
  const slideCount = ref('10')
  const autoImages = ref(true)
  const isGenerating = ref(false)

  // 模板数据
  const templates = [
    {
      id: 'default',
      name: '默认模板',
      desc: '简洁通用',
      color: 'linear-gradient(135deg, #0d9488 0%, #14b8a6 100%)'
    },
    {
      id: 'business',
      name: '商务风格',
      desc: '专业正式',
      color: 'linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)'
    },
    {
      id: 'tech',
      name: '科技风格',
      desc: '现代创新',
      color: 'linear-gradient(135deg, #00c6ff 0%, #0072ff 100%)'
    },
    {
      id: 'simple',
      name: '极简风格',
      desc: '清新淡雅',
      color: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)'
    },
    {
      id: 'creative',
      name: '创意设计',
      desc: '活泼生动',
      color: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)'
    },
    {
      id: 'elegant',
      name: '优雅经典',
      desc: '高贵典雅',
      color: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)'
    }
  ]

  // 计算是否可以生成
  const canGenerate = computed(() => {
    return pptPrompt.value.trim().length > 0 && pptPrompt.value.length <= 2000
  })

  // 关闭
  const close = () => {
    if (!isGenerating.value) {
      emit('close')
    }
  }

  // 生成 PPT
  const generatePPT = async () => {
    if (!canGenerate.value || isGenerating.value) return

    isGenerating.value = true

    try {
      // 构建完整的提示词
      const fullPrompt = buildFullPrompt()

      // 创建 PPT 生成任务
      const result = await api.createPptTask(fullPrompt)

      if (result && result.task_id) {
        // 成功创建任务
        emit('generated', result)

        // 提示用户并跳转到任务队列
        setTimeout(() => {
          navigationStore.hideTool('pptGenerator')
          navigationStore.showTool('taskQueue')
        }, 500)
      } else {
        alert('创建 PPT 任务失败，请稍后重试')
      }
    } catch (error) {
      console.error('PPT 生成失败:', error)
      alert('生成失败：' + (error.message || '未知错误'))
    } finally {
      isGenerating.value = false
    }
  }

  // 构建完整提示词
  const buildFullPrompt = () => {
    const template = templates.find(t => t.id === selectedTemplate.value)
    const features = []

    if (autoImages.value) {
      features.push('自动配图')
    }

    let fullPrompt = `${pptPrompt.value.trim()}\n\n`
    fullPrompt += `模板风格：${template?.name || '默认'}\n`
    fullPrompt += `幻灯片数量：${slideCount.value}页\n`

    if (features.length > 0) {
      fullPrompt += `特殊要求：${features.join('、')}\n`
    }

    return fullPrompt
  }
</script>

<style scoped>
  /* 模态框 */
  .ppt-generator-modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(15, 23, 42, 0.6);
    backdrop-filter: blur(8px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: modalFadeIn 0.25s ease;
  }

  @keyframes modalFadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  /* 容器 */
  .ppt-generator-container {
    background: white;
    border-radius: 16px;
    width: 90%;
    max-width: 800px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    animation: modalSlideUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  }

  @keyframes modalSlideUp {
    from {
      opacity: 0;
      transform: translateY(30px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  /* 头部 */
  .ppt-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
    border-bottom: 1px solid #e5e7eb;
    flex-shrink: 0;
  }

  .ppt-title {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .ppt-icon {
    width: 28px;
    height: 28px;
    color: #0d9488;
  }

  .ppt-title h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .close-btn {
    width: 36px;
    height: 36px;
    border: none;
    background: var(--bg-tertiary);
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    color: var(--text-secondary);
  }

  .close-btn:hover {
    background: var(--bg-secondary);
    color: var(--text-primary);
  }

  .close-btn svg {
    width: 18px;
    height: 18px;
  }

  /* 内容区 */
  .ppt-content {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
  }

  /* 表单区域 */
  .form-section {
    margin-bottom: 24px;
  }

  .form-label {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .label-icon {
    width: 18px;
    height: 18px;
    color: var(--text-secondary);
  }

  .form-textarea {
    width: 100%;
    padding: 12px 16px;
    border: 2px solid var(--border-color);
    border-radius: 10px;
    font-size: 14px;
    font-family: inherit;
    resize: vertical;
    transition: all 0.2s;
    color: var(--text-primary);
    background: var(--bg-secondary);
  }

  .form-textarea:focus {
    outline: none;
    border-color: var(--color-primary);
    background: var(--bg-primary);
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  .char-count {
    text-align: right;
    font-size: 12px;
    color: var(--text-tertiary);
    margin-top: 6px;
  }

  /* 模板选择 */
  .template-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 16px;
  }

  .template-card {
    border: 2px solid var(--border-color);
    border-radius: 12px;
    overflow: hidden;
    cursor: pointer;
    transition: all 0.2s;
  }

  .template-card:hover {
    border-color: var(--color-primary);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
  }

  .template-card.selected {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
  }

  .template-preview {
    height: 100px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 12px;
  }

  .template-preview svg {
    width: 100%;
    height: 100%;
    color: rgba(255, 255, 255, 0.9);
  }

  .template-info {
    padding: 12px;
    background: var(--bg-secondary);
  }

  .template-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .template-desc {
    font-size: 12px;
    color: #6b7280;
  }

  /* 高级选项 */
  .advanced-options {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 16px;
  }

  .option-item {
    margin-bottom: 12px;
  }

  .option-item:last-child {
    margin-bottom: 0;
  }

  .option-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 14px;
    color: var(--text-primary);
    cursor: pointer;
  }

  .option-select {
    padding: 6px 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 13px;
    background: var(--bg-primary);
    color: var(--text-primary);
    cursor: pointer;
  }

  .option-checkbox {
    width: 18px;
    height: 18px;
    margin-right: 8px;
    cursor: pointer;
    accent-color: var(--color-primary);
  }

  /* 底部 */
  .ppt-footer {
    padding: 16px 24px;
    border-top: 1px solid var(--border-color);
    background: var(--bg-secondary);
    border-radius: 0 0 16px 16px;
    flex-shrink: 0;
  }

  .footer-info {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
    padding: 10px 14px;
    background: linear-gradient(90deg, var(--primary-100) 0%, var(--primary-200) 100%);
    border-radius: 8px;
    border: 1px solid var(--primary-200);
  }

  .info-icon {
    width: 18px;
    height: 18px;
    color: var(--color-primary);
    flex-shrink: 0;
  }

  .info-text {
    font-size: 13px;
    color: var(--primary-700);
  }

  .footer-actions {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }

  .cancel-btn,
  .generate-btn {
    padding: 10px 24px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .cancel-btn {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
  }

  .cancel-btn:hover:not(:disabled) {
    background: var(--bg-tertiary);
  }

  .cancel-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .generate-btn {
    background: linear-gradient(135deg, var(--color-primary) 0%, var(--teal-400) 100%);
    border: none;
    color: white;
    box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
  }

  .generate-btn:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(102, 126, 234, 0.4);
  }

  .generate-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
  }

  .loading-spinner {
    width: 18px;
    height: 18px;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  /* 滚动条 */
  .ppt-content::-webkit-scrollbar {
    width: 8px;
  }

  .ppt-content::-webkit-scrollbar-track {
    background: var(--bg-secondary);
    border-radius: 4px;
  }

  .ppt-content::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--gray-300) 0%, var(--gray-400) 100%);
    border-radius: 4px;
  }

  .ppt-content::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, var(--gray-400) 0%, var(--gray-500) 100%);
  }
</style>
