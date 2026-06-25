<template>
  <div class="mcp-settings">
    <div class="mcp-header">
      <div class="mcp-header-left">
        <h4>MCP 工具扩展</h4>
        <p class="mcp-desc">通过 MCP 协议接入外部工具（数据库、浏览器、搜索等）</p>
      </div>
      <button class="btn btn-sm btn-primary" @click="showAddForm = true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        添加 Server
      </button>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="mcp-loading">加载中...</div>

    <!-- 空状态 -->
    <div v-else-if="servers.length === 0 && !showAddForm" class="mcp-empty">
      <p>暂无 MCP Server 配置</p>
      <p class="mcp-empty-hint">点击上方"添加 Server"按钮接入外部工具</p>
    </div>

    <!-- Server 列表 -->
    <div v-else class="mcp-server-list">
      <div v-for="server in servers" :key="server.name" class="mcp-server-card" :class="{ disabled: !server.enabled }">
        <div class="server-card-header">
          <div class="server-card-left">
            <span class="server-name">{{ server.name }}</span>
            <span class="server-transport">{{ server.transport }}</span>
            <span v-if="server.enabled" class="server-status enabled">已启用</span>
            <span v-else class="server-status disabled">已禁用</span>
          </div>
          <div class="server-card-actions">
            <button class="btn-icon" title="测试连接" :disabled="testing === server.name" @click="testServer(server.name)">
              <svg v-if="testing === server.name" class="spin-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            </button>
            <button class="btn-icon" title="切换启用" @click="toggleServer(server.name)">
              <svg v-if="server.enabled" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M18.36 6.64a9 9 0 010 12.73M5.64 5.64a9 9 0 000 12.73"/><circle cx="12" cy="12" r="1"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/></svg>
            </button>
            <button class="btn-icon btn-danger-icon" title="删除" @click="deleteServer(server.name)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
            </button>
          </div>
        </div>
        <div class="server-card-body">
          <p v-if="server.description" class="server-description">{{ server.description }}</p>
          <div class="server-detail">
            <span v-if="server.transport === 'stdio' && server.command" class="detail-item">
              <span class="detail-label">命令:</span> {{ server.command }} {{ (server.args || []).join(' ') }}
            </span>
            <span v-if="server.transport === 'http' && server.url" class="detail-item">
              <span class="detail-label">URL:</span> {{ server.url }}
            </span>
          </div>
          <!-- 测试结果 -->
          <div v-if="testResults[server.name]" class="test-result" :class="testResults[server.name].success ? 'success' : 'error'">
            <span v-if="testResults[server.name].success">
              连接成功，发现 {{ testResults[server.name].tools_count }} 个工具
            </span>
            <span v-else>连接失败: {{ testResults[server.name].error }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加表单 -->
    <div v-if="showAddForm" class="mcp-add-form">
      <h4>添加 MCP Server</h4>
      <div class="form-grid">
        <div class="form-item">
          <label>名称 <span class="required">*</span></label>
          <input v-model="newServer.name" type="text" placeholder="如: filesystem, database, search" class="form-input" />
        </div>
        <div class="form-item">
          <label>传输方式</label>
          <select v-model="newServer.transport" class="form-input">
            <option value="stdio">stdio（本地进程）</option>
            <option value="http">HTTP（远程服务）</option>
          </select>
        </div>
        <div class="form-item full-width">
          <label>描述</label>
          <input v-model="newServer.description" type="text" placeholder="简要描述此工具的用途" class="form-input" />
        </div>
        <template v-if="newServer.transport === 'stdio'">
          <div class="form-item full-width">
            <label>命令 <span class="required">*</span></label>
            <input v-model="newServer.command" type="text" placeholder="如: npx, uvx, python, /usr/local/bin/server" class="form-input" />
          </div>
          <div class="form-item full-width">
            <label>参数（每行一个）</label>
            <textarea v-model="newServer.argsText" rows="3" placeholder="-y&#10;@modelcontextprotocol/server-filesystem&#10;/path/to/dir" class="form-input"></textarea>
          </div>
          <div class="form-item full-width">
            <label>环境变量（JSON 格式）</label>
            <input v-model="newServer.envText" type="text" placeholder='{"API_KEY": "your-key"}' class="form-input" />
          </div>
        </template>
        <template v-else>
          <div class="form-item full-width">
            <label>URL <span class="required">*</span></label>
            <input v-model="newServer.url" type="text" placeholder="http://localhost:8080/mcp" class="form-input" />
          </div>
        </template>
      </div>
      <div class="form-actions">
        <button class="btn btn-outline" @click="showAddForm = false">取消</button>
        <button class="btn btn-primary" :disabled="adding" @click="addServer">
          {{ adding ? '添加中...' : '添加' }}
        </button>
      </div>
      <div v-if="addError" class="form-error">{{ addError }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const API = '/api/v2/mcp'

const servers = ref([])
const loading = ref(true)
const showAddForm = ref(false)
const adding = ref(false)
const addError = ref('')
const testing = ref(null)
const testResults = ref({})

const newServer = ref({
  name: '',
  transport: 'stdio',
  description: '',
  command: '',
  argsText: '',
  envText: '',
  url: '',
  enabled: true,
})

async function loadServers() {
  loading.value = true
  try {
    const res = await fetch(`${API}/servers`)
    const data = await res.json()
    servers.value = data.servers || []
  } catch (e) {
    console.error('加载 MCP 配置失败:', e)
  } finally {
    loading.value = false
  }
}

async function addServer() {
  addError.value = ''
  const s = newServer.value
  if (!s.name.trim()) { addError.value = '请输入名称'; return }
  if (s.transport === 'stdio' && !s.command.trim()) { addError.value = '请输入命令'; return }
  if (s.transport === 'http' && !s.url.trim()) { addError.value = '请输入 URL'; return }

  const body = {
    name: s.name.trim(),
    transport: s.transport,
    description: s.description.trim(),
    enabled: true,
  }
  if (s.transport === 'stdio') {
    body.command = s.command.trim()
    body.args = s.argsText.split('\n').map(a => a.trim()).filter(Boolean)
    if (s.envText.trim()) {
      try { body.env = JSON.parse(s.envText) } catch { addError.value = '环境变量格式错误，需为 JSON'; return }
    }
  } else {
    body.url = s.url.trim()
  }

  adding.value = true
  try {
    const res = await fetch(`${API}/servers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    if (!res.ok) { addError.value = data.detail || '添加失败'; return }
    ElMessage.success(`MCP Server "${s.name}" 已添加`)
    showAddForm.value = false
    newServer.value = { name: '', transport: 'stdio', description: '', command: '', argsText: '', envText: '', url: '', enabled: true }
    await loadServers()
  } catch (e) {
    addError.value = `请求失败: ${e.message}`
  } finally {
    adding.value = false
  }
}

async function toggleServer(name) {
  try {
    const res = await fetch(`${API}/servers/${name}/toggle`, { method: 'POST' })
    const data = await res.json()
    if (res.ok) {
      ElMessage.success(`${name} 已${data.enabled ? '启用' : '禁用'}`)
      await loadServers()
    }
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function deleteServer(name) {
  try {
    await ElMessageBox.confirm(`确定删除 MCP Server "${name}"？`, '确认删除', { type: 'warning' })
    const res = await fetch(`${API}/servers/${name}`, { method: 'DELETE' })
    if (res.ok) {
      ElMessage.success(`已删除 ${name}`)
      await loadServers()
    }
  } catch {
    // Error handled silently
  }
}

async function testServer(name) {
  testing.value = name
  testResults.value[name] = null
  try {
    const res = await fetch(`${API}/servers/${name}/test`, { method: 'POST' })
    const data = await res.json()
    testResults.value[name] = data
  } catch (e) {
    testResults.value[name] = { success: false, error: e.message }
  } finally {
    testing.value = null
  }
}

onMounted(loadServers)
</script>

<style scoped>
.mcp-settings { margin-top: 4px; }
.mcp-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.mcp-header h4 { margin: 0; font-size: 14px; color: var(--text-primary); }
.mcp-header-left { display: flex; flex-direction: column; gap: 2px; }
.mcp-desc { margin: 0; font-size: 11px; color: var(--text-secondary); }
.mcp-loading { text-align: center; padding: 20px; color: var(--text-secondary); font-size: 12px; }
.mcp-empty { text-align: center; padding: 24px; background: var(--bg-tertiary); border-radius: 8px; }
.mcp-empty p { margin: 0; font-size: 13px; color: var(--text-secondary); }
.mcp-empty-hint { font-size: 11px; color: var(--text-tertiary); margin-top: 4px !important; }

.mcp-server-list { display: flex; flex-direction: column; gap: 8px; }
.mcp-server-card { background: var(--bg-tertiary); border-radius: 8px; padding: 12px; border: 1px solid var(--border-color); transition: opacity 0.2s; }
.mcp-server-card.disabled { opacity: 0.5; }
.server-card-header { display: flex; align-items: center; justify-content: space-between; }
.server-card-left { display: flex; align-items: center; gap: 8px; }
.server-name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.server-transport { font-size: 10px; padding: 2px 6px; border-radius: 4px; background: var(--bg-secondary); color: var(--text-secondary); }
.server-status { font-size: 10px; padding: 2px 6px; border-radius: 4px; }
.server-status.enabled { background: rgba(34,197,94,0.15); color: #22c55e; }
.server-status.disabled { background: rgba(239,68,68,0.15); color: #ef4444; }
.server-card-actions { display: flex; gap: 4px; }
.btn-icon { background: none; border: none; cursor: pointer; padding: 4px; border-radius: 4px; color: var(--text-secondary); display: flex; align-items: center; }
.btn-icon:hover { background: var(--bg-secondary); color: var(--text-primary); }
.btn-danger-icon:hover { color: #ef4444; }
.server-card-body { margin-top: 8px; }
.server-description { font-size: 11px; color: var(--text-secondary); margin: 0 0 4px 0; }
.server-detail { font-size: 11px; color: var(--text-tertiary); }
.detail-item { display: block; }
.detail-label { font-weight: 600; }
.test-result { margin-top: 8px; padding: 6px 10px; border-radius: 6px; font-size: 11px; }
.test-result.success { background: rgba(34,197,94,0.1); color: #22c55e; }
.test-result.error { background: rgba(239,68,68,0.1); color: #ef4444; }

.mcp-add-form { margin-top: 12px; background: var(--bg-tertiary); border-radius: 8px; padding: 16px; border: 1px solid var(--border-color); }
.mcp-add-form h4 { margin: 0 0 12px 0; font-size: 13px; color: var(--text-primary); }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.form-item { display: flex; flex-direction: column; gap: 4px; }
.form-item.full-width { grid-column: 1 / -1; }
.form-item label { font-size: 11px; color: var(--text-secondary); font-weight: 600; }
.required { color: #ef4444; }
.form-input { padding: 6px 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-primary); color: var(--text-primary); font-size: 12px; font-family: inherit; }
textarea.form-input { resize: vertical; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.form-error { margin-top: 8px; color: #ef4444; font-size: 11px; }

.spin-icon { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>
