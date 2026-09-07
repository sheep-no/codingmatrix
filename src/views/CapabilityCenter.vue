<template>
  <main class="capability-page">
    <header class="page-header">
      <button class="back" type="button" @click="$router.push('/')">返回</button>
      <div>
        <h1>能力中心</h1>
        <p>管理视觉工具、知识库、Skills、Agent Host 会话和上传项目</p>
      </div>
    </header>

    <nav class="tabs" aria-label="能力中心导航">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        :class="{ active: activeTab === tab.id }"
        :aria-selected="activeTab === tab.id"
        role="tab"
        @click="activeTab = tab.id"
      >{{ tab.label }}</button>
    </nav>

    <section v-if="activeTab === 'vision'" class="panel">
      <h2>视觉工具</h2>
       <label class="drop-zone" @dragover.prevent @drop.prevent="dropVisionFile">
         <span>拖入图片，或点击选择文件</span>
         <input type="file" accept="image/*" @change="setVisionFile" />
       </label>
      <textarea v-model="visionPrompt" placeholder="图片分析提示词"></textarea>
       <LoadingState v-if="panelStates.vision.loading" label="正在处理图片..." />
       <ErrorState v-else-if="panelStates.vision.error" :message="panelStates.vision.error" @retry="runVision(lastVisionOperation)" />
       <div class="actions">
        <button :disabled="!visionFile || busy" @click="runVision('analyze')">分析图片</button>
        <button :disabled="!visionFile || busy" @click="runVision('ocr')">OCR 识别</button>
        <button :disabled="!visionFile || busy" @click="runVision('code')">截图转代码</button>
        <button :disabled="!visionFile || busy" @click="runVision('safety')">安全检查</button>
      </div>
       <pre v-if="result && !panelStates.vision.error">{{ result }}</pre>
    </section>

    <section v-else-if="activeTab === 'skills'" class="panel">
      <div class="panel-title"><h2>Skills</h2><button @click="loadSkills(true)">刷新</button></div>
      <div class="form-grid">
        <input v-model="skill.name" placeholder="名称" />
        <input v-model="skill.category" placeholder="分类，如 workflow" />
        <input v-model="skill.description" placeholder="描述" />
        <textarea v-model="skill.content" placeholder="Markdown 内容"></textarea>
      </div>
      <button :disabled="busy || !skill.name || !skill.content" @click="saveSkill">上传 Skill</button>
       <LoadingState v-if="panelStates.skills.loading" label="正在加载 Skills..." />
       <ErrorState v-else-if="panelStates.skills.error" :message="panelStates.skills.error" @retry="loadSkills(true)" />
       <div v-for="item in skills" :key="item.name" class="list-row">
         <span>{{ item.name }} · {{ item.category }}</span>
         <button @click="removeSkill(item.name)">删除</button>
       </div>
       <div v-if="!panelStates.skills.loading && !panelStates.skills.error && skills.length === 0" class="empty">暂无 Skills</div>
    </section>

    <section v-else-if="activeTab === 'host'" class="panel">
      <div class="panel-title"><h2>Agent Host 会话</h2><button @click="loadHosts(true)">刷新</button></div>
       <LoadingState v-if="panelStates.host.loading" label="正在加载 Host 会话..." />
       <ErrorState v-else-if="panelStates.host.error" :message="panelStates.host.error" @retry="loadHosts(true)" />
       <div v-else-if="hosts.length === 0" class="empty">暂无在线 Host 会话</div>
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
      <div class="panel-title"><h2>知识库</h2><button @click="loadKnowledgeDocs(true)">刷新</button></div>
       <label class="drop-zone" @dragover.prevent @drop.prevent="dropKnowledgeFile">
         <span>拖入文档，或点击选择文件</span>
         <input type="file" accept=".txt,.md,.pdf,.docx,.py,.js,.ts,.json,.yaml,.yml,.csv,.log" @change="uploadKnowledge" />
       </label>
      <input v-model="knowledgeQuery" placeholder="搜索知识库内容" @keyup.enter="searchKnowledge" />
      <div v-if="knowledgeSearchResults.length" class="search-results">
        <h3>搜索结果</h3>
        <div v-for="item in knowledgeSearchResults" :key="item.id || item.chunk_id" class="result-row">
          {{ item.content || item.text || item.filename }}
        </div>
      </div>
       <LoadingState v-if="panelStates.knowledge.loading" label="正在加载知识库..." />
       <ErrorState v-else-if="panelStates.knowledge.error" :message="panelStates.knowledge.error" @retry="loadKnowledgeDocs(true)" />
       <div v-for="doc in knowledgeDocs" :key="doc.id" class="list-row">
        <span>{{ doc.filename }} · {{ doc.chunk_count || 0 }} 个片段</span>
        <button @click="removeKnowledgeDoc(doc.id)">删除</button>
      </div>
       <div v-if="!panelStates.knowledge.loading && !panelStates.knowledge.error && knowledgeDocs.length === 0" class="empty">暂无知识库文档</div>
    </section>

    <section v-else-if="activeTab === 'sandbox'" class="panel">
      <div class="panel-title"><h2>代码执行沙箱</h2></div>
      <select v-model="sandboxLanguage" aria-label="代码语言">
        <option value="python">Python</option>
        <option value="javascript">JavaScript</option>
        <option value="go">Go</option>
      </select>
      <textarea v-model="sandboxCode" class="code-input" placeholder="输入要执行的代码" spellcheck="false"></textarea>
       <LoadingState v-if="panelStates.sandbox.loading" label="正在执行代码..." />
       <ErrorState v-else-if="panelStates.sandbox.error" :message="panelStates.sandbox.error" @retry="executeSandboxCode" />
       <button :disabled="panelStates.sandbox.loading || !sandboxCode.trim()" @click="executeSandboxCode">运行代码</button>
       <pre v-if="sandboxResult && !panelStates.sandbox.error">{{ sandboxResult }}</pre>
    </section>

    <section v-else class="panel">
      <div class="panel-title"><h2>上传项目</h2><button @click="loadProjects(true)">刷新</button></div>
       <label class="drop-zone" @dragover.prevent @drop.prevent="dropProjectFile">
         <span>拖入 ZIP 项目，或点击选择文件</span>
         <input type="file" accept=".zip" @change="uploadProject" />
       </label>
       <LoadingState v-if="panelStates.projects.loading" label="正在加载上传项目..." />
       <ErrorState v-else-if="panelStates.projects.error" :message="panelStates.projects.error" @retry="loadProjects(true)" />
       <div v-for="project in projects" :key="project.project_name" class="list-row">
         <span>{{ project.project_name }} · {{ project.file_count }} 个文件</span>
         <button @click="removeProject(project.project_name)">删除</button>
       </div>
       <div v-if="!panelStates.projects.loading && !panelStates.projects.error && projects.length === 0" class="empty">暂无上传项目</div>
    </section>
  </main>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '@/utils/api/index'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'

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
const lastVisionOperation = ref('analyze')
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
const loadedPanels = new Set()
const panelStates = reactive({
  vision: { loading: false, error: '' },
  sandbox: { loading: false, error: '' },
  skills: { loading: false, error: '' },
  host: { loading: false, error: '' },
  knowledge: { loading: false, error: '' },
  projects: { loading: false, error: '' }
})

