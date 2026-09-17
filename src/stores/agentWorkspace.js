import { ref, computed, nextTick } from 'vue'
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import JSZip from 'jszip'

export const useAgentWorkspaceStore = defineStore('agentWorkspace', () => {
  // ========== Files State ==========
  const generatedFiles = ref([])
  const selectedFile = ref(null)
  const fileDiffs = ref([])
  const fileVersions = ref({})
  const fileSearchQuery = ref('')
  const fileFilterType = ref('all')

  // ========== Workspace State ==========
  const logs = ref([])
  const executionDetails = ref([])
  const thinkingMessages = ref([])
  const pendingDecisions = ref([])
  const decisionAnswers = ref({})
  const decisionHistory = ref([])
  const logsContainer = ref(null)
  const currentAgent = ref(null)
  const currentModel = ref(null)
  const currentProjectPath = ref(null)

  // ========== Results State ==========
  const testResults = ref(null)
  const validationResults = ref(null)
  const costData = ref({
    totalTokens: 0, promptTokens: 0, completionTokens: 0,
    totalCostUsd: 0, tokensPerSecond: 0, modelCosts: {}, modelTokens: {}
  })
  const performanceMetrics = ref({
    generationSpeed: 0, filesPerMinute: 0, avgFileTime: 0,
    totalDuration: 0, llmCalls: 0, retryCount: 0
  })

  // ========== Backend State ==========
  const savedProjects = ref([])
  const isLoadingProjects = ref(false)
  const projectsError = ref(null)
  const backendFileList = ref([])
  const isLoadingBackendFiles = ref(false)
  const backendSnapshots = ref([])
  const isLoadingSnapshots = ref(false)
  const concurrentLimits = ref({})
  const cacheStats = ref({})
  const learningStats = ref({})
  const isLoadingSettings = ref(false)
  const backendPerformanceData = ref(null)
  const backendPerformanceTrends = ref(null)
  const isLoadingPerformance = ref(false)
  const performanceStats = ref({})
  const showSettingsModal = ref(false)
  const showPerformanceModal = ref(false)
  const showLearningModal = ref(false)
  const showVersionHistoryModal = ref(false)
  const showUploadModal = ref(false)
  const showDiffModal = ref(false)
  const selectedDiffFile = ref(null)
  const uploadingZip = ref(false)
  const importProgress = ref({ current: 0, total: 0, currentFile: '' })
  const fileInput = ref(null)
  const settings = ref({
    models: {
      architecture: 'Qwen3-Plus', frontend: 'Qwen3-Coder',
      backend: 'Qwen3-Coder', test: 'Qwen3-Coder', review: 'Qwen3-Plus'
    },
    maxConcurrent: 3, enableReview: true, enableValidation: true,
    enableErrorRecovery: true, enableMemory: true, specFirst: true, dependencyGraph: true
  })

  const pendingApproval = ref(null)

  // ========== Computed ==========
  const filteredFiles = computed(() => {
    let files = generatedFiles.value
    if (fileSearchQuery.value) {
      const query = fileSearchQuery.value.toLowerCase()
      files = files.filter(f => f.path.toLowerCase().includes(query))
    }
    if (fileFilterType.value !== 'all') {
      files = files.filter(f => {
        const lang = getLanguage(f.path).toLowerCase()
        return lang.includes(fileFilterType.value.toLowerCase())
      })
    }
    return files
  })

  // ========== File Methods ==========
  const languageMap = {
    'js': 'JavaScript', 'jsx': 'React JSX', 'ts': 'TypeScript', 'tsx': 'React TSX',
    'vue': 'Vue', 'py': 'Python', 'java': 'Java', 'go': 'Go', 'rb': 'Ruby', 'php': 'PHP',
    'cs': 'C#', 'cpp': 'C++', 'c': 'C', 'h': 'Header', 'html': 'HTML', 'css': 'CSS',
    'scss': 'SCSS', 'sass': 'Sass', 'json': 'JSON', 'xml': 'XML', 'yaml': 'YAML',
    'yml': 'YAML', 'md': 'Markdown', 'txt': 'Text', 'sql': 'SQL', 'sh': 'Shell',
    'bash': 'Bash', 'dockerfile': 'Dockerfile', 'makefile': 'Makefile', 'env': 'Environment',
    'gitignore': 'Git Ignore'
  }

  function getLanguage(filePath) {
    if (!filePath) return 'Unknown'
    const fileName = filePath.split('/').pop().toLowerCase()
    const ext = fileName.split('.').pop().toLowerCase()
    if (fileName === 'dockerfile') return 'Dockerfile'
    if (fileName === 'makefile') return 'Makefile'
    if (fileName.startsWith('.gitignore') || fileName === 'gitignore') return 'Git Ignore'
    return languageMap[ext] || ext.toUpperCase()
  }

  function selectFile(file) {
    selectedFile.value = file
  }

  function clearFiles() {
    generatedFiles.value = []
    fileDiffs.value = []
    selectedFile.value = null
    fileVersions.value = {}
    fileSearchQuery.value = ''
    fileFilterType.value = 'all'
  }

  // ========== Log Methods ==========
  function addLog(level, message) {
    logs.value.push({ level, message, timestamp: new Date().toISOString() })
    nextTick(() => {
      if (logsContainer.value) {
        logsContainer.value.scrollTop = logsContainer.value.scrollHeight
      }
    })
  }

  function addDetail(category, description) {
    executionDetails.value.push({
      category, description, timestamp: new Date().toISOString()
    })
  }

  function clearWorkspace() {
    logs.value = []
    executionDetails.value = []
    thinkingMessages.value = []
    pendingDecisions.value = []
    decisionAnswers.value = {}
    decisionHistory.value = []
    testResults.value = null
    validationResults.value = null
    currentAgent.value = null
    currentModel.value = null
    currentProjectPath.value = null
    pendingApproval.value = null
  }

  // ========== Utility Methods ==========
  function formatTime(timestamp) {
    if (!timestamp) return ''
    const date = new Date(timestamp)
    const diff = Date.now() - date.getTime()
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
    return date.toLocaleDateString()
  }

  function formatLogTime(timestamp) {
    return new Date(timestamp).toLocaleTimeString()
  }

  async function getHighlightedCode() {
    if (!selectedFile.value || !selectedFile.value.content) return '<pre><code></code></pre>'
    const hljsPromise = Promise.all([
      import('highlight.js'),
      import('highlight.js/styles/github-dark.css')
    ]).then(([mod]) => mod.default || mod)
    const hljs = await hljsPromise
    const hljsLangMap = {
      'javascript': 'javascript', 'typescript': 'typescript', 'vue': 'html', 'html': 'html',
      'css': 'css', 'scss': 'scss', 'python': 'python', 'java': 'java', 'go': 'go',
      'json': 'json', 'yaml': 'yaml', 'xml': 'xml', 'markdown': 'markdown',
      'shell': 'bash', 'sql': 'sql'
    }
    const lang = getLanguage(selectedFile.value.path).toLowerCase()
    const hljsLang = hljsLangMap[lang] || 'plaintext'
    const result = hljs.highlight(selectedFile.value.content, { language: hljsLang })
    return `<pre><code class="hljs language-${hljsLang}">${result.value}</code></pre>`
  }

  // ========== Settings Methods ==========
  function loadSettings() {
    try {
      const saved = localStorage.getItem('agent_settings')
      if (saved) settings.value = { ...settings.value, ...JSON.parse(saved) }
    } catch (error) {
      console.warn('加载设置失败:', error)
    }
  }

  function saveSettings() {
    try {
      localStorage.setItem('agent_settings', JSON.stringify(settings.value))
      showSettingsModal.value = false
      ElMessage.success('设置已保存')
    } catch (error) {
      ElMessage.error('保存设置失败')
    }
  }

  return {
    // Files
    generatedFiles, selectedFile, fileDiffs, fileVersions,
    fileSearchQuery, fileFilterType, filteredFiles,
    getLanguage, selectFile, clearFiles,
    // Workspace
    logs, executionDetails, thinkingMessages,
    pendingDecisions, decisionAnswers, decisionHistory,
    logsContainer, currentAgent, currentModel, currentProjectPath,
    testResults, validationResults, costData, performanceMetrics, pendingApproval,
    addLog, addDetail, clearWorkspace,
    // Backend
    savedProjects, isLoadingProjects, projectsError,
    backendFileList, isLoadingBackendFiles,
    backendSnapshots, isLoadingSnapshots,
    concurrentLimits, cacheStats, learningStats, isLoadingSettings,
    backendPerformanceData, backendPerformanceTrends, isLoadingPerformance,
    performanceStats,
    showSettingsModal, showPerformanceModal, showLearningModal,
    showVersionHistoryModal, showUploadModal, showDiffModal, selectedDiffFile,
    uploadingZip, importProgress, fileInput, settings,
    loadSettings, saveSettings,
    // Utility
    formatTime, formatLogTime, getHighlightedCode
  }
})
