<template>
  <div v-if="visible" class="image-generator-container">
    <div class="generator-header">
      <h2>
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
        </svg>
        AI 绘画
      </h2>
      <button class="close-btn" @click="$emit('close')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
      <div class="mode-switch">
        <button :class="['mode-btn', { active: mode === 'text2img' }]" @click="mode = 'text2img'">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path
              d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"
            />
            <circle cx="12" cy="13" r="3" />
          </svg>
          文生图
        </button>
        <button :class="['mode-btn', { active: mode === 'img2img' }]" @click="mode = 'img2img'">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
          图生图
        </button>
      </div>
    </div>

    <div class="generator-content">
      <!-- 文生图模式 -->
      <div v-if="mode === 'text2img'" class="mode-panel">
        <div class="form-section">
          <label class="form-label">提示词</label>
          <textarea
            v-model="text2imgForm.prompt"
            class="form-textarea prompt-input"
            placeholder="描述你想要生成的画面，例如：一只在月光下奔跑的银色狐狸，星空背景，梦幻风格..."
            rows="6"
            maxlength="2000"
          ></textarea>
          <div class="char-count">{{ text2imgForm.prompt.length }} / 2000</div>
        </div>

        <div class="form-section">
          <label class="form-label">画面风格</label>
          <div class="style-grid">
            <div
              v-for="style in styles"
              :key="style.value"
              :class="['style-card', { selected: text2imgForm.style === style.value }]"
              @click="text2imgForm.style = style.value"
            >
              <div class="style-preview" :style="{ background: style.color }">
                <svg
                  v-if="style.icon"
                  class="icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <component :is="style.icon" />
                </svg>
              </div>
              <div class="style-name">{{ style.name }}</div>
            </div>
          </div>
        </div>

        <div class="form-row">
          <div class="form-section half">
            <label class="form-label">分辨率</label>
            <select v-model="text2imgForm.resolution" class="form-select">
              <option value="512x512">512 × 512</option>
              <option value="768x768">768 × 768</option>
              <option value="1024x1024">1024 × 1024</option>
              <option value="512x768">512 × 768 (竖版)</option>
              <option value="768x512">768 × 512 (横版)</option>
            </select>
          </div>
          <div class="form-section half">
            <label class="form-label">迭代步数</label>
            <div class="slider-container">
              <input
                v-model.number="text2imgForm.steps"
                type="range"
                min="10"
                max="50"
                step="1"
                class="form-slider"
              />
              <span class="slider-value">{{ text2imgForm.steps }}</span>
            </div>
          </div>
        </div>

        <div class="form-row">
          <div class="form-section half">
            <label class="form-label">引导系数 (CFG Scale)</label>
            <div class="slider-container">
              <input
                v-model.number="text2imgForm.cfg_scale"
                type="range"
                min="1"
                max="20"
                step="0.5"
                class="form-slider"
              />
              <span class="slider-value">{{ text2imgForm.cfg_scale }}</span>
            </div>
          </div>
          <div class="form-section half">
            <label class="form-label">随机种子</label>
            <div class="seed-input">
              <input
                v-model.number="text2imgForm.seed"
                type="number"
                class="form-input"
                placeholder="-1 表示随机"
              />
              <button class="btn-icon" title="随机种子" @click="randomizeSeed">
                <svg
                  class="icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 图生图模式 -->
      <div v-if="mode === 'img2img'" class="mode-panel">
        <div class="form-section">
          <label class="form-label">参考图片</label>
          <div
            class="upload-area"
            :class="{ 'has-file': img2imgForm.image && img2imgForm.image.path }"
            @dragover.prevent
            @drop.prevent="handleDrop"
            @click="triggerFileSelect"
          >
            <div v-if="!img2imgForm.image || !img2imgForm.image.path" class="upload-placeholder">
              <svg
                class="icon upload-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <p>点击或拖拽上传图片</p>
              <span class="upload-hint">支持 JPG, PNG, WEBP 格式，最大 10MB</span>
            </div>
            <div v-else class="image-preview">
              <img :src="img2imgForm.image.preview" alt="参考图片" />
              <button class="remove-btn" type="button" @click.stop="removeImage">
                <svg
                  class="icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
              <div class="image-info">
                <span>{{ img2imgForm.image.name }}</span>
                <span>{{ img2imgForm.image.size }}</span>
              </div>
            </div>
            <input
              ref="fileInput"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              class="hidden-input"
              @change="handleFileSelect"
            />
          </div>
        </div>

        <div class="form-section">
          <label class="form-label">提示词</label>
          <textarea
            v-model="img2imgForm.prompt"
            class="form-textarea prompt-input"
            placeholder="描述想要修改的内容，例如：将背景改为黄昏，增加一些花朵..."
            rows="4"
            maxlength="2000"
          ></textarea>
          <div class="char-count">{{ img2imgForm.prompt.length }} / 2000</div>
        </div>

        <div class="form-section">
          <label class="form-label">重绘强度</label>
          <div class="slider-container">
            <input
              v-model.number="img2imgForm.denoising_strength"
              type="range"
              min="0.1"
              max="1"
              step="0.05"
              class="form-slider"
            />
            <span class="slider-value">{{ img2imgForm.denoising_strength }}</span>
          </div>
          <p class="hint">值越大，生成结果与原作差异越大（0.1=轻微修改，1=完全重绘）</p>
        </div>

        <div class="form-row">
          <div class="form-section half">
            <label class="form-label">分辨率</label>
            <select v-model="img2imgForm.resolution" class="form-select">
              <option value="keep">保持原图</option>
              <option value="512x512">512 × 512</option>
              <option value="768x768">768 × 768</option>
              <option value="1024x1024">1024 × 1024</option>
            </select>
          </div>
          <div class="form-section half">
            <label class="form-label">迭代步数</label>
            <div class="slider-container">
              <input
                v-model.number="img2imgForm.steps"
                type="range"
                min="10"
                max="50"
                step="1"
                class="form-slider"
              />
              <span class="slider-value">{{ img2imgForm.steps }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 生成按钮 -->
      <div class="action-section">
        <button
          class="generate-btn"
          :disabled="isGenerating || !canGenerate"
          @click="handleGenerate"
        >
          <svg
            v-if="isGenerating"
            class="icon spinning"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
          <svg
            v-else
            class="icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
          </svg>
          {{ isGenerating ? '生成中...' : '开始生成' }}
        </button>
      </div>

      <!-- 生成结果 -->
      <div v-if="generatedImages.length > 0" class="result-section">
        <div class="result-header">
          <h3>
            <svg
              class="icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
            生成结果
          </h3>
          <button class="btn-download-all" @click="downloadAll">
            <svg
              class="icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            下载全部
          </button>
        </div>
        <div class="image-grid">
          <div v-for="(img, index) in generatedImages" :key="index" class="result-card">
            <div class="result-image-wrapper">
              <img
                :src="img.url || img.image_url"
                :alt="'生成结果 ' + (index + 1)"
                class="result-image"
                @load="img.loaded = true"
              />
              <div v-if="!img.loaded" class="loading-overlay">
                <svg
                  class="icon spinning"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
              </div>
            </div>
            <div class="result-actions">
              <button class="btn-action" @click="downloadImage(img, index)">
                <svg
                  class="icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                下载
              </button>
              <button v-if="img.img2img_available" class="btn-action" @click="useAsReference(img)">
                <svg
                  class="icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <polyline points="17 1 21 5 17 9" />
                  <path d="M3 11V9a4 4 0 0 1 4-4h14" />
                  <polyline points="7 23 3 19 7 15" />
                  <path d="M21 13v2a4 4 0 0 1-4 4H3" />
                </svg>
                用作参考
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 历史记录 -->
      <div v-if="history.length > 0" class="history-section">
        <div class="history-header">
          <h3>
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            最近生成
            <span class="image-count">({{ imageCount }}/{{ MAX_IMAGES }})</span>
          </h3>
          <button class="btn-clear-all" :disabled="history.length === 0" @click="clearAllHistory">
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2"></path>
              <line x1="10" y1="11" x2="10" y2="17"></line>
              <line x1="14" y1="11" x2="14" y2="17"></line>
            </svg>
            清空全部
          </button>
        </div>
        <div class="history-list">
          <div
            v-for="item in history"
            :key="item.image_id"
            class="history-item"
          >
            <div class="history-preview" @click="loadFromHistory(item)">
              <img
                v-if="item.image_urls && item.image_urls.length > 0"
                :src="item.image_urls[0]"
                :alt="item.prompt"
              />
              <div v-else class="history-placeholder">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
              </div>
            </div>
            <div class="history-info">
              <div class="history-prompt">{{ item.prompt }}</div>
              <div class="history-meta">
                <span class="history-type">{{ item.generation_type === 'text-to-image' ? '文生图' : '图生图' }}</span>
                <span class="history-time">{{ formatTime(item.created_at) }}</span>
              </div>
            </div>
            <button class="history-delete" title="删除" @click="deleteHistory(item.image_id)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 错误信息 -->
      <div v-if="error" class="error-section">
        <svg
          class="icon error-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <span>{{ error }}</span>
        <button class="btn-close" @click="error = ''">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script>
  import { ref, computed, reactive, toRefs } from 'vue'
  import { useNavigationStore } from '@/stores/navigation'
  import { useApiKeyStore } from '@/stores/apikey'
  import { api } from '@/utils/api/index'
  import { ElMessage, ElMessageBox } from 'element-plus'

  const apiUrl = import.meta.env.VITE_API_BASE || '/api/v1'

  export default {
    name: 'ImageGenerator',
    props: {
      visible: {
        type: Boolean,
        default: false
      }
    },
    emits: ['close'],
    setup(props) {
      const navStore = useNavigationStore()
      const apiKeyStore = useApiKeyStore()
      const fileInput = ref(null)
      const isGenerating = ref(false)
      const error = ref('')
      const generatedImages = ref([])
      const mode = ref('text2img')
      const history = ref([])

      const styles = [
        {
          value: 'realistic',
          name: '写实',
          color: 'linear-gradient(135deg, #0d9488 0%, #14b8a6 100%)',
          icon: 'circle'
        },
        {
          value: 'anime',
          name: '动漫',
          color: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
          icon: 'star'
        },
        {
          value: 'digital_art',
          name: '数字艺术',
          color: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
          icon: 'palette'
        },
        {
          value: 'oil_painting',
          name: '油画',
          color: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
          icon: 'brush'
        },
        {
          value: 'watercolor',
          name: '水彩',
          color: 'linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)',
          icon: 'droplet'
        },
        {
          value: 'sketch',
          name: '素描',
          color: 'linear-gradient(135deg, #d7d2cc 0%, #304352 100%)',
          icon: 'pen-tool'
        },
        {
          value: 'cyberpunk',
          name: '赛博朋克',
          color: 'linear-gradient(135deg, #f953c6 0%, #b91d73 100%)',
          icon: 'zap'
        },
        {
          value: 'fantasy',
          name: '奇幻',
          color: 'linear-gradient(135deg, #0d9488 0%, #14b8a6 100%)',
          icon: 'sun'
        }
      ]

      const text2imgForm = reactive({
        prompt: '',
        style: 'realistic',
        resolution: '1024x1024',
        steps: 25,
        cfg_scale: 7.5,
        seed: -1
      })

      const img2imgForm = reactive({
        image: null,
        prompt: '',
        denoising_strength: 0.7,
        resolution: 'keep',
        steps: 25,
        seed: -1
      })

      const canGenerate = computed(() => {
        if (mode.value === 'text2img') {
          return text2imgForm.prompt.trim().length > 0
        }
        return img2imgForm.image && img2imgForm.image.path
      })

      const imageCount = computed(() => history.value.length)

      const randomizeSeed = () => {
        text2imgForm.seed = Math.floor(Math.random() * 2147483647)
      }

      const triggerFileSelect = () => {
        fileInput.value?.click()
      }

      const handleFileSelect = event => {
        const file = event.target.files?.[0]
        if (file) {
          validateAndSetImage(file)
        }
        event.target.value = ''
      }

      const handleDrop = event => {
        const file = event.dataTransfer?.files?.[0]
        if (file) {
          validateAndSetImage(file)
        }
      }

      const validateAndSetImage = file => {
        if (!file.type.startsWith('image/')) {
          error.value = '请上传有效的图片文件（JPG, PNG, WEBP）'
          return
        }

        const maxSize = 10 * 1024 * 1024
        if (file.size > maxSize) {
          error.value = '图片大小不能超过 10MB'
          return
        }

        const reader = new FileReader()
        reader.onload = e => {
          img2imgForm.image = {
            file: file,
            path: URL.createObjectURL(file),
            preview: e.target.result,
            name: file.name,
            size: formatFileSize(file.size)
          }
        }
        reader.readAsDataURL(file)
      }

      const formatFileSize = bytes => {
        if (bytes < 1024) return bytes + ' B'
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
      }

      const removeImage = () => {
        if (img2imgForm.image?.path) {
          URL.revokeObjectURL(img2imgForm.image.path)
        }
        img2imgForm.image = null
      }

      const handleGenerate = async () => {
        if (!canGenerate.value) return

        // 检查 API Key 配置
        if (!apiKeyStore.hasSiliconflowKey) {
          error.value = '请先配置 API Key 后再使用'
          return
        }

        if (history.value.length >= MAX_IMAGES) {
          error.value = `最多只能保存 ${MAX_IMAGES} 张图片，请先清理部分历史记录`
          return
        }

        isGenerating.value = true
        error.value = ''
        generatedImages.value = []

        try {
          let result
          const token = localStorage.getItem('access_token')
          const headers = {
            Authorization: `Bearer ${token}`
          }

          if (mode.value === 'text2img') {
            const response = await fetch(`${apiUrl}/kolors/text-to-image`, {
              method: 'POST',
              headers: {
                ...headers,
                'Content-Type': 'application/json'
              },
              body: JSON.stringify({
                prompt: text2imgForm.prompt,
                style: text2imgForm.style,
                width: parseInt(text2imgForm.resolution.split('x')[0]),
                height: parseInt(text2imgForm.resolution.split('x')[1]),
                steps: text2imgForm.steps,
                cfg_scale: text2imgForm.cfg_scale,
                seed: text2imgForm.seed === -1 ? undefined : text2imgForm.seed,
                api_key_token: apiKeyStore.siliconflowKey?.token
              })
            })

            if (!response.ok) {
              const errorData = await response.json()
              throw new Error(errorData.message || '文生图失败')
            }
            result = await response.json()
          } else {
            if (!img2imgForm.image?.file) {
              throw new Error('请先上传参考图片')
            }

            const formData = new FormData()
            formData.append('image', img2imgForm.image.file)
            formData.append('prompt', img2imgForm.prompt)
            formData.append('denoising_strength', img2imgForm.denoising_strength.toString())
            formData.append('steps', img2imgForm.steps.toString())
            if (img2imgForm.resolution !== 'keep') {
              formData.append('width', parseInt(img2imgForm.resolution.split('x')[0]))
              formData.append('height', parseInt(img2imgForm.resolution.split('x')[1]))
            }
            if (img2imgForm.seed !== -1) {
              formData.append('seed', img2imgForm.seed.toString())
            }
            formData.append('api_key_token', apiKeyStore.siliconflowKey?.token || '')

            const response = await fetch(`${apiUrl}/kolors/image-to-image`, {
              method: 'POST',
              headers: {
                Authorization: headers.Authorization
              },
              body: formData
            })

            if (!response.ok) {
              const errorData = await response.json()
              throw new Error(errorData.message || '图生图失败')
            }
            result = await response.json()
          }

          if (result && result.images && result.images.length > 0) {
            generatedImages.value = result.images.map(url => ({
              url,
              loaded: false,
              img2img_available: true
            }))
          } else if (result && result.paths && result.paths.length > 0) {
            generatedImages.value = result.paths.map(url => ({
              url,
              loaded: false,
              img2img_available: true
            }))
          } else {
            throw new Error('生成失败，未返回图片数据')
          }
        } catch (err) {
          console.error('图片生成失败:', err)
          error.value = err.message || '图片生成失败，请稍后重试'
        } finally {
          isGenerating.value = false
        }
      }

      const downloadImage = (img, index) => {
        const url = img.url || img.image_url
        const link = document.createElement('a')
        link.href = url
        link.download = `ai-generated-${index + 1}.png`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
      }

      const downloadAll = () => {
        generatedImages.value.forEach((img, index) => {
          setTimeout(() => downloadImage(img, index), index * 200)
        })
      }

      const useAsReference = img => {
        mode.value = 'img2img'
        img2imgForm.image = {
          path: img.url || img.image_url,
          preview: img.url || img.image_url,
          name: 'reference-image.png',
          size: ''
        }
        navStore.showImageGenerator = true
        navStore.activeTool = 'imageGenerator'
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }

      const MAX_IMAGES = 50

      const fetchHistory = async () => {
        try {
          const token = localStorage.getItem('access_token')
          if (!token) return

          const resp = await fetch('/api/v1/kolors/history?page=1&page_size=50', {
            headers: { 'Authorization': `Bearer ${token}` }
          })
          if (resp.ok) {
            const data = await resp.json()
            history.value = (data.items || []).slice(0, MAX_IMAGES)
          }
        } catch (e) {
          console.error('获取绘图历史失败:', e)
        }
      }

      const loadFromHistory = item => {
        if (item.image_urls && item.image_urls.length > 0) {
          generatedImages.value = item.image_urls.map(url => ({
            url,
            loaded: false,
            img2img_available: true
          }))
        }
        if (item.generation_type === 'text-to-image') {
          mode.value = 'text2img'
          text2imgForm.prompt = item.prompt
          if (item.params) {
            text2imgForm.width = item.params.width || 1024
            text2imgForm.height = item.params.height || 1024
          }
        } else if (item.generation_type === 'image-to-image') {
          mode.value = 'img2img'
          img2imgForm.prompt = item.prompt
          if (item.params && item.params.reference_image) {
            img2imgForm.image = {
              path: item.params.reference_image,
              preview: item.params.reference_image,
              name: 'reference.png',
              size: ''
            }
          }
        }
      }

      const clearAllHistory = async () => {
        try {
          await ElMessageBox.confirm('确定要清空所有生图历史吗？此操作不可恢复。', '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
        } catch {
          return
        }

        try {
          const token = localStorage.getItem('access_token')
          if (!token) return

          const resp = await fetch('/api/v1/kolors/history', {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
          })

          if (resp.ok) {
            history.value = []
            generatedImages.value = []
          } else {
            ElMessage.error('清空失败，请稍后重试')
          }
        } catch (e) {
          console.error('清空历史失败:', e)
          ElMessage.error('清空失败，请稍后重试')
        }
      }

      const deleteHistory = async (imageId) => {
        try {
          await ElMessageBox.confirm('确定要删除这条历史记录吗？', '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
        } catch {
          return
        }

        try {
          const token = localStorage.getItem('access_token')
          if (!token) return

          const resp = await fetch(`/api/v1/kolors/history/${imageId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
          })

          if (resp.ok) {
            history.value = history.value.filter(item => item.image_id !== imageId)
          }
        } catch (e) {
          console.error('删除历史记录失败:', e)
        }
      }

      const formatTime = timeString => {
        if (!timeString) return ''
        const date = new Date(timeString)
        const diff = Date.now() - date.getTime()
        const minutes = Math.floor(diff / 60000)
        if (minutes < 1) return '刚刚'
        if (minutes < 60) return `${minutes}分钟前`
        return date.toLocaleString()
      }

      fetchHistory()

      return {
        fileInput,
        isGenerating,
        error,
        generatedImages,
        history,
        mode,
        styles,
        text2imgForm,
        img2imgForm,
        canGenerate,
        randomizeSeed,
        triggerFileSelect,
        handleFileSelect,
        handleDrop,
        removeImage,
        handleGenerate,
        downloadImage,
        downloadAll,
        useAsReference,
        loadFromHistory,
        deleteHistory,
        clearAllHistory,
        formatTime,
        imageCount
      }
    }
  }
</script>

<style scoped>
  .image-generator-container {
    max-width: 1000px;
    margin: 0 auto;
    padding: 1.5rem;
  }

  .generator-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
    flex-wrap: wrap;
    gap: 1rem;
  }

  .close-btn {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    cursor: pointer;
    color: var(--text-secondary);
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .close-btn svg {
    width: 20px;
    height: 20px;
  }

  .generator-header h2 {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 1.5rem;
    font-weight: 700;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .icon {
    width: 1.5rem;
    height: 1.5rem;
  }

  .mode-switch {
    display: flex;
    gap: 0.5rem;
    background: rgba(0, 0, 0, 0.2);
    padding: 0.25rem;
    border-radius: 0.75rem;
  }

  .mode-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border: none;
    background: transparent;
    color: #94a3b8;
    border-radius: 0.5rem;
    cursor: pointer;
    transition: all 0.3s ease;
    font-size: 0.875rem;
  }

  .mode-btn:hover {
    color: #f1f5f9;
  }

  .mode-btn.active {
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
  }

  .mode-btn .icon {
    width: 1.25rem;
    height: 1.25rem;
  }

  .generator-content {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .form-section {
    margin-bottom: 1.5rem;
  }

  .form-label {
    display: block;
    font-weight: 600;
    color: #e2e8f0;
    margin-bottom: 0.75rem;
    font-size: 0.95rem;
  }

  .form-textarea {
    width: 100%;
    padding: 1rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.75rem;
    color: #f1f5f9;
    font-size: 1rem;
    resize: vertical;
    transition: all 0.3s ease;
  }

  .form-textarea:focus {
    outline: none;
    border-color: #0d9488;
    background: rgba(255, 255, 255, 0.08);
  }

  .prompt-input {
    min-height: 120px;
  }

  .char-count {
    text-align: right;
    font-size: 0.75rem;
    color: var(--text-tertiary);
    margin-top: 0.5rem;
  }

  .style-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 1rem;
  }

  .style-card {
    padding: 1rem;
    background: rgba(255, 255, 255, 0.05);
    border: 2px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.75rem;
    cursor: pointer;
    transition: all 0.3s ease;
    text-align: center;
  }

  .style-card:hover {
    border-color: rgba(255, 255, 255, 0.3);
    transform: translateY(-2px);
  }

  .style-card.selected {
    border-color: #0d9488;
    background: rgba(102, 126, 234, 0.1);
  }

  .style-preview {
    width: 100%;
    aspect-ratio: 1;
    border-radius: 0.5rem;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .style-preview .icon {
    width: 2rem;
    height: 2rem;
    color: white;
    opacity: 0.9;
  }

  .style-name {
    font-size: 0.875rem;
    color: #e2e8f0;
    font-weight: 500;
  }

  .form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
  }

  .form-section.half {
    margin-bottom: 0;
  }

  .form-select {
    width: 100%;
    padding: 0.75rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    color: #f1f5f9;
    font-size: 0.95rem;
    cursor: pointer;
  }

  .form-select:focus {
    outline: none;
    border-color: #0d9488;
  }

  .slider-container {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .form-slider {
    flex: 1;
    height: 6px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.1);
    outline: none;
    -webkit-appearance: none;
    appearance: none;
  }

  .form-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    cursor: pointer;
    transition: all 0.3s ease;
  }

  .form-slider::-webkit-slider-thumb:hover {
    transform: scale(1.2);
  }

  .slider-value {
    min-width: 3rem;
    text-align: right;
    font-weight: 600;
    color: #0d9488;
    font-size: 1rem;
  }

  .seed-input {
    display: flex;
    gap: 0.5rem;
  }

  .form-input {
    flex: 1;
    padding: 0.75rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    color: #f1f5f9;
    font-size: 0.95rem;
  }

  .form-input:focus {
    outline: none;
    border-color: #0d9488;
  }

  .btn-icon {
    width: 42px;
    height: 42px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    color: #e2e8f0;
    cursor: pointer;
    transition: all 0.3s ease;
  }

  .btn-icon:hover {
    background: rgba(255, 255, 255, 0.1);
    border-color: #0d9488;
  }

  .upload-area {
    border: 2px dashed rgba(255, 255, 255, 0.2);
    border-radius: 0.75rem;
    padding: 2rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s ease;
    min-height: 200px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .upload-area:hover {
    border-color: #0d9488;
    background: rgba(102, 126, 234, 0.05);
  }

  .upload-area.has-file {
    border-style: solid;
    border-color: #10b981;
    padding: 1rem;
  }

  .upload-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
  }

  .upload-icon {
    width: 4rem;
    height: 4rem;
    color: var(--text-tertiary);
  }

  .upload-placeholder p {
    font-size: 1.1rem;
    color: #e2e8f0;
    margin: 0;
  }

  .upload-hint {
    font-size: 0.875rem;
    color: var(--text-tertiary);
  }

  .hidden-input {
    display: none;
  }

  .image-preview {
    position: relative;
    width: 100%;
    max-width: 400px;
    margin: 0 auto;
  }

  .image-preview img {
    width: 100%;
    border-radius: 0.5rem;
    display: block;
  }

  .remove-btn {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.7);
    border: none;
    border-radius: 50%;
    color: white;
    cursor: pointer;
    transition: all 0.3s ease;
  }

  .remove-btn:hover {
    background: var(--danger);
    transform: scale(1.1);
  }

  .image-info {
    display: flex;
    justify-content: space-between;
    margin-top: 0.5rem;
    font-size: 0.875rem;
    color: #94a3b8;
  }

  .hint {
    margin-top: 0.5rem;
    font-size: 0.875rem;
    color: var(--text-tertiary);
  }

  .action-section {
    margin: 2rem 0;
  }

  .generate-btn {
    width: 100%;
    padding: 1rem 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    border: none;
    border-radius: 0.75rem;
    color: white;
    font-size: 1.1rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
  }

  .generate-btn:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
  }

  .generate-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .generate-btn .icon {
    width: 1.5rem;
    height: 1.5rem;
  }

  .spinning {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .result-section {
    margin-top: 2rem;
    padding-top: 2rem;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
  }

  .result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }

  .result-header h3 {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 1.25rem;
    color: #e2e8f0;
  }

  .btn-download-all {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    color: #e2e8f0;
    cursor: pointer;
    transition: all 0.3s ease;
    font-size: 0.9rem;
  }

  .btn-download-all:hover {
    background: rgba(255, 255, 255, 0.1);
    border-color: #0d9488;
  }

  .image-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1.5rem;
  }

  .result-card {
    background: rgba(255, 255, 255, 0.05);
    border-radius: 0.75rem;
    overflow: hidden;
    transition: all 0.3s ease;
  }

  .result-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
  }

  .result-image-wrapper {
    position: relative;
    aspect-ratio: 1;
    overflow: hidden;
    background: rgba(0, 0, 0, 0.2);
  }

  .result-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: opacity 0.3s ease;
  }

  .loading-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.5);
  }

  .loading-overlay .icon {
    width: 3rem;
    height: 3rem;
    color: white;
  }

  .result-actions {
    display: flex;
    gap: 0.5rem;
    padding: 1rem;
  }

  .btn-action {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.5rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    color: #e2e8f0;
    cursor: pointer;
    transition: all 0.3s ease;
    font-size: 0.875rem;
  }

  .btn-action:hover {
    background: rgba(255, 255, 255, 0.1);
    border-color: #0d9488;
  }

  .btn-action .icon {
    width: 1rem;
    height: 1rem;
  }

  .error-section {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 0.75rem;
    margin-top: 1rem;
  }

  .error-icon {
    width: 1.5rem;
    height: 1.5rem;
    color: var(--danger);
    flex-shrink: 0;
  }

  .error-section span {
    flex: 1;
    color: #fca5a5;
  }

  .btn-close {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    border-radius: 0.5rem;
    color: var(--danger);
    cursor: pointer;
    transition: all 0.3s ease;
  }

  .btn-close:hover {
    background: rgba(239, 68, 68, 0.2);
  }

  .history-section {
    margin-top: 2rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 1rem;
    padding: 1.5rem;
  }

  .history-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }

  .history-header h3 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0;
    color: var(--text-primary);
    font-size: 1.25rem;
  }

  .image-count {
    font-size: 0.875rem;
    color: var(--text-tertiary);
    font-weight: normal;
  }

  .btn-clear-all {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 1rem;
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    background: transparent;
    color: var(--text-secondary);
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.3s ease;
  }

  .btn-clear-all:hover:not(:disabled) {
    border-color: var(--danger);
    color: var(--danger);
    background: rgba(239, 68, 68, 0.1);
  }

  .btn-clear-all:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-clear-all .icon {
    width: 1rem;
    height: 1rem;
  }

  .history-header .icon {
    width: 1.25rem;
    height: 1.25rem;
  }

  .history-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
    margin-top: 1rem;
  }

  .history-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 0.75rem;
    transition: all 0.3s ease;
    position: relative;
  }

  .history-item:hover {
    border-color: #0d9488;
    background: rgba(13, 148, 136, 0.1);
  }

  .history-preview {
    width: 60px;
    height: 60px;
    border-radius: 0.5rem;
    overflow: hidden;
    cursor: pointer;
    flex-shrink: 0;
    background: var(--bg-secondary);
  }

  .history-preview img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .history-placeholder {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-tertiary);
  }

  .history-placeholder svg {
    width: 24px;
    height: 24px;
  }

  .history-info {
    flex: 1;
    min-width: 0;
    cursor: pointer;
  }

  .history-prompt {
    font-size: 0.875rem;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 0.25rem;
  }

  .history-meta {
    display: flex;
    gap: 0.5rem;
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }

  .history-type {
    background: rgba(13, 148, 136, 0.2);
    color: #0d9488;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
  }

  .history-delete {
    display: none;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    background: transparent;
    border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    border-radius: 0.25rem;
    transition: all 0.2s;
    flex-shrink: 0;
  }

  .history-item:hover .history-delete {
    display: flex;
  }

  .history-delete:hover {
    background: var(--danger);
    color: white;
  }

  @media (max-width: 768px) {
    .image-generator-container {
      padding: 1rem;
    }

    .generator-header {
      flex-direction: column;
      align-items: stretch;
    }

    .mode-switch {
      width: 100%;
      justify-content: center;
    }

    .form-row {
      grid-template-columns: 1fr;
    }

    .image-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