function setVisionFile(event) { visionFile.value = event.target.files?.[0] || null }
function dropVisionFile(event) {
  visionFile.value = event.dataTransfer.files?.[0] || null
}

function dropKnowledgeFile(event) {
  uploadKnowledge({ target: { files: event.dataTransfer.files, value: '' } })
}

function dropProjectFile(event) {
  uploadProject({ target: { files: event.dataTransfer.files, value: '' } })
}

async function runVision(operation) {
  lastVisionOperation.value = operation
  panelStates.vision.loading = true
  panelStates.vision.error = ''
  try {
    const calls = {
      analyze: () => api.analyzeImage(visionFile.value, visionPrompt.value),
      ocr: () => api.recognizeImageText(visionFile.value),
      code: () => api.generateCodeFromImage(visionFile.value, visionPrompt.value),
      safety: () => api.checkImageSafety(visionFile.value)
    }
    result.value = JSON.stringify(await calls[operation](), null, 2)
  } catch (error) {
    panelStates.vision.error = error.message || '图片处理失败，请重试。'
  } finally { panelStates.vision.loading = false }
}

async function loadSkills(force = false) {
  if (loadedPanels.has('skills') && !force) return
  panelStates.skills.loading = true
  panelStates.skills.error = ''
  try {
    skills.value = await api.listSkills()
    loadedPanels.add('skills')
  } catch (error) {
    panelStates.skills.error = error.message || 'Skills 加载失败，请重试。'
  } finally { panelStates.skills.loading = false }
}
async function saveSkill() { busy.value = true; try { await api.uploadSkill(skill.value); skill.value = { name: '', category: 'other', description: '', content: '' }; await loadSkills() } finally { busy.value = false } }
async function removeSkill(name) {
  if (!window.confirm(`确认删除 Skill「${name}」吗？`)) return
  await api.deleteSkill(name)
  await loadSkills(true)
}
async function loadHosts(force = false) {
  if (loadedPanels.has('host') && !force) return
  panelStates.host.loading = true
  panelStates.host.error = ''
  try {
    hosts.value = await api.listAgentHostSessions()
    loadedPanels.add('host')
  } catch (error) {
    panelStates.host.error = error.message || 'Host 会话加载失败，请重试。'
  } finally { panelStates.host.loading = false }
}
async function controlHost(sessionId, action) { await api.controlAgentHostSession(sessionId, action); await loadHosts(true) }
async function readActions(sessionId) { hostActions.value = JSON.stringify(await api.getAgentHostActions(sessionId), null, 2) }
async function loadKnowledgeDocs(force = false) {
  if (loadedPanels.has('knowledge') && !force) return
  panelStates.knowledge.loading = true
  panelStates.knowledge.error = ''
  try {
    const response = await api.listKnowledgeDocs()
    knowledgeDocs.value = Array.isArray(response) ? response : response?.docs || []
    loadedPanels.add('knowledge')
  } catch (error) {
    panelStates.knowledge.error = error.message || '知识库加载失败，请重试。'
  } finally { panelStates.knowledge.loading = false }
}
async function uploadKnowledge(event) {
  const file = event.target.files?.[0]
  if (!file) return
  busy.value = true
  try { await api.uploadKnowledge(file); await loadKnowledgeDocs(true) } finally { busy.value = false; event.target.value = '' }
}
async function removeKnowledgeDoc(id) {
  if (!window.confirm('确认删除这份知识库文档吗？')) return
  await api.deleteKnowledgeDoc(id)
  await loadKnowledgeDocs(true)
}
async function searchKnowledge() {
  const query = knowledgeQuery.value.trim()
  knowledgeSearchResults.value = query ? ((await api.searchKnowledge(query))?.results || []) : []
}
async function executeSandboxCode() {
  if (!sandboxCode.value.trim()) return
  panelStates.sandbox.loading = true
  panelStates.sandbox.error = ''
  sandboxResult.value = ''
  try {
    const response = await api.executeCode(sandboxCode.value, sandboxLanguage.value)
    sandboxResult.value = JSON.stringify(response, null, 2)
  } catch (error) {
    panelStates.sandbox.error = error.message || '代码执行失败，请重试。'
  } finally { panelStates.sandbox.loading = false }
}
async function loadProjects(force = false) {
  if (loadedPanels.has('projects') && !force) return
  panelStates.projects.loading = true
  panelStates.projects.error = ''
  try {
    projects.value = await api.listUploadedProjects()
    loadedPanels.add('projects')
  } catch (error) {
    panelStates.projects.error = error.message || '上传项目加载失败，请重试。'
  } finally { panelStates.projects.loading = false }
}
async function uploadProject(event) { const file = event.target.files?.[0]; if (!file) return; busy.value = true; try { await api.uploadProjectZip(file); await loadProjects(true) } finally { busy.value = false } }
async function removeProject(name) {
  if (!window.confirm(`确认删除上传项目「${name}」吗？`)) return
  await api.deleteUploadedProject(name)
  await loadProjects(true)
}

