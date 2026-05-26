<template>
  <div
    class="bottom-input-container"
    :class="{ collapsed: isCollapsed }"
    role="region"
    aria-label="消息输入区域"
  >
    <!-- 展开按钮（折叠时显示） -->
    <button
      v-show="isCollapsed"
      class="expand-btn"
      aria-label="展开输入框"
      @click="toggleCollapse"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M12 3v18M3 12h18" />
      </svg>
    </button>

    <div class="input-content" :class="{ collapsed: isCollapsed }">
      <!-- 配置选项区域 -->
      <div v-if="showConfig" class="config-panel" role="group" aria-label="输入配置">
        <div class="config-row">
          <!-- 深度思考开关 -->
          <label
            class="config-item"
            :class="{ disabled: useHybrid || projectGeneratorMode }"
          >
            <input
              v-model="useReasoning"
              type="checkbox"
              class="config-checkbox"
              :disabled="useHybrid || projectGeneratorMode"
              aria-describedby="reasoning-tooltip"
              @change="handleReasoningChange"
            />
            <span class="config-label">深度思考</span>
            <span id="reasoning-tooltip" class="config-tooltip" role="tooltip">启用后，AI会先进行推理分析</span>
          </label>

          <!-- 混合思考开关 -->
          <label
            class="config-item"
            :class="{ disabled: projectGeneratorMode }"
          >
            <input
              v-model="useHybrid"
              type="checkbox"
              class="config-checkbox"
              :disabled="projectGeneratorMode"
              aria-describedby="hybrid-tooltip"
              @change="handleHybridChange"
            />
            <span class="config-label">混合思考</span>
            <span id="hybrid-tooltip" class="config-tooltip" role="tooltip">结合推理和直接生成</span>
          </label>
        </div>
      </div>

      <!-- 需求联想面板 -->
      <div v-if="associations.length > 0" class="associations-panel" role="list" aria-label="需求联想">
        <div class="associations-header">
          <span class="associations-title">需求联想</span>
          <button class="associations-close" aria-label="关闭联想" @click="associations = []">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="associations-list">
          <div
            v-for="item in associations"
            :key="item.id"
            class="association-item"
            :class="{ confirmed: item.confirmed }"
            @click="selectAssociation(item)"
          >
            <span class="association-type">{{ item.type }}</span>
            <span class="association-text">{{ item.text }}</span>
            <span v-if="item.confirmed" class="association-check">✓</span>
          </div>
        </div>
      </div>

      <!-- 已添加文件列表 -->
      <div
        v-if="attachedFiles.length > 0"
        class="attached-files"
        role="list"
        aria-label="已附加的文件"
      >
        <FilePreview
          v-for="(file, index) in attachedFiles"
          :key="file.id"
          :file="file"
          @remove="removeFile(index)"
        />
      </div>

      <!-- 输入框区域 -->
      <div ref="inputWrapperRef" class="input-wrapper">
        <FileDropZone ref="dropZoneRef" @files-dropped="handleFilesDropped" />
        <textarea
          ref="textareaRef"
          v-model="inputMessage"
          class="chat-input"
          :class="{ 'edit-mode': props.editMessage }"
          :placeholder="
            !userStore.isLoggedIn
              ? '请先登录以发送消息...'
              : props.editMessage
                ? '编辑消息... (Ctrl+Enter 保存，Esc 取消)'
                : props.isStreaming
                  ? '[LOADING] AI thinking...'
                  : useReasoning
                    ? useHybrid
                      ? '[FIND] Hybrid mode - Enter your request...'
                      : '[FIND] Deep thinking mode - Enter your request...'
                    : 'Enter message, press Ctrl+Enter to send...'
          "
          :disabled="props.isStreaming"
          :aria-label="props.editMessage ? '编辑消息输入框' : '消息输入框'"
          :aria-disabled="props.isStreaming"
          rows="1"
          @keydown.enter.exact.prevent="handleEnter"
          @keydown.enter.ctrl="sendMessage"
          @keydown.esc="props.editMessage && cancelEdit()"
          @input="handleInput"
        />
        <!-- 发送/取消按钮 -->
        <template v-if="!isStreaming">
          <button
            v-if="props.editMessage"
            class="cancel-edit-btn"
            aria-label="取消编辑"
            title="取消编辑"
            @click="cancelEdit"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
          <button
            class="send-btn"
            :disabled="!inputMessage.trim() || !userStore.isLoggedIn"
            :aria-label="!userStore.isLoggedIn ? '请先登录' : props.editMessage ? '保存编辑' : '发送消息'"
            :title="
              !userStore.isLoggedIn ? '请先登录' : props.editMessage ? '保存编辑' : '发送消息'
            "
            @click="sendMessage"
          >
            <span class="send-icon" aria-hidden="true">{{ props.editMessage ? '✓' : '➤' }}</span>
          </button>
        </template>
        <!-- 停止按钮：仅在流式输出时显示 -->
        <button
          v-else
          class="stop-btn"
          aria-label="停止输出"
          title="停止输出"
          @click="stopStream"
        >
          <span class="stop-icon" aria-hidden="true">⏹</span>
        </button>

        <!-- 配置面板开关 -->
        <button
          class="config-toggle"
          :class="{ active: showConfig }"
          :aria-label="'配置' + (showConfig ? '，已展开' : '，已收起')"
          :aria-expanded="showConfig"
          title="配置"
          @click="showConfig = !showConfig"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <circle cx="12" cy="12" r="3" />
            <path
              d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"
            />
          </svg>
        </button>

        <!-- 文件上传按钮 -->
        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept="image/*,.js,.ts,.jsx,.tsx,.py,.java,.c,.cpp,.go,.rs,.rb,.php,.vue,.html,.css,.scss,.json,.yaml,.yml,.xml,.sql,.sh,.md,.txt,.pdf,.doc,.docx,.xls,.xlsx,.csv"
          class="hidden-file-input"
          @change="handleFileSelect"
        />
        <button
          class="upload-btn"
          aria-label="上传文件或图片"
          title="上传文件/图片供 AI 分析"
          @click="triggerFileUpload"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
          </svg>
        </button>

        <!-- 折叠按钮 -->
        <button
          class="collapse-btn"
          aria-label="收起输入框"
          title="收起输入框"
          @click="toggleCollapse"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M18 15l-6-6-6 6" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, watch, computed, nextTick, onMounted, onUnmounted } from 'vue'
  import { useNavigationStore } from '@/stores/navigation'
  import { useUserStore } from '@/stores/user'
  import { api } from '@/utils/api/index'
  import FileDropZone from './FileDropZone.vue'
  import FilePreview from './FilePreview.vue'
  import { useToast } from '@/composables/useToast'

  const navigationStore = useNavigationStore()
  const userStore = useUserStore()
  const { success, error: showError } = useToast()

  const inputMessage = ref('')
  const useReasoning = ref(false)
  const useHybrid = ref(false)
  const showConfig = ref(true)
  const textareaRef = ref(null)
  const inputWrapperRef = ref(null)
  const dropZoneRef = ref(null)
  const fileInputRef = ref(null)
  const attachedFiles = ref([])
  const associations = ref([])
  let associationFetchTimer = null

  // 监听 navigation store 的 ProjectGenerator 状态
  const projectGeneratorMode = computed(() => navigationStore.showProjectGenerator)

  let fileCounter = 0

  const codeExtensions = [
    'js', 'ts', 'jsx', 'tsx', 'py', 'java', 'c', 'cpp', 'go', 'rs', 'rb',
    'php', 'vue', 'html', 'css', 'scss', 'json', 'yaml', 'yml', 'xml', 'sql', 'sh', 'md', 'txt'
  ]

  const imageTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml']

  // 从 navigation store 获取折叠状态
  const isCollapsed = computed(() => navigationStore.isBottomInputCollapsed)

  // 切换折叠状态
  const toggleCollapse = () => {
    navigationStore.toggleBottomInputCollapsed()
  }

  // 接收父组件传入的流式状态
  const props = defineProps({
    isStreaming: { type: Boolean, default: false },
    editMessage: { type: String, default: '' }
  })

  const emit = defineEmits(['send', 'stop', 'require-login', 'cancel-edit', 'save-edit'])

  // 监听编辑消息
  watch(
    () => props.editMessage,
    newMsg => {
      if (newMsg) {
        inputMessage.value = newMsg
        nextTick(() => textareaRef.value?.focus())
      }
    }
  )

  // 需求联想：输入较长时自动获取联想建议
  watch(
    () => inputMessage.value,
    newText => {
      if (associationFetchTimer) {
        clearTimeout(associationFetchTimer)
      }

      if (newText.length < 20) {
        associations.value = []
        return
      }

      associationFetchTimer = setTimeout(async () => {
        try {
          const result = await api.getRequirementAssociations(newText)
          const items = result.associations || result.items || []
          if (items.length > 0) {
            associations.value = items.slice(0, 5)
          } else {
            associations.value = []
          }
        } catch (e) {
          associations.value = []
        }
      }, 800)
    }
  )

  // 监听混合思考的变化
  watch(useHybrid, newValue => {
    if (newValue) {
      useReasoning.value = true
    }
  })

  // 停止流式输出
  const stopStream = () => {
    if (props.isStreaming) {
      emit('stop')
    }
  }

  // 选择联想项，追加到输入框
  const selectAssociation = item => {
    if (item.text) {
      inputMessage.value += '\n' + item.text
    }
    item.confirmed = true
    setTimeout(() => {
      associations.value = associations.value.filter(a => a.id !== item.id)
    }, 300)
  }

  // 处理混合思考变化
  const handleHybridChange = () => {
    if (useHybrid.value) {
      useReasoning.value = true
    }
  }

  // 处理深度思考变化
  const handleReasoningChange = event => {
    if (useHybrid.value && !event.target.checked) {
      event.target.checked = true
      useReasoning.value = true
    }
  }

  function triggerFileUpload() {
    fileInputRef.value?.click()
  }

  const MAX_FILE_SIZE = 100 * 1024 * 1024 // 100MB

  async function handleFileSelect(event) {
    const files = event.target.files
    if (!files || files.length === 0) return
    for (const file of files) {
      await processFile(file)
    }
    event.target.value = ''
  }

  async function handleFilesDropped(files) {
    for (const file of files) {
      await processFile(file)
    }
  }

  async function processFile(file) {
    if (file.size > MAX_FILE_SIZE) {
      showError(`文件大小超过 100MB 限制: ${file.name}`)
      return
    }

    if (imageTypes.includes(file.type)) {
      const fileObj = {
        id: ++fileCounter,
        name: file.name,
        size: file.size,
        type: file.type,
        file: file,
        category: 'image',
        uploading: true,
        preview: URL.createObjectURL(file),
        localUrl: URL.createObjectURL(file)
      }
      attachedFiles.value.push(fileObj)

      try {
        const result = await api.uploadFile(file)
        fileObj.serverId = result.id
        fileObj.serverPath = result.file_path
        fileObj.uploading = false
        success(`图片上传成功: ${file.name}`)
      } catch (err) {
        fileObj.uploading = false
        fileObj.uploadError = true
        showError(`图片上传失败: ${file.name}`)
      }
    } else if (isCodeFile(file)) {
      const fileObj = {
        id: ++fileCounter,
        name: file.name,
        size: file.size,
        type: file.type,
        file: file,
        category: 'code',
        uploading: true
      }
      attachedFiles.value.push(fileObj)

      try {
        const result = await api.uploadFile(file)
        fileObj.serverId = result.id
        fileObj.serverPath = result.file_path
        fileObj.uploading = false
        success(`代码文件上传成功: ${file.name}`)
      } catch (err) {
        fileObj.uploading = false
        fileObj.uploadError = true
        showError(`代码文件上传失败: ${file.name}`)
      }
    } else {
      const fileObj = {
        id: ++fileCounter,
        name: file.name,
        size: file.size,
        type: file.type,
        file: file,
        category: 'document',
        uploading: true
      }
      attachedFiles.value.push(fileObj)

      try {
        const result = await api.uploadFile(file)
        fileObj.serverId = result.id
        fileObj.serverPath = result.file_path
        fileObj.uploading = false
        success(`文件上传成功: ${file.name}`)
      } catch (err) {
        fileObj.uploading = false
        fileObj.uploadError = true
        showError(`文件上传失败: ${file.name}`)
      }
    }
    adjustTextareaHeight()
  }

  function isCodeFile(file) {
    const ext = file.name.split('.').pop().toLowerCase()
    return codeExtensions.includes(ext)
  }

  function getFileExtension(fileName) {
    return fileName.split('.').pop().toLowerCase()
  }

  function readFileContent(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = reject
      reader.readAsText(file)
    })
  }

  function removeFile(index) {
    attachedFiles.value.splice(index, 1)
  }

  const sendMessage = () => {
    if (!inputMessage.value.trim() && attachedFiles.value.length === 0) return

    if (!userStore.isLoggedIn) {
      emit('require-login')
      return
    }

    const uploadingFiles = attachedFiles.value.filter(f => f.uploading)
    if (uploadingFiles.length > 0) {
      showError('文件正在上传中，请稍后再发送')
      return
    }

    const messageData = {
      prompt: inputMessage.value,
      use_reasoning: useReasoning.value,
      use_hybrid: useHybrid.value,
      files: attachedFiles.value.map(f => ({
        id: f.serverId || null,
        name: f.name,
        size: f.size,
        type: f.type,
        category: f.category,
        serverPath: f.serverPath || null
      }))
    }

    if (props.editMessage) {
      emit('save-edit', {
        originalMessage: props.editMessage,
        ...messageData
      })
      emit('cancel-edit')
    } else {
      emit('send', messageData)
    }

    for (const f of attachedFiles.value) {
      if (f.category === 'image' && f.file) {
        URL.revokeObjectURL(f.previewUrl)
      }
    }
    inputMessage.value = ''
    attachedFiles.value = []
    const textarea = textareaRef.value
    if (textarea) {
      textarea.style.height = '48px'
    }
  }

  const cancelEdit = () => {
    inputMessage.value = ''
    emit('cancel-edit')
  }

  // 处理Enter键（普通换行）
  const handleEnter = event => {
    if (!props.isStreaming) {
      event.preventDefault()
      const textarea = textareaRef.value
      const start = textarea.selectionStart
      const end = textarea.selectionEnd
      const text = inputMessage.value

      inputMessage.value = text.substring(0, start) + '\n' + text.substring(end)

      nextTick(() => {
        textarea.selectionStart = textarea.selectionEnd = start + 1
        adjustTextareaHeight()
      })
    }
  }

  // 处理输入事件，自动调整高度
  const handleInput = () => {
    adjustTextareaHeight()
  }

  // 自动调整textarea高度
  const adjustTextareaHeight = () => {
    const textarea = textareaRef.value
    if (!textarea) return

    textarea.style.height = 'auto'

    const newHeight = Math.min(textarea.scrollHeight, 200)
    textarea.style.height = newHeight + 'px'
  }

  onMounted(() => {
    if (inputWrapperRef.value) {
      dropZoneRef.value?.setupDropZone(inputWrapperRef.value)
    }
  })

  onUnmounted(() => {
    if (inputWrapperRef.value) {
      dropZoneRef.value?.cleanupDropZone(inputWrapperRef.value)
    }
    for (const file of attachedFiles.value) {
      if (file.category === 'image' && file.file) {
        URL.revokeObjectURL(file.previewUrl)
      }
    }
    if (associationFetchTimer) {
      clearTimeout(associationFetchTimer)
    }
  })

  defineExpose({
    sendMessage,
    textareaRef
  })
