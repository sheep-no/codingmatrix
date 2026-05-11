<template>
  <div class="agent-project-actions">
    <div class="actions-header">
      <h4>项目管理</h4>
    </div>

    <div class="actions-content">
      <!-- 上传压缩包 -->
      <div class="upload-section">
        <h5>上传项目压缩包</h5>
        <div
          class="upload-drop-zone"
          :class="{ 'is-dragging': isDragging, 'is-uploading': uploading }"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
          @click="triggerFileInput"
        >
          <input
            ref="fileInput"
            type="file"
            accept=".zip"
            class="hidden-input"
            @change="handleFileSelect"
          />
          <svg v-if="!uploading" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <div v-if="uploading" class="upload-spinner">
            <div class="spinner-dot"></div>
            <div class="spinner-dot"></div>
            <div class="spinner-dot"></div>
          </div>
          <span v-if="!uploading">拖拽 .zip 文件到此处，或点击上传</span>
          <span v-else>上传中...</span>
        </div>
        <div v-if="uploadProgress > 0 && uploadProgress < 100" class="upload-progress-bar">
          <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
        </div>
        <div v-if="uploadError" class="upload-error">{{ uploadError }}</div>
        <div v-if="uploadSuccess" class="upload-success">{{ uploadSuccess }}</div>
        <p class="upload-hint">支持 .zip 格式，最大 50MB，自动解压到用户项目目录</p>
      </div>

      <!-- 上传的项目 -->
      <div class="uploads-section">
        <div class="uploads-header">
          <h5>我的项目 ({{ uploadedProjects.length }})</h5>
          <button class="btn-refresh" @click="$emit('refreshUploads')" title="刷新">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="23 4 23 10 17 10"/>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
          </button>
        </div>
        <div v-if="uploadedProjects.length === 0" class="empty-uploads">
          暂无上传项目
        </div>
        <div v-else class="uploads-list">
          <div
            v-for="project in uploadedProjects"
            :key="project.project_name"
            class="upload-item"
            @click="$emit('loadUploaded', project.project_path)"
          >
            <div class="item-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <div class="item-info">
              <span class="item-name">{{ project.project_name }}</span>
              <span class="item-meta">{{ project.file_count }} 个文件 / {{ formatSize(project.size_bytes) }}</span>
            </div>
            <button class="btn-delete" title="删除" @click.stop="$emit('deleteUploaded', project.project_name)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 保存的项目 -->
      <div v-if="savedProjects.length > 0" class="saved-section">
        <h5>已保存的项目 ({{ savedProjects.length }})</h5>
        <div class="saved-list">
          <div
            v-for="project in savedProjects"
            :key="project.id"
            class="saved-item"
            @click="$emit('load', project.id)"
          >
            <div class="item-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <div class="item-info">
              <span class="item-name">{{ project.name }}</span>
              <span class="item-date">{{ formatDate(project.created_at) }}</span>
            </div>
            <button class="btn-delete" title="删除" @click.stop="$emit('deleteProject', project.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 保存当前项目 -->
      <div class="save-section">
        <h5>保存当前项目</h5>
        <div class="save-form">
          <input
            v-model="projectName"
            placeholder="项目名称..."
            class="input-field"
            @keydown.enter="saveProject"
          />
          <button :disabled="!projectName.trim() || saving" class="btn-save" @click="saveProject">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>

      <!-- 快速操作 -->
      <div class="quick-actions">
        <h5>快速操作</h5>
        <div class="action-buttons">
          <button class="action-btn" @click="$emit('analyzeComplexity')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="20" x2="18" y2="10"/>
              <line x1="12" y1="20" x2="12" y2="4"/>
              <line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
            <span>复杂度分析</span>
          </button>
          <button class="action-btn" @click="$emit('orchestrate')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="2" width="20" height="8" rx="2"/>
              <rect x="2" y="14" width="20" height="8" rx="2"/>
              <line x1="6" y1="6" x2="6" y2="6.01"/>
              <line x1="6" y1="18" x2="6" y2="18.01"/>
            </svg>
            <span>项目编排</span>
          </button>
          <button class="action-btn" @click="$emit('downloadProject')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            <span>下载项目</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref } from 'vue'

  defineProps({
    savedProjects: { type: Array, default: () => [] },
    uploadedProjects: { type: Array, default: () => [] }
  })

  defineEmits([
    'load', 'deleteProject', 'save', 'analyzeComplexity', 'orchestrate', 'downloadProject',
    'uploadZip', 'loadUploaded', 'deleteUploaded', 'refreshUploads'
  ])

  const projectName = ref('')
  const saving = ref(false)
  const isDragging = ref(false)
  const uploading = ref(false)
  const uploadProgress = ref(0)
  const uploadError = ref('')
  const uploadSuccess = ref('')
  const fileInput = ref(null)

  function saveProject() {
    if (!projectName.value.trim() || saving.value) return
    saving.value = true
    const emit = defineEmits([
      'load', 'deleteProject', 'save', 'analyzeComplexity', 'orchestrate', 'downloadProject',
      'uploadZip', 'loadUploaded', 'deleteUploaded', 'refreshUploads'
    ])
    emit('save', projectName.value.trim())
    projectName.value = ''
    saving.value = false
  }

  function formatDate(ts) {
    if (!ts) return ''
    return new Date(ts).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  function triggerFileInput() {
    if (!uploading.value && fileInput.value) {
      fileInput.value.click()
    }
  }

  function handleFileSelect(event) {
    const files = event.target.files
    if (files && files.length > 0) {
      uploadFile(files[0])
    }
    event.target.value = ''
  }

  function handleDrop(event) {
    isDragging.value = false
    const files = event.dataTransfer.files
    if (files && files.length > 0) {
      uploadFile(files[0])
    }
  }

  function uploadFile(file) {
    const emit = defineEmits([
      'load', 'deleteProject', 'save', 'analyzeComplexity', 'orchestrate', 'downloadProject',
      'uploadZip', 'loadUploaded', 'deleteUploaded', 'refreshUploads'
    ])
    if (!file.name.toLowerCase().endsWith('.zip')) {
      uploadError.value = '仅支持 .zip 格式文件'
      uploadSuccess.value = ''
      return
    }
    if (file.size > 50 * 1024 * 1024) {
      uploadError.value = '文件大小超过 50MB 限制'
      uploadSuccess.value = ''
      return
    }

    uploadError.value = ''
    uploadSuccess.value = ''
    uploading.value = true
    uploadProgress.value = 10

    emit('uploadZip', file, {
      onProgress: (p) => { uploadProgress.value = p },
      onSuccess: (msg) => {
        uploading.value = false
        uploadProgress.value = 100
        uploadSuccess.value = msg
        setTimeout(() => { uploadSuccess.value = ''; uploadProgress.value = 0 }, 3000)
      },
      onError: (msg) => {
        uploading.value = false
        uploadProgress.value = 0
        uploadError.value = msg
      }
    })
  }
</script>

<style scoped>
  .agent-project-actions {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-secondary, #16213e);
  }

  .actions-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
  }

  .actions-header h4 { margin: 0; font-size: 14px; }

  .actions-content {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

  h5 {
    margin: 0 0 12px 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-secondary, #9ca3af);
  }

  /* 上传区域 */
  .upload-section { margin-bottom: 24px; }

  .upload-drop-zone {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 24px 16px;
    border: 2px dashed var(--border-color, #2d3748);
    border-radius: 12px;
    background: var(--bg-tertiary, #1f2937);
    cursor: pointer;
    transition: all 0.2s;
    min-height: 100px;
  }

  .upload-drop-zone:hover {
    border-color: var(--accent-color, #4f46e5);
    background: var(--accent-muted, #4f46e511);
  }

  .upload-drop-zone.is-dragging {
    border-color: var(--accent-color, #4f46e5);
    background: var(--accent-muted, #4f46e522);
    transform: scale(1.02);
  }

  .upload-drop-zone.is-uploading {
    cursor: not-allowed;
    opacity: 0.8;
  }

  .upload-drop-zone svg {
    width: 32px;
    height: 32px;
    color: var(--text-secondary, #9ca3af);
  }

  .upload-drop-zone span {
    font-size: 13px;
    color: var(--text-secondary, #9ca3af);
  }

  .hidden-input { display: none; }

  .upload-spinner {
    display: flex;
    gap: 6px;
  }

  .spinner-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent-color, #4f46e5);
    animation: bounce 1.2s infinite;
  }

  .spinner-dot:nth-child(2) { animation-delay: 0.2s; }
  .spinner-dot:nth-child(3) { animation-delay: 0.4s; }

  @keyframes bounce {
    0%, 80%, 100% { transform: translateY(0); opacity: 0.3; }
    40% { transform: translateY(-8px); opacity: 1; }
  }

  .upload-progress-bar {
    height: 4px;
    background: var(--bg-tertiary, #1f2937);
    border-radius: 2px;
    margin-top: 8px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: var(--accent-color, #4f46e5);
    border-radius: 2px;
    transition: width 0.3s;
  }

  .upload-error {
    margin-top: 8px;
    padding: 6px 10px;
    font-size: 12px;
    color: #ef4444;
    background: #ef444411;
    border-radius: 4px;
  }

  .upload-success {
    margin-top: 8px;
    padding: 6px 10px;
    font-size: 12px;
    color: #10b981;
    background: #10b98111;
    border-radius: 4px;
  }

  .upload-hint {
    margin: 8px 0 0;
    font-size: 11px;
    color: var(--text-secondary, #9ca3af);
    text-align: center;
  }

  /* 上传的项目 */
  .uploads-section { margin-bottom: 24px; }

  .uploads-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  .uploads-header h5 { margin: 0; }

  .btn-refresh {
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-refresh:hover { background: var(--bg-hover, #374151); }
  .btn-refresh svg { width: 14px; height: 14px; }

  .empty-uploads {
    padding: 16px;
    text-align: center;
    font-size: 12px;
    color: var(--text-secondary, #9ca3af);
    background: var(--bg-tertiary, #1f2937);
    border-radius: 8px;
  }

  .uploads-list { display: flex; flex-direction: column; gap: 8px; }

  .upload-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: 8px;
    background: var(--bg-tertiary, #1f2937);
    cursor: pointer;
    transition: background 0.15s;
  }

  .upload-item:hover { background: var(--bg-hover, #374151); }

  .upload-item .item-icon {
    width: 36px;
    height: 36px;
    border-radius: 8px;
    background: var(--accent-muted, #4f46e533);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .upload-item .item-icon svg { width: 18px; height: 18px; color: var(--accent-color, #4f46e5); }

  .upload-item .item-info { flex: 1; }
  .upload-item .item-name { display: block; font-size: 13px; font-weight: 500; }
  .upload-item .item-meta { display: block; font-size: 11px; color: var(--text-secondary, #9ca3af); }

  /* 保存的项目 */
  .saved-section { margin-bottom: 24px; }

  .saved-list { display: flex; flex-direction: column; gap: 8px; }

  .saved-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: 8px;
    background: var(--bg-tertiary, #1f2937);
    cursor: pointer;
    transition: background 0.15s;
  }

  .saved-item:hover { background: var(--bg-hover, #374151); }

  .saved-item .item-icon {
    width: 36px;
    height: 36px;
    border-radius: 8px;
    background: var(--accent-muted, #4f46e533);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .saved-item .item-icon svg { width: 18px; height: 18px; color: var(--accent-color, #4f46e5); }

  .saved-item .item-info { flex: 1; }
  .saved-item .item-name { display: block; font-size: 13px; font-weight: 500; }
  .saved-item .item-date { display: block; font-size: 11px; color: var(--text-secondary, #9ca3af); }

  .btn-delete {
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-delete:hover { background: #ef444422; color: #ef4444; }
  .btn-delete svg { width: 14px; height: 14px; }

  .save-section { margin-bottom: 24px; }

  .save-form { display: flex; gap: 8px; }

  .input-field {
    flex: 1;
    padding: 8px 12px;
    border-radius: 6px;
    border: 1px solid var(--border-color, #2d3748);
    background: var(--bg-tertiary, #1f2937);
    color: var(--text-primary, #e0e0e0);
    font-size: 13px;
  }

  .input-field:focus { outline: none; border-color: var(--accent-color, #4f46e5); }

  .btn-save {
    padding: 8px 16px;
    border-radius: 6px;
    border: none;
    background: var(--accent-color, #4f46e5);
    color: white;
    font-size: 13px;
    cursor: pointer;
    white-space: nowrap;
  }

  .btn-save:disabled { opacity: 0.5; cursor: not-allowed; }

  .action-buttons { display: flex; flex-direction: column; gap: 8px; }

  .action-btn {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    border: 1px solid var(--border-color, #2d3748);
    border-radius: 8px;
    background: var(--bg-tertiary, #1f2937);
    color: var(--text-primary, #e0e0e0);
    cursor: pointer;
    transition: all 0.15s;
  }

  .action-btn:hover { border-color: var(--accent-color, #4f46e5); background: var(--accent-muted, #4f46e533); }
  .action-btn svg { width: 18px; height: 18px; color: var(--accent-color, #4f46e5); flex-shrink: 0; }
  .action-btn span { font-size: 13px; }
</style>
