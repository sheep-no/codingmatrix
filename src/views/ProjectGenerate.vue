<template>
  <div class="project-generate-container">
    <div class="header">
      <h2>AI 项目生成器</h2>
      <div class="github-toggle">
        <GithubConfigPanel />
      </div>
    </div>
    
    <div class="main-content">
      <div class="input-section">
        <el-input
          v-model="projectPrompt"
          type="textarea"
          :rows="4"
          placeholder="描述您想要生成的项目..."
          class="prompt-input"
        />
        
        <div class="button-group">
          <el-button 
            type="primary" 
            @click="generateProject"
            :loading="isGenerating"
            :disabled="!projectPrompt.trim()"
          >
            {{ isGenerating ? '生成中...' : '生成项目' }}
          </el-button>
          
          <el-button 
            @click="saveCurrentProject"
            :disabled="!canSave"
          >
            保存项目
          </el-button>
          
          <el-button 
            @click="stopSession"
            :disabled="!isGenerating"
          >
            停止生成
          </el-button>
        </div>
      </div>
      
      <div class="output-section">
        <div v-if="generatedFiles.length > 0" class="file-tree">
          <h3>生成的文件</h3>
          <el-tree
            :data="fileTreeData"
            :props="{ label: 'name', children: 'children' }"
            @node-click="handleFileClick"
            default-expand-all
          />
        </div>
        
        <div v-if="selectedFile" class="file-preview">
          <h3>{{ selectedFile.name }}</h3>
          <pre><code>{{ selectedFile.content }}</code></pre>
        </div>
        
        <div v-if="logs.length > 0" class="logs-section">
          <h3>生成日志</h3>
          <div class="logs-container">
            <div 
              v-for="(log, index) in logs" 
              :key="index" 
              :class="`log-item log-${log.level}`"
            >
              {{ log.message }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import GithubConfigPanel from '@/components/GithubConfigPanel.vue'
import { useGithubStore } from '@/stores/github'
import { saveProjectToGithub } from '@/utils/api/github'
import api from '@/utils/api/project'

const githubStore = useGithubStore()

// 状态
const projectPrompt = ref('')
const isGenerating = ref(false)
const hasStopped = ref(false)
const generatedFiles = ref([])
const selectedFile = ref(null)
const logs = ref([])
const sessionId = ref(null)

// 计算属性
const canSave = computed(() => {
  return generatedFiles.value.length > 0 && !isGenerating.value
})

const fileTreeData = computed(() => {
  const tree = {}
  
  generatedFiles.value.forEach(file => {
    const parts = file.path.split('/')
    let current = tree
    
    parts.forEach((part, index) => {
      if (index === parts.length - 1) {
        // 文件
        if (!current.children) current.children = []
        current.children.push({
          name: part,
          path: file.path,
          content: file.content
        })
      } else {
        // 目录
        if (!current.children) current.children = []
        let dir = current.children.find(item => item.name === part && item.children)
        if (!dir) {
          dir = { name: part, children: [] }
          current.children.push(dir)
        }
        current = dir
      }
    })
  })
  
  return Object.values(tree).map(item => ({
    ...item,
    name: item.name || 'root'
  }))
})

// 方法
const addLog = (level, message) => {
  logs.value.push({ level, message, timestamp: new Date().toISOString() })
}

const generateProject = async () => {
  if (!projectPrompt.value.trim()) return
  
  isGenerating.value = true
  hasStopped.value = false
  generatedFiles.value = []
  selectedFile.value = null
  logs.value = []
  
  try {
    const response = await api.generateProject({
      prompt: projectPrompt.value,
      stream: true
    })
    
    // 处理 SSE 流
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      
      const text = decoder.decode(value)
      const lines = text.split('\n').filter(line => line.trim())
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            handleSseMessage(data)
          } catch (e) {
            console.error('Failed to parse SSE message:', e)
          }
        }
      }
    }
    
    isGenerating.value = false
    addLog('info', '项目生成完成')
    
  } catch (error) {
    isGenerating.value = false
    addLog('error', `生成失败: ${error.message}`)
    ElMessage.error('项目生成失败')
  }
}

const handleSseMessage = (data) => {
  switch (data.type) {
    case 'file':
      generatedFiles.value.push({
        path: data.path,
        content: data.content
      })
      addLog('info', `生成文件: ${data.path}`)
      break
    case 'progress':
      addLog('info', `进度: ${data.message}`)
      break
    case 'error':
      addLog('error', `错误: ${data.message}`)
      break
    case 'complete':
      sessionId.value = data.sessionId
      addLog('success', '项目生成完成')
      break
  }
}

const handleFileClick = (node) => {
  if (node.path) {
    const file = generatedFiles.value.find(f => f.path === node.path)
    if (file) {
      selectedFile.value = file
    }
  }
}

const saveCurrentProject = async () => {
  if (!canSave.value) return
  
  try {
    const projectName = prompt('请输入项目名称:', 'my-ai-project')
    if (!projectName) return
    
    const projectData = {
      name: projectName,
      description: projectPrompt.value,
      files: {}
    }
    
    generatedFiles.value.forEach(file => {
      projectData.files[file.path] = file.content
    })
    
    const githubConfig = githubStore.getGithubConfig()
    
    const result = await saveProjectToGithub(projectData, githubConfig)
    
    if (result.success) {
      ElMessage.success(`项目已${githubConfig.useGithub ? '保存到 GitHub' : '保存到本地'}: ${result.repo_url}`)
      addLog('success', `项目保存成功: ${result.repo_url}`)
    } else {
      ElMessage.error('项目保存失败')
      addLog('error', '项目保存失败')
    }
    
  } catch (error) {
    ElMessage.error(`保存失败: ${error.message}`)
    addLog('error', `保存失败: ${error.message}`)
  }
}

const stopSession = async () => {
  if (!sessionId.value) return
  
  try {
    await api.stopSession(sessionId.value)
    isGenerating.value = false
    hasStopped.value = true
    addLog('info', '项目已停止')
  } catch (error) {
    addLog('error', `停止项目失败: ${error.message}`)
  }
}

// 初始化
onMounted(() => {
  githubStore.restoreGithubConfig()
})
</script>

<style scoped>
.project-generate-container {
  padding: 20px;
  height: 100vh;
  overflow: auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.github-toggle {
  margin-left: 20px;
}

.main-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.input-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.prompt-input {
  width: 100%;
}

.button-group {
  display: flex;
  gap: 12px;
}

.output-section {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.file-tree {
  flex: 1;
  min-width: 300px;
}

.file-preview {
  flex: 2;
  min-width: 400px;
}

.file-preview pre {
  background: var(--bg-secondary);
  padding: 16px;
  border-radius: 6px;
  overflow-x: auto;
}

.logs-section {
  width: 100%;
  margin-top: 20px;
}

.logs-container {
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
}

.log-item {
  padding: 4px 0;
  font-family: monospace;
  font-size: 12px;
}

.log-info {
  color: var(--text-primary);
}

.log-success {
  color: #2ecc71;
}

.log-error {
  color: #e74c3c;
}

.log-warning {
  color: #f39c12;
}
</style>