import { ref, onMounted, onUnmounted } from 'vue'

export function useFileDrop(options = {}) {
  const {
    acceptTypes = [],
    maxSize = 10 * 1024 * 1024,
    multiple = true
  } = options

  const isDragging = ref(false)
  const draggedFiles = ref([])
  const validationErrors = ref([])
  let dragCounter = 0

  function validateFile(file) {
    if (acceptTypes.length > 0) {
      const fileExt = '.' + file.name.split('.').pop().toLowerCase()
      const mimeType = file.type
      const isAccepted = acceptTypes.some(type => {
        if (type.startsWith('.')) {
          return fileExt === type.toLowerCase()
        }
        if (type.endsWith('/*')) {
          const baseType = type.split('/')[0]
          return mimeType.startsWith(baseType + '/')
        }
        return mimeType === type
      })
      if (!isAccepted) {
        return `文件 "${file.name}" 类型不支持`
      }
    }

    if (file.size > maxSize) {
      const sizeMB = (maxSize / (1024 * 1024)).toFixed(1)
      return `文件 "${file.name}" 超过大小限制 (${sizeMB}MB)`
    }

    return null
  }

  function handleDragEnter(e) {
    e.preventDefault()
    e.stopPropagation()
    dragCounter++
    if (dragCounter === 1) {
      isDragging.value = true
    }
  }

  function handleDragOver(e) {
    e.preventDefault()
    e.stopPropagation()
  }

  function handleDragLeave(e) {
    e.preventDefault()
    e.stopPropagation()
    dragCounter--
    if (dragCounter === 0) {
      isDragging.value = false
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    e.stopPropagation()
    isDragging.value = false
    dragCounter = 0

    const files = Array.from(e.dataTransfer.files)
    if (!multiple && files.length > 1) {
      validationErrors.value = ['仅支持拖拽单个文件']
      return
    }

    const errors = []
    const validFiles = []

    for (const file of files) {
      const error = validateFile(file)
      if (error) {
        errors.push(error)
      } else {
        validFiles.push(file)
      }
    }

    validationErrors.value = errors
    draggedFiles.value = validFiles
  }

  function reset() {
    isDragging.value = false
    draggedFiles.value = []
    validationErrors.value = []
    dragCounter = 0
  }

  function bindEvents(element) {
    if (!element) return
    element.addEventListener('dragenter', handleDragEnter)
    element.addEventListener('dragover', handleDragOver)
    element.addEventListener('dragleave', handleDragLeave)
    element.addEventListener('drop', handleDrop)
  }

  function unbindEvents(element) {
    if (!element) return
    element.removeEventListener('dragenter', handleDragEnter)
    element.removeEventListener('dragover', handleDragOver)
    element.removeEventListener('dragleave', handleDragLeave)
    element.removeEventListener('drop', handleDrop)
  }

  onMounted(() => {
    document.body.addEventListener('dragenter', handleDragEnter)
    document.body.addEventListener('dragover', handleDragOver)
    document.body.addEventListener('dragleave', handleDragLeave)
    document.body.addEventListener('drop', handleDrop)
  })

  onUnmounted(() => {
    document.body.removeEventListener('dragenter', handleDragEnter)
    document.body.removeEventListener('dragover', handleDragOver)
    document.body.removeEventListener('dragleave', handleDragLeave)
    document.body.removeEventListener('drop', handleDrop)
  })

  return {
    isDragging,
    draggedFiles,
    validationErrors,
    reset,
    bindEvents,
    unbindEvents,
    validateFile
  }
}
