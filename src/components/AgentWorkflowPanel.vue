<template>
  <div class="agent-workflow-panel">
    <!-- 左侧：工作流控制 -->
    <div class="workflow-control">
      <!-- 输入区域 -->
      <div class="input-section">
        <textarea
          v-model="userRequest"
          class="request-input"
          placeholder="描述您想要执行的任务，例如：搜索最新AI新闻并生成摘要报告"
          rows="3"
          @keydown.ctrl.enter="executeWorkflow"
        />
        <div class="input-actions">
          <button v-if="isExecuting" class="btn-stop" @click="stopWorkflow">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
            </svg>
            <span>停止</span>
          </button>
          <button
            v-else-if="hasStopped && !workflowGraph"
            class="btn-continue"
            @click="continueWorkflow"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            <span>继续</span>
          </button>
          <button v-else class="btn-execute" :disabled="!userRequest.trim() || executingPlan" @click="executeWorkflow">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            <span>{{ executingPlan ? '生成计划中...' : '执行' }}</span>
          </button>
          <button class="btn-secondary" :disabled="!userRequest.trim() || executingPlan" @click="explainWorkflow">
            查看计划
          </button>
          <button class="btn-icon-sm" title="导入 JSON" @click="showImport = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- 快捷模板 -->
      <div class="templates-section">
        <h5>快捷模板</h5>
        <div class="template-list">
          <button v-for="t in templates" :key="t.id" class="template-btn" @click="userRequest = t.request">
            <span class="template-icon">{{ t.icon }}</span>
            <span class="template-text">{{ t.label }}</span>
          </button>
        </div>
      </div>

      <!-- 进度条 -->
      <div v-if="isExecuting || workflowStatus === 'completed'" class="progress-section">
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" :style="{ width: progressPercentage + '%' }"></div>
        </div>
        <div class="progress-text">
          <span>{{ completedNodes }}/{{ totalNodes }} 节点</span>
          <span>{{ progressPercentage }}%</span>
        </div>
      </div>

      <!-- 节点列表 -->
      <div v-if="workflowGraph" class="nodes-section">
        <h5>节点 ({{ workflowGraph.nodes?.length || 0 }})</h5>
        <div class="nodes-list">
          <div
            v-for="(node, idx) in workflowGraph.nodes"
            :key="node.id"
            :class="['node-item', `status-${node.status || 'pending'}`]"
            @click="selectNode(node)"
          >
            <div class="node-item-left">
              <span class="node-idx">{{ idx + 1 }}</span>
              <span class="node-type">{{ getNodeTypeLabel(node.type) }}</span>
            </div>
            <div class="node-item-right">
              <span :class="['node-status-badge', `status-${node.status || 'pending'}`]">
                {{ getStatusLabel(node.status) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 历史记录 -->
      <div v-if="history.length > 0" class="history-section">
        <h5>最近执行</h5>
        <div class="history-list">
          <div
            v-for="item in history"
            :key="item.id"
            class="history-item"
            @click="loadHistory(item)"
          >
            <span class="history-request">{{ item.request }}</span>
            <span class="history-meta">{{ item.nodes?.length || 0 }} 节点 · {{ formatTime(item.timestamp) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧：可视化面板 -->
    <div class="workflow-visual">
      <!-- 切换标签 -->
      <div class="visual-tabs">
        <button
          v-for="tab in visualTabs"
          :key="tab.key"
          :class="['visual-tab', { active: visualTab === tab.key }]"
          @click="visualTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- DAG 图 -->
      <WorkflowDAG
        v-show="visualTab === 'dag' && workflowGraph"
        :nodes="workflowGraph.nodes || []"
        @nodeSelect="selectNode"
      />
      <div v-show="visualTab === 'dag' && !workflowGraph" class="visual-empty">
        <p>输入任务描述后生成工作流图</p>
      </div>

      <!-- 日志 -->
      <WorkflowLogViewer
        v-show="visualTab === 'log'"
        :logs="logs"
        :active-node="selectedNode"
      />

      <!-- JSON 预览 -->
      <div v-show="visualTab === 'json'" class="json-preview">
        <pre v-if="workflowGraph">{{ formatJson(workflowGraph) }}</pre>
        <div v-else class="visual-empty">
          <p>暂无工作流数据</p>
        </div>
      </div>
    </div>

    <!-- 导入对话框 -->
    <div v-if="showImport" class="import-overlay" @click.self="showImport = false">
      <div class="import-dialog">
        <h4>导入工作流 JSON</h4>
        <textarea v-model="importJson" class="import-input" placeholder="粘贴工作流 JSON..." rows="12" />
        <div class="import-actions">
          <button class="btn-secondary" @click="showImport = false">取消</button>
          <button class="btn-primary" @click="confirmImport">导入</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed } from 'vue'
  import WorkflowDAG from './WorkflowDAG.vue'
  import WorkflowLogViewer from './WorkflowLogViewer.vue'

  const emit = defineEmits(['notify'])

  const userRequest = ref('')
  const workflowGraph = ref(null)
  const isExecuting = ref(false)
  const executingPlan = ref(false)
  const hasStopped = ref(false)
  const workflowStatus = ref('idle')
  const selectedNode = ref(null)
  const showImport = ref(false)
  const importJson = ref('')
  const visualTab = ref('dag')
  const logs = ref([])
  const history = ref([])
  const sessionId = ref('')

  let abortController = null

  const visualTabs = [
    { key: 'dag', label: 'DAG 图' },
    { key: 'log', label: '日志' },
    { key: 'json', label: 'JSON' }
  ]

  const templates = [
    { id: 'search', icon: '🔍', label: '搜索并总结', request: '搜索最新的技术新闻并生成总结报告' },
    { id: 'chart', icon: '📊', label: '数据分析', request: '分析项目数据并生成可视化图表' },
    { id: 'code', icon: '💻', label: '代码生成', request: '生成一个用户登录页面的前端代码' },
    { id: 'file', icon: '📁', label: '文件处理', request: '处理上传的 CSV 文件并生成分析报告' }
  ]

  const totalNodes = computed(() => workflowGraph.value?.nodes?.length || 0)
  const completedNodes = computed(() => {
    if (!workflowGraph.value?.nodes) return 0
    return workflowGraph.value.nodes.filter(n => n.status === 'completed' || n.result).length
  })
  const progressPercentage = computed(() => {
    if (!totalNodes.value) return 0
    return Math.round((completedNodes.value / totalNodes.value) * 100)
  })

  function getNodeTypeLabel(type) {
    const labels = {
      web_search: '网络搜索', code_execution: '代码执行', chart_generation: '图表生成',
      file_processing: '文件处理', data_analysis: '数据分析', api_call: 'API 调用',
      text_generation: '文本生成', image_generation: '图像生成'
    }
    return labels[type] || type
  }

  function getStatusLabel(status) {
    const labels = { pending: '等待', running: '执行', completed: '完成', failed: '失败' }
    return labels[status] || '等待'
  }

  function formatTime(ts) {
    if (!ts) return ''
    const d = new Date(ts)
    const diff = Date.now() - d.getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return '刚刚'
    if (mins < 60) return `${mins}分钟前`
    return d.toLocaleDateString('zh-CN')
  }

  function formatJson(obj) {
    return JSON.stringify(obj, null, 2)
  }

  function addLog(level, message, node) {
    logs.value.push({
      id: Date.now() + Math.random(),
      timestamp: new Date().toISOString(),
      level,
      message,
      node: node?.title || node?.id
    })
  }

  function selectNode(node) {
    selectedNode.value = node
  }

  async function executeWorkflow() {
    if (!userRequest.value.trim() || isExecuting.value) return
    isExecuting.value = true
    hasStopped.value = false
    workflowGraph.value = null
    workflowStatus.value = 'running'
    logs.value = []
    abortController = new AbortController()

    addLog('info', '开始执行工作流')

    try {
      const token = localStorage.getItem('access_token') || localStorage.getItem('token') || ''
      const response = await fetch('/api/v1/workflow/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: token ? `Bearer ${token}` : '' },
        body: JSON.stringify({ natural_language_request: userRequest.value }),
        signal: abortController.signal
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
          if (!line.trim()) continue
          try {
            const data = JSON.parse(line)
            handleStreamEvent(data)
          } catch (e) {
            console.warn('JSON parse error:', e)
          }
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        addLog('error', `执行失败: ${error.message}`)
      }
    } finally {
      isExecuting.value = false
      abortController = null
    }
  }

  function handleStreamEvent(data) {
    if (data.event === 'workflow_started') {
      if (data.session_id) sessionId.value = data.session_id
      addLog('info', '工作流已启动')
    } else if (data.event === 'task_graph_generated') {
      workflowGraph.value = {
        workflow_id: data.workflow_id,
        nodes: data.nodes.map(n => ({
          id: n.id,
          type: n.type,
          params: n.params,
          depends_on: n.depends_on || [],
          status: 'pending',
          title: n.params?.description || n.id
        }))
      }
      addLog('info', `生成任务图: ${data.nodes.length} 个节点`)
    } else if (data.event === 'node_started') {
      const node = workflowGraph.value?.nodes.find(n => n.id === data.node_id)
      if (node) {
        node.status = 'running'
        addLog('info', `节点开始执行: ${node.title || node.id}`, node)
      }
    } else if (data.event === 'node_completed') {
      const node = workflowGraph.value?.nodes.find(n => n.id === data.node_id)
      if (node) {
        node.status = data.success ? 'completed' : 'failed'
        if (data.data) node.result = data.data
        if (data.error) node.error = data.error
        addLog(data.success ? 'info' : 'error', `节点执行${data.success ? '完成' : '失败'}: ${node.title || node.id}`, node)
      }
    } else if (data.event === 'workflow_completed') {
      workflowStatus.value = 'completed'
      addLog('info', '工作流执行完成')
      addToHistory()
    } else if (data.event === 'workflow_error') {
      addLog('error', `工作流错误: ${data.message || data.error}`)
      workflowStatus.value = 'error'
    } else if (data.event === 'stream' || data.content) {
      addLog('info', data.content || data.text || '')
    }
  }

  function stopWorkflow() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    isExecuting.value = false
    hasStopped.value = true
    workflowStatus.value = 'stopped'
    addLog('warn', '工作流已停止')
  }

  function continueWorkflow() {
    hasStopped.value = false
    executeWorkflow()
  }

  async function explainWorkflow() {
    if (!userRequest.value.trim()) return
    executingPlan.value = true
    workflowGraph.value = null

    try {
      const token = localStorage.getItem('access_token') || localStorage.getItem('token') || ''
      const response = await fetch('/api/v1/workflow/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: token ? `Bearer ${token}` : '' },
        body: JSON.stringify({ natural_language_request: userRequest.value, export_workflow: true })
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
          if (!line.trim()) continue
          try {
            handleStreamEvent(JSON.parse(line))
          } catch (e) {}
        }
      }
    } catch (e) {
      addLog('error', `获取计划失败: ${e.message}`)
    } finally {
      executingPlan.value = false
    }
  }

  function confirmImport() {
    try {
      const parsed = JSON.parse(importJson.value)
      if (!parsed.nodes || !Array.isArray(parsed.nodes)) throw new Error('Invalid format')
      workflowGraph.value = {
        ...parsed,
        nodes: parsed.nodes.map(n => ({ ...n, status: n.status || 'pending', title: n.title || n.params?.description || n.id }))
      }
      showImport.value = false
      addLog('info', `导入工作流: ${parsed.nodes.length} 个节点`)
    } catch (e) {
      addLog('error', `导入失败: ${e.message}`)
    }
  }

  function addToHistory() {
    history.value.unshift({
      id: Date.now(),
      request: userRequest.value,
      nodes: workflowGraph.value?.nodes,
      timestamp: new Date().toISOString()
    })
    if (history.value.length > 10) history.value = history.value.slice(0, 10)
  }

  function loadHistory(item) {
    userRequest.value = item.request
    workflowGraph.value = { ...item, nodes: item.nodes?.map(n => ({ ...n, status: n.status || 'pending' })) }
  }
</script>

<style scoped>
  .agent-workflow-panel {
    display: flex;
    height: 100%;
    background: var(--bg-primary, #0f172a);
  }

  .workflow-control {
    width: 360px;
    border-right: 1px solid var(--border-color, #2d3748);
    background: var(--bg-secondary, #16213e);
    overflow-y: auto;
    flex-shrink: 0;
  }

  .input-section { padding: 16px; border-bottom: 1px solid var(--border-color, #2d3748); }

  .request-input {
    width: 100%;
    padding: 12px;
    border: 1px solid var(--border-color, #2d3748);
    border-radius: 8px;
    background: var(--bg-tertiary, #1f2937);
    color: var(--text-primary, #e0e0e0);
    font-size: 13px;
    resize: vertical;
    margin-bottom: 12px;
  }

  .request-input:focus { outline: none; border-color: var(--accent-color, #4f46e5); }

  .input-actions { display: flex; gap: 8px; flex-wrap: wrap; }

  .btn-execute, .btn-stop, .btn-continue {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: 6px;
    border: none;
    font-size: 13px;
    cursor: pointer;
    color: white;
  }

  .btn-execute { background: var(--accent-color, #4f46e5); }
  .btn-execute:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-stop { background: #ef4444; }
  .btn-continue { background: #f59e0b; }
  .btn-execute svg, .btn-stop svg, .btn-continue svg { width: 16px; height: 16px; }

  .btn-secondary {
    padding: 8px 12px;
    border-radius: 6px;
    border: 1px solid var(--border-color, #2d3748);
    background: transparent;
    color: var(--text-primary, #e0e0e0);
    font-size: 13px;
    cursor: pointer;
  }

  .btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-icon-sm {
    width: 36px;
    height: 36px;
    border: 1px solid var(--border-color, #2d3748);
    border-radius: 6px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-icon-sm:hover { background: var(--bg-hover, #374151); }
  .btn-icon-sm svg { width: 16px; height: 16px; }

  .templates-section { padding: 12px 16px; border-bottom: 1px solid var(--border-color, #2d3748); }
  .templates-section h5 { margin: 0 0 8px; font-size: 12px; color: var(--text-secondary, #9ca3af); }

  .template-list { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }

  .template-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px;
    border: 1px solid var(--border-color, #2d3748);
    border-radius: 8px;
    background: var(--bg-tertiary, #1f2937);
    color: var(--text-primary, #e0e0e0);
    cursor: pointer;
    font-size: 12px;
  }

  .template-btn:hover { border-color: var(--accent-color, #4f46e5); }
  .template-icon { font-size: 16px; }

  .progress-section { padding: 12px 16px; border-bottom: 1px solid var(--border-color, #2d3748); }

  .progress-bar-bg {
    height: 6px;
    background: var(--bg-tertiary, #1f2937);
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 6px;
  }

  .progress-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent-color, #4f46e5), #10b981);
    border-radius: 3px;
    transition: width 0.3s;
  }

  .progress-text { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-secondary, #9ca3af); }

  .nodes-section { padding: 12px 16px; border-bottom: 1px solid var(--border-color, #2d3748); }
  .nodes-section h5 { margin: 0 0 8px; font-size: 12px; color: var(--text-secondary, #9ca3af); }

  .nodes-list { display: flex; flex-direction: column; gap: 6px; }

  .node-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border-radius: 6px;
    background: var(--bg-tertiary, #1f2937);
    cursor: pointer;
  }

  .node-item:hover { background: var(--bg-hover, #374151); }
  .node-item.status-running { border-left: 3px solid #f59e0b; }
  .node-item.status-completed { border-left: 3px solid #10b981; }
  .node-item.status-failed { border-left: 3px solid #ef4444; }

  .node-item-left { display: flex; align-items: center; gap: 8px; }
  .node-idx {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--accent-muted, #4f46e533);
    color: var(--accent-color, #4f46e5);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 600;
  }
  .node-type { font-size: 12px; }

  .node-status-badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; }
  .node-status-badge.status-pending { background: var(--bg-secondary, #16213e); color: var(--text-secondary, #9ca3af); }
  .node-status-badge.status-running { background: #f59e0b22; color: #f59e0b; }
  .node-status-badge.status-completed { background: #10b98122; color: #10b981; }
  .node-status-badge.status-failed { background: #ef444422; color: #ef4444; }

  .history-section { padding: 12px 16px; }
  .history-section h5 { margin: 0 0 8px; font-size: 12px; color: var(--text-secondary, #9ca3af); }

  .history-list { display: flex; flex-direction: column; gap: 6px; }

  .history-item {
    padding: 10px;
    border-radius: 6px;
    background: var(--bg-tertiary, #1f2937);
    cursor: pointer;
  }

  .history-item:hover { background: var(--bg-hover, #374151); }
  .history-request { font-size: 12px; margin-bottom: 4px; }
  .history-meta { font-size: 11px; color: var(--text-secondary, #9ca3af); }

  .workflow-visual {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .visual-tabs {
    display: flex;
    gap: 4px;
    padding: 8px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
    background: var(--bg-secondary, #16213e);
  }

  .visual-tab {
    padding: 6px 14px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    font-size: 13px;
  }

  .visual-tab:hover { background: var(--bg-hover, #374151); }
  .visual-tab.active { background: var(--accent-muted, #4f46e533); color: var(--accent-color, #4f46e5); }

  .visual-empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary, #9ca3af);
    font-size: 14px;
  }

  .json-preview {
    flex: 1;
    overflow: auto;
    padding: 16px;
  }

  .json-preview pre {
    margin: 0;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    line-height: 1.6;
  }

  .import-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .import-dialog {
    width: 500px;
    max-height: 80%;
    background: var(--bg-secondary, #16213e);
    border-radius: 12px;
    padding: 24px;
    border: 1px solid var(--border-color, #2d3748);
  }

  .import-dialog h4 { margin: 0 0 16px; font-size: 16px; }

  .import-input {
    width: 100%;
    padding: 12px;
    border: 1px solid var(--border-color, #2d3748);
    border-radius: 8px;
    background: var(--bg-tertiary, #1f2937);
    color: var(--text-primary, #e0e0e0);
    font-size: 13px;
    font-family: monospace;
    resize: vertical;
    margin-bottom: 16px;
  }

  .import-input:focus { outline: none; border-color: var(--accent-color, #4f46e5); }

  .import-actions { display: flex; justify-content: flex-end; gap: 8px; }

  .btn-primary {
    padding: 8px 16px;
    border-radius: 6px;
    border: none;
    background: var(--accent-color, #4f46e5);
    color: white;
    font-size: 13px;
    cursor: pointer;
  }
</style>
