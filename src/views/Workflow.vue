<template>
  <div class="workflow-page">
    <header class="page-header">
      <button class="back-btn" @click="goBack">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        返回
      </button>
      <div class="header-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
        </svg>
        <span>AI 工作流编排</span>
      </div>
      <div class="header-actions">
        <input ref="importInput" type="file" accept=".json" hidden @change="importWorkflow" />
        <button class="export-btn" @click="importInput?.click()">导入</button>
        <button class="export-btn" :disabled="!workflowNodes.length" @click="exportWorkflow">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          导出
        </button>
      </div>
    </header>

    <div class="page-content">
      <aside class="config-panel">
        <div class="form-group">
          <label for="workflow-prompt">自然语言描述</label>
          <textarea
            id="workflow-prompt"
            v-model="prompt"
            placeholder="描述你想要实现的功能，AI 将自动生成工作流..."
            rows="6"
            :disabled="executing"
          ></textarea>
        </div>

        <button
          class="execute-btn"
          :disabled="!canExecute || executing"
          @click="handleExecute"
        >
          <span v-if="executing" class="loading-spinner"></span>
          {{ executing ? '执行中...' : '执行工作流' }}
        </button>

        <TaskFeedbackPanel
          :feedback="taskFeedbackState"
          :connection-status="taskFeedbackConnection"
          :visible="hasTaskFeedback"
          :actions="taskFeedbackActions"
          @action="handleTaskFeedbackAction"
        />

        <div v-if="workflowNodes.length" class="node-list">
          <h4>工作流节点</h4>
          <div
            v-for="(node, index) in workflowNodes"
            :key="node.id || index"
            class="node-item"
          >
            <div class="node-header">
              <span class="node-type">{{ node.type }}</span>
              <span class="node-name">{{ node.name }}</span>
            </div>
            <p class="node-desc">{{ node.description }}</p>
          </div>
        </div>
        <div v-if="history.length" class="history-list">
          <h4>最近工作流</h4>
          <button v-for="item in history" :key="item.workflow_id" class="history-item" @click="loadHistory(item.workflow_id)">
            {{ item.workflow_id }} · {{ item.status }}
          </button>
        </div>
      </aside>

      <main class="preview-panel">
        <div v-if="!workflowNodes.length" class="preview-placeholder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
          <p>输入需求后点击执行，AI 将自动生成工作流</p>
        </div>

        <div v-else class="workflow-canvas">
          <div
            v-for="(node, index) in workflowNodes"
            :key="node.id || index"
            class="canvas-node"
          >
            <div class="node-badge">{{ node.type }}</div>
            <h3>{{ node.name }}</h3>
            <p>{{ node.description }}</p>
            <div v-if="node.output" class="node-output">
              <pre>{{ node.output }}</pre>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/utils/api/index'
import { consumeJsonStream } from '@/utils/streamParser'
import { useTaskFeedback } from '@/composables/useTaskFeedback'
import TaskFeedbackPanel from '@/components/TaskFeedbackPanel.vue'

const router = useRouter()
const prompt = ref('')
const executing = ref(false)
const workflowNodes = ref([])
const sessionId = ref(null)
const workflowId = ref(null)
const history = ref([])
const importInput = ref(null)
const taskFeedback = useTaskFeedback('workflow')
const taskFeedbackState = taskFeedback.feedback
const taskFeedbackConnection = taskFeedback.connectionStatus
const hasTaskFeedback = taskFeedback.hasFeedback
const taskFeedbackActions = computed(() => {
  const status = taskFeedbackState.value.status
  if (status === 'running') return [{ key: 'cancel', label: '取消执行', variant: 'danger' }]
  if (status === 'failed' || status === 'paused') return [{ key: 'retry', label: '重新执行', variant: 'primary' }]
  if (status === 'completed') return [{ key: 'export', label: '导出工作流', variant: 'primary' }]
  return []
})
let abortController = null

const canExecute = computed(() => prompt.value.trim().length > 0)

function goBack() {
  router.push('/')
}

async function handleExecute() {
  if (!canExecute.value || executing.value) return
  executing.value = true
  workflowNodes.value = []
  let terminalEventReceived = false
  taskFeedback.start({ event: 'workflow_started', progress: 0 })

  try {
    abortController = new AbortController()
    const response = await api.executeWorkflowStream(prompt.value.trim(), sessionId.value, abortController.signal)
    await consumeJsonStream(response, data => {
      if (['workflow_completed', 'workflow_error'].includes(data.event)) terminalEventReceived = true
      handleWorkflowEvent(data)
    })
    if (!terminalEventReceived) {
      taskFeedback.markDisconnected('工作流连接意外结束，输入和节点状态已保留')
    }
  } catch (e) {
    console.error('工作流执行失败:', e)
    if (e.name === 'AbortError') {
      taskFeedback.update({ event: 'workflow_paused', stage: '工作流已取消', nextAction: '调整输入后重新执行' })
    } else if (e.name === 'TypeError' || e.name === 'NetworkError') {
      taskFeedback.markDisconnected('工作流连接中断，输入和节点状态已保留')
    } else {
      taskFeedback.fail(e, { event: 'workflow_error', nextAction: '检查输入后重新执行' })
    }
    if (e.name !== 'AbortError') ElMessage.error('执行失败: ' + e.message)
  } finally {
    abortController = null
    executing.value = false
  }
}