</script>

<style scoped>
  :root {
    --input-bg: rgba(255, 255, 255, 0.95);
    --border-color: #e2e8f0;
    --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  }

  /* 需求联想面板 */
  .associations-panel {
    margin: 8px 16px 0;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    max-height: 200px;
    overflow-y: auto;
  }

  .associations-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color);
  }

  .associations-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .associations-close {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-tertiary);
    padding: 2px;
  }

  .associations-close:hover {
    color: var(--text-primary);
  }

  .associations-list {
    padding: 4px;
  }

  .association-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s ease;
  }

  .association-item:hover {
    background: var(--bg-tertiary);
  }

  .association-item.confirmed {
    opacity: 0.5;
    pointer-events: none;
  }

  .association-type {
    font-size: 11px;
    padding: 2px 6px;
    background: var(--accent-blue);
    color: #fff;
    border-radius: 4px;
    white-space: nowrap;
  }

  .association-text {
    flex: 1;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .association-check {
    color: var(--accent-green);
    font-weight: bold;
  }

  /* 焦点可见样式 */
  :focus-visible {
    outline: 2px solid #2563eb;
    outline-offset: 2px;
  }

  .expand-btn:focus-visible,
  .send-btn:focus-visible,
  .stop-btn:focus-visible,
  .config-toggle:focus-visible,
  .collapse-btn:focus-visible,
  .cancel-edit-btn:focus-visible {
    outline: 2px solid #2563eb;
    outline-offset: 2px;
    box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.15);
  }

  .config-checkbox:focus-visible {
    outline: 2px solid #2563eb;
    outline-offset: 2px;
  }

  /* 固定定位容器 - 添加顶部圆角 */
  .bottom-input-container {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--input-bg);
    backdrop-filter: blur(20px);
    padding: 14px 24px 20px;
    border-top: 1px solid var(--border-color);
    border-left: 1px solid var(--border-color);
    border-right: 1px solid var(--border-color);
    border-top-left-radius: 18px;
    border-top-right-radius: 18px;
    box-shadow: var(--shadow-lg);
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-width: 900px;
    margin: 0 auto;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
  }

  /* 折叠状态 */
  .bottom-input-container.collapsed {
    width: 44px;
    height: 44px;
    padding: 0;
    min-height: 44px;
    min-width: 44px;
    overflow: visible;
    border-radius: 14px;
  }

  /* 展开按钮（折叠时显示） */
  .expand-btn {
    width: 44px;
    height: 44px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    z-index: 10;
    box-shadow: var(--shadow-md);
  }

  .expand-btn svg {
    width: 20px;
    height: 20px;
    color: var(--text-primary);
  }

  .expand-btn:hover {
    background: var(--bg-tertiary);
    transform: scale(1.08);
    box-shadow: var(--shadow-lg);
  }

  /* 输入内容区域 */
  .input-content {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 10px;
    transition:
      opacity 0.3s ease,
      transform 0.3s ease;
  }

  .input-content.collapsed {
    display: none;
  }

  /* 配置面板 */
  .config-panel {
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(10px);
    border-radius: 14px;
    padding: 12px 16px;
    border: 1px solid rgba(226, 232, 240, 0.7);
    animation: slideDown 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: var(--shadow-sm);
  }

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .config-row {
    display: flex;
    align-items: center;
    gap: 20px;
    flex-wrap: wrap;
  }

  .config-item {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    transition: opacity 0.2s;
  }

  .config-item.disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .config-item.disabled .config-checkbox {
    cursor: not-allowed;
  }

  .config-checkbox {
    width: 17px;
    height: 17px;
    cursor: pointer;
    accent-color: #2563eb;
  }

  .config-checkbox:disabled {
    cursor: not-allowed;
  }

  .config-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
  }

  .config-tooltip {
    font-size: 11px;
    color: var(--text-tertiary);
    margin-left: 3px;
  }

  /* 输入框包装器 */
  .input-wrapper {
    flex: 1;
    position: relative;
    display: flex;
    flex-direction: column;
    min-height: 46px;
    gap: 8px;
  }

  /* 已添加文件列表 */
  .attached-files {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 8px;
    background: rgba(248, 250, 252, 0.8);
    border-radius: 10px;
    border: 1px solid #e2e8f0;
  }

  .chat-input {
    flex: 1;
    width: 100%;
    min-height: 46px;
    max-height: 180px;
    padding: 11px 140px 11px 14px;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    font-size: 15px;
    font-family: inherit;
    line-height: 1.5;
    outline: none;
    transition: all 0.2s ease;
    background: white;
    box-shadow: var(--shadow-sm);
    resize: none;
    overflow-y: auto;
    word-wrap: break-word;
    word-break: break-word;
  }

  .chat-input:focus {
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
  }

  .chat-input::placeholder {
    color: #94a3b8;
  }

  /* 发送按钮 */
  .send-btn {
    position: absolute;
    right: 130px;
    top: 50%;
    transform: translateY(-50%);
    width: 38px;
    height: 38px;
    background: linear-gradient(135deg, #2563eb, #3b82f6);
    border: none;
    border-radius: 10px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    flex-shrink: 0;
    box-shadow: 0 2px 4px rgba(37, 99, 235, 0.3);
  }

  .send-btn:hover:not(:disabled) {
    background: linear-gradient(135deg, #1d4ed8, #2563eb);
    transform: translateY(-50%) scale(1.06);
    box-shadow: 0 4px 8px rgba(37, 99, 235, 0.4);
  }

  .send-btn:disabled {
    background: #cbd5e1;
    cursor: not-allowed;
    box-shadow: none;
  }

  .send-icon {
    color: white;
    font-size: 16px;
    transform: rotate(-90deg);
  }

  /* 停止按钮 */
  .stop-btn {
    position: absolute;
    right: 130px;
    top: 50%;
    transform: translateY(-50%);
    width: 38px;
    height: 38px;
    background: linear-gradient(135deg, #ef4444, #dc2626);
    border: none;
    border-radius: 10px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    flex-shrink: 0;
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.3);
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.8;
    }
  }

  .stop-btn:hover {
    background: linear-gradient(135deg, #f87171, #ef4444);
    transform: translateY(-50%) scale(1.06);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.4);
  }

  .stop-btn .stop-icon {
    font-size: 20px;
    color: white;
  }

  /* 配置开关按钮 */
  .config-toggle {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    width: 34px;
    height: 34px;
    background: var(--bg-tertiary);
    border: none;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    z-index: 10;
  }

  .config-toggle svg {
    width: 18px;
    height: 18px;
    color: var(--text-secondary);
  }

  .config-toggle:hover {
    background: var(--bg-tertiary);
    transform: translateY(-50%) rotate(30deg);
  }

  .config-toggle.active {
    background: #2563eb;
    color: white;
  }

  /* 文件上传按钮 */
  .upload-btn {
    position: absolute;
    right: 50px;
    top: 50%;
    transform: translateY(-50%);
    width: 34px;
    height: 34px;
    background: var(--bg-tertiary);
    border: none;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    z-index: 10;
  }

  .upload-btn svg {
    width: 16px;
    height: 16px;
    color: var(--text-secondary);
  }

  .upload-btn:hover {
    background: var(--bg-tertiary);
    transform: translateY(-50%) scale(0.95);
  }

  .hidden-file-input {
    display: none;
  }

  /* 折叠按钮 */
  .collapse-btn {
    position: absolute;
    right: 90px;
    top: 50%;
    transform: translateY(-50%);
    width: 34px;
    height: 34px;
    background: var(--bg-tertiary);
    border: none;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    z-index: 10;
  }

  .collapse-btn svg {
    width: 16px;
    height: 16px;
    color: var(--text-secondary);
  }

  .collapse-btn:hover {
    background: var(--bg-tertiary);
    transform: translateY(-50%) scale(0.95);
  }

  /* 响应式设计 */
  @media (max-width: 1024px) {
    .bottom-input-container {
      max-width: 85vw;
    }
  }

  @media (max-width: 768px) {
    .bottom-input-container {
      max-width: 95vw;
      padding: 12px 16px 16px;
      border-top-left-radius: 16px;
      border-top-right-radius: 16px;
    }

    .config-panel {
      padding: 10px 12px;
    }

    .config-row {
      gap: 12px;
    }

    .config-label {
      font-size: 12px;
    }

    .chat-input {
      padding: 10px 110px 10px 12px;
      font-size: 14px;
    }

    .send-btn,
    .stop-btn {
      right: 95px;
    }

    .collapse-btn {
      right: 55px;
    }
    
    .upload-btn {
      right: 20px;
    }
  }

  @media (max-width: 480px) {
    .bottom-input-container {
      max-width: 98vw;
    }

    .config-row {
      flex-direction: column;
      align-items: flex-start;
      gap: 8px;
    }

    .config-item {
      width: 100%;
    }
  }
</style>
