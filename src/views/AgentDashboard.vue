<template>
  <div class="agent-page">
    <AgentHeader
      :session-id="sessionId"
      :sessions="sessionHistory"
      :has-files="generatedFiles.length > 0"
      :prompt="projectPrompt || ''"
      @open-settings="openSettingsWithBackend"
      @open-performance="openPerformancePanel"
      @save-project="saveProjectToBackend"
      @open-learning="openLearningPanel"
      @analyze-complexity="analyzeRequirementComplexity(projectPrompt)"
      @open-upload="backend.showUploadModal = true"
      @switch-session="doSwitchSession"
      @new-session="doCreateNewSession"
      @delete-session="doDeleteSession"
    />

    <div class="page-content">
      <AgentInputPanel
        :mode="generationMode || 'create'"
        :prompt="projectPrompt || ''"
        :placeholder-text="getPlaceholder"
        :generating="isGenerating"
        :has-files="generatedFiles.length > 0"
        :file-count="generatedFiles.length"
        :categories="files.fileCategories"
        :search-query="files.fileSearchQuery"
        :filter-type="files.fileFilterType"
        :selected-path="selectedFilePath"
        @update:mode="session.generationMode = $event"
        @update:prompt="session.projectPrompt = $event"
        @update:search-query="files.fileSearchQuery = $event"
        @update:filter-type="files.fileFilterType = $event"
        @generate="generateProject"
        @incremental-generate="incrementalGenerate"
        @debug="startDebug"
        @regenerate="regenerateProject"
        @clear="clearAllState"
        @stop="doStopSession"
        @select-template="useTemplate"
        @toggle-category="toggleCategory"
        @select-file="selectFile"
      />

      <AgentWorkspace
        :stages="workflowStages"
        :overall-progress="getOverallProgress"
        :eta="getETA"
        :decisions="workspace.pendingDecisions"
        :decision-answers="workspace.decisionAnswers"
        :selected-file="selectedFile"
        :file-type="getFileType(selectedFilePath)"
        :highlighted-code="getHighlightedCode"
        :line-count="getLineCount || 0"
        :file-size="formatFileSize"
        :language="getLanguage"
        :has-diff="hasFileDiff"
        :thinking-messages="workspace.thinkingMessages"
        :execution-steps="workspace.executionDetails"
        :logs="workspace.logs"
        @select-decision="(id, label) => workspace.decisionAnswers[id] = label"
        @use-default="(id) => { const d = workspace.pendingDecisions.find(x => x.id === id); if (d?.default) workspace.decisionAnswers[id] = d.default }"
        @submit-decision="doSubmitDecision"
        @show-diff="showFileDiff(selectedFilePath)"
        @save-version="saveFileVersion(selectedFilePath)"
        @version-history="doOpenVersionHistory(selectedFilePath)"
        @copy="copyFileContent"
        @download="downloadFile(selectedFile)"
        @delete-file="deleteFileFromBackend(selectedFilePath, workspace.currentProjectPath)"
        @download-project="downloadProject(workspace.currentProjectPath)"
        @clear-thinking="workspace.thinkingMessages = []"
        @clear-steps="workspace.executionDetails = []"
        @clear-logs="workspace.logs = []"
      />
    </div>

    <!-- Modals -->
    <UploadModal v-model="backend.showUploadModal" @upload="(f) => handleFileSelect(f)" />
    <SettingsModal v-model="backend.showSettingsModal" :settings="backend.settings" :concurrent-limits="backend.concurrentLimits" :cache-stats="backend.cacheStats" @save="saveSettings" @copy="copySettingsToClipboard" @export="exportPerformanceData" @clear-cache="clearBackendCache" />
    <LearningModal v-model="backend.showLearningModal" :learning-stats="backend.learningStats" />
    <PerformanceModal v-model="backend.showPerformanceModal" :performance-stats="backend.performanceStats" />
    <VersionHistoryModal v-model="backend.showVersionHistoryModal" :file="selectedFile" :file-versions="backend.fileVersions" :snapshots="backend.backendSnapshots" @restore="(i) => restoreVersion(i)" @view-diff="(i) => viewVersionDiff(i)" @rollback="rollback" />
    <DiffModal v-model="backend.showDiffModal" :diff="backend.selectedDiffFile" />
  </div>
</template>

