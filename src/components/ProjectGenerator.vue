<template>
  <div v-if="visible" class="project-generator-overlay" @click.self="close">
    <div class="project-generator-modal">
      <!-- 头部 -->
      <div class="modal-header">
        <div class="header-left">
          <div class="header-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div>
            <h2>AI 项目生成</h2>
            <p class="header-subtitle">多角色协作，智能生成完整项目</p>
          </div>
        </div>
        <button class="close-btn" @click="close">×</button>
      </div>

      <div class="modal-body">
        <!-- 生成状态显示 -->
        <div v-if="isGenerating" class="generation-progress">
          <!-- 进度概览 -->
          <div class="progress-overview">
            <div class="progress-status">
              <div class="status-indicator">
                <span class="pulse-dot"></span>
                <span class="status-text">{{ progressMessage }}</span>
              </div>
              <div class="progress-meta">
                <span class="meta-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="2" y="3" width="20" height="14" rx="2"/>
                    <path d="M8 21h8"/>
                    <path d="M12 17v4"/>
                  </svg>
                  步骤 {{ currentStep }}/{{ totalSteps }}
                </span>
                <span class="meta-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                  </svg>
                  文件 {{ filesCreated }} 个
                </span>
              </div>
            </div>
            <div class="progress-bar-wrapper">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
              </div>
              <span class="progress-percent">{{ Math.round(progressPercent) }}%</span>
            </div>
          </div>

          <!-- 阶段指示器 -->
          <div class="phase-indicators">
            <div
              v-for="(phase, idx) in phases"
              :key="phase.key"
              class="phase-item"
              :class="{
                active: currentPhase === phase.key,
                completed: completedPhases.includes(phase.key),
                pending: !completedPhases.includes(phase.key) && currentPhase !== phase.key
              }"
            >
              <div class="phase-icon">
                <span v-if="completedPhases.includes(phase.key)">✓</span>
                <span v-else-if="currentPhase === phase.key" class="phase-spinner"></span>
                <span v-else>{{ idx + 1 }}</span>
              </div>
              <span class="phase-label">{{ phase.label }}</span>
            </div>
          </div>

          <!-- 流式输出日志 -->
          <div ref="logsContainer" class="generation-logs">
            <!-- 思考内容按 agent 分组展示 -->
            <div v-if="thinkingGroups.length > 0" class="thinking-log-block">
              <details
                v-for="(group, idx) in thinkingGroups"
                :key="group.agent"
                class="thinking-log-details"
                :open="idx === thinkingGroups.length - 1 && isGenerating"
              >
                <summary class="thinking-log-summary">
                  <span class="thinking-log-label">
                    {{ group.agent }} 思考过程
                    <span v-if="group.model" class="thinking-model">({{ group.model }})</span>
                  </span>
                  <svg class="chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                </summary>
                <div class="thinking-log-content markdown-body" v-html="renderThinkingMarkdown(group.content)"></div>
              </details>
            </div>
            <!-- 普通日志 -->
            <div v-for="(log, index) in logs" :key="index" class="log-item" :class="log.type">
              <span class="log-time">{{ formatTime(log.time) }}</span>
              <span class="log-icon" v-html="getLogIcon(log.type)"></span>
              <span class="log-message">{{ log.message }}</span>
            </div>
          </div>
        </div>

        <!-- 输入表单 -->
        <div v-else class="generation-form">
          <!-- 保存的项目列表 -->
          <div v-if="savedProjects.length > 0" class="saved-projects-section">
            <div class="section-header">
              <h4>已保存的项目</h4>
              <span class="project-count">{{ savedProjects.length }}/3</span>
              <button class="btn-small" @click="loadSavedProjects">刷新</button>
            </div>
            <div class="saved-projects-list">
              <div
                v-for="project in savedProjects"
                :key="project.id"
                class="saved-project-item"
                @click="loadProject(project.id)"
              >
                <div class="project-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  </svg>
                </div>
                <div class="project-details">
                  <span class="project-name">{{ project.name }}</span>
                  <span class="project-date">{{ formatDate(project.updated_at) }}</span>
                </div>
                <button class="btn-delete" title="删除" @click.stop="confirmDeleteProject(project)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <div class="form-group">
            <label>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              项目需求描述
            </label>
            <textarea
              v-model="form.requirement"
              placeholder="描述你想要生成的项目，例如：&#10;• 生成一个五子棋小游戏&#10;• 创建一个 Todo 管理 Web 应用&#10;• 实现一个 RESTful API 服务"
              rows="6"
              class="form-textarea"
            ></textarea>
          </div>

          <div class="form-group">
            <label>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              会话 ID
            </label>
            <input
              v-model="form.sessionId"
              type="text"
              readonly
              class="form-input session-id-readonly"
              :placeholder="isGenerating ? '生成中...' : '点击生成新项目时自动创建'"
            />
            <p class="field-hint">每次新项目会自动清理旧会话资源，后期管理员可开启多会话模式</p>
          </div>

          <div class="form-info">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 16v-4"/>
              <path d="M12 8h.01"/>
            </svg>
            <p>系统将根据项目复杂度自动分配合适的 AI 模型，通过多角色协作生成高质量代码。</p>
            <p class="info-warning">每次开始新项目会自动清理之前的会话资源（项目文件、历史记录），请谨慎操作。</p>
          </div>
        </div>
      </div>

      <!-- 文件预览面板 -->
      <FilePreviewPanel
        v-if="showFilePreview"
        :files="projectFiles"
        :visible="showFilePreview"
        @close="showFilePreview = false"
        @select="onSelectProjectFile"
        @copy="onCopyFileContent"
        @delete="onDeleteFile"
      />

      <!-- 快照管理面板 -->
      <div v-if="showSnapshotPanel" class="snapshot-panel">
        <div class="panel-header">
          <h3>快照管理</h3>
          <button class="close-panel" @click="showSnapshotPanel = false">×</button>
        </div>
        <div class="snapshot-body">
          <div v-if="snapshots.length === 0" class="snapshot-empty">
            <p>暂无快照</p>
          </div>
          <div v-else class="snapshot-list">
            <div
              v-for="(snapshot, index) in snapshots"
              :key="snapshot.tag || snapshot.name || index"
              class="snapshot-item"
            >
              <div class="snapshot-info">
                <span class="snapshot-tag">{{ snapshot.tag || snapshot.name }}</span>
                <span class="snapshot-date">{{ snapshot.created_at || snapshot.date || '' }}</span>
              </div>
              <div class="snapshot-actions">
                <button class="btn-small" @click="rollbackToSnapshot(snapshot.tag || snapshot.name)">回滚</button>
                <button
                  v-if="index < snapshots.length - 1"
                  class="btn-small"
                  @click="compareSnapshots(
                    snapshot.tag || snapshot.name,
                    snapshots[index + 1].tag || snapshots[index + 1].name
                  )"
                >对比</button>
              </div>
            </div>
          </div>
          <div v-if="diffResult" class="diff-view">
            <h4>快照差异</h4>
            <pre class="diff-code"><code>{{ JSON.stringify(diffResult, null, 2) }}</code></pre>
          </div>
        </div>
      </div>

      <!-- 知识库面板 -->
      <div v-if="showKnowledgePanel" class="knowledge-panel">
        <div class="panel-header">
          <h3>知识库</h3>
          <button class="close-panel" @click="showKnowledgePanel = false">×</button>
        </div>
        <div class="knowledge-body">
          <div class="knowledge-add">
            <textarea
              v-model="newKnowledgeContent"
              placeholder="添加知识条目..."
              rows="3"
              class="knowledge-input"
            />
            <input
              v-model="newKnowledgeCategory"
              placeholder="分类（可选）"
              class="knowledge-category"
            />
            <button class="btn-small" @click="addKnowledge">添加</button>
          </div>
          <div class="knowledge-search">
            <input
              v-model="knowledgeSearchQuery"
              placeholder="搜索知识库..."
              class="knowledge-search-input"
              @keyup.enter="searchKnowledge"
            />
            <button class="btn-small" @click="searchKnowledge">搜索</button>
          </div>
          <div v-if="knowledgeSearchResults.length > 0" class="knowledge-results">
            <div v-for="result in knowledgeSearchResults" :key="result.id" class="knowledge-result">
              <p>{{ result.content }}</p>
              <span class="knowledge-score">相似度: {{ (result.score * 100).toFixed(1) }}%</span>
            </div>
          </div>
          <div v-else class="knowledge-list">
            <div v-for="entry in knowledgeEntries" :key="entry.id" class="knowledge-item">
              <p>{{ entry.content }}</p>
              <span v-if="entry.category" class="knowledge-category-tag">{{ entry.category }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 对话历史面板 -->
      <div v-if="showConversationPanel" class="knowledge-panel">
        <div class="panel-header">
          <h3>对话历史</h3>
          <button class="close-panel" @click="showConversationPanel = false">×</button>
        </div>
        <div class="knowledge-body">
          <div v-if="conversationHistory.length === 0" class="snapshot-empty">
            <p>暂无对话历史</p>
          </div>
          <div v-else class="conversation-list">
            <div
              v-for="(msg, index) in conversationHistory"
              :key="index"
              class="conversation-item"
              :class="msg.role"
            >
              <div class="conversation-role">{{ msg.role === 'user' ? '用户' : '助手' }}</div>
              <div class="conversation-content">{{ msg.content }}</div>
              <div class="conversation-time">{{ formatConversationTime(msg.timestamp) }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部按钮 -->
      <div class="modal-footer">
        <button
          v-if="!isGenerating && !generationComplete"
          class="btn btn-secondary"
          @click="close"
        >
          取消
        </button>
        <button
          v-if="!isGenerating && !generationComplete && savedProjects.length < 3"
          class="btn btn-save"
          :disabled="!form.requirement.trim()"
          @click="saveCurrentProject"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
            <polyline points="17 21 17 13 7 13 7 21"/>
            <polyline points="7 3 7 8 15 8"/>
          </svg>
          保存项目
        </button>
        <button
          v-if="hasStopped && !isGenerating && !generationComplete"
          class="btn btn-warning"
          :disabled="!form.requirement.trim()"
          @click="startGeneration"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
          继续生成
        </button>
        <button
          v-if="!hasStopped && !isGenerating && !generationComplete"
          class="btn btn-primary"
          :disabled="!form.requirement.trim()"
          @click="startGeneration"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
          开始生成
        </button>
        <button v-if="isGenerating" class="btn btn-danger" @click="stopGeneration">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
          </svg>
          停止生成
        </button>
        <button v-if="generationComplete" class="btn btn-download" @click="handleDownload">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          下载项目
        </button>
        <button v-if="generationComplete" class="btn btn-info" @click="showFilePreview = true; loadProjectFiles()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          文件预览
        </button>
        <button v-if="generationComplete && form.sessionId" class="btn btn-info" @click="showSnapshotPanel = !showSnapshotPanel; loadSnapshots()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
          快照管理
        </button>
        <button v-if="generationComplete" class="btn btn-info" @click="showKnowledgePanel = !showKnowledgePanel; loadKnowledge()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
          </svg>
          知识库
        </button>
        <button v-if="generationComplete" class="btn btn-info" @click="showConversationPanel = !showConversationPanel; loadConversationHistory()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          对话历史
        </button>
        <button v-if="generationComplete" class="btn btn-warning" @click="enableIncrementalModify">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 2L11 13"/>
            <path d="M22 2L15 22L11 13L2 9L22 2Z"/>
          </svg>
          发送
        </button>
        <button v-if="generationComplete" class="btn btn-success" @click="close">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 6L9 17l-5-5"/>
          </svg>
          完成
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { useGithubStore } from '@/stores/github'
  import { useApiKeyStore } from '@/stores/apikey'
  import { useRouter } from 'vue-router'
  import GithubConfigPanel from './GithubConfigPanel.vue'
  import FilePreviewPanel from './FilePreviewPanel.vue'
  import { createProjectClient } from '@/utils/api/project'
  import { consumeJsonStream } from '@/utils/streamParser'
  import { api } from '@/utils/api/index'

  // ========== 1. Props & Emit ==========
  const router = useRouter()
  const props = defineProps({
    visible: {
      type: Boolean,
      default: false
    }
  })

  const emit = defineEmits(['close'])

  // API Key Store
  const apiKeyStore = useApiKeyStore()

  // ========== 2. Reactive State ==========
  const form = ref({
    requirement: '',
    sessionId: ''
  })
  const isGenerating = ref(false)
  const generationComplete = ref(false)
  const hasStopped = ref(false)
  const progressMessage = ref('')
  const currentStep = ref(0)
  const totalSteps = ref(0)
  const filesCreated = ref(0)
  const logs = ref([])
  const logsContainer = ref(null)
  const outputDir = ref('')
  const currentPhase = ref('')
  const completedPhases = ref([])
  const savedProjects = ref([])
  const thinkingContent = ref('')

  // 思考内容按 agent 分组
  const thinkingGroups = ref([])
  const _thinkingMap = {}  // agent -> { content, model }

  // 文件预览
  const projectFiles = ref([])
  const fileContent = ref('')
  const showFilePreview = ref(false)
  const filePreviewPanelRef = ref(null)

  // 对话历史
  const showConversationPanel = ref(false)
  const conversationHistory = ref([])

  const onSelectProjectFile = async (filePath) => {
    try {
      const result = await api.readProjectFile(filePath)
      fileContent.value = result.content || ''
      if (filePreviewPanelRef.value) {
        filePreviewPanelRef.value.setContent(fileContent.value)
      }
      showFilePreview.value = true
    } catch (error) {
      ElMessage.error('读取文件失败')
    }
  }

  const onCopyFileContent = async () => {
    try {
      await navigator.clipboard.writeText(fileContent.value)
      ElMessage.success('已复制到剪贴板')
    } catch {
      ElMessage.error('复制失败')
    }
  }

  const onDeleteFile = async (filePath) => {
    if (!filePath) return
    try {
      await ElMessageBox.confirm(`确定要删除文件 "${filePath}" 吗？`, '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
    } catch {
      return
    }
    try {
      await api.deleteProjectFile(filePath)
      ElMessage.success('文件已删除')
      fileContent.value = ''
      showFilePreview.value = false
      if (filePreviewPanelRef.value) {
        filePreviewPanelRef.value.reset()
      }
      await loadProjectFiles()
    } catch (error) {
      ElMessage.error('删除文件失败')
    }
  }

  // 快照管理
  const snapshots = ref([])
  const showSnapshotPanel = ref(false)
  const selectedSnapshotTag = ref('')
  const diffResult = ref(null)
  const showDiffView = ref(false)

  // 知识库
  const knowledgeEntries = ref([])
  const showKnowledgePanel = ref(false)
  const newKnowledgeContent = ref('')
  const newKnowledgeCategory = ref('')
  const knowledgeSearchQuery = ref('')
  const knowledgeSearchResults = ref([])

  // 需求联想
  const associations = ref([])
  const showAssociations = ref(false)

  // 增量修改模式
  const isIncrementalMode = ref(false)

  const MAX_SAVED_PROJECTS = 3
  let abortController = null

  // localStorage 持久化 key
  const STORAGE_KEY = 'project_generator_state'

  // 阶段定义
  const phases = [
    { key: 'analyzing', label: '分析需求' },
    { key: 'assigning', label: '分配模型' },
    { key: 'initializing', label: '初始化角色' },
    { key: 'designing', label: '架构设计' },
    { key: 'generating', label: '生成代码' },
    { key: 'testing', label: '测试验证' }
  ]

  // 阶段映射
  const phaseMap = {
    '分析项目复杂度': 'analyzing',
    '分配 AI 模型': 'assigning',
    '初始化专家角色': 'initializing',
    '预估生成成本': 'designing',
    '构建文件依赖关系': 'designing',
    '正在生成文件': 'generating',
    '文件生成完成': 'generating',
    '启用增强生成模式': 'generating',
    '运行自动化测试': 'testing',
    '测试全部通过': 'testing',
    '测试存在失败': 'testing',
    '自动修复测试问题': 'testing',
    '修复完成': 'testing',
    '测试失败，正在自动修复': 'testing',
    '自动修复成功': 'testing',
    '自动修复失败': 'testing',
    '最终项目验证': 'testing',
    '项目生成完成': 'complete'
  }

  // ========== 3. Computed ==========
  const progressPercent = computed(() => {
    return totalSteps.value > 0 ? (currentStep.value / totalSteps.value) * 100 : 0
  })

  // ========== 4. Watchers (现在 ref 已声明，watch 可以安全访问) ==========
  watch(
    () => props.visible,
    newVal => {
      if (newVal) {
        loadSavedProjects()
        loadPersistedState()
      }
    }
  )

  watch(
    () => form.value.requirement,
    () => {
      if (form.value.requirement.trim()) {
        savePersistedState()
      }
    }
  )

  watch(generationComplete, (val) => {
    if (val) savePersistedState()
  })

  // ========== 5. Lifecycle ==========
  onMounted(() => {
    loadPersistedState()
  })

  onBeforeUnmount(() => {
    savePersistedState()
  })

  // ========== 6. Persistence Functions ==========
  function loadPersistedState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const state = JSON.parse(raw)
      if (state.form) {
        form.value = state.form
      }
      if (state.outputDir) {
        outputDir.value = state.outputDir
      }
      if (state.generationComplete) {
        generationComplete.value = true
        hasStopped.value = false
        currentStep.value = state.currentStep || 0
        totalSteps.value = state.totalSteps || 0
        filesCreated.value = state.filesCreated || 0
        progressMessage.value = '项目生成完成'
      }
    } catch {
      // 忽略解析错误
    }
  }

  function savePersistedState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        form: form.value,
        outputDir: outputDir.value,
        generationComplete: generationComplete.value,
        currentStep: currentStep.value,
        totalSteps: totalSteps.value,
        filesCreated: filesCreated.value
      }))
    } catch {
      // 忽略存储错误
    }
  }

  function clearPersistedState() {
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // 忽略
    }
  }

  // ========== 7. Action Functions ==========
  const close = async () => {
    if (isGenerating.value) {
      try {
        await ElMessageBox.confirm('生成正在进行中，确定要关闭吗？', '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
      } catch {
        return
      }
    }
    emit('close')
  }

  const resetForm = (keepSession = false) => {
    stopGeneration()
    const keepSessionId = keepSession ? form.value.sessionId : ''
    form.value = {
      requirement: '',
      sessionId: keepSessionId
    }
    isGenerating.value = false
    generationComplete.value = false
    progressMessage.value = ''
    currentStep.value = 0
    totalSteps.value = 0
    filesCreated.value = 0
    logs.value = []
    outputDir.value = ''
    currentPhase.value = ''
    completedPhases.value = []
    clearPersistedState()
  }

  const loadSavedProjects = async () => {
    try {
      if (typeof api.getSavedProjects !== 'function') {
        savedProjects.value = []
        return
      }
      const result = await api.getSavedProjects()
      if (result && Array.isArray(result.projects)) {
        savedProjects.value = result.projects
      } else {
        savedProjects.value = []
      }
    } catch (error) {
      // 忽略加载失败
      savedProjects.value = []
    }
  }

  const saveCurrentProject = async () => {
    if (!form.value.requirement.trim()) {
      ElMessage.error('请先输入项目需求描述')
      return
    }
    if (savedProjects.value.length >= MAX_SAVED_PROJECTS) {
      ElMessage.error(`最多只能保存 ${MAX_SAVED_PROJECTS} 个项目，请先删除不需要的项目`)
      return
    }
    const name = prompt('请输入项目名称:', `项目_${Date.now()}`)
    if (!name) return
    const description = prompt('请输入项目描述（可选）:', '')
    try {
      const projectData = JSON.stringify({
        requirement: form.value.requirement,
        sessionId: form.value.sessionId
      })
      await api.saveProject(name, description || '', projectData)
      ElMessage.success('项目保存成功')
      await loadSavedProjects()
    } catch (error) {
      ElMessage.error(error.message || '保存项目失败')
    }
  }

  const loadProject = async projectId => {
    try {
      const result = await api.loadProject(projectId)
      if (result) {
        const projectData = JSON.parse(result.project_data)
        form.value.requirement = projectData.requirement || ''
        form.value.sessionId = projectData.sessionId || ''
        ElMessage.success(`已加载项目: ${result.name}`)
      }
    } catch (error) {
      // 忽略加载失败
      ElMessage.error('加载项目失败')
    }
  }

  const confirmDeleteProject = async project => {
    try {
      await ElMessageBox.confirm(`确定要删除项目 "${project.name}" 吗？`, '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
    } catch {
      return
    }
    deleteProject(project.id)
  }

  const deleteProject = async projectId => {
    try {
      const result = await api.deleteProject(projectId)
      if (result && result.status === 'deleted') {
        await loadSavedProjects()
        ElMessage.success('项目已删除')
      } else {
        ElMessage.error('删除项目失败')
      }
    } catch (error) {
      // 忽略删除失败
      ElMessage.error('删除项目失败')
    }
  }

  const formatDate = dateStr => {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const startGeneration = async () => {
    if (!form.value.requirement.trim()) {
      ElMessage.error('请输入项目需求描述')
      return
    }

    // 检查 API Key 配置
    if (!apiKeyStore.hasSiliconflowKey) {
      ElMessage.error('请先配置 API Key 后再使用')
      router.push('/settings')
      return
    }

    isGenerating.value = true
    generationComplete.value = false
    hasStopped.value = false
    logs.value = []
    thinkingContent.value = ''
    currentPhase.value = ''
    completedPhases.value = []
    abortController = new AbortController()

    // 增量修改模式：复用 sessionId，调用 modify 端点
    if (isIncrementalMode.value) {
      form.value.sessionId = form.value.sessionId || `project_${Date.now()}`
      addLog('info', '开始增量修改')
      addLog('info', `修改需求: ${form.value.requirement}`)
      addLog('info', `会话ID: ${form.value.sessionId}`)

      try {
        const response = await api.modifyProjectStream(
          {
            requirement: form.value.requirement,
            session_id: form.value.sessionId,
            incremental: true,
            output_dir: outputDir.value || undefined,
            api_key_token: apiKeyStore.siliconflowKey?.token
          },
          abortController.signal
        )

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || '修改失败')
        }

        await consumeJsonStream(response, handleStreamData)

        onGenerationComplete()
        isIncrementalMode.value = false
        addLog('success', '增量修改完成！')
      } catch (error) {
        if (error.name !== 'AbortError') {
          addLog('error', `修改失败: ${error.message}`)
        } else {
          addLog('warning', '修改已取消')
        }
        isGenerating.value = false
      }
      return
    }

    // 全新项目生成
    form.value.sessionId = `project_${Date.now()}`

    addLog('info', '开始项目生成')
    addLog('info', `需求: ${form.value.requirement}`)
    addLog('info', '模型: 自动分配')
    addLog('info', `会话ID: ${form.value.sessionId}`)
    addLog('info', '模式: 单会话（新会话将清理旧资源）')

    try {
      const response = await api.stream(
        '/agent/orchestrate/stream',
        {
          requirement: form.value.requirement,
          output_dir: outputDir.value || undefined,
          enable_review: true,
          enable_validation: true,
          enable_error_recovery: true,
          enable_memory: true,
          session_id: form.value.sessionId,
          incremental: false,
          require_approval: false,
          api_key_token: apiKeyStore.siliconflowKey?.token
        },
        abortController.signal
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || '生成失败')
      }

      await consumeJsonStream(response, handleStreamData, {
        onParseError: (error, line) => console.error('解析流数据失败:', line, error)
      })

      generationComplete.value = true
      currentPhase.value = 'complete'
      completedPhases.value = phases.map(p => p.key)
      addLog('success', '项目生成完成！')
    } catch (error) {
      if (error.name !== 'AbortError') {
        addLog('error', `生成失败: ${error.message}`)
      } else {
        addLog('warning', '生成已取消')
      }
      isGenerating.value = false
    }
  }

  const handleStreamData = data => {
    const eventType = data.type
    const eventData = data.data || data
    const step = eventData.step || eventType

    const mappedPhase = phaseMap[step]
    if (mappedPhase) {
      if (currentPhase.value && currentPhase.value !== mappedPhase && currentPhase.value !== 'complete') {
        if (!completedPhases.value.includes(currentPhase.value)) {
          completedPhases.value.push(currentPhase.value)
        }
      }
      currentPhase.value = mappedPhase
    }

    switch (eventType) {
      case 'progress':
        if (eventData.step) {
          currentStep.value = eventData.current || 0
          totalSteps.value = eventData.total || 0
          progressMessage.value = eventData.step || '处理中...'
          let logMsg = eventData.step
          if (eventData.file_path) {
            logMsg += ` - ${eventData.file_path}`
          }
          if (eventData.complexity) {
            logMsg = `复杂度: ${eventData.complexity}`
          }
          if (eventData.file_count) {
            logMsg += `（${eventData.file_count} 个文件）`
          }
          addLog('info', logMsg)
        }
        break
      case 'log':
        addLog('info', eventData.message || '')
        break
      case 'done':
        onGenerationComplete()
        progressMessage.value = '生成完成！'
        outputDir.value = eventData.output_dir || ''
        if (eventData.total_files_created !== undefined) {
          filesCreated.value = eventData.total_files_created
        }
        addLog('success', `项目生成完成！共创建 ${eventData.total_files_created || 0} 个文件`)
        break
      case 'error':
        addLog('error', eventData.error || eventData.message || '未知错误')
        break
      case 'thinking':
        progressMessage.value = 'AI 正在思考...'
        if (eventData.message) {
          // 按 agent 分组存储
          const agent = eventData.agent || 'unknown'
          const model = eventData.model || ''
          if (!_thinkingMap[agent]) {
            _thinkingMap[agent] = { content: '', model: model }
          }
          _thinkingMap[agent].content += eventData.message
          if (model && !_thinkingMap[agent].model) {
            _thinkingMap[agent].model = model
          }
          // 更新响应式数组
          thinkingGroups.value = Object.entries(_thinkingMap).map(([name, data]) => ({
            agent: name,
            content: data.content,
            model: data.model
          }))
          // 同时更新旧的 thinkingContent（兼容）
          thinkingContent.value += eventData.message
        }
        break
      case 'step_start':
        currentStep.value = eventData.step || 0
        totalSteps.value = eventData.max_steps || 0
        addLog('info', `${eventData.message} (${eventData.step}/${eventData.max_steps})`)
        break
      case 'step_end':
        addLog('success', eventData.message || '')
        break
      case 'file_create_start':
        addLog('info', `开始创建文件: ${eventData.file_path || ''}`)
        break
      case 'file_created':
        filesCreated.value++
        addLog('success', `文件创建成功: ${eventData.file_path || ''}`)
        break
      case 'file_error':
        addLog('error', `文件创建失败: ${eventData.file_path || ''} - ${eventData.error || ''}`)
        break
      case 'validation':
        progressMessage.value = eventData.message || ''
        addLog('info', eventData.message || '')
        if (eventData.status === 'failed') {
          addLog('warning', `验证失败: ${eventData.message || ''}`)
          if (eventData.missing_deps) {
            addLog('warning', `缺失依赖: ${eventData.missing_deps.join(', ')}`)
          }
        } else {
          addLog('success', '验证通过')
        }
        break
      case 'complete':
        progressMessage.value = eventData.message || '生成完成！'
        totalSteps.value = eventData.total_steps || 0
        filesCreated.value = eventData.total_files_created || 0
        outputDir.value = eventData.output_dir || ''
        addLog('success', `生成完成！共创建 ${eventData.total_files_created || 0} 个文件`)
        break
      case 'cache_hit':
        addLog('success', '命中缓存！跳过架构设计')
        break
      case 'cache_loaded':
        progressMessage.value = '使用缓存架构...'
        addLog('info', `加载缓存: ${eventData.file_count || 0} 个文件`)
        break
      case 'incremental_analysis':
        progressMessage.value = '分析变更...'
        addLog('info', `需重新生成: ${eventData.files_to_regenerate || 0} 个文件`)
        addLog('info', `可复用: ${eventData.files_reusable || 0} 个文件`)
        break
      case 'incremental_no_changes':
        progressMessage.value = '无变更，无需重新生成'
        addLog('info', '所有文件均为最新，跳过生成')
        generationComplete.value = true
        break
      case 'dependency_graph':
        addLog('info', `依赖图: ${eventData.file_count || 0} 个文件, ${eventData.layers?.length || 0} 个层级`)
        break
      case 'pause_for_approval':
        progressMessage.value = '等待审批...'
        addLog('warning', `关键文件等待确认: ${eventData.file_path || ''}`)
        break
      case 'file_rejected':
        addLog('warning', `文件被拒绝: ${eventData.file_path || ''}`)
        break
      case 'tests_finished': {
        const testSummary = []
        if (eventData.total) testSummary.push(`总计: ${eventData.total}`)
        if (eventData.passed) testSummary.push(`通过: ${eventData.passed}`)
        if (eventData.failed) testSummary.push(`失败: ${eventData.failed}`)
        if (testSummary.length > 0) {
          if (eventData.success) {
            addLog('success', `测试完成 - ${testSummary.join(', ')}`)
          } else {
            addLog('warning', `测试存在失败 - ${testSummary.join(', ')}`)
          }
        }
        break
      }
      default:
        if (step && typeof step === 'string') {
          addLog('info', step)
        }
    }

    nextTick(() => {
      if (logsContainer.value) {
        logsContainer.value.scrollTop = logsContainer.value.scrollHeight
      }
    })
  }

  const stopGeneration = () => {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    isGenerating.value = false
    hasStopped.value = true
    addLog('warning', '生成已停止，可以修改需求继续生成')
  }

  const addLog = (type, message) => {
    logs.value.push({
      type,
      message,
      time: new Date()
    })
  }

  const renderThinkingMarkdown = text => {
    if (!text) return ''
    const html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>')
    return html
  }

  const formatTime = date => {
    return date.toLocaleTimeString('zh-CN', { hour12: false })
  }

  const getLogIcon = type => {
    const icons = {
      info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
      success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>',
      warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
      error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
      thinking: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
    }
    return icons[type] || icons.info
  }

  const handleDownload = () => {
    if (!outputDir.value) {
      ElMessage.error('没有可下载的项目')
      return
    }
    const downloadUrl = api.downloadProject(outputDir.value)
    window.open(downloadUrl, '_blank')
    addLog('info', '开始下载项目...')
  }

  // ========== 文件预览 ==========
  const loadProjectFiles = async () => {
    try {
      const result = await api.getProjectFiles()
      projectFiles.value = result.files || []
    } catch (error) {
      // 忽略加载失败
    }
  }

  // ========== 快照管理 ==========
  const loadSnapshots = async () => {
    if (!form.value.sessionId) return
    try {
      const result = await api.getSnapshots(form.value.sessionId)
      snapshots.value = result.snapshots || result.tags || []
    } catch (error) {
      // 忽略加载失败
    }
  }

  const rollbackToSnapshot = async (tag) => {
    if (!form.value.sessionId || !tag) return
    try {
      await ElMessageBox.confirm(`确定要回滚到快照 "${tag}" 吗？当前修改将会丢失。`, '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
    } catch {
      return
    }
    try {
      await api.rollbackToSnapshot(form.value.sessionId, tag)
      ElMessage.success(`已回滚到快照 ${tag}`)
      addLog('info', `回滚到快照: ${tag}`)
      await loadSnapshots()
    } catch (error) {
      ElMessage.error('回滚失败')
    }
  }

  const compareSnapshots = async (tag1, tag2) => {
    if (!tag1 || !tag2) return
    try {
      const result = await api.getSnapshotDiff(tag1, tag2)
      diffResult.value = result
      showDiffView.value = true
    } catch (error) {
      ElMessage.error('获取快照差异失败')
    }
  }

  // ========== 知识库管理 ==========
  const loadKnowledge = async () => {
    try {
      const result = await api.listKnowledge(newKnowledgeCategory.value)
      knowledgeEntries.value = result.entries || []
    } catch (error) {
      // 忽略加载失败
    }
  }

  const addKnowledge = async () => {
    if (!newKnowledgeContent.value.trim()) {
      ElMessage.warning('请输入知识内容')
      return
    }
    try {
      await api.addKnowledge(
        newKnowledgeContent.value,
        newKnowledgeCategory.value,
        []
      )
      ElMessage.success('知识已添加')
      newKnowledgeContent.value = ''
      await loadKnowledge()
    } catch (error) {
      ElMessage.error('添加知识失败')
    }
  }

  const searchKnowledge = async () => {
    if (!knowledgeSearchQuery.value.trim()) return
    try {
      const result = await api.searchKnowledge(knowledgeSearchQuery.value)
      knowledgeSearchResults.value = result.results || []
    } catch (error) {
      // 忽略搜索失败
    }
  }

  // ========== 需求联想 ==========
  const loadAssociations = async () => {
    if (!form.value.requirement.trim()) return
    try {
      const result = await api.getRequirementAssociations(form.value.requirement)
      associations.value = result.associations || []
      showAssociations.value = true
    } catch (error) {
      // 忽略加载失败
    }
  }

  const confirmAssociation = async (associationId) => {
    try {
      await api.confirmAssociation(associationId)
      ElMessage.success('已确认')
      associations.value = associations.value.map(a =>
        a.id === associationId ? { ...a, confirmed: true } : a
      )
    } catch (error) {
      ElMessage.error('确认失败')
    }
  }

  const rateAssociation = async (associationId, helpful) => {
    try {
      await api.submitAssociationHelpful(associationId, helpful)
    } catch {
      // 静默失败
    }
  }

  // ========== 增量修改 ==========
  const enableIncrementalModify = () => {
    isIncrementalMode.value = true
    generationComplete.value = false
    hasStopped.value = true
    addLog('info', '进入增量修改模式，请输入修改需求')
    ElMessage.info('已进入增量修改模式，请输入修改需求')
  }

  // ========== 对话历史 ==========
  const loadConversationHistory = async () => {
    if (!form.value.sessionId) return
    try {
      // 使用 Redis 存储的历史（通过后端 API 获取）
      const result = await api.getConversationHistory(form.value.sessionId)
      conversationHistory.value = result.items || result.messages || []
    } catch (error) {
      console.error('加载对话历史失败:', error)
      conversationHistory.value = []
    }
  }

  const formatConversationTime = (timestamp) => {
    if (!timestamp) return ''
    const date = new Date(timestamp * 1000)
    return date.toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  // ========== 生成完成后自动加载文件 ==========
  const onGenerationComplete = async () => {
    generationComplete.value = true
    currentPhase.value = 'complete'
    completedPhases.value = phases.map(p => p.key)
    addLog('success', '项目生成完成！')
    // 自动生成后加载文件列表
    if (outputDir.value) {
      await loadProjectFiles()
    }
  }
</script>

<style scoped>
  .project-generator-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2000;
    padding: 20px;
    backdrop-filter: blur(4px);
  }

  .project-generator-modal {
    background: var(--bg-primary);
    border-radius: 16px;
    width: 100%;
    max-width: 880px;
    max-height: 92vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 25px 80px rgba(0, 0, 0, 0.35);
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 28px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    color: #fff;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .header-icon {
    width: 44px;
    height: 44px;
    background: rgba(255, 255, 255, 0.2);
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .header-icon svg {
    width: 24px;
    height: 24px;
  }

  .modal-header h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
  }

  .header-subtitle {
    margin: 2px 0 0;
    font-size: 13px;
    opacity: 0.85;
  }

  .close-btn {
    background: rgba(255, 255, 255, 0.2);
    border: none;
    font-size: 28px;
    cursor: pointer;
    color: #fff;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 10px;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: rgba(255, 255, 255, 0.3);
  }

  .modal-body {
    flex: 1;
    overflow-y: auto;
    padding: 24px 28px;
  }

  .generation-progress {
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .progress-overview {
    background: var(--bg-secondary);
    border-radius: 12px;
    padding: 18px 20px;
    border: 1px solid var(--border-color);
  }

  .progress-status {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .pulse-dot {
    width: 10px;
    height: 10px;
    background: var(--primary);
    border-radius: 50%;
    animation: pulse 1.5s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(1.2); }
  }

  .status-text {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .progress-meta {
    display: flex;
    gap: 16px;
  }

  .meta-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--text-tertiary);
  }

  .meta-item svg {
    width: 14px;
    height: 14px;
  }

  .progress-bar-wrapper {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .progress-bar {
    flex: 1;
    height: 8px;
    background: var(--border-color);
    border-radius: 4px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--primary) 0%, var(--primary-hover) 50%, var(--primary) 100%);
    border-radius: 4px;
    transition: width 0.4s ease;
    background-size: 200% 100%;
    animation: shimmer 2s linear infinite;
  }

  @keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  .progress-percent {
    font-size: 14px;
    font-weight: 600;
    color: var(--primary);
    min-width: 40px;
    text-align: right;
  }

  .phase-indicators {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .phase-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    transition: all 0.3s;
    background: var(--bg-tertiary);
    color: var(--text-tertiary);
  }

  .phase-item.active {
    background: var(--primary);
    color: #fff;
  }

  .phase-item.completed {
    background: var(--color-success-50, #dcfce7);
    color: var(--success);
  }

  .phase-icon {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
  }

  .phase-item.active .phase-icon {
    background: rgba(255, 255, 255, 0.3);
  }

  .phase-item.completed .phase-icon {
    background: var(--success);
    color: #fff;
  }

  .phase-spinner {
    width: 12px;
    height: 12px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .generation-logs {
    flex: 1;
    background: var(--bg-primary);
    border-radius: 12px;
    padding: 16px;
    max-height: 380px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 12px;
    line-height: 1.8;
    border: 1px solid var(--text-primary);
  }

  .thinking-log-block {
    margin-bottom: 8px;
  }

  .thinking-log-details {
    background: rgba(139, 92, 246, 0.1);
    border: 1px solid rgba(139, 92, 246, 0.2);
    border-radius: 8px;
    overflow: hidden;
  }

  .thinking-log-summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    cursor: pointer;
    list-style: none;
    color: var(--color-primary-500);
    font-size: 12px;
    font-weight: 600;
  }

  .thinking-log-summary::marker {
    display: none;
  }

  .thinking-log-label {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .thinking-log-details[open] .chevron-icon {
    transform: rotate(180deg);
  }

  .chevron-icon {
    width: 14px;
    height: 14px;
    transition: transform 0.2s;
  }

  .thinking-log-content {
    padding: 12px;
    color: var(--color-primary-400);
    font-size: 12px;
    line-height: 1.6;
    border-top: 1px solid rgba(139, 92, 246, 0.15);
    background: rgba(139, 92, 246, 0.05);
    max-height: 200px;
    overflow-y: auto;
  }

  .thinking-log-content code {
    background: rgba(139, 92, 246, 0.2);
    color: var(--color-primary-300);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 11px;
  }

  .thinking-log-content strong {
    color: var(--color-primary-300);
  }

  .log-item {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 4px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }

  .log-time {
    color: var(--text-tertiary);
    min-width: 70px;
    font-size: 11px;
  }

  .log-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .log-icon svg {
    width: 14px;
    height: 14px;
  }

  .log-message {
    flex: 1;
    word-break: break-word;
  }

  .log-item.info .log-message {
    color: var(--text-tertiary);
  }

  .log-item.success .log-message {
    color: var(--success);
  }

  .log-item.warning .log-message {
    color: var(--warning);
  }

  .log-item.error .log-message {
    color: var(--danger);
  }

  .log-item.thinking .log-message {
    color: var(--color-primary-500);
    font-style: italic;
  }

  .log-item.success .log-icon svg {
    color: var(--success);
  }

  .log-item.warning .log-icon svg {
    color: var(--warning);
  }

  .log-item.error .log-icon svg {
    color: var(--danger);
  }

  .generation-form {
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .saved-projects-section {
    background: var(--bg-secondary);
    border-radius: 12px;
    padding: 16px;
    border: 1px solid var(--border-color);
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }

  .section-header h4 {
    margin: 0;
    font-size: 14px;
    color: var(--text-secondary);
  }

  .project-count {
    background: var(--border-color);
    color: var(--text-tertiary);
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
  }

  .btn-small {
    margin-left: auto;
    padding: 4px 10px;
    font-size: 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-primary);
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-small:hover {
    background: var(--bg-tertiary);
  }

  .saved-projects-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .saved-project-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    background: var(--bg-primary);
    border-radius: 8px;
    border: 1px solid var(--border-color);
    cursor: pointer;
    transition: all 0.2s;
  }

  .saved-project-item:hover {
    border-color: var(--primary);
    box-shadow: 0 2px 8px rgba(13, 148, 136, 0.1);
  }

  .project-icon {
    width: 36px;
    height: 36px;
    background: var(--color-primary-50);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--primary);
  }

  .project-icon svg {
    width: 18px;
    height: 18px;
  }

  .project-details {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .project-name {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .project-date {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .btn-delete {
    width: 32px;
    height: 32px;
    border: none;
    background: transparent;
    color: var(--text-tertiary);
    cursor: pointer;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }

  .btn-delete:hover {
    background: var(--color-danger-100, #fee2e2);
    color: var(--danger);
  }

  .btn-delete svg {
    width: 16px;
    height: 16px;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .form-group label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    color: var(--text-secondary);
    font-size: 14px;
  }

  .form-group label svg {
    width: 16px;
    height: 16px;
    color: var(--primary);
  }

  .form-textarea,
  .form-input {
    padding: 12px 14px;
    border: 2px solid var(--border-color);
    border-radius: 10px;
    font-size: 14px;
    font-family: inherit;
    transition: all 0.2s;
    resize: vertical;
    background: var(--bg-primary);
  }

  .form-textarea:focus,
  .form-input:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.1);
  }

  .form-textarea {
    min-height: 140px;
  }

  .form-info {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 14px;
    background: var(--color-primary-50);
    border-left: 3px solid var(--primary);
    border-radius: 8px;
  }

  .form-info svg {
    width: 18px;
    height: 18px;
    color: var(--primary);
    flex-shrink: 0;
    margin-top: 1px;
  }

  .form-info p {
    margin: 0;
    color: var(--text-secondary);
    font-size: 13px;
    line-height: 1.5;
  }

  .info-warning {
    margin-top: 8px !important;
    color: var(--text-primary) !important;
    font-weight: 500;
  }

  .session-id-readonly {
    background: var(--bg-secondary);
    color: var(--text-tertiary);
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px;
    cursor: default;
  }

  .session-id-readonly:focus {
    border-color: var(--text-tertiary);
    box-shadow: none;
  }

  .field-hint {
    margin: 6px 0 0;
    font-size: 12px;
    color: var(--text-tertiary);
    line-height: 1.4;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    padding: 16px 28px;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
  }

  .btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 20px;
    border-radius: 10px;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    border: none;
    transition: all 0.2s;
  }

  .btn svg {
    width: 16px;
    height: 16px;
  }

  .btn-primary {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    color: #fff;
  }

  .btn-primary:hover:not(:disabled) {
    opacity: 0.9;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(13, 148, 136, 0.3);
  }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-secondary {
    background: var(--border-color);
    color: var(--text-secondary);
  }

  .btn-secondary:hover {
    background: var(--text-tertiary);
  }

  .btn-save {
    background: var(--color-primary-50);
    color: var(--primary);
    border: 1px solid var(--color-primary-200);
  }

  .btn-save:hover:not(:disabled) {
    background: var(--color-primary-100);
  }

  .btn-save:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-success {
    background: var(--success);
    color: #fff;
  }

  .btn-success:hover {
    background: var(--success);
  }

  .btn-danger {
    background: var(--danger);
    color: #fff;
  }

  .btn-danger:hover {
    background: var(--danger-hover);
  }

  .btn-warning {
    background: var(--warning);
    color: #fff;
  }

  .btn-warning:hover {
    background: var(--warning-hover);
  }

  .btn-download {
    background: var(--primary);
    color: #fff;
  }

  .btn-download:hover {
    background: var(--primary-hover);
  }

  .btn-info {
    background: var(--color-primary-500);
    color: #fff;
  }

  .btn-info:hover {
    background: var(--color-primary-600);
  }

  /* 面板通用样式 */
  .file-preview-panel,
  .snapshot-panel,
  .knowledge-panel {
    margin: 16px 28px;
    background: var(--bg-secondary);
    border-radius: 12px;
    border: 1px solid var(--border-color);
    overflow: hidden;
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: var(--bg-primary);
    border-bottom: 1px solid var(--border-color);
  }

  .panel-header h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .close-panel {
    background: transparent;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: var(--text-tertiary);
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
  }

  .close-panel:hover {
    background: var(--bg-tertiary);
  }

  /* 文件预览 */
  .file-preview-body {
    display: flex;
    max-height: 400px;
  }

  .file-list {
    width: 220px;
    overflow-y: auto;
    border-right: 1px solid var(--border-color);
    background: var(--bg-primary);
  }

  .file-list-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    cursor: pointer;
    border-bottom: 1px solid var(--bg-tertiary);
  }

  .file-list-item:hover {
    background: var(--color-primary-50);
  }

  .file-list-item.active {
    background: var(--color-primary-100);
    color: var(--primary);
  }

  .file-icon-small {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .file-path {
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .file-content-view {
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  .file-content-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background: var(--bg-primary);
    border-bottom: 1px solid var(--border-color);
  }

  .file-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .file-actions {
    display: flex;
    gap: 8px;
  }

  .file-code {
    flex: 1;
    overflow: auto;
    padding: 12px;
    margin: 0;
    background: var(--bg-primary);
    color: var(--border-color);
    font-size: 12px;
    line-height: 1.6;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
  }

  .file-content-empty {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: var(--text-tertiary);
  }

  .file-content-empty svg {
    width: 48px;
    height: 48px;
    margin-bottom: 12px;
    opacity: 0.5;
  }

  /* 快照管理 */
  .snapshot-body {
    max-height: 400px;
    overflow-y: auto;
    background: var(--bg-primary);
  }

  .snapshot-list {
    padding: 8px;
  }

  .snapshot-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 12px;
    border-radius: 8px;
    border: 1px solid var(--border-color);
    margin-bottom: 8px;
  }

  .snapshot-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .snapshot-tag {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .snapshot-date {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .snapshot-actions {
    display: flex;
    gap: 8px;
  }

  .snapshot-empty {
    padding: 32px;
    text-align: center;
    color: var(--text-tertiary);
  }

  .diff-view {
    margin: 8px;
    padding: 12px;
    background: var(--bg-primary);
    border-radius: 8px;
  }

  .diff-view h4 {
    margin: 0 0 8px;
    color: var(--border-color);
  }

  .diff-code {
    margin: 0;
    color: var(--border-color);
    font-size: 12px;
    line-height: 1.6;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    max-height: 200px;
    overflow: auto;
  }

  /* 知识库 */
  .knowledge-body {
    max-height: 400px;
    overflow-y: auto;
    background: var(--bg-primary);
    padding: 12px;
  }

  .knowledge-add {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
  }

  .knowledge-input {
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    font-size: 13px;
    font-family: inherit;
    resize: vertical;
  }

  .knowledge-category {
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    font-size: 13px;
  }

  .knowledge-search {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
  }

  .knowledge-search-input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    font-size: 13px;
  }

  .knowledge-results {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .knowledge-result {
    padding: 8px 12px;
    background: var(--color-primary-50);
    border-radius: 8px;
  }

  .knowledge-result p {
    margin: 0 0 4px;
    font-size: 13px;
  }

  .knowledge-score {
    font-size: 11px;
    color: var(--primary);
  }

  .knowledge-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .knowledge-item {
    padding: 8px 12px;
    background: var(--bg-secondary);
    border-radius: 8px;
  }

  .knowledge-item p {
    margin: 0 0 4px;
    font-size: 13px;
  }

  .knowledge-category-tag {
    font-size: 11px;
    background: var(--border-color);
    color: var(--text-tertiary);
    padding: 2px 8px;
    border-radius: 10px;
  }

  /* 小按钮 */
  .btn-small {
    padding: 4px 10px;
    font-size: 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-primary);
    color: var(--text-tertiary);
    cursor: pointer;
  }

  .btn-small:hover {
    background: var(--bg-tertiary);
  }

  .btn-danger-small {
    color: var(--danger);
    border-color: #fecaca;
  }

  .btn-danger-small:hover {
    background: var(--danger-bg);
  }

  /* 对话历史面板 */
  .conversation-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-height: 400px;
    overflow-y: auto;
  }

  .conversation-item {
    padding: 12px;
    border-radius: 8px;
    background: var(--bg-secondary);
  }

  .conversation-item.user {
    background: var(--color-primary-50);
    border-left: 3px solid var(--primary);
  }

  .conversation-item.assistant {
    background: var(--bg-tertiary);
    border-left: 3px solid var(--success);
  }

  .conversation-role {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 4px;
  }

  .conversation-content {
    font-size: 13px;
    color: var(--text-primary);
    line-height: 1.5;
    word-break: break-word;
  }

  .conversation-time {
    font-size: 11px;
    color: var(--text-tertiary);
    margin-top: 4px;
  }

  /* thinking model 标签 */
  .thinking-model {
    font-size: 11px;
    font-weight: normal;
    color: var(--text-tertiary);
    margin-left: 4px;
  }
</style>
