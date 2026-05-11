<template>
  <div v-if="visible" class="file-manager-overlay" @click="close">
    <div class="file-manager-window" @click.stop>
      <!-- 窗口头部 -->
      <div class="file-manager-header">
        <h3 class="file-manager-title">文件管理</h3>
        <div class="file-manager-actions">
          <button class="icon-btn" title="刷新" @click="refreshFiles">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <polyline points="23 4 23 10 17 10"></polyline>
              <polyline points="1 20 1 14 7 14"></polyline>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
          </button>
          <button class="icon-btn" title="关闭" @click="close">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
      </div>

      <!-- 上传区域 -->
      <div class="upload-section">
        <div
          class="upload-area"
          :class="{ 'drag-over': isDragOver }"
          @dragover.prevent="isDragOver = true"
          @dragleave.prevent="isDragOver = false"
          @drop.prevent="handleDrop"
        >
          <input
            ref="fileInput"
            type="file"
            class="file-input"
            multiple
            accept="*/*,.jpg,.jpeg,.png,.gif,.webp,.svg,.bmp"
            @change="handleFileSelect"
          />
          <div class="upload-content">
            <svg
              class="upload-icon"
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="17 8 12 3 7 8"></polyline>
              <line x1="12" y1="3" x2="12" y2="15"></line>
            </svg>
            <p class="upload-text">点击或拖拽文件到此处上传</p>
            <p class="upload-hint">支持代码、文档、图片等格式，最大 100MB</p>
          </div>
        </div>
      </div>

      <!-- 筛选和搜索 -->
      <div class="filter-section">
        <div class="search-box">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input
            v-model="searchKeyword"
            type="text"
            placeholder="搜索文件..."
            class="search-input"
            @keyup.enter="searchFiles"
          />
        </div>
        <div class="filter-actions">
          <select v-model="fileType" class="type-select" @change="filterFiles">
            <option value="">全部类型</option>
            <option value="code">代码文件</option>
            <option value="image">图片</option>
            <option value="document">文档</option>
            <option value="archive">压缩包</option>
          </select>
        </div>
      </div>

      <!-- 文件列表 -->
      <div class="file-list-section">
        <div v-if="loading" class="loading-state">
          <div class="loading-spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else-if="files.length === 0" class="empty-state">
          <svg
            width="64"
            height="64"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path
              d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"
            ></path>
          </svg>
          <p>暂无文件</p>
          <p class="empty-hint">上传第一个文件开始使用</p>
        </div>

        <div v-else class="file-list">
          <div v-for="file in filteredFiles" :key="file.id" class="file-item">
            <div class="file-icon">
              <svg
                v-if="isCodeFile(file.filename)"
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="16 18 22 12 16 6"></polyline>
                <polyline points="8 6 2 12 8 18"></polyline>
              </svg>
              <svg
                v-else-if="isImageFile(file.filename)"
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                <polyline points="21 15 16 10 5 21"></polyline>
              </svg>
              <svg
                v-else
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
              </svg>
            </div>
            <div class="file-info">
              <div class="file-name" :title="file.filename">{{ file.filename }}</div>
              <div class="file-meta">
                <span class="file-size">{{ formatFileSize(file.file_size) }}</span>
                <span class="file-date">{{ formatDate(file.created_at) }}</span>
              </div>
            </div>
            <div class="file-actions">
              <button class="action-btn download" title="下载" @click="downloadFile(file.id)">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="7 10 12 15 17 10"></polyline>
                  <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
              </button>
              <button class="action-btn info" title="详情" @click="showFileDetail(file)">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="12" y1="16" x2="12" y2="12"></line>
                  <line x1="12" y1="8" x2="12.01" y2="8"></line>
                </svg>
              </button>
              <button class="action-btn delete" title="删除" @click="confirmDelete(file)">
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path
                    d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
                  ></path>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- 文件详情对话框 -->
        <div
          v-if="showingDetail && selectedFile"
          class="file-detail-overlay"
          @click="closeFileDetail"
        >
          <div class="file-detail-dialog" @click.stop>
            <div class="file-detail-header">
              <h3>文件详情</h3>
              <button class="close-btn" @click="closeFileDetail">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>
            <div class="file-detail-content">
              <div class="file-icon-large">
                <svg
                  v-if="isCodeFile(selectedFile.filename)"
                  width="64"
                  height="64"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                >
                  <polyline points="16 18 22 12 16 6"></polyline>
                  <polyline points="8 6 2 12 8 18"></polyline>
                </svg>
                <svg
                  v-else-if="isImageFile(selectedFile.filename)"
                  width="64"
                  height="64"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                >
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                  <circle cx="8.5" cy="8.5" r="1.5"></circle>
                  <polyline points="21 15 16 10 5 21"></polyline>
                </svg>
                <svg
                  v-else
                  width="64"
                  height="64"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                >
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                  <line x1="16" y1="13" x2="8" y2="13"></line>
                  <line x1="16" y1="17" x2="8" y2="17"></line>
                </svg>
              </div>
              <div class="file-info-grid">
                <div class="info-item">
                  <span class="info-label">文件名:</span>
                  <span class="info-value">{{ selectedFile.filename }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">文件大小:</span>
                  <span class="info-value">{{
                    formatFileSize(selectedFile.file_size || selectedFile.size)
                  }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">MIME 类型:</span>
                  <span class="info-value">{{
                    selectedFile.content_type || selectedFile.mime_type || '未知'
                  }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">创建时间:</span>
                  <span class="info-value">{{ formatDate(selectedFile.created_at) }}</span>
                </div>
                <div v-if="selectedFile.uploaded_at" class="info-item">
                  <span class="info-label">上传时间:</span>
                  <span class="info-value">{{ formatDate(selectedFile.uploaded_at) }}</span>
                </div>
                <div v-if="selectedFile.id" class="info-item">
                  <span class="info-label">文件 ID:</span>
                  <span class="info-value">{{ selectedFile.id }}</span>
                </div>
                <div v-if="selectedFile.conversation_id" class="info-item">
                  <span class="info-label">对话 ID:</span>
                  <span class="info-value">{{ selectedFile.conversation_id }}</span>
                </div>
                <div v-if="selectedFile.storage_path" class="info-item">
                  <span class="info-label">存储路径:</span>
                  <span class="info-value file-path">{{ selectedFile.storage_path }}</span>
                </div>
              </div>
              <div v-if="selectedFileDetails" class="file-extended-info">
                <h4>详细信息</h4>
                <pre class="json-viewer">{{ JSON.stringify(selectedFileDetails, null, 2) }}</pre>
              </div>
            </div>
          </div>
          <div class="file-detail-actions">
            <button class="btn-primary" @click="downloadFile(selectedFile.id)">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
              下载文件
            </button>
            <button class="btn-secondary" @click="closeFileDetail">关闭</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed, onMounted } from 'vue'
  import { api } from '@/utils/api/index'

  const props = defineProps({
    visible: { type: Boolean, default: false }
  })

  const emit = defineEmits(['close', 'file-select'])

  // 状态管理
  const loading = ref(false)
  const files = ref([])
  const filteredFiles = ref([])
  const searchKeyword = ref('')
  const fileType = ref('')
  const currentPage = ref(1)
  const totalPages = ref(1)
  const isDragOver = ref(false)
  const showingDetail = ref(false)
  const selectedFile = ref(null)
  const selectedFileDetails = ref(null)

  // 加载文件列表
  const loadFiles = async () => {
    loading.value = true
    try {
      const data = await api.getFileList({
        page: currentPage.value,
        page_size: 20,
        keyword: searchKeyword.value
      })

      if (data && data.files) {
        files.value = data.files
        filteredFiles.value = data.files
        totalPages.value = Math.ceil(data.total / data.page_size)
      }
    } catch (error) {
      console.error('加载文件列表失败:', error)
    } finally {
      loading.value = false
    }
  }

  // 刷新文件列表
  const refreshFiles = () => {
    currentPage.value = 1
    searchKeyword.value = ''
    fileType.value = ''
    loadFiles()
  }

  // 搜索文件
  const searchFiles = () => {
    currentPage.value = 1
    loadFiles()
  }

  // 筛选文件类型
  const filterFiles = () => {
    if (!fileType.value) {
      filteredFiles.value = files.value
    } else {
      filteredFiles.value = files.value.filter(file => {
        const ext = getExtension(file.filename)
        switch (fileType.value) {
          case 'code':
            return [
              '.py',
              '.js',
              '.ts',
              '.java',
              '.cpp',
              '.go',
              '.rs',
              '.html',
              '.css',
              '.vue'
            ].includes(ext)
          case 'image':
            return ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'].includes(ext)
          case 'document':
            return ['.pdf', '.doc', '.docx', '.txt', '.md'].includes(ext)
          case 'archive':
            return ['.zip', '.tar', '.gz', '.rar', '.7z'].includes(ext)
          default:
            return true
        }
      })
    }
  }

  // 文件类型判断
  const isCodeFile = filename => {
    const codeExts = ['.py', '.js', '.ts', '.java', '.cpp', '.go', '.rs', '.html', '.css', '.vue']
    return codeExts.some(ext => filename.toLowerCase().endsWith(ext))
  }

  const isImageFile = filename => {
    const imageExts = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']
    return imageExts.some(ext => filename.toLowerCase().endsWith(ext))
  }

  // 获取文件扩展名
  const getExtension = filename => {
    const parts = filename.toLowerCase().split('.')
    return parts.length > 1 ? '.' + parts.pop() : ''
  }

  // 格式化文件大小
  const formatFileSize = bytes => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
  }

  // 格式化日期
  const formatDate = dateString => {
    const date = new Date(dateString)
    const now = new Date()
    const diff = now - date
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(minutes / 60)
    const days = Math.floor(hours / 24)

    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN')
  }

  // 处理文件选择
  const handleFileSelect = event => {
    const selectedFiles = event.target.files
    uploadFiles(Array.from(selectedFiles))
  }

  // 处理拖拽上传
  const handleDrop = event => {
    isDragOver.value = false
    const files = event.dataTransfer.files
    uploadFiles(Array.from(files))
  }

  // 显示文件详情
  const showFileDetail = async file => {
    selectedFile.value = file
    selectedFileDetails.value = null
    showingDetail.value = true

    // 获取详细文件信息
    try {
      const details = await api.getFile(file.id)
      if (details) {
        selectedFileDetails.value = details
        // 合并详细信息到 selectedFile
        selectedFile.value = { ...file, ...details }
      }
    } catch (error) {
      console.error('获取文件详情失败:', error)
    }
  }

  // 关闭文件详情
  const closeFileDetail = () => {
    showingDetail.value = false
    selectedFile.value = null
    selectedFileDetails.value = null
  }

  // 上传文件（支持分片上传）
  const uploadFiles = async fileList => {
    if (fileList.length === 0) return

    for (const file of fileList) {
      try {
        loading.value = true

        // 大于 10MB 的文件使用分片上传
        const CHUNK_SIZE = 10 * 1024 * 1024 // 10MB
        let result

        if (file.size > CHUNK_SIZE) {
          // 分片上传
          console.log(`文件 ${file.name} 大于 10MB，使用分片上传`)
          result = await uploadFileInChunks(file)
        } else {
          // 普通上传
          console.log(`文件 ${file.name} 小于 10MB，使用普通上传`)
          result = await api.uploadFile(file)
        }

        if (result) {
          console.log(`文件上传成功：${file.name}`)
        }
      } catch (error) {
        console.error(`文件上传失败：${file.name}`, error)
        alert(`文件 ${file.name} 上传失败：${error.message}`)
      }
    }

    await loadFiles()
    emit('file-select', files.value[0])
  }

  // 分片上传
  const uploadFileInChunks = async file => {
    const CHUNK_SIZE = 10 * 1024 * 1024 // 10MB
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE)

    try {
      // 1. 初始化分片上传
      const initResult = await api.initMultipartUpload(file.name, file.size)
      if (!initResult || !initResult.file_id) {
        throw new Error('初始化分片上传失败')
      }

      const fileId = initResult.file_id

      // 2. 上传所有分片
      for (let i = 0; i < totalChunks; i++) {
        const start = i * CHUNK_SIZE
        const end = Math.min(start + CHUNK_SIZE, file.size)
        const chunk = file.slice(start, end)

        console.log(`上传分片 ${i + 1}/${totalChunks}`)
        const uploadResult = await api.uploadChunk(fileId, i, chunk)

        if (!uploadResult) {
          throw new Error(`分片 ${i} 上传失败`)
        }
      }

      // 3. 合并分片
      const mergeResult = await api.mergeChunks(fileId)
      if (!mergeResult) {
        throw new Error('合并分片失败')
      }

      return mergeResult
    } catch (error) {
      console.error('分片上传失败:', error)
      throw error
    }
  }

  // 下载文件
  const downloadFile = async fileId => {
    try {
      const response = await api.downloadFile(fileId)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download =
        response.headers.get('Content-Disposition')?.split('filename=')[1]?.replace(/"/g, '') ||
        'download'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('下载失败:', error)
    }
  }

  // 删除文件确认
  const confirmDelete = file => {
    if (confirm(`确定要删除文件 "${file.filename}" 吗？`)) {
      deleteFile(file.id)
    }
  }

  // 删除文件
  const deleteFile = async fileId => {
    try {
      const success = await api.deleteFile(fileId)
      if (success) {
        await loadFiles()
      }
    } catch (error) {
      console.error('删除失败:', error)
    }
  }

  // 分页导航
  const goToPage = page => {
    if (page < 1 || page > totalPages.value) return
    currentPage.value = page
    loadFiles()
  }

  // 关闭窗口
  const close = () => {
    emit('close')
  }

  // 生命周期
  onMounted(() => {
    if (props.visible) {
      loadFiles()
    }
  })
</script>

<style scoped>
  .file-manager-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    backdrop-filter: blur(4px);
  }

  .file-manager-window {
    width: 90%;
    max-width: 800px;
    height: 600px;
    background: white;
    border-radius: 12px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .file-manager-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
  }

  .file-manager-title {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
  }

  .file-manager-actions {
    display: flex;
    gap: 8px;
  }

  .icon-btn {
    padding: 6px;
    background: rgba(255, 255, 255, 0.2);
    border: none;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .icon-btn:hover {
    background: rgba(255, 255, 255, 0.3);
  }

  .upload-section {
    padding: 20px;
    border-bottom: 1px solid #e8e8e8;
  }

  .upload-area {
    border: 2px dashed #ddd;
    border-radius: 8px;
    padding: 30px;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s;
  }

  .upload-area:hover,
  .upload-area.drag-over {
    border-color: #0d9488;
    background: rgba(102, 126, 234, 0.05);
  }

  .file-input {
    display: none;
  }

  .upload-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }

  .upload-icon {
    color: #0d9488;
  }

  .upload-text {
    margin: 0;
    font-size: 16px;
    color: #333;
    font-weight: 500;
  }

  .upload-hint {
    margin: 0;
    font-size: 13px;
    color: #999;
  }

  .filter-section {
    display: flex;
    gap: 12px;
    padding: 12px 20px;
    background: var(--bg-secondary);
  }

  .search-box {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: white;
    border: 1px solid #ddd;
    border-radius: 6px;
  }

  .search-input {
    border: none;
    outline: none;
    flex: 1;
    font-size: 14px;
  }

  .type-select {
    padding: 8px 12px;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 14px;
    cursor: pointer;
  }

  .file-list-section {
    flex: 1;
    overflow-y: auto;
    padding: 0 20px;
  }

  .loading-state,
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 200px;
    gap: 12px;
    color: #999;
  }

  .loading-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #f3f3f3;
    border-top: 3px solid #0d9488;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  .empty-hint {
    font-size: 13px;
    color: #bbb;
  }

  .file-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px 0;
  }

  .file-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    background: white;
    border: 1px solid #e8e8e8;
    border-radius: 8px;
    transition: all 0.2s;
  }

  .file-item:hover {
    background: var(--bg-secondary);
    border-color: #0d9488;
    transform: translateX(4px);
  }

  .file-icon {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f0f2f5;
    border-radius: 8px;
    color: #0d9488;
  }

  .file-info {
    flex: 1;
    min-width: 0;
  }

  .file-name {
    font-size: 14px;
    font-weight: 500;
    color: #333;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 4px;
  }

  .file-meta {
    display: flex;
    gap: 12px;
    font-size: 12px;
    color: #999;
  }

  .file-actions {
    display: flex;
    gap: 8px;
  }

  .action-btn {
    padding: 6px;
    background: white;
    border: 1px solid #ddd;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .action-btn.download:hover {
    border-color: #0d9488;
    color: #0d9488;
    background: #f6f9ff;
  }

  .action-btn.delete:hover {
    border-color: #f5222d;
    color: #f5222d;
    background: #fff2f0;
  }

  .pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 12px;
    padding: 16px;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
  }

  .page-btn {
    padding: 6px 10px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .page-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .page-btn:hover:not(:disabled) {
    border-color: var(--color-primary);
    color: var(--color-primary);
  }

  .page-info {
    font-size: 14px;
    color: var(--text-secondary);
  }

  /* 文件详情对话框样式 */
  .file-detail-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10001;
    backdrop-filter: blur(4px);
  }

  .file-detail-dialog {
    width: 90%;
    max-width: 600px;
    max-height: 80vh;
    background: white;
    border-radius: 12px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .file-detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem 2rem;
    border-bottom: 1px solid #e9ecef;
  }

  .file-detail-header h3 {
    margin: 0;
    font-size: 1.25rem;
    color: #212529;
  }

  .close-btn {
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: #6c757d;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: var(--bg-secondary);
    color: #212529;
  }

  .file-detail-content {
    padding: 2rem;
    overflow-y: auto;
    flex: 1;
  }

  .file-icon-large {
    display: flex;
    justify-content: center;
    align-items: center;
    margin-bottom: 1.5rem;
    padding: 2rem;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    border-radius: 12px;
    color: white;
  }

  .file-info-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  .info-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .info-label {
    font-size: 0.875rem;
    color: #6c757d;
    font-weight: 500;
  }

  .info-value {
    font-size: 1rem;
    color: #212529;
    word-break: break-word;
  }

  .info-value.file-path {
    font-family: 'Courier New', monospace;
    font-size: 0.875rem;
    background: var(--bg-secondary);
    padding: 0.5rem;
    border-radius: 4px;
  }

  .file-extended-info {
    margin-top: 1.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid #e9ecef;
  }

  .file-extended-info h4 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    color: #212529;
  }

  .json-viewer {
    background: var(--bg-secondary);
    padding: 1rem;
    border-radius: 6px;
    font-family: 'Courier New', monospace;
    font-size: 0.875rem;
    overflow-x: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
    max-height: 300px;
    overflow-y: auto;
  }

  .file-detail-actions {
    display: flex;
    gap: 1rem;
    padding: 1.5rem 2rem;
    border-top: 1px solid #e9ecef;
  }

  .btn-primary {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s;
  }

  .btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
  }

  .btn-secondary {
    flex: 1;
    padding: 0.75rem 1.5rem;
    background: var(--bg-secondary);
    color: #212529;
    border: 1px solid #dee2e6;
    border-radius: 6px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s;
  }

  .btn-secondary:hover {
    background: #e9ecef;
    border-color: #adb5bd;
  }
</style>
