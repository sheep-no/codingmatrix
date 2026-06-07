<template>
  <div class="agent-page">
    <!-- 顶部栏 -->
    <AgentTopBar
      :status="agentStatus"
      :cost-data="workspace.costData"
      :has-files="generatedFiles.length > 0"
      :prompt="projectPrompt || ''"
      @open-upload="backend.showUploadModal = true"
      @open-settings="openSettingsWithBackend"
      @save-project="saveProjectToBackend"
      @open-performance="openPerformancePanel"
      @open-learning="openLearningPanel"
      @analyze-complexity="analyzeRequirementComplexity(projectPrompt)"
    />

    <div class="agent-main">
      <!-- 左侧栏 -->
      <AgentSidebar
        :session-id="sessionId"
        :sessions="sessionHistory"
        :has-files="generatedFiles.length > 0"
        :file-count="generatedFiles.length"
        :categories="files.fileCategories"
        :search-query="files.fileSearchQuery"
        :selected-path="selectedFilePath"
        @new-session="doCreateNewSession"
        @switch-session="doSwitchSession"
        @delete-session="doDeleteSession"
        @update:search-query="files.fileSearchQuery = $event"
        @toggle-category="toggleCategory"
        @select-file="selectFile"
      />

      <!-- 中间工作区 -->
      <div class="agent-center">
        <AgentWorkspace
          :stages="workflowStages"
          :overall-progress="getOverallProgress"
          :eta="getETA"
          :decisions="workspace.pendingDecisions"
          :decision-answers="workspace.decisionAnswers"
          :thinking-messages="workspace.thinkingMessages"
          :execution-steps="workspace.executionDetails"
          :logs="workspace.logs"
          :test-results="workspace.testResults"
          :validation-results="workspace.validationResults"
          @select-decision="(id, label) => workspace.decisionAnswers[id] = label"
          @use-default="(id) => { const d = workspace.pendingDecisions.find(x => x.id === id); if (d?.default) workspace.decisionAnswers[id] = d.default }"
          @submit-decision="doSubmitDecision"
          @clear-thinking="workspace.thinkingMessages = []"
          @clear-steps="workspace.executionDetails = []"
          @clear-logs="workspace.logs = []"
        />
        <!-- 底部输入框 -->
        <AgentInputBar
          :prompt="projectPrompt || ''"
          :placeholder-text="getPlaceholder"
          :generating="isGenerating"
          :has-files="generatedFiles.length > 0"
          :dynamic-models="dynamicModels"
          :selected-provider-model="selectedProviderModel"
          @update:prompt="session.projectPrompt = $event"
          @update:selected-provider-model="selectedProviderModel = $event"
          @generate="generateProject"
          @regenerate="regenerateProject"
          @clear="clearAllState"
          @stop="doStopSession"
        />
      </div>

      <!-- 右侧文件预览 -->
      <AgentFilePanel
        :selected-file="selectedFile"
        :highlighted-code="getHighlightedCode"
        :line-count="getLineCount || 0"
        :file-size="formatFileSize"
        :language="getLanguage"
        :has-diff="hasFileDiff"
        :file-complexity="selectedFile?.complexity || null"
        @show-diff="showFileDiff(selectedFilePath)"
        @save-version="saveFileVersion(selectedFilePath)"
        @version-history="doOpenVersionHistory(selectedFilePath)"
        @copy="copyFileContent"
        @download="downloadFile(selectedFile)"
        @delete-file="deleteFileFromBackend(selectedFilePath, workspace.currentProjectPath)"
      />
    </div>

    <!-- Modals -->
    <UploadModal v-model="backend.showUploadModal" @upload="(f) => handleFileSelect(f)" />
    <SettingsModal v-model="backend.showSettingsModal" :settings="backend.settings" :concurrent-limits="backend.concurrentLimits" :cache-stats="backend.cacheStats" @save="saveSettings" @copy="copySettingsToClipboard" @export="exportPerformanceData" @clear-cache="clearBackendCache" @open-api-key="goToApiKeySettings" @open-model-config="goToModelConfig" />
    <LearningModal v-model="backend.showLearningModal" :learning-stats="backend.learningStats" />
    <PerformanceModal v-model="backend.showPerformanceModal" :performance-stats="backend.performanceStats" />
    <VersionHistoryModal v-model="backend.showVersionHistoryModal" :file="selectedFile" :file-versions="backend.fileVersions" :snapshots="backend.backendSnapshots" @restore="(i) => restoreVersion(i)" @view-diff="(i) => viewVersionDiff(i)" @rollback="rollback" />
    <DiffModal v-model="backend.showDiffModal" :diff="backend.selectedDiffFile" />
  </div>
