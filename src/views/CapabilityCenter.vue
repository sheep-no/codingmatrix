<template>
  <main class="capability-page">
    <header class="page-header">
      <button class="back" @click="$router.push('/')">返回</button>
      <div>
        <h1>能力中心</h1>
        <p>管理视觉工具、知识库、Skills、Agent Host 会话和上传项目</p>
      </div>
    </header>

    <nav class="tabs" aria-label="能力中心导航">
      <button v-for="tab in tabs" :key="tab.id" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">{{ tab.label }}</button>
    </nav>

    <section v-if="activeTab === 'vision'" class="panel">
      <h2>视觉工具</h2>
      <input type="file" accept="image/*" @change="setVisionFile" />
      <textarea v-model="visionPrompt" placeholder="图片分析提示词"></textarea>
      <div class="actions">
        <button :disabled="!visionFile || busy" @click="runVision('analyze')">分析图片</button>
        <button :disabled="!visionFile || busy" @click="runVision('ocr')">OCR 识别</button>
        <button :disabled="!visionFile || busy" @click="runVision('code')">截图转代码</button>
        <button :disabled="!visionFile || busy" @click="runVision('safety')">安全检查</button>
      </div>
      <pre v-if="result">{{ result }}</pre>
    </section>

    <section v-else-if="activeTab === 'skills'" class="panel">
      <div class="panel-title"><h2>Skills</h2><button @click="loadSkills">刷新</button></div>
      <div class="form-grid">
        <input v-model="skill.name" placeholder="名称" />
        <input v-model="skill.category" placeholder="分类，如 workflow" />
        <input v-model="skill.description" placeholder="描述" />
        <textarea v-model="skill.content" placeholder="Markdown 内容"></textarea>
      </div>
      <button :disabled="busy || !skill.name || !skill.content" @click="saveSkill">上传 Skill</button>
      <div v-for="item in skills" :key="item.name" class="list-row">
        <span>{{ item.name }} · {{ item.category }}</span>
        <button @click="removeSkill(item.name)">删除</button>
      </div>
    </section>

    <section v-else-if="activeTab === 'host'" class="panel">
      <div class="panel-title"><h2>Agent Host 会话</h2><button @click="loadHosts">刷新</button></div>
      <div v-if="hosts.length === 0" class="empty">暂无在线 Host 会话</div>
      <div v-for="host in hosts" :key="host.session_id" class="list-row column">
        <strong>{{ host.workspace_id }}</strong>
        <span>{{ host.session_id }} · {{ host.control_status }}</span>
        <div class="actions">
          <button @click="controlHost(host.session_id, 'pause')">暂停</button>
          <button @click="controlHost(host.session_id, 'resume')">恢复</button>
          <button @click="controlHost(host.session_id, 'cancel')">取消</button>
          <button @click="readActions(host.session_id)">查看待执行动作</button>
        </div>
      </div>
      <pre v-if="hostActions">{{ hostActions }}</pre>
    </section>

    <section v-else-if="activeTab === 'knowledge'" class="panel">
      <div class="panel-title"><h2>知识库</h2><button @click="loadKnowledgeDocs">刷新</button></div>
      <input type="file" accept=".txt,.md,.pdf,.docx,.py,.js,.ts,.json,.yaml,.yml,.csv,.log" @change="uploadKnowledge" />
      <input v-model="knowledgeQuery" placeholder="搜索知识库内容" @keyup.enter="searchKnowledge" />
      <div v-if="knowledgeSearchResults.length" class="search-results">
        <h3>搜索结果</h3>
        <div v-for="item in knowledgeSearchResults" :key="item.id || item.chunk_id" class="result-row">
          {{ item.content || item.text || item.filename }}
        </div>
      </div>
      <div v-for="doc in knowledgeDocs" :key="doc.id" class="list-row">
        <span>{{ doc.filename }} · {{ doc.chunk_count || 0 }} 个片段</span>
        <button @click="removeKnowledgeDoc(doc.id)">删除</button>
      </div>
      <div v-if="knowledgeDocs.length === 0" class="empty">暂无知识库文档</div>
    </section>

    <section v-else-if="activeTab === 'sandbox'" class="panel">
      <div class="panel-title"><h2>代码执行沙箱</h2></div>
      <select v-model="sandboxLanguage" aria-label="代码语言">
        <option value="python">Python</option>
        <option value="javascript">JavaScript</option>
        <option value="go">Go</option>
      </select>
      <textarea v-model="sandboxCode" class="code-input" placeholder="输入要执行的代码" spellcheck="false"></textarea>
      <button :disabled="busy || !sandboxCode.trim()" @click="executeSandboxCode">{{ busy ? '执行中...' : '运行代码' }}</button>
      <pre v-if="sandboxResult">{{ sandboxResult }}</pre>
    </section>

    <section v-else class="panel">
      <div class="panel-title"><h2>上传项目</h2><button @click="loadProjects">刷新</button></div>
      <input type="file" accept=".zip" @change="uploadProject" />
      <div v-for="project in projects" :key="project.project_name" class="list-row">
        <span>{{ project.project_name }} · {{ project.file_count }} 个文件</span>
        <button @click="removeProject(project.project_name)">删除</button>
      </div>
    </section>
  </main>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/utils/api/index'

