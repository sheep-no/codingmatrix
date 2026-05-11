<template>
  <div class="workflow-page">
    <!-- 顶部导航栏 -->
    <header class="page-header">
      <div class="header-left">
        <button class="back-btn" @click="router.push('/')">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="15 18 9 12 15 6"></polyline>
          </svg>
          返回
        </button>
        <h1 class="page-title">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="title-icon">
            <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"></polygon>
            <line x1="12" y1="22" x2="12" y2="15.5"></line>
            <polyline points="22 8.5 12 15.5 2 8.5"></polyline>
            <polyline points="2 15.5 12 8.5 22 15.5"></polyline>
            <line x1="12" y1="2" x2="12" y2="8.5"></line>
          </svg>
          智能工作流
        </h1>
      </div>
      <div class="header-right">
        <button v-if="workflowGraph && workflowStatus !== 'completed'" class="header-btn header-btn-success" @click="runImportedWorkflow">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
          </svg>
          运行
        </button>
        <button v-if="workflowGraph" class="header-btn" @click="showRawJson = !showRawJson">
          {{ showRawJson ? '隐藏' : '查看' }} JSON
        </button>
        <button v-if="workflowGraph" class="header-btn" @click="exportWorkflow">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
          导出
        </button>
        <button v-if="workflowGraph" class="header-btn header-btn-danger" @click="deleteWorkflow">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2"></path>
          </svg>
          删除
        </button>
        <button class="collapse-toggle" @click="leftPanelCollapsed = !leftPanelCollapsed" :title="leftPanelCollapsed ? '展开面板' : '收缩面板'">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :style="{ transform: leftPanelCollapsed ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }">
            <polyline points="11 17 6 12 11 7"></polyline>
            <polyline points="18 17 13 12 18 7"></polyline>
          </svg>
        </button>
        <button class="header-btn" @click="showImportDialog = true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="17 8 12 3 7 8"></polyline>
            <line x1="12" y1="3" x2="12" y2="15"></line>
          </svg>
          导入
        </button>
      </div>
    </header>

    <div class="page-content" :class="{ 'panel-collapsed': leftPanelCollapsed }">
      <!-- 左侧面板 -->
      <aside class="left-panel">
        <!-- 输入区域 -->
        <section class="input-card">
          <div class="card-header">
            <h2>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
              描述任务
            </h2>
          </div>
          <textarea
            v-model="userRequest"
            class="request-input"
            placeholder="例如：帮我搜索最新的AI新闻，然后生成一个摘要报告，最后发送邮件"
            rows="5"
            :disabled="isExecuting"
          ></textarea>
          <div class="input-actions">
            <button
              v-if="isExecuting"
              class="btn btn-danger"
              @click="stopWorkflow"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2"></rect>
              </svg>
              停止
            </button>
            <button
              v-else-if="hasStopped && !workflowGraph"
              class="btn btn-warning"
              @click="continueWorkflow"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
              继续
            </button>
            <button
              v-else
              class="btn btn-primary btn-execute"
              :disabled="!userRequest.trim()"
              @click="executeWorkflow"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
              执行工作流
            </button>
            <button class="btn btn-secondary" :loading="isExplaining" @click="explainWorkflow">
              查看计划
            </button>
          </div>
        </section>

        <!-- 快捷模板 -->
        <section class="templates-card">
          <div class="card-header">
            <h2>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="7" height="7"></rect>
                <rect x="14" y="3" width="7" height="7"></rect>
                <rect x="14" y="14" width="7" height="7"></rect>
                <rect x="3" y="14" width="7" height="7"></rect>
              </svg>
              快捷模板
            </h2>
          </div>
          <div class="template-list">
            <button
              v-for="tpl in templates"
              :key="tpl.id"
              class="template-btn"
              @click="userRequest = tpl.text"
            >
              <span class="template-icon">{{ tpl.icon }}</span>
              <span class="template-text">{{ tpl.label }}</span>
            </button>
          </div>
        </section>

        <!-- 历史记录 -->
        <section class="history-card">
          <div class="card-header">
            <h2>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <polyline points="12 6 12 12 16 14"></polyline>
              </svg>
              最近工作流
            </h2>
          </div>
          <div v-if="history.length === 0" class="history-empty">
            <p>{{ hasToken ? '暂无历史记录，快去执行工作流吧！' : '请先登录以查看历史记录' }}</p>
          </div>
          <div v-else class="history-list">
            <button
              v-for="item in history"
              :key="item.workflow_id"
              class="history-item"
              @click="loadFromHistory(item)"
            >
              <div class="history-content">
                <div class="history-request">{{ item.request }}</div>
                <div class="history-meta">
                  <span class="history-time">{{ formatTime(item.created_at) }}</span>
                  <span class="history-nodes">{{ item.nodes_count || 0 }} 个节点</span>
                  <span class="history-status" :class="item.status">{{ item.status || 'unknown' }}</span>
                </div>
              </div>
              <button
                class="history-delete"
                title="删除"
                @click.stop="deleteHistory(item.workflow_id)"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </button>
          </div>

          <!-- 分页控件 -->
          <div v-if="historyTotal > historyPageSize" class="history-pagination">
            <button
              class="page-btn"
              :disabled="!hasPrevPage"
              @click="goToPage(historyPage - 1)"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="15 18 9 12 15 6"></polyline>
              </svg>
            </button>
            <span class="page-info">
              {{ historyPage }} / {{ Math.ceil(historyTotal / historyPageSize) }}
              <span class="page-total">（共 {{ historyTotal }} 条）</span>
            </span>
            <button
              class="page-btn"
              :disabled="!hasNextPage"
              @click="goToPage(historyPage + 1)"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 18 15 12 9 6"></polyline>
              </svg>
            </button>
          </div>
        </section>
      </aside>

      <!-- 右侧面板 -->
      <main class="right-panel">
        <!-- 空状态 -->
        <div v-if="!workflowGraph && !isExecuting" class="empty-state">
          <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="empty-icon">
            <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"></polygon>
            <line x1="12" y1="22" x2="12" y2="15.5"></line>
            <polyline points="22 8.5 12 15.5 2 8.5"></polyline>
            <polyline points="2 15.5 12 8.5 22 15.5"></polyline>
            <line x1="12" y1="2" x2="12" y2="8.5"></line>
          </svg>
          <h2>输入任务描述开始工作流</h2>
          <p>系统会自动将您的需求拆解为可执行的工作流步骤</p>
        </div>

        <!-- 执行中状态 -->
        <div v-if="isExecuting && !workflowGraph" class="loading-state">
          <div class="loading-spinner"></div>
          <h2>正在生成工作流计划...</h2>
          <p>AI 正在分析您的需求并拆解任务</p>
        </div>

        <!-- 工作流可视化 -->
        <div v-if="workflowGraph" class="workflow-visualization">
          <!-- 头部信息 -->
          <div class="workflow-header">
            <div class="workflow-info">
              <h2>工作流计划</h2>
              <span class="workflow-id">{{ workflowGraph.workflow_id }}</span>
            </div>
            <div v-if="isExecuting || workflowStatus === 'completed'" class="workflow-progress-info">
              <span class="progress-label">{{ completedNodes }}/{{ workflowGraph.nodes.length }}</span>
              <span class="progress-percentage">{{ progressPercentage }}%</span>
            </div>
          </div>

          <!-- 进度条 -->
          <div v-if="isExecuting || workflowStatus === 'completed'" class="progress-bar-wrapper">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: progressPercentage + '%' }"></div>
            </div>
          </div>

          <!-- 节点列表 -->
          <div class="nodes-container">
            <div
              v-for="(node, index) in workflowGraph.nodes"
              :key="node.id"
              class="node-card"
              :class="getNodeStatusClass(node)"
            >
              <!-- 连接线 -->
              <div v-if="index > 0" class="node-connector"></div>

              <div class="node-header">
                <div class="node-index">{{ index + 1 }}</div>
                <div class="node-type-info">
                  <span class="node-type">{{ getNodeTypeLabel(node.type) }}</span>
                  <span v-if="node.depends_on && node.depends_on.length > 0" class="node-depends">
                    依赖: {{ node.depends_on.join(', ') }}
                  </span>
                </div>
                <span class="node-status" :class="getNodeStatusClass(node)">
                  {{ getNodeStatusLabel(node) }}
                </span>
              </div>

              <!-- 参数 -->
              <div class="node-params">
                <pre>{{ formatParams(node.params) }}</pre>
              </div>

              <!-- 结果 -->
              <div v-if="node.result" class="node-result">
                <div class="result-header">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                  执行结果
                </div>
                <pre class="result-content">{{ formatResult(node.result) }}</pre>
              </div>

              <!-- 错误 -->
              <div v-if="node.error" class="node-error">
                <div class="error-header">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="15" y1="9" x2="9" y2="15"></line>
                    <line x1="9" y1="9" x2="15" y2="15"></line>
                  </svg>
                  错误信息
                </div>
                <pre class="error-content">{{ node.error }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- JSON 预览 -->
        <div v-if="showRawJson && workflowGraph" class="json-preview">
          <div class="json-header">
            <h2>工作流 JSON</h2>
            <button class="close-btn" @click="showRawJson = false">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
          <pre class="json-content">{{ formatJson(workflowGraph) }}</pre>
        </div>
      </main>
    </div>

    <!-- 导入对话框 -->
    <div v-if="showImportDialog" class="import-modal">
      <div class="modal-backdrop" @click="showImportDialog = false"></div>
      <div class="modal-content">
        <div class="modal-header">
          <h2>导入工作流 JSON</h2>
          <button class="close-btn" @click="showImportDialog = false">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        <textarea
          v-model="importJson"
          class="import-input"
          placeholder='粘贴工作流 JSON，例如：{"nodes": [...]}'
          rows="12"
        ></textarea>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showImportDialog = false">取消</button>
          <button class="btn btn-primary" @click="confirmImport">确认导入</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/utils/api/index'

const router = useRouter()

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
const historyPage = ref(1)
const historyPageSize = ref(20)
const historyTotal = ref(0)
const isImported = ref(false)
const leftPanelCollapsed = ref(false)

let abortController = null

const templates = [
  { id: 1, icon: '🔍', label: '搜索并总结新闻', text: '帮我搜索最新的AI领域新闻，筛选出重要的5条，然后生成一份摘要报告' },
  { id: 2, icon: '📊', label: '数据分析报告', text: '分析 GitHub 上 Python 项目的 star 趋势，生成可视化图表和总结报告' },
  { id: 3, icon: '📧', label: '邮件自动化', text: '检查我的待办事项，将未完成的任务整理成邮件发送给我自己' },
  { id: 4, icon: '🔧', label: '代码检查', text: '扫描当前项目的代码质量，找出潜在问题并生成改进建议报告' },
]

onMounted(() => {
  fetchHistory()
})

onUnmounted(() => {
  stopStatusPolling()
})

const fetchHistory = async () => {
  try {
    const token = localStorage.getItem('access_token')
    if (!token) return

    const resp = await fetch(`/api/v1/workflow/history?page=${historyPage.value}&page_size=${historyPageSize.value}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    if (resp.ok) {
      const data = await resp.json()
      history.value = data.items || []
      historyTotal.value = data.total || 0
    }
  } catch (e) {
    console.error('获取工作流历史失败:', e)
  }
}

const goToPage = (page) => {
  const maxPage = Math.ceil(historyTotal.value / historyPageSize.value)
  if (page < 1 || page > maxPage) return
  historyPage.value = page
  fetchHistory()
}

const hasNextPage = computed(() => {
  return historyPage.value < Math.ceil(historyTotal.value / historyPageSize.value)
})

const hasPrevPage = computed(() => {
  return historyPage.value > 1
})

const hasToken = computed(() => !!localStorage.getItem('access_token'))

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
  stopStatusPolling()
}

const runImportedWorkflow = async () => {
  if (!workflowGraph.value) return

  isExecuting.value = true
  hasStopped.value = false
  workflowStatus.value = 'running'
  abortController = new AbortController()

  const workflowId = workflowGraph.value.workflow_id

  try {
    const token =
      localStorage.getItem('access_token') ||
      localStorage.getItem('token') ||
      sessionStorage.getItem('access_token') ||
      sessionStorage.getItem('token')

    const response = await fetch(`/api/v1/workflow/${workflowId}/execute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: token ? `Bearer ${token}` : ''
      },
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

const resetWorkflow = () => {
  hasStopped.value = false
  sessionId.value = ''
  workflowGraph.value = null
  workflowStatus.value = 'idle'
  userRequest.value = ''
  isImported.value = false
  stopStatusPolling()
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

const confirmImport = async () => {
  try {
    const parsed = JSON.parse(importJson.value)
    if (!parsed.nodes || !Array.isArray(parsed.nodes)) {
      throw new Error('Invalid workflow format')
    }
    const token = localStorage.getItem('access_token')
    if (!token) {
      alert('请先登录')
      return
    }

    const resp = await fetch('/api/v1/workflow/import', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(parsed)
    })

    if (!resp.ok) {
      const err = await resp.json()
      throw new Error(err.detail || '导入失败')
    }

    const data = await resp.json()
    workflowGraph.value = {
      workflow_id: data.workflow_id,
      nodes: parsed.nodes.map(n => ({
        id: n.id,
        type: n.type,
        params: n.params,
        depends_on: n.depends_on || [],
        status: 'pending'
      }))
    }
    isImported.value = true
    showRawJson.value = true
    showImportDialog.value = false
    alert(`导入成功！共 ${data.node_count} 个节点，点击顶部"运行"按钮开始执行`)
  } catch (error) {
    alert('导入失败: ' + error.message)
  }
}

const exportWorkflow = async () => {
  if (!workflowGraph.value) return

  const token = localStorage.getItem('access_token')
  const workflowId = workflowGraph.value.workflow_id

  if (token && workflowId) {
    try {
      const resp = await fetch(`/api/v1/workflow/export/${workflowId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (resp.ok) {
        const data = await resp.json()
        const jsonStr = JSON.stringify(data.export_data, null, 2)
        const blob = new Blob([jsonStr], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `workflow_${workflowId}.json`
        a.click()
        URL.revokeObjectURL(url)
        return
      }
    } catch (e) {
      console.warn('后端导出失败，使用本地导出:', e)
    }
  }

  const jsonStr = JSON.stringify(workflowGraph.value, null, 2)
  const blob = new Blob([jsonStr], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `workflow_${workflowId || 'local'}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const deleteWorkflow = async () => {
  if (!workflowGraph.value) return
  if (!confirm('确定要删除当前工作流吗？')) return

  const token = localStorage.getItem('access_token')
  const workflowId = workflowGraph.value.workflow_id

  if (!token || !workflowId) return

  try {
    const resp = await fetch(`/api/v1/workflow/${workflowId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    })

    if (resp.ok) {
      workflowGraph.value = null
      workflowStatus.value = 'idle'
      alert('工作流已删除')
    }
  } catch (e) {
    console.error('删除工作流失败:', e)
    alert('删除失败: ' + e.message)
  }
}

let statusPollTimer = null

const startStatusPolling = (workflowId) => {
  stopStatusPolling()
  statusPollTimer = setInterval(async () => {
    if (!workflowGraph.value || workflowStatus.value === 'completed') {
      stopStatusPolling()
      return
    }
    await fetchWorkflowStatus(workflowId)
  }, 3000)
}

const stopStatusPolling = () => {
  if (statusPollTimer) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
}

const fetchWorkflowStatus = async (workflowId) => {
  try {
    const token = localStorage.getItem('access_token')
    if (!token) return

    const resp = await fetch(`/api/v1/workflow/status/${workflowId}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    if (!resp.ok) return

    const data = await resp.json()
    if (data.status && workflowGraph.value) {
      workflowStatus.value = data.status
      if (data.summary) {
        const completedCount = data.summary.completed_nodes || 0
        workflowGraph.value.nodes.forEach((node, idx) => {
          if (idx < completedCount && node.status === 'pending') {
            node.status = 'completed'
          }
        })
      }
    }
  } catch (e) {
    console.error('获取工作流状态失败:', e)
  }
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
    startStatusPolling(data.workflow_id)
  } else if (data.event === 'workflow_exported') {
    console.log('Workflow exported:', data.export_data)
  } else if (data.event === 'node_started') {
    const node = workflowGraph.value?.nodes.find(n => n.id === data.node_id)
    if (node) {
      node.status = 'running'
    }
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
    stopStatusPolling()
    fetchHistory()
  } else if (data.event === 'workflow_error') {
    console.error('Workflow error:', data.message || data.error)
    alert('工作流执行失败: ' + (data.message || data.error))
    workflowStatus.value = 'error'
    stopStatusPolling()
  }
}

const loadFromHistory = item => {
  userRequest.value = item.request
  if (item.task_graph && item.task_graph.nodes) {
    workflowGraph.value = {
      workflow_id: item.workflow_id,
      nodes: item.task_graph.nodes.map(n => ({
        id: n.id,
        type: n.type,
        params: n.params,
        depends_on: n.depends_on || [],
        status: n.status || 'completed'
      }))
    }
  }
  if (item.workflow_id) {
    sessionId.value = item.workflow_id
    hasStopped.value = true
  }
}

const deleteHistory = async (workflowId) => {
  if (!confirm('确定要删除这条历史记录吗？')) return

  try {
    const token = localStorage.getItem('access_token')
    if (!token) return

    const resp = await fetch(`/api/v1/workflow/history/${workflowId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    })

    if (resp.ok) {
      history.value = history.value.filter(item => item.workflow_id !== workflowId)
    }
  } catch (e) {
    console.error('删除历史记录失败:', e)
  }
}

const getNodeTypeLabel = type => {
  const labels = {
    web_search: '网络搜索',
    code_execution: '代码执行',
    chart_generation: '图表生成',
    file_processing: '文件处理',
    analysis: '数据分析',
    report: '报告生成',
    notification: '通知发送'
  }
  return labels[type] || type
}

const getNodeStatusClass = node => {
  if (node.error) return 'failed'
  if (node.result || node.status === 'completed') return 'completed'
  if (node.status === 'running') return 'running'
  return 'pending'
}

const getNodeStatusLabel = node => {
  if (node.error) return '失败'
  if (node.result || node.status === 'completed') return '完成'
  if (node.status === 'running') return '运行中'
  if (node.status === 'pending') return '等待'
  return '等待'
}

const formatParams = params => {
  if (!params) return '{}'
  if (typeof params === 'string') return params
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
.workflow-page {
  min-height: 100vh;
  background: var(--bg-primary);
  color: var(--text-primary);
  display: flex;
  flex-direction: column;
}

/* 顶部导航 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-bottom: 1px solid #334155;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: transparent;
  border: 1px solid #475569;
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.back-btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-color: var(--text-tertiary);
}

.page-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 20px;
  font-weight: 600;
  margin: 0;
  background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.title-icon {
  stroke: #60a5fa;
}

.header-right {
  display: flex;
  gap: 8px;
}

.header-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--bg-secondary);
  border: 1px solid #334155;
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.header-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.header-btn-danger {
  border-color: rgba(239, 68, 68, 0.3);
  color: var(--color-danger-500);
}

.header-btn-danger:hover {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.5);
  color: #f87171;
}

.header-btn-success {
  border-color: rgba(16, 185, 129, 0.3);
  color: var(--color-success-500);
}

.header-btn-success:hover {
  background: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.5);
  color: #34d399;
}

/* 收缩切换按钮 */
.collapse-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px 10px;
  background: transparent;
  border: 1px solid #475569;
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s;
}

.collapse-toggle:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: #64748b;
  color: var(--text-primary);
}

/* 页面内容 */
.page-content {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 0;
  flex: 1;
  overflow: hidden;
  transition: grid-template-columns 0.3s ease;
}

.page-content.panel-collapsed {
  grid-template-columns: 0 1fr;
}

/* 左侧面板 */
.left-panel {
  background: var(--bg-secondary);
  border-right: 1px solid #334155;
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
  opacity: 1;
  transition: opacity 0.2s ease, padding 0.3s ease, border 0.3s ease;
}

.panel-collapsed .left-panel {
  opacity: 0;
  padding: 0;
  border-right: none;
  pointer-events: none;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.card-header h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

/* 输入卡片 */
.input-card {
  background: var(--bg-primary);
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
}

.request-input {
  width: 100%;
  padding: 12px;
  border: 1px solid #475569;
  border-radius: 8px;
  font-size: 14px;
  resize: vertical;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-family: inherit;
  margin-bottom: 12px;
}

.request-input:focus {
  outline: none;
  border-color: #60a5fa;
  box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.2);
}

.request-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.input-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* 按钮样式 */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.btn-primary {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-secondary:hover {
  background: #475569;
}

.btn-danger {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: white;
}

.btn-danger:hover {
  background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
}

.btn-warning {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  color: white;
}

.btn-warning:hover {
  background: linear-gradient(135deg, #d97706 0%, #b45309 100%);
}

.btn-success {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: white;
}

.btn-success:hover {
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
}

.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid #475569;
}

.btn-ghost:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.btn-execute {
  flex: 1;
}

/* 模板卡片 */
.templates-card {
  background: var(--bg-primary);
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
}

.template-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.template-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  background: var(--bg-secondary);
  border: 1px solid #334155;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.template-btn:hover {
  background: var(--bg-tertiary);
  border-color: #60a5fa;
  transform: translateY(-2px);
}

.template-icon {
  font-size: 20px;
}

.template-text {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
}

/* 历史卡片 */
.history-card {
  background: var(--bg-primary);
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.history-empty {
  text-align: center;
  padding: 20px 0;
  color: var(--text-tertiary);
  font-size: 13px;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border: 1px solid #334155;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
  width: 100%;
}

.history-item:hover {
  background: var(--bg-tertiary);
  border-color: #60a5fa;
}

.history-content {
  flex: 1;
  min-width: 0;
}

.history-delete {
  display: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
  flex-shrink: 0;
  margin-left: 8px;
}

.history-item:hover .history-delete {
  display: flex;
}

.history-delete:hover {
  background: #ef4444;
  color: white;
}

.history-request {
  font-size: 13px;
  color: var(--text-primary);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.history-status {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
}

.history-status.completed {
  background: rgba(16, 185, 129, 0.15);
  color: var(--color-success-500);
}

.history-status.failed {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-danger-500);
}

.history-status.running {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.history-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #334155;
}

.page-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: var(--bg-secondary);
  border: 1px solid #334155;
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.page-btn:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.page-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.page-info {
  font-size: 12px;
  color: var(--text-tertiary);
}

.page-total {
  color: #475569;
}

/* 右侧面板 */
.right-panel {
  padding: 24px;
  overflow-y: auto;
  background: var(--bg-primary);
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  text-align: center;
}

.empty-icon {
  stroke: #475569;
  margin-bottom: 24px;
}

.empty-state h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 8px;
}

.empty-state p {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  text-align: center;
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #334155;
  border-top-color: #60a5fa;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 24px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-state h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 8px;
}

.loading-state p {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

/* 工作流可视化 */
.workflow-visualization {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.workflow-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.workflow-info h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.workflow-id {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: monospace;
}

.workflow-progress-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-label {
  font-size: 14px;
  color: var(--text-secondary);
}

.progress-percentage {
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* 进度条 */
.progress-bar-wrapper {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 4px;
}

.progress-bar {
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  border-radius: 4px;
  transition: width 0.4s ease;
}

/* 节点容器 */
.nodes-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 节点卡片 */
.node-card {
  background: var(--bg-secondary);
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
  position: relative;
  transition: all 0.3s;
}

.node-card.running {
  border-color: #f59e0b;
  box-shadow: 0 0 0 1px #f59e0b, 0 0 20px rgba(245, 158, 11, 0.2);
}

.node-card.completed {
  border-color: var(--color-success-500);
}

.node-card.failed {
  border-color: var(--color-danger-500);
}

.node-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.node-index {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: white;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.node-card.completed .node-index {
  background: linear-gradient(135deg, #10b981, #059669);
}

.node-card.failed .node-index {
  background: linear-gradient(135deg, #ef4444, #dc2626);
}

.node-card.running .node-index {
  background: linear-gradient(135deg, #f59e0b, #d97706);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); }
  50% { box-shadow: 0 0 0 6px rgba(245, 158, 11, 0); }
}

.node-type-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.node-type {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 14px;
}

.node-depends {
  font-size: 11px;
  color: var(--text-tertiary);
}

.node-status {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.node-status.pending {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.node-status.running {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.node-status.completed {
  background: rgba(16, 185, 129, 0.2);
  color: var(--color-success-500);
}

.node-status.failed {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-danger-500);
}

.node-params pre {
  margin: 0;
  padding: 10px;
  background: var(--bg-primary);
  border-radius: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  overflow-x: auto;
  font-family: 'Fira Code', monospace;
}

.node-result {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #334155;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-success-500);
  margin-bottom: 8px;
}

.result-content {
  margin: 0;
  padding: 10px;
  background: rgba(16, 185, 129, 0.1);
  border-radius: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  overflow-x: auto;
  font-family: 'Fira Code', monospace;
}

.node-error {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #334155;
}

.error-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-danger-500);
  margin-bottom: 8px;
}

.error-content {
  margin: 0;
  padding: 10px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: 8px;
  font-size: 12px;
  color: #fca5a5;
  overflow-x: auto;
  font-family: 'Fira Code', monospace;
}

/* JSON 预览 */
.json-preview {
  margin-top: 20px;
  background: var(--bg-secondary);
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
}

.json-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.json-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.json-content {
  margin: 0;
  padding: 16px;
  background: var(--bg-primary);
  border-radius: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 500px;
  font-family: 'Fira Code', monospace;
}

/* 导入对话框 */
.import-modal {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.modal-content {
  position: relative;
  width: 90%;
  max-width: 600px;
  background: var(--bg-secondary);
  border: 1px solid #334155;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.modal-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.import-input {
  width: 100%;
  padding: 12px;
  border: 1px solid #475569;
  border-radius: 8px;
  font-size: 13px;
  font-family: 'Fira Code', monospace;
  resize: vertical;
  background: var(--bg-primary);
  color: var(--text-primary);
  margin-bottom: 16px;
}

.import-input:focus {
  outline: none;
  border-color: #60a5fa;
  box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.2);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* 滚动条 */
.left-panel::-webkit-scrollbar,
.right-panel::-webkit-scrollbar,
.history-list::-webkit-scrollbar,
.json-content::-webkit-scrollbar {
  width: 6px;
}

.left-panel::-webkit-scrollbar-track,
.right-panel::-webkit-scrollbar-track {
  background: transparent;
}

.left-panel::-webkit-scrollbar-thumb,
.right-panel::-webkit-scrollbar-thumb {
  background: var(--bg-tertiary);
  border-radius: 3px;
}

.left-panel::-webkit-scrollbar-thumb:hover,
.right-panel::-webkit-scrollbar-thumb:hover {
  background: #475569;
}

/* 响应式 */
@media (max-width: 1024px) {
  .page-content {
    grid-template-columns: 1fr;
  }

  .left-panel {
    border-right: none;
    border-bottom: 1px solid #334155;
  }
}
</style>