</template>

<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useApiKeyStore } from '@/stores/apikey'
import { useProviderStore } from '@/stores/providers'
import { useAgentSession } from '@/composables/useAgentSession'
import { useAgentGeneration } from '@/composables/useAgentGeneration'
import { useAgentFiles } from '@/composables/useAgentFiles'
import { useAgentWorkspace } from '@/composables/useAgentWorkspace'
import { useAgentStreaming } from '@/composables/useAgentStreaming'
import { useAgentBackend } from '@/composables/useAgentBackend'

import AgentTopBar from '@/components/agent/AgentTopBar.vue'
import AgentSidebar from '@/components/agent/AgentSidebar.vue'
import AgentWorkspace from '@/components/agent/AgentWorkspace.vue'
import AgentInputBar from '@/components/agent/AgentInputBar.vue'
import AgentFilePanel from '@/components/agent/AgentFilePanel.vue'
import UploadModal from '@/components/agent/modals/UploadModal.vue'
import SettingsModal from '@/components/agent/modals/SettingsModal.vue'
import LearningModal from '@/components/agent/modals/LearningModal.vue'
import PerformanceModal from '@/components/agent/modals/PerformanceModal.vue'
import VersionHistoryModal from '@/components/agent/modals/VersionHistoryModal.vue'
import DiffModal from '@/components/agent/modals/DiffModal.vue'

const userStore = useUserStore()
const apiKeyStore = useApiKeyStore()
const providerStore = useProviderStore()
const router = useRouter()
const projectApi = window.api || {}

const selectedProviderModel = ref('')
const projectName = ref('')

// ========== Composables ==========
const session = useAgentSession()
const generation = useAgentGeneration()
const files = useAgentFiles()
const workspace = useAgentWorkspace({ session, files, generation })
const streaming = useAgentStreaming(projectApi, workspace, files, generation, session)
const backend = useAgentBackend(projectApi, workspace, files, generation)

const goToApiKeySettings = () => {
  backend.showSettingsModal = false
  router.push('/settings?tab=apikey')
}

const goToModelConfig = () => {
  backend.showSettingsModal = false
  router.push('/settings?tab=agent')
}

// ========== Unwrapped values ==========
const sessionId = computed(() => session.currentSessionId)
const sessionHistory = computed(() => session.sessionHistory)
const projectPrompt = computed(() => session.projectPrompt)
const generatedFiles = computed(() => files.generatedFiles.value)
const isGenerating = computed(() => generation.isGenerating)
const workflowStages = computed(() => generation.workflowStages)
const selectedFile = computed(() => files.selectedFile || null)
const templates = computed(() => files.templates)

const agentStatus = computed(() => {
  if (generation.isGenerating) return 'running'
  if (workflowStages.value?.some(s => s.status === 'failed')) return 'failed'
  if (generatedFiles.value.length > 0) return 'completed'
  return 'idle'
})

// ========== Helpers ==========
const getFileType = (path) => files.getFileType(path)
const getPlaceholder = computed(() => generation.getPlaceholder(generatedFiles.value.length > 0))
const getOverallProgress = computed(() => generation.getOverallProgress())
const getETA = computed(() => generation.getETA())
const highlightedCode = ref('')
const getHighlightedCode = computed(() => highlightedCode.value)

watch(selectedFile, async (newFile) => {
  if (newFile) {
    highlightedCode.value = await files.getHighlightedCode()
  } else {
    highlightedCode.value = ''
  }
}, { immediate: true })