<script setup>
/* AgentDashboard - Refactored from 5029 to ~150 lines using composables */
import { ElMessage } from 'element-plus'
import { onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { useUserStore } from '@/stores/user'
import { useAgentSession } from '@/composables/useAgentSession'
import { useAgentGeneration } from '@/composables/useAgentGeneration'
import { useAgentFiles } from '@/composables/useAgentFiles'
import { useAgentWorkspace } from '@/composables/useAgentWorkspace'
import { useAgentStreaming } from '@/composables/useAgentStreaming'
import { useAgentBackend } from '@/composables/useAgentBackend'

import AgentHeader from '@/components/agent/AgentHeader.vue'
import AgentInputPanel from '@/components/agent/AgentInputPanel.vue'
import AgentWorkspace from '@/components/agent/AgentWorkspace.vue'
import UploadModal from '@/components/agent/modals/UploadModal.vue'
import SettingsModal from '@/components/agent/modals/SettingsModal.vue'
import LearningModal from '@/components/agent/modals/LearningModal.vue'
import PerformanceModal from '@/components/agent/modals/PerformanceModal.vue'
import VersionHistoryModal from '@/components/agent/modals/VersionHistoryModal.vue'
import DiffModal from '@/components/agent/modals/DiffModal.vue'

const userStore = useUserStore()
const projectApi = window.api || {}

// ========== Composables ==========
const session = useAgentSession()
const generation = useAgentGeneration()
const files = useAgentFiles()
const workspace = useAgentWorkspace({ session, files, generation })
const streaming = useAgentStreaming(projectApi, workspace, files, generation, session)
const backend = useAgentBackend(projectApi, workspace, files, generation)

// ========== Unwrapped values for child components ==========
const sessionId = computed(() => session.currentSessionId)
const sessionHistory = computed(() => session.sessionHistory)
const generationMode = computed(() => session.generationMode)
const projectPrompt = computed(() => session.projectPrompt)
const generatedFiles = computed(() => files.generatedFiles)
const isGenerating = computed(() => generation.isGenerating)
const workflowStages = computed(() => generation.workflowStages)
const currentPhase = computed(() => generation.currentPhase)
const currentStep = computed(() => generation.currentStep)
const selectedFile = computed(() => files.selectedFile || null)
const templates = computed(() => files.templates)

// ========== Template Helpers ==========
const getFileType = (path) => files.getFileType(path)
const getPlaceholder = computed(() => generation.getPlaceholder(generationMode.value))
const getOverallProgress = computed(() => generation.getOverallProgress())
const getETA = computed(() => generation.getETA())
const getHighlightedCode = computed(() => files.getHighlightedCode(selectedFile.value))
const getLineCount = computed(() => files.getLineCount(selectedFile.value?.content))
const formatFileSize = computed(() => selectedFile.value ? files.formatFileSize(selectedFile.value.content) : '')
const getLanguage = computed(() => selectedFile.value ? files.getLanguage(selectedFile.value.path) : '')
const hasFileDiff = computed(() => selectedFile.value ? files.hasFileDiff(selectedFile.value.path) : false)
const selectedFilePath = computed(() => selectedFile.value?.path || null)

// ========== Generation Actions ==========
const generateProject = () => streaming.streamGenerate('create')
const incrementalGenerate = () => streaming.streamGenerate('modify')
const startDebug = async () => {
  if (!session.projectPrompt.trim()) return ElMessage.warning('请输入问题描述')
  streaming.streamGenerate('debug')
}
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
  workspace.currentProjectPath = []
  session.projectPrompt = ''
  session.clearSessionState()
  generation.resetStages()
  generation.resetState()
  ElMessage.success('已清空所有状态')
}

// ========== Session Actions ==========
const doCreateNewSession = () => session.createNewSession({
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
  files.generatedFiles = []
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
const deleteFileFromBackend = (p) => backend.deleteFileFromBackend(p, workspace.currentProjectPath)
const downloadProject = () => backend.downloadProject(workspace.currentProjectPath)

// ========== File Actions (delegated to files composable) ==========
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
watch([() => files.generatedFiles?.length, () => session.currentSessionId, () => generation.workflowStages?.length], () => {
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
  session.loadSessionHistory()
  backend.loadSettings()
  session.startAutoSave(
    () => files.generatedFiles.length > 0 || workspace.logs.length > 0,
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

<style scoped>
/* 组件特定样式已移至全局 agent-layout.css */
/* 保留此空 style 标签以防构建问题 */
</style>
