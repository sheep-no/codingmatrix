<template>
  <Modal :visible="visible" title="临时工作流" size="xl" @close="$emit('close')">
    <div class="ephemeral-workflow">
      <!-- 输入区域 -->
      <div class="input-section">
        <div class="input-header">
          <h3>描述您的任务</h3>
          <p class="input-hint">用自然语言描述您想要执行的任务，系统会自动拆解为可执行的工作流</p>
        </div>
        <textarea
          v-model="userRequest"
          class="request-input"
          placeholder="例如：帮我搜索最新的AI新闻，然后生成一个摘要报告"
          rows="4"
        ></textarea>
        <div class="input-actions">
          <!-- 停止按钮（执行中显示） -->
          <Button v-if="isExecuting" variant="danger" @click="stopWorkflow"> 停止 </Button>
          <!-- 继续生成按钮（停止后显示） -->
          <Button
            v-else-if="hasStopped && !workflowGraph"
            variant="warning"
            @click="continueWorkflow"
          >
            继续生成
          </Button>
          <!-- 开始执行按钮（首次） -->
          <Button v-else variant="primary" :disabled="!userRequest.trim()" @click="executeWorkflow">
            执行工作流
          </Button>
          <Button variant="secondary" :loading="isExplaining" @click="explainWorkflow">
            查看计划
          </Button>
          <Button variant="ghost" @click="importWorkflow"> 导入 JSON </Button>
          <Button v-if="workflowGraph" variant="ghost" @click="exportWorkflow"> 导出 JSON </Button>
          <Button v-if="hasStopped" variant="ghost" @click="resetWorkflow"> 新建工作流 </Button>
        </div>
      </div>

      <!-- 工作流图显示 -->
      <div v-if="workflowGraph" class="workflow-graph-section">
        <div class="section-header">
          <h3>工作流计划</h3>
          <div class="workflow-meta">
            <span class="workflow-id">ID: {{ workflowGraph.workflow_id }}</span>
            <span v-if="isExecuting" class="workflow-progress">
              执行进度: {{ completedNodes }}/{{ workflowGraph.nodes.length }}
            </span>
          </div>
        </div>

        <!-- 进度条 -->
        <div v-if="isExecuting || workflowStatus === 'completed'" class="progress-bar-container">
          <div class="progress-bar" :style="{ width: progressPercentage + '%' }"></div>
          <span class="progress-text">{{ progressPercentage }}%</span>
        </div>

        <div class="task-nodes">
          <div
            v-for="(node, index) in workflowGraph.nodes"
            :key="node.id"
            class="task-node"
            :class="getNodeStatusClass(node)"
          >
            <div class="node-header">
              <span class="node-index">{{ index + 1 }}</span>
              <span class="node-type">{{ getNodeTypeLabel(node.type) }}</span>
              <span class="node-status" :class="getNodeStatusClass(node)">
                {{ getNodeStatusLabel(node) }}
              </span>
            </div>
            <div class="node-params">
              <pre>{{ formatParams(node.params) }}</pre>
            </div>
            <div v-if="node.depends_on && node.depends_on.length > 0" class="node-depends">
              <span class="depends-label">依赖:</span>
              <span v-for="dep in node.depends_on" :key="dep" class="depends-item">{{ dep }}</span>
            </div>
            <div v-if="node.result" class="node-result">
              <div class="result-header">结果:</div>
              <pre class="result-content">{{ formatResult(node.result) }}</pre>
            </div>
            <div v-if="node.error" class="node-error">
              <div class="error-header">错误:</div>
              <pre class="error-content">{{ node.error }}</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- 任务图原始JSON -->
      <div v-if="showRawJson" class="raw-json-section">
        <div class="section-header">
          <h3>工作流 JSON</h3>
          <Button variant="ghost" size="sm" @click="showRawJson = false">隐藏</Button>
        </div>
        <pre class="json-content">{{ formatJson(workflowGraph) }}</pre>
      </div>

      <!-- 历史记录 -->
      <div v-if="history.length > 0" class="history-section">
        <div class="section-header">
          <h3>最近工作流</h3>
        </div>
        <div class="history-list">
          <div
            v-for="item in history"
            :key="item.id"
            class="history-item"
            @click="loadFromHistory(item)"
          >
            <div class="history-request">{{ item.request }}</div>
            <div class="history-meta">
              <span class="history-time">{{ formatTime(item.timestamp) }}</span>
              <span class="history-nodes">{{ item.nodes?.length || 0 }} 个节点</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 导入对话框 -->
      <div v-if="showImportDialog" class="import-dialog">
        <div class="dialog-backdrop" @click="showImportDialog = false"></div>
        <div class="dialog-content">
          <h3>导入工作流 JSON</h3>
          <textarea
            v-model="importJson"
            class="import-input"
            placeholder="粘贴工作流 JSON..."
            rows="10"
          ></textarea>
          <div class="dialog-actions">
            <Button variant="ghost" @click="showImportDialog = false">取消</Button>
            <Button variant="primary" @click="confirmImport">确认导入</Button>
          </div>
        </div>
      </div>
    </div>
  </Modal>