watch(activeTab, tab => {
  const loaders = { skills: loadSkills, host: loadHosts, knowledge: loadKnowledgeDocs, projects: loadProjects }
  loaders[tab]?.()
}, { immediate: true })
</script>

<style scoped>
.capability-page { min-height: 100vh; padding: 28px; background: var(--surface-app); color: var(--content-primary); box-sizing: border-box; }
.page-header, .panel-title, .list-row { display: flex; align-items: center; gap: 16px; }
.page-header { margin: 0 auto 24px; max-width: 1100px; }
.page-header h1, h2 { margin: 0; }
.page-header p { margin: 6px 0 0; color: var(--content-secondary); }
.back, .tabs button, button { min-height: 40px; border: 1px solid var(--control-border); border-radius: 8px; padding: 8px 14px; background: var(--surface-subtle); color: inherit; cursor: pointer; transition: background var(--motion-fast), border-color var(--motion-fast), color var(--motion-fast); }
.back:hover, .tabs button:hover, button:hover:not(:disabled) { border-color: var(--control-border-focus); color: var(--accent-primary); }
.back:focus-visible, .tabs button:focus-visible, button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible { outline: 3px solid color-mix(in srgb, var(--accent-primary) 35%, transparent); outline-offset: 2px; }
.back:disabled, button:disabled { cursor: not-allowed; opacity: 0.55; }
.tabs { max-width: 1100px; margin: 0 auto 18px; display: flex; gap: 8px; flex-wrap: wrap; }
.tabs button.active { color: var(--accent-primary); border-color: var(--accent-primary); background: var(--surface-app); }
.panel { max-width: 1100px; margin: auto; padding: 24px; border: 1px solid var(--control-border); border-radius: 12px; background: var(--surface-subtle); box-shadow: var(--shadow-sm); }
.panel-title { justify-content: space-between; margin-bottom: 18px; }
input, textarea, select { width: 100%; box-sizing: border-box; padding: 10px; margin: 12px 0; border: 1px solid var(--control-border); border-radius: 8px; background: var(--surface-app); color: inherit; }
textarea { min-height: 100px; resize: vertical; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
.list-row { justify-content: space-between; padding: 14px 0; border-top: 1px solid var(--control-border); }
.list-row.column { align-items: flex-start; flex-direction: column; }
pre { overflow: auto; padding: 16px; border-radius: 8px; background: #111827; color: #d1fae5; white-space: pre-wrap; }
.empty { color: var(--content-secondary); padding: 20px 0; }
.search-results { margin: 12px 0 20px; }
.search-results h3 { margin: 0 0 8px; }
.result-row { padding: 10px 0; border-top: 1px solid var(--control-border); white-space: pre-wrap; }
.code-input { min-height: 220px; font-family: monospace; }
.drop-zone { display: flex; align-items: center; justify-content: center; min-height: 72px; margin: 12px 0; padding: 12px; border: 1px dashed var(--control-border); border-radius: 10px; color: var(--content-secondary); background: var(--surface-app); cursor: pointer; transition: border-color var(--motion-fast), color var(--motion-fast), background var(--motion-fast); }
.drop-zone:hover, .drop-zone:focus-within { border-color: var(--control-border-focus); color: var(--accent-primary); background: var(--surface-subtle); }
.drop-zone input { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 600px) {
  .capability-page { padding: 16px; }
  .panel { padding: 16px; }
  .page-header { align-items: flex-start; flex-direction: column; }
  .list-row { align-items: flex-start; flex-direction: column; }
}
</style>
