<template>
  <Transition name="drop-zone">
    <div
      v-if="isDragging"
      class="file-drop-zone"
      :class="{ 'has-files': draggedFiles.length > 0, 'has-errors': validationErrors.length > 0 }"
      @dragenter.prevent
      @dragover.prevent
      @dragleave.prevent
      @drop.prevent
    >
      <div class="drop-zone-content">
        <div class="drop-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <p class="drop-title">拖拽文件到此处</p>
        <p class="drop-hint">支持的文件类型: {{ supportedTypesText }}</p>
        <p v-if="draggedFiles.length > 0" class="drop-files-count">
          已检测到 {{ draggedFiles.length }} 个文件
        </p>
        <ul v-if="validationErrors.length > 0" class="drop-errors">
          <li v-for="(error, index) in validationErrors" :key="index">{{ error }}</li>
        </ul>
      </div>
    </div>
  </Transition>
</template>

<script setup>
  import { computed } from 'vue'
  import { useFileDrop } from '@/composables/useFileDrop'

  const props = defineProps({
    acceptTypes: {
      type: Array,
      default: () => ['image/*', '.pdf', '.doc', '.docx', '.txt', '.js', '.ts', '.py', '.java', '.go', '.vue', '.html', '.css', '.json', '.md']
    },
    maxSize: {
      type: Number,
      default: 10 * 1024 * 1024
    }
  })

  const emit = defineEmits(['files-dropped'])

  const { isDragging, draggedFiles, validationErrors, bindEvents, unbindEvents } = useFileDrop({
    acceptTypes: props.acceptTypes,
    maxSize: props.maxSize
  })

  const supportedTypesText = computed(() => {
    const types = props.acceptTypes.map(t => {
      if (t.startsWith('.')) return t.toUpperCase()
      if (t.endsWith('/*')) return t.split('/')[0].toUpperCase() + ' 图片'
      return t
    })
    return types.join(', ')
  })

  function onDrop() {
    if (draggedFiles.value.length > 0 && validationErrors.value.length === 0) {
      emit('files-dropped', draggedFiles.value)
    }
  }

  function setupDropZone(element) {
    bindEvents(element)
    element.addEventListener('drop', onDrop)
  }

  function cleanupDropZone(element) {
    unbindEvents(element)
    element.removeEventListener('drop', onDrop)
  }

  defineExpose({ setupDropZone, cleanupDropZone, isDragging, draggedFiles, validationErrors })
</script>

<style scoped>
  .file-drop-zone {
    position: absolute;
    inset: 0;
    z-index: 100;
    background: rgba(37, 99, 235, 0.08);
    backdrop-filter: blur(8px);
    border: 3px dashed #2563eb;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s ease;
  }

  .file-drop-zone.has-files {
    background: rgba(37, 99, 235, 0.12);
    border-color: #1d4ed8;
  }

  .file-drop-zone.has-errors {
    background: rgba(239, 68, 68, 0.08);
    border-color: #ef4444;
  }

  .drop-zone-content {
    text-align: center;
    padding: 32px;
  }

  .drop-icon {
    width: 80px;
    height: 80px;
    margin: 0 auto 16px;
    border-radius: 50%;
    background: linear-gradient(135deg, #2563eb, #3b82f6);
    display: flex;
    align-items: center;
    justify-content: center;
    animation: bounce 1.5s ease-in-out infinite;
  }

  .drop-icon svg {
    width: 40px;
    height: 40px;
    color: white;
  }

  @keyframes bounce {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-10px); }
  }

  .drop-title {
    font-size: 20px;
    font-weight: 600;
    color: #1e293b;
    margin: 0 0 8px;
  }

  .drop-hint {
    font-size: 13px;
    color: #64748b;
    margin: 0 0 12px;
  }

  .drop-files-count {
    font-size: 14px;
    font-weight: 500;
    color: #2563eb;
    margin: 0 0 8px;
  }

  .drop-errors {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .drop-errors li {
    font-size: 12px;
    color: #ef4444;
    padding: 4px 0;
  }

  .drop-zone-enter-active,
  .drop-zone-leave-active {
    transition: opacity 0.3s ease;
  }

  .drop-zone-enter-from,
  .drop-zone-leave-to {
    opacity: 0;
  }
</style>