const tabs = [
  { id: 'vision', label: '视觉工具' },
  { id: 'knowledge', label: '知识库' },
  { id: 'sandbox', label: '代码沙箱' },
  { id: 'skills', label: 'Skills' },
  { id: 'host', label: 'Agent Host' },
  { id: 'projects', label: '上传项目' }
]
const activeTab = ref('vision')
const busy = ref(false)
const result = ref('')
const visionFile = ref(null)
const visionPrompt = ref('请详细描述这张图片的内容')
const skills = ref([])
const hosts = ref([])
const projects = ref([])
const hostActions = ref('')
const knowledgeDocs = ref([])
const knowledgeQuery = ref('')
const knowledgeSearchResults = ref([])
const sandboxLanguage = ref('python')
const sandboxCode = ref('')
const sandboxResult = ref('')
const skill = ref({ name: '', category: 'other', description: '', content: '' })

function setVisionFile(event) { visionFile.value = event.target.files?.[0] || null }

async function runVision(operation) {
  busy.value = true
  try {
    const calls = {
      analyze: () => api.analyzeImage(visionFile.value, visionPrompt.value),
      ocr: () => api.recognizeImageText(visionFile.value),
      code: () => api.generateCodeFromImage(visionFile.value, visionPrompt.value),
      safety: () => api.checkImageSafety(visionFile.value)
    }
    result.value = JSON.stringify(await calls[operation](), null, 2)
  } catch (error) { result.value = error.message }
  finally { busy.value = false }
}

async function loadSkills() { skills.value = await api.listSkills() }
async function saveSkill() { busy.value = true; try { await api.uploadSkill(skill.value); skill.value = { name: '', category: 'other', description: '', content: '' }; await loadSkills() } finally { busy.value = false } }
async function removeSkill(name) { await api.deleteSkill(name); await loadSkills() }
async function loadHosts() { hosts.value = await api.listAgentHostSessions() }
async function controlHost(sessionId, action) { await api.controlAgentHostSession(sessionId, action); await loadHosts() }
async function readActions(sessionId) { hostActions.value = JSON.stringify(await api.getAgentHostActions(sessionId), null, 2) }
async function loadKnowledgeDocs() {
  const response = await api.listKnowledgeDocs()
  knowledgeDocs.value = Array.isArray(response) ? response : response?.docs || []
}
async function uploadKnowledge(event) {
  const file = event.target.files?.[0]
  if (!file) return
  busy.value = true
  try { await api.uploadKnowledge(file); await loadKnowledgeDocs() } finally { busy.value = false; event.target.value = '' }
}
async function removeKnowledgeDoc(id) { await api.deleteKnowledgeDoc(id); await loadKnowledgeDocs() }
async function searchKnowledge() {
  const query = knowledgeQuery.value.trim()
  knowledgeSearchResults.value = query ? ((await api.searchKnowledge(query))?.results || []) : []
}
async function executeSandboxCode() {
  if (!sandboxCode.value.trim()) return
  busy.value = true
  sandboxResult.value = ''
  try {
    const response = await api.executeCode(sandboxCode.value, sandboxLanguage.value)
    sandboxResult.value = JSON.stringify(response, null, 2)
  } catch (error) {
    sandboxResult.value = error.message
  } finally {
    busy.value = false
  }
}
async function loadProjects() { projects.value = await api.listUploadedProjects() }
async function uploadProject(event) { const file = event.target.files?.[0]; if (!file) return; busy.value = true; try { await api.uploadProjectZip(file); await loadProjects() } finally { busy.value = false } }
async function removeProject(name) { await api.deleteUploadedProject(name); await loadProjects() }

onMounted(() => { loadSkills(); loadHosts(); loadKnowledgeDocs(); loadProjects() })
</script>

<style scoped>
.capability-page { min-height: 100vh; padding: 28px; background: var(--bg-primary); color: var(--text-primary); box-sizing: border-box; }
.page-header, .panel-title, .list-row { display: flex; align-items: center; gap: 16px; }
.page-header { margin: 0 auto 24px; max-width: 1100px; }
.page-header h1, h2 { margin: 0; }
.page-header p { margin: 6px 0 0; color: var(--text-secondary); }
.back, .tabs button, button { border: 1px solid var(--border-color); border-radius: 7px; padding: 8px 14px; background: var(--bg-secondary); color: inherit; cursor: pointer; }
.tabs { max-width: 1100px; margin: 0 auto 18px; display: flex; gap: 8px; flex-wrap: wrap; }
.tabs button.active { color: var(--primary); border-color: var(--primary); }
.panel { max-width: 1100px; margin: auto; padding: 24px; border: 1px solid var(--border-color); border-radius: 12px; background: var(--bg-secondary); }
.panel-title { justify-content: space-between; margin-bottom: 18px; }
input, textarea { width: 100%; box-sizing: border-box; padding: 10px; margin: 12px 0; border: 1px solid var(--border-color); border-radius: 7px; background: var(--bg-primary); color: inherit; }
textarea { min-height: 100px; resize: vertical; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
.list-row { justify-content: space-between; padding: 14px 0; border-top: 1px solid var(--border-color); }
.list-row.column { align-items: flex-start; flex-direction: column; }
pre { overflow: auto; padding: 16px; border-radius: 8px; background: #111827; color: #d1fae5; white-space: pre-wrap; }
.empty { color: var(--text-secondary); padding: 20px 0; }
.search-results { margin: 12px 0 20px; }
.search-results h3 { margin: 0 0 8px; }
.result-row { padding: 10px 0; border-top: 1px solid var(--border-color); white-space: pre-wrap; }
.code-input { min-height: 220px; font-family: monospace; }
</style>