</template>

<script setup>
  import { ref, watch, computed } from 'vue'
  import Modal from './ui/Modal.vue'
  import Button from './ui/Button.vue'
  import { api } from '@/utils/api/index'

  const props = defineProps({
    visible: { type: Boolean, default: false }
  })

  const emit = defineEmits(['close'])

  const userRequest = ref('')
  const workflowGraph = ref(null)
  const isExecuting = ref(false)
  const isExplaining = ref(false)
  const hasStopped = ref(false)
  const sessionId = ref('')
  const showRawJson = ref(false)
  const showImportDialog = ref(false)
  const importJson = ref('')
  const history = ref([])
  const workflowStatus = ref('idle')

  let abortController = null

  const executeWorkflow = async () => {
    if (!userRequest.value.trim()) return

    isExecuting.value = true
    hasStopped.value = false
    workflowGraph.value = null
    workflowStatus.value = 'running'
    abortController = new AbortController()

    try {
      const response = await api.executeWorkflowStream(
        userRequest.value,
        sessionId.value || null,
        abortController.signal
      )

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.trim()) {
            try {
              const data = JSON.parse(line)
              handleStreamData(data)
            } catch (e) {
              console.warn('JSON parse error:', e, line)
            }
          }
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        console.error('工作流执行失败:', error)
        alert('工作流执行失败: ' + error.message)
      }
    } finally {
      isExecuting.value = false
      abortController = null
    }
  }

  const continueWorkflow = async () => {
    if (!userRequest.value.trim()) return
    await executeWorkflow()
  }

  const stopWorkflow = () => {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    isExecuting.value = false
    hasStopped.value = true
    workflowStatus.value = 'stopped'
  }

  const resetWorkflow = () => {
    hasStopped.value = false
    sessionId.value = ''
    workflowGraph.value = null
    workflowStatus.value = 'idle'
    userRequest.value = ''
  }

  const explainWorkflow = async () => {
    userRequest.value = userRequest.value.trim()
    if (!userRequest.value) return

    isExplaining.value = true
    workflowGraph.value = null
    try {
      const token =
        localStorage.getItem('access_token') ||
        localStorage.getItem('token') ||
        sessionStorage.getItem('access_token') ||
        sessionStorage.getItem('token')

      const response = await fetch('/api/v1/workflow/execute', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({
          natural_language_request: userRequest.value,
          export_workflow: true
        })
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.trim()) {
            try {
              const data = JSON.parse(line)
              handleStreamData(data)
            } catch (e) {
              console.warn('JSON parse error:', e, line)
            }
          }
        }
      }
      showRawJson.value = true
    } catch (error) {
      console.error('获取工作流计划失败:', error)
      alert('获取工作流计划失败: ' + error.message)
    } finally {
      isExplaining.value = false
    }
  }

  const importWorkflow = () => {
    importJson.value = ''
    showImportDialog.value = true
  }

  const confirmImport = () => {
    try {
      const parsed = JSON.parse(importJson.value)
      if (!parsed.nodes || !Array.isArray(parsed.nodes)) {
        throw new Error('Invalid workflow format')
      }
      workflowGraph.value = parsed
      showRawJson.value = true
      showImportDialog.value = false
    } catch (error) {
      alert('JSON 格式错误: ' + error.message)
    }
  }

  const exportWorkflow = () => {
    if (!workflowGraph.value) return

    const jsonStr = JSON.stringify(workflowGraph.value, null, 2)
    const blob = new Blob([jsonStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `workflow_${workflowGraph.value.workflow_id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleStreamData = data => {
    if (data.event === 'workflow_started') {
      if (data.session_id) {
        sessionId.value = data.session_id
      }
      if (data.is_continuation) {
        console.log('继续之前的workflow:', data.previous_workflow_id)
      }
    } else if (data.event === 'continuation_context') {
      console.log('继续上下文:', data.previous_request)
    } else if (data.event === 'task_graph_generated') {
      workflowGraph.value = {
        workflow_id: data.workflow_id,
        nodes: data.nodes.map(n => ({
          id: n.id,
          type: n.type,
          params: n.params,
          depends_on: n.depends_on || [],
          status: 'pending'
        }))
      }
      if (sessionId.value) {
        console.log('工作流已保存，session_id:', sessionId.value)
      }
    } else if (data.event === 'workflow_exported') {
      console.log('Workflow exported:', data.export_data)
    } else if (data.event === 'node_completed') {
      const node = workflowGraph.value?.nodes.find(n => n.id === data.node_id)
      if (node) {
        node.status = data.success ? 'completed' : 'failed'
        if (data.data) node.result = data.data
        if (data.error) node.error = data.error
      }
    } else if (data.event === 'workflow_completed') {
      workflowStatus.value = 'completed'
      if (data.session_id) {
        sessionId.value = data.session_id
      }
      addToHistory(workflowGraph.value)
    } else if (data.event === 'workflow_error') {
      console.error('Workflow error:', data.message || data.error)
      alert('工作流执行失败: ' + (data.message || data.error))
      workflowStatus.value = 'error'
    }
  }

  const addToHistory = graph => {
    history.value.unshift({
      id: Date.now(),
      request: userRequest.value,
      nodes: graph.nodes,
      workflow_id: graph.workflow_id,
      session_id: sessionId.value,
      timestamp: new Date().toISOString()
    })
    if (history.value.length > 10) history.value = history.value.slice(0, 10)
  }

  const loadFromHistory = item => {
    userRequest.value = item.request
    workflowGraph.value = { ...item, nodes: item.nodes }
    if (item.session_id) {
      sessionId.value = item.session_id
      hasStopped.value = true
    }
  }

  const getNodeTypeLabel = type => {
    const labels = {
      web_search: '网络搜索',
      code_execution: '代码执行',
      chart_generation: '图表生成',
      file_processing: '文件处理'
    }
    return labels[type] || type
  }

  const getNodeStatusClass = node => {
    return node.status || 'pending'
  }

  const getNodeStatusLabel = node => {
    if (node.error) return '失败'
    if (node.result) return '完成'
    if (node.status === 'running') return '运行中'
    if (node.status === 'pending') return '等待'
    return '等待'
  }

  const formatParams = params => {
    if (!params) return '{}'
    return JSON.stringify(params, null, 2)
  }

  const formatResult = result => {
    if (!result) return ''
    if (typeof result === 'string') return result
    return JSON.stringify(result, null, 2)
  }

  const formatJson = obj => {
    if (!obj) return ''
    return JSON.stringify(obj, null, 2)
  }

  const formatTime = timeString => {
    if (!timeString) return ''
    const date = new Date(timeString)
    const diff = Date.now() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    return date.toLocaleString()
  }

  // 进度计算
  const completedNodes = computed(() => {
    if (!workflowGraph.value?.nodes) return 0
    return workflowGraph.value.nodes.filter(n => n.status === 'completed' || n.result).length
  })

  const progressPercentage = computed(() => {
    if (!workflowGraph.value?.nodes?.length) return 0
    return Math.round((completedNodes.value / workflowGraph.value.nodes.length) * 100)
  })
</script>

<style scoped>
  .ephemeral-workflow {
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .input-section {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .input-header h3 {
    margin: 0;
    font-size: 16px;
    color: var(--text-primary);
  }

  .input-hint {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .request-input {
    width: 100%;
    padding: 12px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    font-size: 14px;
    resize: vertical;
    background: var(--bg-secondary);
    color: var(--text-primary);
  }

  .request-input:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .input-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .workflow-graph-section,
  .raw-json-section,
  .history-section {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .section-header h3 {
    margin: 0;
    font-size: 15px;
    color: var(--text-primary);
  }

  .workflow-id {
    font-size: 12px;
    color: var(--text-secondary);
    font-family: monospace;
  }

  .workflow-meta {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .workflow-progress {
    font-size: 12px;
    color: var(--primary-color);
    font-weight: 500;
  }

  .progress-bar-container {
    position: relative;
    height: 8px;
    background: var(--bg-tertiary);
    border-radius: 4px;
    overflow: hidden;
  }

  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, var(--primary-color), var(--success-color));
    border-radius: 4px;
    transition: width 0.3s ease;
  }

  .progress-text {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 10px;
    color: var(--text-primary);
    font-weight: 500;
  }

  .task-nodes {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .task-node {
    padding: 12px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-secondary);
  }

  .task-node.running {
    border-color: var(--warning-color);
  }

  .task-node.completed {
    border-color: var(--success-color);
  }

  .task-node.failed {
    border-color: var(--danger-color);
  }

  .node-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  .node-index {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--primary-color);
    color: white;
    border-radius: 50%;
    font-size: 12px;
    font-weight: bold;
  }

  .node-type {
    font-weight: 500;
    color: var(--text-primary);
  }

  .node-status {
    margin-left: auto;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
  }

  .node-status.pending {
    background: var(--bg-tertiary);
    color: var(--text-secondary);
  }

  .node-status.running {
    background: rgba(255, 193, 7, 0.2);
    color: var(--warning-color);
  }

  .node-status.completed {
    background: rgba(40, 167, 69, 0.2);
    color: var(--success-color);
  }

  .node-status.failed {
    background: rgba(220, 53, 69, 0.2);
    color: var(--danger-color);
  }

  .node-params pre {
    margin: 0;
    padding: 8px;
    background: var(--bg-primary);
    border-radius: 4px;
    font-size: 12px;
    overflow-x: auto;
  }

  .node-depends {
    margin-top: 8px;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .depends-label {
    margin-right: 4px;
  }

  .depends-item {
    margin-left: 4px;
    padding: 2px 6px;
    background: var(--bg-tertiary);
    border-radius: 4px;
    font-family: monospace;
  }

  .node-result,
  .node-error {
    margin-top: 8px;
  }

  .result-header,
  .error-header {
    font-size: 12px;
    font-weight: 500;
    margin-bottom: 4px;
  }

  .result-content {
    margin: 0;
    padding: 8px;
    background: rgba(40, 167, 69, 0.1);
    border-radius: 4px;
    font-size: 12px;
    overflow-x: auto;
  }

  .error-content {
    margin: 0;
    padding: 8px;
    background: rgba(220, 53, 69, 0.1);
    border-radius: 4px;
    font-size: 12px;
    overflow-x: auto;
    color: var(--danger-color);
  }

  .json-content {
    margin: 0;
    padding: 12px;
    background: var(--bg-secondary);
    border-radius: 8px;
    font-size: 12px;
    overflow-x: auto;
    max-height: 400px;
  }

  .history-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .history-item {
    padding: 10px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.2s;
  }

  .history-item:hover {
    background: var(--bg-secondary);
  }

  .history-request {
    font-size: 14px;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .history-meta {
    display: flex;
    gap: 12px;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .import-dialog {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .dialog-backdrop {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
  }

  .dialog-content {
    position: relative;
    width: 90%;
    max-width: 600px;
    padding: 20px;
    background: var(--bg-primary);
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  }

  .dialog-content h3 {
    margin: 0 0 16px;
    font-size: 18px;
    color: var(--text-primary);
  }

  .import-input {
    width: 100%;
    padding: 12px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    font-size: 13px;
    font-family: monospace;
    resize: vertical;
    background: var(--bg-secondary);
    color: var(--text-primary);
  }

  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 16px;
  }
</style>
