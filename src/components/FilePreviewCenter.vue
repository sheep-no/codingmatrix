<template>
  <Modal
    :visible="visible"
    :title="currentFile?.name || '文件预览'"
    size="full"
    @close="$emit('close')"
  >
    <div class="file-preview-center">
      <!-- 左侧文件列表 -->
      <div v-if="files.length > 1" class="file-sidebar">
        <div class="sidebar-header">
          <input v-model="searchQuery" type="text" placeholder="搜索文件..." class="search-input" />
        </div>

        <div class="file-list">
          <div
            v-for="file in filteredFiles"
            :key="file.id"
            class="file-item"
            :class="{ active: currentFile?.id === file.id }"
            @click="selectFile(file)"
          >
            <div class="file-icon">
              <svg
                v-if="isImage(file)"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                width="20"
                height="20"
              >
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
              <svg
                v-else-if="isPDF(file)"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                width="20"
                height="20"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
              <svg
                v-else-if="isCode(file)"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                width="20"
                height="20"
              >
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
              <svg
                v-else
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                width="20"
                height="20"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
            </div>
            <div class="file-info">
              <div class="file-name">{{ file.name }}</div>
              <div class="file-meta">{{ formatFileSize(file.size) }} · {{ file.type }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 中间预览区域 -->
      <div class="preview-main">
        <!-- 工具栏 -->
        <div class="preview-toolbar">
          <div class="toolbar-group">
            <button :disabled="zoomLevel >= 200" class="toolbar-btn" title="放大" @click="zoomIn">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                width="18"
                height="18"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
                <line x1="11" y1="8" x2="11" y2="14" />
                <line x1="8" y1="11" x2="14" y2="11" />
              </svg>
            </button>
            <button :disabled="zoomLevel <= 50" class="toolbar-btn" title="缩小" @click="zoomOut">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                width="18"
                height="18"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
                <line x1="8" y1="11" x2="14" y2="11" />
              </svg>
            </button>
            <button class="toolbar-btn" title="重置" @click="resetZoom">
              <span class="zoom-text">{{ zoomLevel }}%</span>
            </button>
          </div>

          <div class="toolbar-group">
            <button class="toolbar-btn" title="全屏" @click="toggleFullscreen">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                width="18"
                height="18"
              >
                <polyline points="15 3 21 3 21 9" />
                <polyline points="9 21 3 21 3 15" />
                <line x1="21" y1="3" x2="14" y2="10" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
            </button>
            <button class="toolbar-btn" title="下载" @click="downloadFile">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                width="18"
                height="18"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
            </button>
            <button class="toolbar-btn" title="分享" @click="shareFile">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                width="18"
                height="18"
              >
                <circle cx="18" cy="5" r="3" />
                <circle cx="6" cy="12" r="3" />
                <circle cx="18" cy="19" r="3" />
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
              </svg>
            </button>
          </div>

          <div class="toolbar-group">
            <select v-model="previewMode" class="mode-select">
              <option value="view">查看</option>
              <option value="edit">编辑</option>
              <option value="annotate">批注</option>
            </select>
          </div>
        </div>

        <!-- 预览内容 -->
        <div ref="previewContainer" class="preview-content">
          <!-- 图片预览 -->
          <div v-if="isImagePreview" class="image-preview">
            <img
              :src="fileUrl"
              :alt="currentFile?.name"
              :style="{ transform: `scale(${zoomLevel / 100})` }"
              @load="onImageLoad"
              @error="onImageError"
            />
          </div>

          <!-- PDF 预览 -->
          <div v-else-if="isPDFPreview" class="pdf-preview">
            <iframe
              v-if="!usePDFJS"
              :src="fileUrl"
              class="pdf-frame"
              :style="{ transform: `scale(${zoomLevel / 100})` }"
            ></iframe>
            <div v-else class="pdfjs-container">
              <div v-for="page in pdfPages" :key="page.num" class="pdf-page">
                <canvas :ref="`page-${page.num}`"></canvas>
                <div class="page-number">{{ page.num }}</div>
              </div>
            </div>
          </div>

          <!-- 代码预览 -->
          <div v-else-if="isCodePreview" class="code-preview">
            <div class="code-header">
              <div class="code-language">{{ codeLanguage }}</div>
              <button class="copy-btn" @click="copyCode">复制</button>
            </div>
            <pre
              class="code-content"
            ><code :class="codeLanguageClass">{{ codeContent }}</code></pre>
          </div>

          <!-- Markdown 预览 -->
          <div v-else-if="isMarkdownPreview" class="markdown-preview">
            <div class="markdown-content" v-html="renderedMarkdown"></div>
          </div>

          <!-- 文本预览 -->
          <div v-else-if="isTextPreview" class="text-preview">
            <pre>{{ textContent }}</pre>
          </div>

          <!-- 视频预览 -->
          <div v-else-if="isVideoPreview" class="video-preview">
            <video :src="fileUrl" controls :autoplay="autoPlay"></video>
          </div>

          <!-- 音频预览 -->
          <div v-else-if="isAudioPreview" class="audio-preview">
            <audio :src="fileUrl" controls :autoplay="autoPlay"></audio>
            <div class="audio-info">
              <div class="audio-waveform"></div>
              <div class="audio-duration">{{ audioDuration }}</div>
            </div>
          </div>

          <!-- 未知格式 -->
          <div v-else class="unknown-preview">
            <div class="unknown-icon">[FILE]</div>
            <p>不支持预览此文件格式</p>
            <button class="download-btn" @click="downloadFile">下载查看</button>
          </div>
        </div>

        <!-- 加载状态 -->
        <div v-if="isLoading" class="loading-overlay">
          <div class="loading-spinner"></div>
          <p>{{ loadingMessage }}</p>
        </div>

        <!-- 错误状态 -->
        <div v-if="error" class="error-overlay">
          <div class="error-icon">[ERR]</div>
          <p>{{ errorMessage }}</p>
          <button class="retry-btn" @click="retry">重试</button>
        </div>

        <!-- 批注面板 -->
        <div v-if="previewMode === 'annotate'" class="annotation-panel">
          <div class="annotation-tools">
            <button class="annotation-tool" title="文字批注" @click="addTextAnnotation">T</button>
            <button class="annotation-tool" title="高亮" @click="addHighlightAnnotation">H</button>
            <button class="annotation-tool" title="Draw" @click="addDrawAnnotation">[DRAW]</button>
            <button class="annotation-tool" title="Clear" @click="clearAnnotations">[DEL]</button>
          </div>
          <div class="annotation-list">
            <div v-for="annotation in annotations" :key="annotation.id" class="annotation-item">
              <div class="annotation-content">{{ annotation.content }}</div>
              <div class="annotation-meta">
                {{ annotation.author }} · {{ formatTime(annotation.createdAt) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧信息面板 -->
      <div class="info-sidebar">
        <div class="info-section">
          <h4>文件信息</h4>
          <div class="info-item">
            <span class="label">名称:</span>
            <span class="value">{{ currentFile?.name }}</span>
          </div>
          <div class="info-item">
            <span class="label">类型:</span>
            <span class="value">{{ currentFile?.type }}</span>
          </div>
          <div class="info-item">
            <span class="label">大小:</span>
            <span class="value">{{ formatFileSize(currentFile?.size) }}</span>
          </div>
          <div class="info-item">
            <span class="label">修改时间:</span>
            <span class="value">{{ formatDate(currentFile?.modifiedAt) }}</span>
          </div>
        </div>

        <div v-if="previewMode === 'annotate'" class="info-section">
          <h4>批注统计</h4>
          <div class="info-item">
            <span class="label">批注数:</span>
            <span class="value">{{ annotations.length }}</span>
          </div>
        </div>

        <div class="info-section">
          <h4>操作</h4>
          <button class="action-btn" @click="downloadFile">下载文件</button>
          <button class="action-btn" @click="shareFile">分享链接</button>
          <button class="action-btn" @click="openInNewTab">新窗口打开</button>
        </div>
      </div>
    </div>
  </Modal>
</template>

<script setup>
  import { ref, computed, watch } from 'vue'
  import Modal from './ui/Modal.vue'
  import { createApiClient } from '../utils/api/index'

  const props = defineProps({
    visible: { type: Boolean, default: false },
    fileId: { type: String, default: null },
    file: { type: Object, default: null },
    files: { type: Array, default: () => [] }
  })

  const emit = defineEmits(['close', 'annotate'])

  const api = createApiClient()

  // 状态
  const currentFile = ref(null)
  const fileUrl = ref('')
  const isLoading = ref(false)
  const loadingMessage = ref('加载中...')
  const error = ref(false)
  const errorMessage = ref('')
  const zoomLevel = ref(100)
  const previewMode = ref('view')
  const searchQuery = ref('')
  const autoPlay = ref(false)

  // PDF 相关
  const usePDFJS = ref(false)
  const pdfPages = ref([])

  // 代码相关
  const codeContent = ref('')
  const codeLanguage = ref('text')

  // Markdown 相关
  const markdownContent = ref('')

  // 文本相关
  const textContent = ref('')

  // 音频相关
  const audioDuration = ref('0:00')

  // 批注
  const annotations = ref([])

  // 计算属性
  const filteredFiles = computed(() => {
    if (!searchQuery.value) return props.files
    return props.files.filter(f => f.name.toLowerCase().includes(searchQuery.value.toLowerCase()))
  })

  const isImagePreview = computed(() => currentFile.value && isImage(currentFile.value))
  const isPDFPreview = computed(() => currentFile.value && isPDF(currentFile.value))
  const isCodePreview = computed(() => currentFile.value && isCode(currentFile.value))
  const isMarkdownPreview = computed(() => currentFile.value && isMarkdown(currentFile.value))
  const isTextPreview = computed(() => currentFile.value && isText(currentFile.value))
  const isVideoPreview = computed(() => currentFile.value && isVideo(currentFile.value))
  const isAudioPreview = computed(() => currentFile.value && isAudio(currentFile.value))

  const codeLanguageClass = computed(() => `language-${codeLanguage.value}`)
  const renderedMarkdown = computed(() => {
    // 简单的 Markdown 渲染（实际项目应使用 marked 库）
    return markdownContent.value
      .replace(/^# (.*$)/gim, '<h1>$1</h1>')
      .replace(/^## (.*$)/gim, '<h2>$1</h2>')
      .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
      .replace(/\*(.*)\*/gim, '<em>$1</em>')
  })

  // 文件类型检测
  function isImage(file) {
    const imageTypes = ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp']
    return imageTypes.some(ext => file.name.toLowerCase().endsWith(ext))
  }

  function isPDF(file) {
    return file.name.toLowerCase().endsWith('.pdf')
  }

  function isCode(file) {
    const codeTypes = [
      'js',
      'ts',
      'jsx',
      'tsx',
      'py',
      'java',
      'c',
      'cpp',
      'go',
      'rs',
      'rb',
      'php',
      'vue',
      'html',
      'css',
      'scss',
      'json',
      'yaml',
      'yml',
      'xml',
      'sql',
      'sh'
    ]
    return codeTypes.some(ext => file.name.toLowerCase().endsWith('.' + ext))
  }

  function isMarkdown(file) {
    return file.name.toLowerCase().endsWith('.md') || file.name.toLowerCase().endsWith('.markdown')
  }

  function isText(file) {
    return file.name.toLowerCase().endsWith('.txt') || file.name.toLowerCase().endsWith('.log')
  }

  function isVideo(file) {
    const videoTypes = ['mp4', 'webm', 'ogg', 'avi', 'mov']
    return videoTypes.some(ext => file.name.toLowerCase().endsWith(ext))
  }

  function isAudio(file) {
    const audioTypes = ['mp3', 'wav', 'ogg', 'flac', 'aac']
    return audioTypes.some(ext => file.name.toLowerCase().endsWith(ext))
  }

  // 选择文件
  async function selectFile(file) {
    currentFile.value = file
    zoomLevel.value = 100
    isLoading.value = true
    error.value = false

    try {
      if (file.url) {
        fileUrl.value = file.url
      } else if (file.id) {
        fileUrl.value = await getPreviewUrl(file.id)
      }

      await loadFileContent(file)
      isLoading.value = false
    } catch (err) {
      error.value = true
      errorMessage.value = `加载失败：${err.message}`
      isLoading.value = false
    }
  }

  // 加载文件内容
  async function loadFileContent(file) {
    if (isPDF(file)) {
      await loadPDFContent()
    } else if (isCode(file)) {
      await loadCodeContent(file)
    } else if (isMarkdown(file)) {
      await loadMarkdownContent(file)
    } else if (isText(file)) {
      await loadTextContent(file)
    } else if (isAudio(file)) {
      await loadAudioContent(file)
    }
  }

  // 获取预览 URL
  async function getPreviewUrl(fileId) {
    return `/api/v1/files/preview/${fileId}`
  }

  // 加载 PDF
  async function loadPDFContent() {
    if (usePDFJS.value) {
      // 使用 PDF.js 渲染
      await renderPDFWithPDFJS()
    }
    // 否则使用 iframe 嵌入
  }

  async function renderPDFWithPDFJS() {
    // PDF.js 渲染逻辑
    pdfPages.value = [{ num: 1 }]
  }

  // 加载代码
  async function loadCodeContent(file) {
    try {
      const response = await fetch(fileUrl.value)
      codeContent.value = await response.text()

      // 检测语言
      const ext = file.name.split('.').pop().toLowerCase()
      const languageMap = {
        js: 'javascript',
        ts: 'typescript',
        py: 'python',
        java: 'java',
        cpp: 'cpp',
        vue: 'vue',
        html: 'html',
        css: 'css',
        json: 'json',
        yaml: 'yaml'
      }
      codeLanguage.value = languageMap[ext] || 'text'
    } catch (err) {
      console.error('加载代码失败:', err)
    }
  }

  // 加载 Markdown
  async function loadMarkdownContent(file) {
    try {
      const response = await fetch(fileUrl.value)
      markdownContent.value = await response.text()
    } catch (err) {
      console.error('加载 Markdown 失败:', err)
    }
  }

  // 加载文本
  async function loadTextContent(file) {
    try {
      const response = await fetch(fileUrl.value)
      textContent.value = await response.text()
    } catch (err) {
      console.error('加载文本失败:', err)
    }
  }

  // 加载音频
  async function loadAudioContent(file) {
    try {
      const audio = new Audio(fileUrl.value)
      audio.addEventListener('loadedmetadata', () => {
        const minutes = Math.floor(audio.duration / 60)
        const seconds = Math.floor(audio.duration % 60)
        audioDuration.value = `${minutes}:${seconds.toString().padStart(2, '0')}`
      })
    } catch (err) {
      console.error('加载音频失败:', err)
    }
  }

  // 工具栏操作
  function zoomIn() {
    if (zoomLevel.value < 200) zoomLevel.value += 25
  }

  function zoomOut() {
    if (zoomLevel.value > 50) zoomLevel.value -= 25
  }

  function resetZoom() {
    zoomLevel.value = 100
  }

  function toggleFullscreen() {
    const container = document.querySelector('.preview-main')
    if (document.fullscreenElement) {
      document.exitFullscreen()
    } else {
      container.requestFullscreen()
    }
  }

  async function downloadFile() {
    const link = document.createElement('a')
    link.href = fileUrl.value
    link.download = currentFile.value?.name || 'download'
    link.click()
  }

  function shareFile() {
    const shareUrl = `${window.location.origin}/preview/${currentFile.value?.id}`
    navigator.clipboard.writeText(shareUrl)
    alert('分享链接已复制到剪贴板')
  }

  function copyCode() {
    navigator.clipboard.writeText(codeContent.value)
    alert('代码已复制到剪贴板')
  }

  function openInNewTab() {
    window.open(fileUrl.value, '_blank')
  }

  // 批注功能
  function addTextAnnotation() {
    emit('annotate', { type: 'text', fileId: currentFile.value?.id })
  }

  function addHighlightAnnotation() {
    emit('annotate', { type: 'highlight', fileId: currentFile.value?.id })
  }

  function addDrawAnnotation() {
    emit('annotate', { type: 'draw', fileId: currentFile.value?.id })
  }

  function clearAnnotations() {
    annotations.value = []
  }

  // 工具函数
  function formatFileSize(bytes) {
    if (!bytes) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
  }

  function formatDate(date) {
    if (!date) return '-'
    return new Date(date).toLocaleString('zh-CN')
  }

  function formatTime(date) {
    return new Date(date).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }

  function retry() {
    if (currentFile.value) {
      selectFile(currentFile.value)
    }
  }

  function onImageLoad() {
    console.log('图片加载完成')
  }

  function onImageError() {
    error.value = true
    errorMessage.value = '图片加载失败'
  }

  // 监听 props 变化
  watch(
    () => props.fileId,
    newId => {
      if (newId && props.files.length > 0) {
        const file = props.files.find(f => f.id === newId)
        if (file) selectFile(file)
      }
    },
    { immediate: true }
  )

  watch(
    () => props.file,
    newFile => {
      if (newFile) {
        selectFile(newFile)
      }
    },
    { immediate: true }
  )

  watch(
    () => props.visible,
    newVal => {
      if (newVal && props.files.length > 0 && !currentFile.value) {
        selectFile(props.files[0])
      }
    }
  )
</script>

<style scoped>
  .file-preview-center {
    display: flex;
    height: calc(100vh - 120px);
    background: var(--bg-primary);
  }

  .file-sidebar {
    width: 280px;
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    background: var(--bg-secondary);
  }

  .sidebar-header {
    padding: var(--spacing-3);
    border-bottom: 1px solid var(--border-color);
  }

  .search-input {
    width: 100%;
    padding: var(--spacing-2) var(--spacing-3);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
  }

  .file-list {
    flex: 1;
    overflow-y: auto;
  }

  .file-item {
    display: flex;
    align-items: center;
    gap: var(--spacing-3);
    padding: var(--spacing-3);
    cursor: pointer;
    border-bottom: 1px solid var(--border-color);
    transition: background var(--transition-base);
  }

  .file-item:hover {
    background: var(--bg-tertiary);
  }

  .file-item.active {
    background: var(--color-blue-50);
    border-left: 3px solid var(--color-blue-600);
  }

  .file-icon {
    color: var(--text-secondary);
  }

  .file-info {
    flex: 1;
    overflow: hidden;
  }

  .file-name {
    font-size: var(--text-sm);
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .file-meta {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    margin-top: var(--spacing-1);
  }

  .preview-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .preview-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--spacing-2) var(--spacing-3);
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-primary);
  }

  .toolbar-group {
    display: flex;
    gap: var(--spacing-2);
  }

  .toolbar-btn {
    padding: var(--spacing-2);
    border: 1px solid var(--border-color);
    background: var(--bg-primary);
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all var(--transition-base);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .toolbar-btn:hover {
    background: var(--bg-secondary);
    border-color: var(--color-blue-400);
  }

  .toolbar-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .zoom-text {
    font-size: var(--text-xs);
    color: var(--text-primary);
  }

  .mode-select {
    padding: var(--spacing-2) var(--spacing-3);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
  }

  .preview-content {
    flex: 1;
    overflow: auto;
    background: var(--bg-tertiary);
    padding: var(--spacing-4);
    position: relative;
  }

  .image-preview,
  .pdf-preview,
  .code-preview,
  .markdown-preview,
  .text-preview,
  .video-preview,
  .audio-preview {
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .image-preview img {
    max-width: 100%;
    transition: transform var(--transition-base);
  }

  .pdf-frame {
    width: 100%;
    height: 800px;
    border: none;
  }

  .code-preview,
  .markdown-preview,
  .text-preview {
    width: 100%;
    max-width: 1000px;
  }

  .code-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--spacing-2) var(--spacing-3);
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    margin-bottom: var(--spacing-2);
  }

  .code-language {
    font-size: var(--text-sm);
    color: var(--text-secondary);
    text-transform: uppercase;
  }

  .copy-btn {
    padding: var(--spacing-1) var(--spacing-2);
    background: var(--color-blue-600);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-size: var(--text-xs);
    cursor: pointer;
  }

  .code-content {
    width: 100%;
    overflow-x: auto;
    padding: var(--spacing-3);
    background: var(--bg-primary);
    border-radius: var(--radius-md);
  }

  .markdown-content {
    padding: var(--spacing-4);
    background: var(--bg-primary);
    border-radius: var(--radius-md);
    max-width: 100%;
  }

  .text-preview pre,
  .code-content code {
    font-family: 'JetBrains Mono', monospace;
    font-size: var(--text-sm);
    line-height: 1.6;
  }

  video,
  audio {
    max-width: 100%;
    border-radius: var(--radius-lg);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  }

  .unknown-preview {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--spacing-8);
    text-align: center;
  }

  .unknown-icon {
    font-size: 64px;
    margin-bottom: var(--spacing-4);
  }

  .loading-overlay,
  .error-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.9);
    backdrop-filter: blur(4px);
  }

  .error-overlay {
    background: rgba(255, 0, 0, 0.1);
  }

  .loading-spinner,
  .error-icon {
    font-size: 48px;
    margin-bottom: var(--spacing-4);
  }

  .retry-btn {
    padding: var(--spacing-2) var(--spacing-4);
    background: var(--color-blue-600);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    cursor: pointer;
  }

  .annotation-panel {
    position: absolute;
    right: 0;
    top: 60px;
    width: 300px;
    bottom: 0;
    background: var(--bg-primary);
    border-left: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
  }

  .annotation-tools {
    display: flex;
    padding: var(--spacing-2);
    border-bottom: 1px solid var(--border-color);
    gap: var(--spacing-2);
  }

  .annotation-tool {
    padding: var(--spacing-2);
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    cursor: pointer;
  }

  .annotation-list {
    flex: 1;
    overflow-y: auto;
    padding: var(--spacing-3);
  }

  .annotation-item {
    padding: var(--spacing-3);
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    margin-bottom: var(--spacing-2);
  }

  .annotation-content {
    font-size: var(--text-sm);
    color: var(--text-primary);
    margin-bottom: var(--spacing-1);
  }

  .annotation-meta {
    font-size: var(--text-xs);
    color: var(--text-secondary);
  }

  .info-sidebar {
    width: 240px;
    border-left: 1px solid var(--border-color);
    padding: var(--spacing-4);
    background: var(--bg-secondary);
    overflow-y: auto;
  }

  .info-section {
    margin-bottom: var(--spacing-4);
  }

  .info-section h4 {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: var(--spacing-3);
  }

  .info-item {
    display: flex;
    justify-content: space-between;
    padding: var(--spacing-2) 0;
    font-size: var(--text-sm);
    border-bottom: 1px solid var(--border-color);
  }

  .info-item .label {
    color: var(--text-secondary);
  }

  .info-item .value {
    color: var(--text-primary);
    text-align: right;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .action-btn {
    width: 100%;
    padding: var(--spacing-2) var(--spacing-3);
    margin-bottom: var(--spacing-2);
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
    cursor: pointer;
    transition: all var(--transition-base);
  }

  .action-btn:hover {
    border-color: var(--color-blue-400);
    background: var(--color-blue-50);
  }
</style>
