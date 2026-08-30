import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'

export function useAgentBackend(projectApi, workspace, files, generation) {
  const { addLog } = workspace
  const { generatedFiles, selectedFile } = files

  // State
  const savedProjects = ref([])
  const isLoadingProjects = ref(false)
  const projectsError = ref(null)
  const fileVersions = ref({})
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
  const userSkills = ref([])
  const workspaceSkills = ref([])
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

  const loadSavedProjects = async () => {
    if (isLoadingProjects.value) return
    isLoadingProjects.value = true
    projectsError.value = null
    try {
      const response = await projectApi.listSavedProjects()
      savedProjects.value = response.projects || []
    } catch (error) {
      console.error('加载项目列表失败:', error)
      projectsError.value = '加载项目列表失败'
      ElMessage.error('加载项目列表失败')
    } finally {
      isLoadingProjects.value = false
    }
  }

  const loadAvailableSkills = async () => {
    try {
      const [userResponse, sessions] = await Promise.all([
        projectApi.listSkills?.() || [],
        projectApi.listAgentHostSessions?.() || []
      ])
      userSkills.value = Array.isArray(userResponse) ? userResponse : userResponse.skills || []
      const latestSession = (sessions || []).find(session => session.control_status !== 'cancelled')
      workspaceSkills.value = latestSession ? Object.values(latestSession.skills || {}) : []
    } catch (error) {
      console.error('加载 Skills 失败:', error)
    }
  }

  const saveProjectToBackend = async () => {
    if (generatedFiles.value.length === 0) {
      ElMessage.warning('没有可保存的文件')
      return
    }
    try {
      const projectName = `项目_${workspace.formatTime(Date.now())}`
      const projectData = generatedFiles.value.map(f => ({
        path: f.path, content: f.content, name: f.path.split('/').pop()
      }))
      await projectApi.saveProject(projectName, '由 AI Agent 生成的项目', JSON.stringify(projectData))
      ElMessage.success('项目已保存到数据库')
      addLog('success', `项目已保存: ${projectName}`)
    } catch (error) {
      console.error('保存项目失败:', error)
      ElMessage.error('保存项目失败')
    }
  }

  const downloadProject = async (currentProjectPath) => {
    if (!currentProjectPath) {
      ElMessage.warning('当前没有可下载的项目')
      return
    }
    try {
      ElMessage.info('正在准备下载...')
      await projectApi.downloadProject(currentProjectPath)
      ElMessage.success('下载已开始')
    } catch (error) {
      console.error('下载失败:', error)
      ElMessage.error('下载失败，请重试')
    }
  }

  const deleteFileFromBackend = async (filePath, currentProjectPath) => {
    if (!currentProjectPath) {
      ElMessage.warning('请先选择一个项目')
      return
    }
    try {
      await projectApi.deleteProjectFile({ project_path: currentProjectPath, file_path: filePath })
      const idx = generatedFiles.value.findIndex(f => f.path === filePath)
      if (idx !== -1) generatedFiles.value.splice(idx, 1)
      if (selectedFile.value?.path === filePath) selectedFile.value = null
      ElMessage.success(`文件 ${filePath} 已删除`)
    } catch (error) {
      console.error('删除文件失败:', error)
      ElMessage.error('删除文件失败')
    }
  }

  const loadPerformanceMetrics = async () => {
    isLoadingPerformance.value = true
    try {
      const [metricsResponse, trendsResponse] = await Promise.all([
        projectApi.getPerformanceMetrics(), projectApi.getPerformanceTrends()
      ])
      backendPerformanceData.value = metricsResponse
      backendPerformanceTrends.value = trendsResponse
      return { metrics: metricsResponse, trends: trendsResponse }
    } catch (error) {
      console.error('加载性能数据失败:', error)
      return null
    } finally {
      isLoadingPerformance.value = false
    }
  }

  const openPerformancePanel = async () => {
    showPerformanceModal.value = true
    const data = await loadPerformanceMetrics()
    if (!data) return
    const metrics = data.metrics.metrics || {}
    const trends = data.trends.trends || {}
    performanceStats.value = {
      startTime: generation.startTime ? new Date(generation.startTime).toLocaleTimeString() : '未知',
      endTime: new Date().toLocaleTimeString(),
      totalFiles: generatedFiles.value.length,
      totalTokens: generatedFiles.value.reduce((sum, f) => sum + f.content.length, 0),
      avgTokenPerFile: generatedFiles.value.length > 0
        ? Math.round(generatedFiles.value.reduce((sum, f) => sum + f.content.length, 0) / generatedFiles.value.length)
        : 0,
      stageTimings: (generation.workflowStages || []).map(s => ({ name: s.name, status: s.status, progress: s.progress })),
      modelCalls: Object.values(generation.modelAssignments || {}).reduce((sum, m) => sum + m.calls, 0),
      errorCount: (workspace.logs || []).filter(l => l.level === 'error').length,
      successRate: (workspace.logs || []).length > 0
        ? Math.round((((workspace.logs || []).length - (workspace.logs || []).filter(l => l.level === 'error').length) / (workspace.logs || []).length) * 100)
        : 100,
      moduleMetrics: Object.keys(trends).map(moduleName => ({ name: moduleName, ...trends[moduleName] }))
    }
  }

  const loadSnapshots = async (sessionId) => {
    if (!sessionId) { ElMessage.warning('请先启动一个会话'); return }
    isLoadingSnapshots.value = true
    try {
      const response = await projectApi.getSnapshots(sessionId)
      backendSnapshots.value = response.snapshots || []
      return backendSnapshots.value
    } catch (error) {
      console.error('加载快照失败:', error)
      return []
    } finally {
      isLoadingSnapshots.value = false
    }
  }

  const rollbackToSnapshot = async (tag, sessionId) => {
    if (!sessionId) return
    try {
      await projectApi.rollbackToSnapshot(sessionId, { tag })
      ElMessage.success(`已回滚到快照 ${tag}`)
      addLog('warning', `回滚到快照: ${tag}`)
      await loadSnapshots(sessionId)
    } catch (error) {
      console.error('回滚失败:', error)
      ElMessage.error('回滚失败')
    }
  }

  const loadBackendSettings = async () => {
    isLoadingSettings.value = true
    try {
      const [limitsResponse, cacheResponse, learningResponse] = await Promise.all([
        projectApi.getRecommendedConcurrentLimits(), projectApi.getCacheStats(), projectApi.getLearningStats()
      ])
      concurrentLimits.value = limitsResponse.recommendations || {}
      cacheStats.value = cacheResponse || {}
      learningStats.value = learningResponse || {}
      return true
    } catch (error) {
      console.error('加载后端设置失败:', error)
      return false
    } finally {
      isLoadingSettings.value = false
    }
  }

  const clearBackendCache = async () => {
    try {
      await projectApi.clearCache()
      cacheStats.value = {}
      ElMessage.success('缓存已清除')
      await loadBackendSettings()
    } catch (error) {
      console.error('清除缓存失败:', error)
      ElMessage.error('清除缓存失败')
    }
  }

  const exportPerformanceData = async () => {
    try {
      await projectApi.exportPerformance()
      ElMessage.success('性能数据已导出')
    } catch (error) {
      console.error('导出性能数据失败:', error)
      ElMessage.error('导出性能数据失败')
    }
  }

  const saveSettings = () => {
    try {
      localStorage.setItem('agent_settings', JSON.stringify(settings.value))
      showSettingsModal.value = false
      ElMessage.success('设置已保存')
    } catch (error) {
      ElMessage.error('保存设置失败')
    }
  }

  const loadSettings = () => {
    try {
      const saved = localStorage.getItem('agent_settings')
      if (saved) settings.value = { ...settings.value, ...JSON.parse(saved) }
    } catch (error) {
      console.warn('加载设置失败:', error)
    }
  }

  const copySettingsToClipboard = () => {
    try {
      navigator.clipboard.writeText(JSON.stringify(settings.value, null, 2))
      ElMessage.success('配置已复制到剪贴板')
    } catch (error) {
      ElMessage.error('复制失败')
    }
  }

  const openSettingsWithBackend = async () => {
    showSettingsModal.value = true
    await loadBackendSettings()
  }

  const openLearningPanel = async () => {
    showLearningModal.value = true
    try {
      learningStats.value = await projectApi.getLearningStats()
    } catch (error) {
      console.error('加载学习统计失败:', error)
    }
  }

  const openVersionHistoryWithBackend = async (file, sessionId) => {
    if (!sessionId) {
      ElMessage.warning('请先启动会话以启用快照功能')
      return
    }
    selectedFile.value = file
    await loadSnapshots(sessionId)
    showVersionHistoryModal.value = true
  }

  const analyzeRequirementComplexity = async (prompt) => {
    if (!prompt.trim()) { ElMessage.warning('请输入需求描述'); return }
    try {
      addLog('info', '正在分析需求复杂度...')
      const response = await projectApi.analyzeComplexity(prompt)
      const c = response
      let message = `复杂度级别: ${c.level}\n预估文件数: ${c.estimated_files}\n`
      message += `前端: ${c.has_frontend ? '是' : '否'}\n后端: ${c.has_backend ? '是' : '否'}\n数据库: ${c.has_database ? '是' : '否'}\n`
      if (c.key_technologies) message += `关键技术: ${c.key_technologies.join(', ')}\n`
      if (c.risk_factors) message += `风险因素: ${c.risk_factors.join(', ')}`
      addLog('info', `复杂度分析完成: ${c.level}`)
      ElMessage({ message, type: 'info', duration: 10000, showClose: true })
    } catch (error) {
      console.error('复杂度分析失败:', error)
      ElMessage.error('复杂度分析失败')
    }
  }

  const stopSession = async (sessionId) => {
    if (sessionId) {
      try {
        await projectApi.stopSession(sessionId)
        addLog('warning', '生成已停止')
      } catch (error) {
        addLog('error', '停止生成失败')
      }
    }
  }

  const submitDecision = async (sessionId) => {
    if (!sessionId || !workspace.pendingDecisions || workspace.pendingDecisions.length === 0) return
    try {
      const decisions = {}
      for (const d of workspace.pendingDecisions) {
        decisions[d.id] = (workspace.decisionAnswers && workspace.decisionAnswers[d.id]) || d.default
      }
      await projectApi.submitDecision(sessionId, decisions)
      workspace.pendingDecisions = []
      workspace.decisionAnswers = {}
      addLog('success', '决策已提交，继续生成')
    } catch (error) {
      addLog('error', '提交决策失败')
    }
  }

  return reactive({
    savedProjects, isLoadingProjects, projectsError, fileVersions,
    backendFileList, isLoadingBackendFiles, backendSnapshots, isLoadingSnapshots,
    concurrentLimits, cacheStats, learningStats, isLoadingSettings,
    backendPerformanceData, backendPerformanceTrends, isLoadingPerformance,
    performanceStats, showSettingsModal, showPerformanceModal, showLearningModal,
    showVersionHistoryModal, showUploadModal, showDiffModal, selectedDiffFile,
    userSkills, workspaceSkills,
    uploadingZip, importProgress, fileInput, settings,
    loadSavedProjects, saveProjectToBackend, downloadProject, deleteFileFromBackend,
    loadPerformanceMetrics, openPerformancePanel, loadSnapshots, rollbackToSnapshot,
    loadBackendSettings, clearBackendCache, exportPerformanceData,
    saveSettings, loadSettings, copySettingsToClipboard,
    openSettingsWithBackend, openLearningPanel, openVersionHistoryWithBackend,
    analyzeRequirementComplexity, stopSession, submitDecision, loadAvailableSkills
  })
}