function handleTaskFeedbackAction(action) {
  if (action === 'cancel' && abortController) {
    abortController.abort()
  } else if (action === 'retry') {
    handleExecute()
  } else if (action === 'export') {
    exportWorkflow()
  }
}

function handleWorkflowEvent(data) {
  if (data.event === 'workflow_started') {
    if (data.session_id) sessionId.value = data.session_id
  } else if (data.event === 'task_graph_generated') {
    workflowId.value = data.workflow_id || workflowId.value
    workflowNodes.value = (data.nodes || []).map(node => ({
      ...node,
      name: node.name || node.type,
      description: node.description || '等待执行',
      status: 'pending'
    }))
  } else if (data.event === 'node_started') {
    const node = workflowNodes.value.find(item => item.id === data.node_id)
    if (node) node.status = 'running'
  } else if (data.event === 'node_completed') {
    const node = workflowNodes.value.find(item => item.id === data.node_id)
    if (node) {
      node.status = data.success ? 'completed' : 'failed'
      node.output = data.data || ''
      node.error = data.error || null
    }
  } else if (data.event === 'workflow_completed') {
    if (data.workflow_id) workflowId.value = data.workflow_id
    if (data.session_id) sessionId.value = data.session_id
  }

  const feedbackEvent = data.event === 'workflow_completed'
    ? { ...data, progress: 100, nextAction: '查看节点结果或导出工作流' }
    : data.event === 'workflow_error'
      ? { ...data, error: data.message || data.error, nextAction: '检查输入后重新执行' }
      : data
  taskFeedback.update(feedbackEvent, { nodes: workflowNodes.value })
}

async function exportWorkflow() {
  if (workflowId.value) {
    const data = await api.exportWorkflow(workflowId.value)
    downloadJson(data.export_data, `workflow_${workflowId.value}.json`)
    return
  }
  downloadJson(workflowNodes.value, 'workflow.json')
}

function downloadJson(data, filename) {
  const blob = new Blob(
    [JSON.stringify(data, null, 2)],
    { type: 'application/json' }
  )
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 100)
}

async function importWorkflow(event) {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    const data = JSON.parse(await file.text())
    const imported = await api.importWorkflow(data)
    workflowId.value = imported.workflow_id
    workflowNodes.value = data.nodes || []
    ElMessage.success('工作流导入成功')
  } catch (error) { ElMessage.error(`导入失败: ${error.message}`) }
  event.target.value = ''
}

async function loadHistory(workflowIdValue) {
  const item = await api.getWorkflowHistoryDetail(workflowIdValue)
  workflowId.value = workflowIdValue
  workflowNodes.value = item.task_graph?.nodes || []
  taskFeedback.reset({
    status: item.status === 'failed' ? 'failed' : 'completed',
    stage: '已恢复历史工作流',
    progress: 100,
    nextAction: '查看节点结果或导出工作流'
  })
}

onMounted(async () => {
  try { history.value = (await api.listWorkflowHistory()).items || [] } catch { history.value = [] }
})
</script>

<style scoped>
.workflow-page {
  min-height: 100vh;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  cursor: pointer;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
}

.header-title svg {
  width: 20px;
  height: 20px;
}

.header-actions {
  margin-left: auto;
}

.export-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  cursor: pointer;
}

.export-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-content {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 24px;
  padding: 24px;
  flex: 1;
}

.config-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-group textarea {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
}

.execute-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  border: none;
  border-radius: 8px;
  background: var(--accent-color);
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.execute-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.node-list {
  margin-top: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.node-list h4 {
  margin: 0 0 12px;
  font-size: 14px;
}

.node-item {
  padding: 10px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  margin-bottom: 8px;
}

.node-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 4px;
}

.node-type {
  font-size: 11px;
  padding: 2px 6px;
  background: var(--accent-color);
  color: white;
  border-radius: 4px;
}

.node-name {
  font-size: 13px;
  font-weight: 500;
}

.node-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
}

.preview-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 24px;
  overflow-y: auto;
}

.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--text-secondary);
}

.preview-placeholder svg {
  width: 64px;
  height: 64px;
  opacity: 0.4;
}

.workflow-canvas {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.canvas-node {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
}

.node-badge {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  background: var(--accent-color);
  color: white;
  border-radius: 4px;
  margin-bottom: 8px;
}

.canvas-node h3 {
  font-size: 15px;
  margin: 0 0 8px;
}

.canvas-node p {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 12px;
  line-height: 1.5;
}

.node-output {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
}

.node-output pre {
  margin: 0;
  font-size: 12px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

@media (max-width: 768px) {
  .page-content {
    grid-template-columns: 1fr;
  }
}
</style>
