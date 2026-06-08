import { ref, nextTick, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import JSZip from 'jszip'

export function useAgentWorkspace({
  session, files, generation
}) {
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
  
  // 新增：测试结果、验证结果、成本数据、性能指标
  const testResults = ref(null)
  const validationResults = ref(null)
  const costData = ref({
    totalTokens: 0,
    promptTokens: 0,
    completionTokens: 0,
    totalCostUsd: 0,
    tokensPerSecond: 0,
    modelCosts: {},
    modelTokens: {}
  })
  const performanceMetrics = ref({
    generationSpeed: 0,
    filesPerMinute: 0,
    avgFileTime: 0,
    totalDuration: 0,
    llmCalls: 0,
    retryCount: 0
  })

  const addLog = (level, message) => {
    logs.value.push({ level, message, timestamp: new Date().toISOString() })
    nextTick(() => {
      if (logsContainer.value) {
        logsContainer.value.scrollTop = logsContainer.value.scrollHeight
      }
    })
  }

  const addDetail = (category, description) => {
    executionDetails.value.push({
      category, description, timestamp: new Date().toISOString()
    })
  }

  const showFileDiff = (fileDiffs, filePath, showDiffModal, selectedDiffFile) => {
    const diff = fileDiffs.value.find(d => d.path === filePath)
    if (diff) {
      selectedDiffFile.value = diff
      showDiffModal.value = true
    } else {
      ElMessage.info('该文件没有变更记录')
    }
  }

  const hasFileDiff = (fileDiffs, filePath) => {
    return fileDiffs.value.some(d => d.path === filePath)
  }

  const handleFileSelect = async (file, importing) => {
    if (!file) return
    await importZipFile(file, importing)
  }

  const importZipFile = async (file, importing) => {
    importing.zip.value = true
    importing.progress.value = { current: 0, total: 0, currentFile: '' }
    try {
      const zip = await JSZip.loadAsync(file)
      const entries = Object.keys(zip.files)
      const projectFiles = entries.filter(e => !e.endsWith('/'))
      importing.progress.value.total = projectFiles.length
      const importedFiles = []
      for (const entry of projectFiles) {
        importing.progress.value.currentFile = entry
        importing.progress.value.current++
        const content = await zip.files[entry].async('string')
        importedFiles.push({ path: entry, content, name: entry.split('/').pop() })
      }
      files.generatedFiles = importedFiles
      files.fileDiffs = importedFiles.map(f => ({
        path: f.path, oldContent: '', newContent: f.content, operation: 'create'
      }))
      importing.show.value = false
      ElMessage.success(`成功导入 ${projectFiles.length} 个文件`)
      addLog('success', `导入项目: ${file.name} (${projectFiles.length} 个文件)`)
      if (!session.currentSessionId) {
        session.createNewSession({})
      }
    } catch (error) {
      console.error('ZIP 导入失败:', error)
      ElMessage.error(`导入失败: ${error.message}`)
    } finally {
      importing.zip.value = false
      importing.progress.value = { current: 0, total: 0, currentFile: '' }
    }
  }

  const downloadFile = (file) => {
    if (!file) return
    try {
      const blob = new Blob([file.content], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = file.path.split('/').pop() || 'file'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      ElMessage.success(`文件 ${file.path.split('/').pop()} 已保存`)
    } catch (error) {
      ElMessage.error('保存文件失败')
    }
  }

  const copyFileContent = async () => {
    if (files.selectedFile) {
      await navigator.clipboard.writeText(files.selectedFile.content)
      ElMessage.success('已复制到剪贴板')
    }
  }

  const saveFileVersion = (filePath, fileVersions, currentSessionId) => {
    if (!filePath) return
    const file = files.generatedFiles.find(f => f.path === filePath)
    if (!file) return
    if (!fileVersions.value[filePath]) fileVersions.value[filePath] = []
    fileVersions.value[filePath].push({
      content: file.content,
      timestamp: new Date().toISOString(),
      label: `v${fileVersions.value[filePath].length + 1}`
    })
    localStorage.setItem(`file_versions_${currentSessionId.value}`, JSON.stringify(fileVersions.value))
  }

  const restoreVersion = (filePath, versionIndex, fileVersions, currentSessionId, filesArr, selectedFile, showVersionHistoryModal) => {
    const versions = fileVersions.value[filePath]
    if (!versions || !versions[versionIndex]) return
    const fileIndex = filesArr.value.findIndex(f => f.path === filePath)
    if (fileIndex === -1) return
    const currentContent = filesArr.value[fileIndex].content
    if (!fileVersions.value[filePath]) fileVersions.value[filePath] = []
    fileVersions.value[filePath].push({
      content: currentContent,
      timestamp: new Date().toISOString(),
      label: `v${fileVersions.value[filePath].length + 1}`
    })
    filesArr.value[fileIndex].content = versions[versionIndex].content
    if (selectedFile.value?.path === filePath) {
      selectedFile.value.content = versions[versionIndex].content
    }
    localStorage.setItem(`file_versions_${currentSessionId.value}`, JSON.stringify(fileVersions.value))
    showVersionHistoryModal.value = false
    ElMessage.success('已恢复版本')
  }

  const viewVersionDiff = (filePath, versionIndex, fileVersions, filesArr, showDiffModal, selectedDiffFile, showVersionHistoryModal) => {
    const versions = fileVersions.value[filePath]
    if (!versions || !versions[versionIndex]) return
    const currentFile = filesArr.value.find(f => f.path === filePath)
    if (!currentFile) return
    selectedDiffFile.value = {
      path: filePath,
      oldContent: versions[versionIndex].content,
      newContent: currentFile.content,
      operation: 'update'
    }
    showDiffModal.value = true
    showVersionHistoryModal.value = false
  }

  const formatTime = (timestamp) => {
    if (!timestamp) return ''
    const date = new Date(timestamp)
    const diff = Date.now() - date.getTime()
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
    return date.toLocaleDateString()
  }

  const formatLogTime = (timestamp) => {
    const date = new Date(timestamp)
    return date.toLocaleTimeString()
  }

  return reactive({
    logs, executionDetails, thinkingMessages, pendingDecisions,
    decisionAnswers, decisionHistory, logsContainer,
    currentAgent, currentModel, currentProjectPath,
    testResults, validationResults, costData, performanceMetrics,
    addLog, addDetail, showFileDiff, hasFileDiff,
    handleFileSelect, importZipFile, downloadFile, copyFileContent,
    saveFileVersion, restoreVersion, viewVersionDiff,
    formatTime, formatLogTime
  })
}