const getLineCount = computed(() => files.getLineCount(selectedFile.value?.content))
const formatFileSize = computed(() => selectedFile.value ? files.formatFileSize(selectedFile.value.content) : '')
const getLanguage = computed(() => selectedFile.value ? files.getLanguage(selectedFile.value.path) : '')
const hasFileDiff = computed(() => selectedFile.value ? files.hasFileDiff(selectedFile.value.path) : false)
const selectedFilePath = computed(() => selectedFile.value?.path || null)
const dynamicModels = computed(() => providerStore.getAllDynamicModels())

// ========== Actions ==========
const generateProject = () => streaming.streamGenerate(selectedProviderModel.value, projectName.value)
const regenerateProject = async () => {
  if (!session.projectPrompt.trim()) return ElMessage.warning('请输入项目描述')
  files.clearAll()
  workspace.thinkingMessages = []
  workspace.executionDetails = []
  workspace.logs = []
  session.currentSessionId = null
  workspace.currentProjectPath = null
  session.clearSessionState()
  await generateProject()
}
const doStopSession = async () => {
  const hasFiles = generatedFiles.value.length > 0
  try {
    if (hasFiles) {
      await ElMessageBox.confirm(
        '会话结束后项目文件将被清理，是否先下载？',
        '结束会话',
        {
          confirmButtonText: '下载并结束',
          cancelButtonText: '直接结束',
          type: 'warning',
          distinguishCancelAndClose: true
        }
      )
      await backend.downloadProject(workspace.currentProjectPath)
    }
  } catch (action) {
    if (action === 'close') return
  }
  await backend.stopSession(session.currentSessionId)
  generation.isGenerating = false
  session.currentSessionId = null
}
const doSubmitDecision = async () => {
  await backend.submitDecision(session.currentSessionId)
}
const clearAllState = () => {
  files.clearAll()
  workspace.thinkingMessages = []
  workspace.executionDetails = []
  workspace.logs = []
  session.currentSessionId = null
  workspace.currentProjectPath = null
  session.projectPrompt = ''
  session.clearSessionState()
  generation.resetStages()
  generation.resetState()
  ElMessage.success('已清空所有状态')
}

// ========== Session ==========
const doCreateNewSession = () => session.createNewSession({
  _generation: generation,
  _workspace: workspace,
  _files: files,
  workflowStages: generation.workflowStages,
  pendingDecisions: workspace.pendingDecisions,
  decisionHistory: workspace.decisionHistory,
  generatedFiles: files.generatedFiles,
  thinkingMessages: workspace.thinkingMessages,
  executionDetails: workspace.executionDetails,
  logs: workspace.logs,
  currentPhase: generation.currentPhase,
  currentStep: generation.currentStep,
  totalSteps: generation.totalSteps,
  startTime: generation.startTime,
  modelAssignments: generation.modelAssignments,
  recoveryAttempts: generation.recoveryAttempts
})
const doSwitchSession = (id) => session.switchSession(id, {
  _generation: generation,
  _workspace: workspace,
  _files: files,
  workflowStages: generation.workflowStages,
  pendingDecisions: workspace.pendingDecisions,
  decisionHistory: workspace.decisionHistory,
  generatedFiles: files.generatedFiles,
  thinkingMessages: workspace.thinkingMessages,
  executionDetails: workspace.executionDetails,
  logs: workspace.logs,
  currentPhase: generation.currentPhase,
  currentStep: generation.currentStep,
  totalSteps: generation.totalSteps,
  startTime: generation.startTime,
  modelAssignments: generation.modelAssignments,
  recoveryAttempts: generation.recoveryAttempts
})
const doDeleteSession = (id) => session.deleteSession(id, () => {
  files.generatedFiles.value = []
  workspace.logs = []
  workspace.thinkingMessages = []
})

