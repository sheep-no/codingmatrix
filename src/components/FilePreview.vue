<template>
  <div class="file-preview-item" :class="{ uploading: file.uploading, 'upload-error': file.uploadError }">
    <div v-if="file.uploading" class="upload-spinner">
      <svg class="spinner-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10" stroke-dasharray="31.4" stroke-dashoffset="10" />
      </svg>
    </div>
    <template v-else>
      <div v-if="isImage" class="file-thumbnail">
        <img :src="thumbnailUrl" :alt="file.name" />
      </div>
      <div v-else class="file-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
      </div>
    </template>
    <div class="file-info">
      <span class="file-name" :title="file.name">{{ file.name }}</span>
      <span v-if="file.uploading" class="upload-status">上传中...</span>
      <span v-else-if="file.uploadError" class="error-status">上传失败</span>
      <span v-else class="file-size">{{ formatFileSize(file.size) }}</span>
    </div>
    <button class="remove-btn" title="移除文件" @click="$emit('remove')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    </button>
  </div>
</template>

<script setup>
  import { computed } from 'vue'

  const props = defineProps({
    file: { type: Object, required: true }
  })

  defineEmits(['remove'])

  const imageTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml']

  const isImage = computed(() => imageTypes.includes(props.file.type))

  const thumbnailUrl = computed(() => {
    if (isImage.value) {
      const actualFile = props.file.file || props.file
      if (actualFile instanceof Blob) {
        return URL.createObjectURL(actualFile)
      }
    }
    return ''
  })

  function formatFileSize(bytes) {
    if (!bytes) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
  }
</script>

<style scoped>
  .file-preview-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .file-preview-item:hover {
    background: var(--bg-tertiary);
  }

  .file-preview-item.uploading {
    border-color: #3b82f6;
    background: rgba(59, 130, 246, 0.05);
  }

  .file-preview-item.upload-error {
    border-color: var(--danger);
    background: rgba(239, 68, 68, 0.05);
  }

  .upload-spinner {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .spinner-icon {
    width: 24px;
    height: 24px;
    animation: spin 1s linear infinite;
    color: #3b82f6;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .upload-status {
    font-size: 11px;
    color: #3b82f6;
  }

  .error-status {
    font-size: 11px;
    color: var(--danger);
  }

  .file-thumbnail {
    width: 40px;
    height: 40px;
    border-radius: 6px;
    overflow: hidden;
    flex-shrink: 0;
  }

  .file-thumbnail img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .file-icon {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--border-color);
    border-radius: 6px;
    flex-shrink: 0;
  }

  .file-icon svg {
    width: 20px;
    height: 20px;
    color: #64748b;
  }

  .file-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .file-name {
    font-size: 13px;
    font-weight: 500;
    color: #1e293b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .file-size {
    font-size: 11px;
    color: #94a3b8;
  }

  .remove-btn {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
    flex-shrink: 0;
  }

  .remove-btn:hover {
    background: var(--danger-100);
  }

  .remove-btn svg {
    width: 16px;
    height: 16px;
    color: var(--danger);
  }
</style>