// ========== File Operations ==========
const showFileDiff = (p) => workspace.showFileDiff(files.fileDiffs, p, backend.showDiffModal, backend.selectedDiffFile)
const saveFileVersion = (p) => workspace.saveFileVersion(p, backend.fileVersions, session.currentSessionId)
const restoreVersion = (i) => workspace.restoreVersion(
  files.selectedFile?.path, i, backend.fileVersions,
  session.currentSessionId, files.generatedFiles, files.selectedFile,
  backend.showVersionHistoryModal
)
const viewVersionDiff = (i) => workspace.viewVersionDiff(
  files.selectedFile?.path, i, backend.fileVersions,
  files.generatedFiles, backend.showDiffModal, backend.selectedDiffFile,
  backend.showVersionHistoryModal
)
const copyFileContent = () => workspace.copyFileContent()
const downloadFile = (f) => workspace.downloadFile(f)
const deleteFileFromBackend = (filePath) => backend.deleteFileFromBackend(filePath, workspace.currentProjectPath)
const downloadProject = () => backend.downloadProject(workspace.currentProjectPath)
const useTemplate = (template) => session.projectPrompt = templates.value[template]?.prompt || ''
const toggleCategory = (category) => files.toggleCategory(category)
const selectFile = (file) => files.selectFile(file)

// ========== Modal Actions ==========
const openSettingsWithBackend = () => backend.openSettingsWithBackend()
const openLearningPanel = () => backend.openLearningPanel()
const openPerformancePanel = () => backend.openPerformancePanel()
const analyzeRequirementComplexity = (p) => backend.analyzeRequirementComplexity(p)
const doOpenVersionHistory = (f) => backend.openVersionHistoryWithBackend(f, session.currentSessionId)
const saveProjectToBackend = () => backend.saveProjectToBackend()
const handleFileSelect = (f) => workspace.handleFileSelect(f, {
  zip: backend.uploadingZip,
  progress: backend.importProgress,
  show: backend.showUploadModal
})
const saveSettings = (localSettings) => {
  backend.settings = localSettings
  backend.saveSettings()
}
const copySettingsToClipboard = (localSettings) => {
  backend.copySettingsToClipboard()
}
const exportPerformanceData = () => backend.exportPerformanceData()
const clearBackendCache = () => backend.clearBackendCache()
const rollback = (tag) => backend.rollbackToSnapshot(tag, session.currentSessionId)

// ========== Auto-save ==========
watch([() => files.generatedFiles.value?.length, () => session.currentSessionId, () => generation.workflowStages?.length], () => {
  if (session.currentSessionId) {
    session.saveSessionState({
      workflowStages: generation.workflowStages,
      pendingDecisions: workspace.pendingDecisions,
      decisionHistory: workspace.decisionHistory,
      generatedFiles: files.generatedFiles,
      thinkingMessages: workspace.thinkingMessages,
      executionDetails: workspace.executionDetails,
      logs: workspace.logs,
      currentPhase: generation.currentPhase,
      currentStep: generation.currentStep,
      totalSteps: generation.totalSteps,
      startTime: generation.startTime,
      modelAssignments: generation.modelAssignments,
      recoveryAttempts: generation.recoveryAttempts
    })
  }
}, { deep: true })

onMounted(() => {
  apiKeyStore.loadFromStorage()
  providerStore.loadFromStorage()
  providerStore.listProviders().catch(() => {})
  session.loadSessionHistory()
  backend.loadSettings()
  session.startAutoSave(
    () => files.generatedFiles.value.length > 0 || workspace.logs.length > 0,
    () => session.saveSessionState({
      workflowStages: generation.workflowStages,
      pendingDecisions: workspace.pendingDecisions,
      decisionHistory: workspace.decisionHistory,
      generatedFiles: files.generatedFiles,
      thinkingMessages: workspace.thinkingMessages,
      executionDetails: workspace.executionDetails,
      logs: workspace.logs,
      currentPhase: generation.currentPhase,
      currentStep: generation.currentStep,
      totalSteps: generation.totalSteps,
      startTime: generation.startTime,
      modelAssignments: generation.modelAssignments,
      recoveryAttempts: generation.recoveryAttempts
    })
  )
  backend.loadBackendSettings().catch(() => {})
})
onBeforeUnmount(() => {
  session.stopAutoSave()
  if (session.currentSessionId) session.clearSessionState()
})
</script>
