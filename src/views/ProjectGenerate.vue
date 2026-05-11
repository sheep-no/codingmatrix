<template>
  <div class="project-generate-page">
    <!-- 顶部导航 -->
    <header class="page-header">
      <button class="back-btn" @click="goBack">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        返回
      </button>
      <div class="header-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/>
          <path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
        </svg>
        <span>多模态 Agent 工作台</span>
      </div>
      <div class="header-actions">
        <button class="collapse-toggle" @click="leftPanelCollapsed = !leftPanelCollapsed" :title="leftPanelCollapsed ? '展开面板' : '收缩面板'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px;" :style="{ transform: leftPanelCollapsed ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }">
            <polyline points="11 17 6 12 11 7"></polyline>
            <polyline points="18 17 13 12 18 7"></polyline>
          </svg>
        </button>
        <!-- Agent 模型状态 -->
        <div v-if="isGenerating" class="agent-status">
          <span class="status-dot" :class="currentAgent"></span>
          <span class="agent-name">{{ getAgentLabel(currentAgent) }}</span>
        </div>
        <button v-if="generationComplete" class="btn btn-download" @click="handleDownload">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          下载项目
        </button>
      </div>
    </header>

    <!-- 主内容区 -->
    <div class="page-content" :class="{ 'panel-collapsed': leftPanelCollapsed }">
      <!-- 左侧：配置面板 -->
      <aside class="config-panel">
        <div class="panel-section">
          <h3 class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            项目需求
          </h3>
          <textarea
            v-model="form.requirement"
            class="requirement-input"
            placeholder="描述你想要生成的项目...&#10;&#10;例如：&#10;• 生成一个五子棋小游戏&#10;• 创建一个 Todo 管理 Web 应用&#10;• 实现 RESTful API 服务"
            :disabled="isGenerating"
          ></textarea>
        </div>

        <div class="panel-section">
          <h3 class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 6v6l4 2"/>
            </svg>
            生成选项
          </h3>
          <label class="option-item">
            <input v-model="options.enableReview" type="checkbox" :disabled="isGenerating" />
            <span class="option-label">
              <span class="option-name">代码审查</span>
              <span class="option-desc">生成后进行质量和安全审查</span>
            </span>
          </label>
          <label class="option-item">
            <input v-model="options.enableValidation" type="checkbox" :disabled="isGenerating" />
            <span class="option-label">
              <span class="option-name">语法验证</span>
              <span class="option-desc">验证代码语法和导入</span>
            </span>
          </label>
          <label class="option-item">
            <input v-model="options.enableErrorRecovery" type="checkbox" :disabled="isGenerating" />
            <span class="option-label">
              <span class="option-name">自动修复</span>
              <span class="option-desc">测试失败时自动尝试修复</span>
            </span>
          </label>
        </div>

        <!-- 快捷模板 -->
        <div class="panel-section">
          <h3 class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            快捷模板
          </h3>
          <div class="template-list">
            <button
              v-for="tpl in templates"
              :key="tpl.name"
              class="template-btn"
              :disabled="isGenerating"
              @click="applyTemplate(tpl)"
            >
              {{ tpl.name }}
            </button>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="panel-actions">
          <button
            v-if="!isGenerating && !generationComplete"
            class="btn btn-primary btn-large"
            :disabled="!form.requirement.trim()"
            @click="startGeneration"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            开始生成
          </button>
          <button
            v-if="isGenerating"
            class="btn btn-danger btn-large"
            @click="stopGeneration"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="6" y="6" width="12" height="12"/>
            </svg>
            停止生成
          </button>
          <button
            v-if="generationComplete"
            class="btn btn-success btn-large"
            @click="resetAndStartNew"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            新建项目
          </button>
        </div>
      </aside>

      <!-- 右侧：生成过程 -->
      <main class="progress-panel">
        <!-- 未开始状态 -->
        <div v-if="!isGenerating && !generationComplete && logs.length === 0" class="empty-state">
          <div class="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <h2>准备就绪</h2>
          <p>在左侧输入需求，即可开始 AI Agent 生成</p>
          <div class="feature-list">
            <div class="feature-item">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              <span>多角色协作生成</span>
            </div>
            <div class="feature-item">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              <span>架构自动设计</span>
            </div>
            <div class="feature-item">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              <span>实时代码预览</span>
            </div>
            <div class="feature-item">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              <span>自动测试验证</span>
            </div>
          </div>
        </div>

        <!-- 生成中/完成状态 -->
        <div v-else class="generation-content">
          <!-- 顶部状态栏 -->
          <div class="status-bar">
            <div class="status-left">
              <span class="status-indicator" :class="statusClass">
                <span class="pulse"></span>
                {{ statusText }}
              </span>
              <span v-if="currentStep" class="status-step">
                {{ currentStep }}/{{ totalSteps }}
              </span>
            </div>
            <div class="status-right">
              <span v-if="filesCreated > 0" class="status-file">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                </svg>
                {{ filesCreated }} 文件
              </span>
            </div>
          </div>

          <!-- 进度条 -->
          <div class="progress-bar-container">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
            </div>
            <span class="progress-percent">{{ Math.round(progressPercent) }}%</span>
          </div>

          <!-- 阶段指示器 -->
          <div class="phase-nav">
            <div
              v-for="(phase, idx) in phases"
              :key="phase.key"
              class="phase-tab"
              :class="{
                active: currentPhase === phase.key,
                completed: completedPhases.includes(phase.key)
              }"
            >
              <span class="phase-num">{{ idx + 1 }}</span>
              <span class="phase-name">{{ phase.label }}</span>
            </div>
          </div>

          <!-- 思考过程（架构设计阶段） -->
          <div v-if="architectThinking" class="thinking-card architect-thinking">
            <div class="thinking-header">
              <div class="thinking-avatar architect">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
                  <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
                </svg>
              </div>
              <div class="thinking-meta">
                <span class="thinking-role">架构师</span>
                <span class="thinking-time">{{ formatThinkingTime(architectThinking.startTime) }}</span>
              </div>
              <span class="thinking-badge">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 1 1 7.072 0l-.548.547A3.374 3.374 0 0 0 14 18.469V19a2 2 0 1 1-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
                </svg>
                架构思考
              </span>
            </div>
            <div class="thinking-content">
              <div class="thinking-text">{{ architectThinking.content }}</div>
            </div>
          </div>

          <!-- 思考过程（代码生成阶段） -->
          <div v-if="codeThinking" class="thinking-card code-thinking">
            <div class="thinking-header">
              <div class="thinking-avatar coder">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="16 18 22 12 16 6"/>
                  <polyline points="8 6 2 12 8 18"/>
                </svg>
              </div>
              <div class="thinking-meta">
                <span class="thinking-role">工程师</span>
                <span class="thinking-time">{{ formatThinkingTime(codeThinking.startTime) }}</span>
              </div>
              <span class="thinking-badge">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/>
                </svg>
                代码思考
              </span>
            </div>
            <div class="thinking-content">
              <div class="thinking-text">{{ codeThinking.content }}</div>
            </div>
          </div>

          <!-- 文件树 -->
          <div v-if="fileTree.length > 0" class="file-section">
            <div class="section-header" @click="toggleFileTree">
              <svg class="chevron" :class="{ expanded: fileTreeExpanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <span>项目文件</span>
              <span class="file-count">{{ fileTree.length }}</span>
            </div>
            <div v-show="fileTreeExpanded" class="file-tree">
              <TreeNode
                v-for="node in fileTree"
                :key="node.path"
                :node="node"
                :selected="selectedFile === node.path"
                @select="selectFile"
              />
            </div>
          </div>

          <!-- 代码预览 -->
          <div v-if="selectedFile" class="code-preview">
            <div class="preview-header">
              <div class="preview-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="16 18 22 12 16 6"/>
                  <polyline points="8 6 2 12 8 18"/>
                </svg>
                <span>{{ selectedFile }}</span>
              </div>
              <div class="preview-actions">
                <button v-if="getFileType(selectedFile) === 'image'" class="btn-icon" title="视觉分析" @click="analyzeImage(selectedFile)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                </button>
                <button v-if="getFileType(selectedFile) === 'code'" class="btn-icon" title="代码审查" @click="reviewCode(selectedFile)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M9 11l3 3L22 4"/>
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                  </svg>
                </button>
                <button class="btn-icon" title="关闭" @click="selectedFile = null">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"/>
                    <line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                </button>
              </div>
            </div>

            <!-- 面板切换标签 -->
            <div class="preview-tabs">
              <button :class="{ active: activeTab === 'preview' }" @click="activeTab = 'preview'">
                预览
              </button>
              <button :class="{ active: activeTab === 'vision' }" :disabled="!visionResult" @click="activeTab = 'vision'">
                视觉分析
              </button>
              <button :class="{ active: activeTab === 'review' }" :disabled="!reviewResult" @click="activeTab = 'review'">
                代码审查
              </button>
            </div>

            <!-- 预览面板 -->
            <div v-show="activeTab === 'preview'" class="preview-content">
              <img v-if="getFileType(selectedFile) === 'image'" :src="`/api/v1/files/read?path=${encodeURIComponent(selectedFile)}`" class="preview-image" />
              <iframe v-else-if="selectedFile.endsWith('.html')" :srcdoc="fileContents[selectedFile]" class="preview-iframe"></iframe>
              <pre v-else class="preview-code"><code v-html="highlightedCode"></code></pre>
            </div>

            <!-- 视觉分析面板 -->
            <div v-show="activeTab === 'vision'" class="vision-panel">
              <div v-if="visionResult" class="vision-result">
                <div class="vision-meta">
                  <span class="vision-model">{{ visionResult.model_used }}</span>
                </div>
                <div class="vision-description">
                  <h4>图片描述</h4>
                  <p>{{ visionResult.description }}</p>
                </div>
                <div v-if="visionResult.text" class="vision-text">
                  <h4>提取文字</h4>
                  <pre>{{ visionResult.text }}</pre>
                </div>
                <div v-if="visionResult.objects && visionResult.objects.length > 0" class="vision-objects">
                  <h4>检测到的对象</h4>
                  <div class="object-list">
                    <span v-for="(obj, idx) in visionResult.objects" :key="idx" class="object-tag">{{ obj }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="empty-hint">点击上方"视觉分析"按钮开始分析</div>
            </div>

            <!-- 代码审查面板 -->
            <div v-show="activeTab === 'review'" class="review-panel">
              <div v-if="reviewResult" class="review-result">
                <div class="review-header">
                  <span class="review-status" :class="reviewResult.approved ? 'approved' : 'rejected'">
                    <svg v-if="reviewResult.approved" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M20 6L9 17l-5-5"/>
                    </svg>
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
                    </svg>
                    {{ reviewResult.approved ? '通过' : '未通过' }}
                  </span>
                  <span class="review-risk" :class="reviewResult.risk_level">
                    风险等级: {{ reviewResult.risk_level }}
                  </span>
                </div>
                <div v-if="reviewResult.issues && reviewResult.issues.length > 0" class="review-section">
                  <h4>问题列表</h4>
                  <div class="issue-list">
                    <div v-for="(issue, idx) in reviewResult.issues" :key="idx" class="issue-item">
                      <span class="issue-icon">!</span>
                      <p>{{ issue }}</p>
                    </div>
                  </div>
                </div>
                <div v-if="reviewResult.suggestions && reviewResult.suggestions.length > 0" class="review-section">
                  <h4>改进建议</h4>
                  <div class="suggestion-list">
                    <div v-for="(suggestion, idx) in reviewResult.suggestions" :key="idx" class="suggestion-item">
                      <span class="suggestion-icon">i</span>
                      <p>{{ suggestion }}</p>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="empty-hint">点击上方"代码审查"按钮开始审查</div>
            </div>
          </div>

          <!-- 日志列表 -->
          <div ref="logsContainer" class="logs-container">
            <div
              v-for="(log, index) in logs"
              :key="index"
              class="log-entry"
              :class="log.type"
            >
              <span class="log-time">{{ formatTime(log.time) }}</span>
              <span class="log-icon" v-html="getLogIcon(log.type)"></span>
              <span class="log-message">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed, watch, nextTick, onMounted, h } from 'vue'
  import { useRouter } from 'vue-router'
  import { api } from '@/utils/api/index'
  import hljs from 'highlight.js/lib/core'
  import python from 'highlight.js/lib/languages/python'
  import javascript from 'highlight.js/lib/languages/javascript'
  import css from 'highlight.js/lib/languages/css'
  import html from 'highlight.js/lib/languages/xml'
  import typescript from 'highlight.js/lib/languages/typescript'
  import bash from 'highlight.js/lib/languages/bash'
  import json from 'highlight.js/lib/languages/json'
  import yaml from 'highlight.js/lib/languages/yaml'
  import sql from 'highlight.js/lib/languages/sql'
  import dockerfile from 'highlight.js/lib/languages/dockerfile'
  import go from 'highlight.js/lib/languages/go'
  import rust from 'highlight.js/lib/languages/rust'
  import 'highlight.js/styles/github-dark.css'

  hljs.registerLanguage('python', python)
  hljs.registerLanguage('javascript', javascript)
  hljs.registerLanguage('css', css)
  hljs.registerLanguage('html', html)
  hljs.registerLanguage('xml', html)
  hljs.registerLanguage('typescript', typescript)
  hljs.registerLanguage('bash', bash)
  hljs.registerLanguage('json', json)
  hljs.registerLanguage('yaml', yaml)
  hljs.registerLanguage('sql', sql)
  hljs.registerLanguage('dockerfile', dockerfile)
  hljs.registerLanguage('go', go)
  hljs.registerLanguage('rust', rust)
  hljs.registerLanguage('vue', html)

  const router = useRouter()

  // 状态
  const form = ref({ requirement: '', sessionId: '' })
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
  const currentAgent = ref('') // 当前活跃的 Agent 模型
  const activeTab = ref('preview') // 当前激活的面板：preview | vision | review
  const visionResult = ref(null) // 视觉分析结果
  const reviewResult = ref(null) // 代码审查结果
  const leftPanelCollapsed = ref(false)

  // 思考过程
  const architectThinking = ref(null)
  const codeThinking = ref(null)

  // 文件树
  const fileTree = ref([])
  const fileTreeExpanded = ref(true)
  const selectedFile = ref(null)
  const fileContents = ref({})

  let abortController = null

  // 选项
  const options = ref({
    enableReview: true,
    enableValidation: true,
    enableErrorRecovery: true
  })

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
    '启用增强生成模式': 'generating',
    '运行自动化测试': 'testing',
    '测试全部通过': 'testing',
    '自动修复测试问题': 'testing',
    '最终项目验证': 'testing',
    'Agent 生成完成': 'complete'
  }

  // 状态计算
  const statusClass = computed(() => {
    if (generationComplete.value) return 'complete'
    if (isGenerating.value) return 'generating'
    return 'idle'
  })

  const statusText = computed(() => {
    if (generationComplete.value) return '生成完成'
    if (isGenerating.value) return progressMessage.value || '生成中...'
    return '等待开始'
  })

  const progressPercent = computed(() => {
    return totalSteps.value > 0 ? (currentStep.value / totalSteps.value) * 100 : 0
  })

  const extToLang = {
    py: 'python', js: 'javascript', jsx: 'javascript', mjs: 'javascript',
    ts: 'typescript', tsx: 'typescript', vue: 'vue', html: 'html', htm: 'html',
    css: 'css', scss: 'css', json: 'json', yaml: 'yaml', yml: 'yaml',
    sql: 'sql', sh: 'bash', zsh: 'bash', Dockerfile: 'dockerfile',
    go: 'go', rs: 'rust', toml: 'yaml', md: 'markdown', xml: 'xml'
  }

  const getCodeLang = (path) => {
    if (!path) return 'text'
    const base = path.split('/').pop()
    if (extToLang[base]) return extToLang[base]
    const ext = base.split('.').pop().toLowerCase()
    return extToLang[ext] || 'text'
  }

  const highlightedCode = computed(() => {
    if (!selectedFile.value || !fileContents.value[selectedFile.value]) return ''
    const code = fileContents.value[selectedFile.value]
    const lang = getCodeLang(selectedFile.value)
    if (lang === 'text' || !hljs.getLanguage(lang)) {
      return hljs.highlightAuto(code).value
    }
    return hljs.highlight(code, { language: lang }).value
  })

  // 快捷模板
  const templates = [
    { name: 'Web API', requirement: '创建一个 RESTful API 服务，使用 FastAPI框架，包含用户管理、认证授权、数据 CRUD 接口，支持分页查询' },
    { name: 'Vue3 项目', requirement: '创建一个 Vue3 项目，使用 Vite 构建，包含登录注册、内容列表、详情页，使用 Pinia 状态管理' },
    { name: 'Python 脚本', requirement: '创建一个 Python 工具脚本，实现批量文件处理功能，支持按扩展名筛选、日志记录、错误重试' },
    { name: 'Next.js 全栈', requirement: '创建一个 Next.js 全栈项目，包含首页、博客列表、博客详情页，使用 App Router 和 Server Actions' }
  ]

  // TreeNode 组件
  const TreeNode = (props, { emit }) => {
    const { node, selected } = props
    const expanded = ref(node.isExpanded ?? false)
    const isDir = !node.path.includes('.')
    const fileName = node.path.split('/').pop()

    const handleClick = () => {
      if (isDir) {
        expanded.value = !expanded.value
      }
      emit('select', node.path)
    }

    return h('div', { class: 'tree-node' }, [
      h('div', {
        class: ['tree-item', { selected, dir: isDir }],
        onClick: handleClick
      }, [
        isDir && h('svg', {
          class: ['chevron', { expanded }],
          viewBox: '0 0 24 24',
          fill: 'none',
          stroke: 'currentColor',
          'stroke-width': '2'
        }, [
          h('polyline', { points: '9 18 15 12 9 6' })
        ]),
        h('svg', {
          class: 'file-icon',
          viewBox: '0 0 24 24',
          fill: 'none',
          stroke: 'currentColor',
          'stroke-width': '2'
        }, [
          isDir
            ? h('path', { d: 'M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z' })
            : h('path', { d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' })
        ]),
        h('span', { class: 'node-name' }, fileName)
      ]),
      node.children && expanded.value && h('div', { class: 'tree-children' },
        node.children.map(child => h(TreeNode, { node: child, selected, onSelect: emit('select') }))
      )
    ])
  }

  // 方法
  const goBack = () => router.push('/')

  const getAgentLabel = (agent) => {
    const labels = {
      architect: '架构师',
      engineer: '工程师',
      reviewer: '审查员',
      tester: '测试员',
      planner: '规划员',
      designer: '设计师',
      optimizer: '优化员',
      validator: '验证员'
    }
    return labels[agent] || agent || '待分配'
  }

  const getFileType = (path) => {
    const ext = path.split('.').pop().toLowerCase()
    const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp']
    const codeExts = ['js', 'ts', 'vue', 'jsx', 'tsx', 'py', 'html', 'css', 'json']
    if (imageExts.includes(ext)) return 'image'
    if (codeExts.includes(ext) || ext === 'html') return 'code'
    return 'other'
  }

  const analyzeImage = async (filePath) => {
    try {
      const token = localStorage.getItem('access_token')
      const fileRes = await fetch(`/api/v1/agent/generate/read?file_path=${encodeURIComponent(filePath)}&project_path=${outputDir.value}`, {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      if (!fileRes.ok) return

      const blob = await fileRes.blob()
      const reader = new FileReader()
      reader.onloadend = async () => {
        const base64 = reader.result
        const res = await fetch(`/api/v1/vision/analyze?prompt=${encodeURIComponent('请详细描述这张图片的内容')}`, {
          method: 'POST',
          body: JSON.stringify({ image_url: base64 }),
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': token ? `Bearer ${token}` : ''
          }
        })
        if (res.ok) {
          visionResult.value = await res.json()
          activeTab.value = 'vision'
        }
      }
    } catch (e) {
      console.error('视觉分析失败:', e)
    }
  }

  const reviewCode = async (filePath) => {
    try {
      if (!fileContents.value[filePath]) {
        await loadFileContent(filePath)
      }
      const content = fileContents.value[filePath] || ''
      const token = localStorage.getItem('access_token')
      const res = await fetch(`/api/v1/agent/review`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({ content_type: 'code', content, context: `文件：${filePath}` })
      })
      if (res.ok) {
        reviewResult.value = await res.json()
        activeTab.value = 'review'
      }
    } catch (e) {
      console.error('代码审查失败:', e)
    }
  }

  const applyTemplate = (tpl) => {
    form.value.requirement = tpl.requirement
  }

  const toggleFileTree = () => {
    fileTreeExpanded.value = !fileTreeExpanded.value
  }

  const selectFile = (path) => {
    selectedFile.value = path
    activeTab.value = 'preview'
    visionResult.value = null
    reviewResult.value = null
    // 懒加载文件内容
    if (!fileContents.value[path]) {
      loadFileContent(path)
    }
  }

  const loadFileContent = async (path) => {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`/api/v1/files/read?path=${encodeURIComponent(path)}`, {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      if (res.ok) {
        fileContents.value[path] = await res.text()
      }
    } catch {
      fileContents.value[path] = '// 无法加载文件内容'
    }
  }

  const handleDownload = () => {
    if (!outputDir.value) return
    window.open(api.downloadProject(outputDir.value), '_blank')
  }

  const resetAndStartNew = () => {
    form.value = { requirement: '', sessionId: '' }
    generationComplete.value = false
    isGenerating.value = false
    progressMessage.value = ''
    currentStep.value = 0
    totalSteps.value = 0
    filesCreated.value = 0
    logs.value = []
    outputDir.value = ''
    currentPhase.value = ''
    completedPhases.value = []
    currentAgent.value = ''
    activeTab.value = 'preview'
    visionResult.value = null
    reviewResult.value = null
    architectThinking.value = null
    codeThinking.value = null
    fileTree.value = []
    selectedFile.value = null
    fileContents.value = {}
  }

  const startGeneration = async () => {
    if (!form.value.requirement.trim()) return

    isGenerating.value = true
    generationComplete.value = false
    logs.value = []
    currentPhase.value = ''
    completedPhases.value = []
    currentAgent.value = ''
    activeTab.value = 'preview'
    visionResult.value = null
    reviewResult.value = null
    architectThinking.value = null
    codeThinking.value = null
    fileTree.value = []
    fileContents.value = {}

    abortController = new AbortController()

    addLog('info', '开始 Agent 生成...')
    addLog('info', `需求: ${form.value.requirement}`)

    try {
      const response = await api.stream(
        '/agent/orchestrate/stream',
        {
          requirement: form.value.requirement,
          enable_review: options.value.enableReview,
          enable_validation: options.value.enableValidation,
          enable_error_recovery: options.value.enableErrorRecovery,
          enable_memory: true,
          require_approval: false
        },
        abortController.signal
      )

      if (!response.ok) {
        throw new Error((await response.json()).detail || '生成失败')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        for (const line of chunk.split('\n').filter(l => l.trim())) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.substring(6))
              handleStreamData(data)
            } catch (e) {
              // 忽略无效的 JSON 行
            }
          }
        }
      }

      generationComplete.value = true
      addLog('success', 'Agent 生成完成！')
    } catch (e) {
      if (e.name !== 'AbortError') {
        addLog('error', `生成失败: ${e.message}`)
      } else {
        addLog('warning', '生成已停止')
      }
      isGenerating.value = false
    }
  }

  const stopGeneration = () => {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    isGenerating.value = false
    hasStopped.value = true
    addLog('warning', '生成已停止')
  }

  const handleStreamData = (data) => {
    const eventType = data.type
    const eventData = data.data || data
    const step = eventData.step || eventType

    // 更新阶段
    const mappedPhase = phaseMap[step]
    if (mappedPhase) {
      if (currentPhase.value && !completedPhases.value.includes(currentPhase.value)) {
        completedPhases.value.push(currentPhase.value)
      }
      currentPhase.value = mappedPhase
    }

    switch (eventType) {
      case 'progress':
        currentStep.value = eventData.current || 0
        totalSteps.value = eventData.total || 0
        progressMessage.value = eventData.step || '处理中...'
        addLog('info', eventData.step)
        break

      case 'thinking':
        // 更新当前 Agent
        if (eventData.agent) {
          currentAgent.value = eventData.agent
        }
        // 架构师思考
        if (eventData.agent === 'architect' || eventData.step?.includes('架构')) {
          architectThinking.value = {
            content: eventData.message,
            startTime: new Date()
          }
        }
        // 工程师思考
        if (eventData.agent === 'engineer' || eventData.step?.includes('代码')) {
          codeThinking.value = {
            content: eventData.message,
            startTime: new Date()
          }
        }
        addLog('thinking', `[${eventData.agent || '思考'}] ${eventData.message}`)
        break

      case 'done':
        generationComplete.value = true
        progressMessage.value = '生成完成'
        outputDir.value = eventData.output_dir || ''
        filesCreated.value = eventData.total_files_created || 0
        addLog('success', `生成完成！共 ${filesCreated.value} 个文件`)
        break

      case 'file_created':
        filesCreated.value++
        addLog('success', `生成: ${eventData.file_path}`)
        // 更新文件树
        updateFileTree(eventData.file_path)
        break

      case 'file_tree':
        // 接收完整的文件树
        if (eventData.tree) {
          fileTree.value = eventData.tree
        }
        break

      default:
        if (step && typeof step === 'string' && !step.includes('data')) {
          addLog('info', step)
        }
    }

    nextTick(() => {
      if (logsContainer.value) {
        logsContainer.value.scrollTop = logsContainer.value.scrollHeight
      }
    })
  }

  const updateFileTree = (filePath) => {
    const parts = filePath.split('/')
    let current = fileTree.value

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      const isDir = i < parts.length - 1

      let node = current.find(n => n.path === part)
      if (!node) {
        node = {
          path: i === 0 ? part : parts.slice(0, i + 1).join('/'),
          children: [],
          isExpanded: true
        }
        current.push(node)
      }
      current = node.children
    }
  }

  const addLog = (type, message) => {
    logs.value.push({ type, message, time: new Date() })
  }

  const formatTime = (date) => {
    return date.toLocaleTimeString('zh-CN', { hour12: false })
  }

  const formatThinkingTime = (date) => {
    const now = new Date()
    const diff = Math.floor((now - date) / 1000)
    if (diff < 60) return `${diff}秒前`
    return `${Math.floor(diff / 60)}分钟前`
  }

  const getLogIcon = (type) => {
    const icons = {
      info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
      success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>',
      warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/></svg>',
      error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
      thinking: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 1 1 7.072 0l-.548.547A3.374 3.374 0 0 0 14 18.469V19a2 2 0 1 1-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>'
    }
    return icons[type] || icons.info
  }

  onMounted(() => {
    // 恢复输入内容
    try {
      const raw = localStorage.getItem('project_generator_requirement')
      if (raw) {
        const state = JSON.parse(raw)
        if (state.requirement) {
          form.value.requirement = state.requirement
        }
      }
    } catch (e) {
      // 忽略恢复失败
    }
  })

  watch(() => form.value.requirement, (val) => {
    if (val.trim()) {
      localStorage.setItem('project_generator_requirement', JSON.stringify({ requirement: val }))
    }
  })
</script>

<style scoped>
  .project-generate-page {
    min-height: 100vh;
    background: var(--bg-primary);
    color: var(--text-primary);
    display: flex;
    flex-direction: column;
  }

  /* 顶部导航 */
  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
    backdrop-filter: blur(20px);
  }

  .back-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    color: var(--text-secondary);
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .back-btn:hover {
    background: var(--hover-bg);
    color: var(--text-primary);
  }

  .back-btn svg {
    width: 16px;
    height: 16px;
  }

  .header-title {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 18px;
    font-weight: 600;
  }

  .header-title svg {
    width: 28px;
    height: 28px;
    color: var(--color-success-500);
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .collapse-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
  }

  .collapse-toggle:hover {
    background: var(--bg-secondary);
    border-color: var(--color-success-500);
    color: var(--text-primary);
  }

  .agent-status {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 20px;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
  }

  .status-dot.architect { color: #a78bfa; animation: pulse 1.5s infinite; }
  .status-dot.engineer { color: #60a5fa; animation: pulse 1.5s infinite; }
  .status-dot.reviewer { color: #fbbf24; animation: pulse 1.5s infinite; }
  .status-dot.tester { color: #34d399; animation: pulse 1.5s infinite; }
  .status-dot.planner { color: #f472b6; animation: pulse 1.5s infinite; }
  .status-dot.designer { color: #fb923c; animation: pulse 1.5s infinite; }
  .status-dot.optimizer { color: #38bdf8; animation: pulse 1.5s infinite; }
  .status-dot.validator { color: #a3e635; animation: pulse 1.5s infinite; }

  .agent-name {
    font-weight: 500;
  }

  /* 主内容 */
  .page-content {
    flex: 1;
    display: grid;
    grid-template-columns: 400px 1fr;
    gap: 0;
    overflow: hidden;
    transition: grid-template-columns 0.3s ease;
  }

  .page-content.panel-collapsed {
    grid-template-columns: 0 1fr;
  }

  /* 左侧配置面板 */
  .config-panel {
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
    padding: 24px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 24px;
    min-width: 0;
    opacity: 1;
    transition: opacity 0.2s ease, padding 0.3s ease, border 0.3s ease;
  }

  .panel-collapsed .config-panel {
    opacity: 0;
    padding: 0;
    border-right: none;
    pointer-events: none;
  }

  .panel-section {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .section-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .section-title svg {
    width: 16px;
    height: 16px;
    color: var(--color-success-500);
  }

  .requirement-input {
    width: 100%;
    min-height: 180px;
    padding: 14px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    color: var(--text-primary);
    font-size: 14px;
    font-family: inherit;
    resize: vertical;
    transition: all 0.2s;
  }

  .requirement-input:focus {
    outline: none;
    border-color: var(--color-success-500);
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1);
  }

  .requirement-input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .option-item {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 12px;
    background: var(--bg-tertiary);
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.2s;
  }

  .option-item:hover {
    background: var(--hover-bg);
  }

  .option-item input[type="checkbox"] {
    width: 18px;
    height: 18px;
    accent-color: var(--color-success-500);
    margin-top: 2px;
  }

  .option-label {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .option-name {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .option-desc {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .template-list {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .template-btn {
    padding: 10px 12px;
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.2);
    border-radius: 8px;
    color: var(--color-success-500);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .template-btn:hover:not(:disabled) {
    background: rgba(16, 185, 129, 0.2);
    border-color: rgba(16, 185, 129, 0.4);
  }

  .template-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .panel-actions {
    margin-top: auto;
    padding-top: 24px;
  }

  /* 按钮 */
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
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
    width: 18px;
    height: 18px;
  }

  .btn-primary {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: #fff;
  }

  .btn-primary:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(16, 185, 129, 0.4);
  }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-danger {
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: var(--color-danger-500);
  }

  .btn-danger:hover {
    background: rgba(239, 68, 68, 0.25);
  }

  .btn-success {
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.3);
    color: var(--color-success-500);
  }

  .btn-download {
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid rgba(59, 130, 246, 0.3);
    color: #60a5fa;
  }

  .btn-download:hover {
    background: rgba(59, 130, 246, 0.25);
  }

  .btn-large {
    width: 100%;
    padding: 14px 20px;
    font-size: 15px;
  }

  /* 右侧进度面板 */
  .progress-panel {
    padding: 24px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  /* 空状态 */
  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: 20px;
  }

  .empty-icon {
    width: 100px;
    height: 100px;
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(16, 185, 129, 0.05));
    border-radius: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--color-success-500);
  }

  .empty-icon svg {
    width: 50px;
    height: 50px;
  }

  .empty-state h2 {
    font-size: 28px;
    font-weight: 700;
    background: linear-gradient(135deg, #e4e4e7, #a1a1aa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .empty-state p {
    color: var(--text-tertiary);
    font-size: 15px;
    max-width: 400px;
  }

  .feature-list {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-top: 10px;
  }

  .feature-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
    font-size: 14px;
    color: var(--text-secondary);
  }

  .feature-item svg {
    width: 18px;
    height: 18px;
    color: var(--color-success-500);
  }

  /* 生成内容 */
  .generation-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  /* 状态栏 */
  .status-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .status-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 15px;
    font-weight: 600;
  }

  .pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
  }

  .status-indicator.idle { color: var(--text-tertiary); }
  .status-indicator.idle .pulse { animation: none; }
  .status-indicator.generating { color: var(--color-success-500); }
  .status-indicator.generating .pulse { animation: pulse 1.5s ease-in-out infinite; }
  .status-indicator.complete { color: #60a5fa; }
  .status-indicator.complete .pulse { background: #60a5fa; animation: none; }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(1.3); }
  }

  .status-step {
    font-size: 13px;
    color: var(--text-tertiary);
    font-weight: normal;
  }

  .status-file {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--text-tertiary);
  }

  .status-file svg {
    width: 16px;
    height: 16px;
  }

  /* 进度条 */
  .progress-bar-container {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .progress-bar {
    flex: 1;
    height: 6px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #10b981, #34d399);
    border-radius: 3px;
    transition: width 0.4s ease;
  }

  .progress-percent {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-success-500);
    min-width: 45px;
    text-align: right;
  }

  /* 阶段导航 */
  .phase-nav {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 4px;
  }

  .phase-tab {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 20px;
    font-size: 13px;
    color: #52525b;
    white-space: nowrap;
    transition: all 0.3s;
  }

  .phase-tab.active {
    background: rgba(16, 185, 129, 0.15);
    border-color: rgba(16, 185, 129, 0.3);
    color: var(--color-success-500);
  }

  .phase-tab.completed {
    background: rgba(16, 185, 129, 0.08);
    border-color: rgba(16, 185, 129, 0.2);
    color: #34d399;
  }

  .phase-num {
    width: 20px;
    height: 20px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
  }

  .phase-tab.active .phase-num {
    background: #10b981;
    color: #fff;
  }

  .phase-tab.completed .phase-num {
    background: #10b981;
    color: #fff;
  }

  /* 思考卡片 */
  .thinking-card {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    overflow: hidden;
  }

  .thinking-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    background: rgba(255, 255, 255, 0.02);
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }

  .thinking-avatar {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .thinking-avatar.architect {
    background: linear-gradient(135deg, rgba(139, 92, 246, 0.2), rgba(139, 92, 246, 0.1));
    color: #a78bfa;
  }

  .thinking-avatar.coder {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(59, 130, 246, 0.1));
    color: #60a5fa;
  }

  .thinking-avatar svg {
    width: 18px;
    height: 18px;
  }

  .thinking-meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .thinking-role {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .thinking-time {
    font-size: 11px;
    color: var(--text-tertiary);
  }

  .thinking-badge {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: var(--bg-tertiary);
    border-radius: 20px;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .thinking-badge svg {
    width: 14px;
    height: 14px;
  }

  .thinking-content {
    padding: 16px;
  }

  .thinking-text {
    font-size: 14px;
    line-height: 1.7;
    color: #d4d4d8;
    white-space: pre-wrap;
  }

  /* 文件区域 */
  .file-section {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    overflow: hidden;
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 16px;
    cursor: pointer;
    user-select: none;
    transition: background 0.2s;
  }

  .section-header:hover {
    background: rgba(255, 255, 255, 0.02);
  }

  .section-header .chevron {
    width: 16px;
    height: 16px;
    color: var(--text-tertiary);
    transition: transform 0.2s;
  }

  .section-header .chevron.expanded {
    transform: rotate(90deg);
  }

  .section-header svg {
    width: 18px;
    height: 18px;
    color: var(--text-tertiary);
  }

  .section-header span {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .file-count {
    margin-left: auto;
    padding: 2px 10px;
    background: rgba(16, 185, 129, 0.15);
    border-radius: 10px;
    font-size: 12px;
    color: var(--color-success-500) !important;
    font-weight: 600 !important;
  }

  .file-tree {
    padding: 8px 16px 16px;
  }

  :deep(.tree-node) {
    font-size: 13px;
  }

  :deep(.tree-item) {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s;
    color: var(--text-secondary);
  }

  :deep(.tree-item:hover) {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  :deep(.tree-item.selected) {
    background: rgba(16, 185, 129, 0.15);
    color: var(--color-success-500);
  }

  :deep(.tree-item.dir) {
    color: #60a5fa;
  }

  :deep(.tree-item .chevron) {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  :deep(.tree-item .file-icon) {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  :deep(.tree-item .node-name) {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  :deep(.tree-children) {
    padding-left: 20px;
  }

  /* 代码预览 */
  .code-preview {
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    overflow: hidden;
  }

  .preview-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 12px 16px;
    background: rgba(255, 255, 255, 0.02);
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }

  .preview-title {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .preview-title svg {
    width: 16px;
    height: 16px;
    color: #60a5fa;
  }

  .preview-title span {
    font-size: 13px;
    color: var(--text-primary);
    font-family: 'JetBrains Mono', monospace;
  }

  .preview-actions {
    display: flex;
    gap: 8px;
  }

  .btn-icon {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-icon:hover {
    background: rgba(255, 255, 255, 0.1);
    color: var(--text-primary);
  }

  .btn-icon svg {
    width: 16px;
    height: 16px;
  }

  .preview-tabs {
    display: flex;
    gap: 4px;
    padding: 8px 16px;
    background: var(--bg-tertiary);
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }

  .preview-tabs button {
    padding: 6px 16px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: var(--text-tertiary);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .preview-tabs button:hover:not(:disabled) {
    background: var(--bg-tertiary);
    color: var(--text-secondary);
  }

  .preview-tabs button.active {
    background: rgba(16, 185, 129, 0.15);
    border-color: rgba(16, 185, 129, 0.3);
    color: var(--color-success-500);
  }

  .preview-tabs button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .preview-content {
    min-height: 200px;
    max-height: 500px;
    overflow: auto;
  }

  .preview-image {
    width: 100%;
    max-height: 400px;
    object-fit: contain;
    background: var(--bg-tertiary);
  }

  .preview-iframe {
    width: 100%;
    height: 400px;
    border: none;
    background: #fff;
  }

  .preview-code {
    margin: 0;
    padding: 16px;
    max-height: 400px;
    overflow: auto;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 12px;
    line-height: 1.6;
    color: var(--text-secondary);
    white-space: pre;
  }

  .preview-code code {
    font-family: inherit;
  }

  .preview-code :deep(.hljs) {
    background: transparent !important;
    padding: 0 !important;
  }

  .vision-panel,
  .review-panel {
    padding: 16px;
    min-height: 150px;
    max-height: 400px;
    overflow-y: auto;
  }

  .vision-meta {
    margin-bottom: 16px;
  }

  .vision-model {
    padding: 4px 10px;
    background: rgba(59, 130, 246, 0.1);
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 12px;
    font-size: 11px;
    color: #60a5fa;
    font-family: monospace;
  }

  .vision-description,
  .vision-text,
  .vision-objects,
  .review-section {
    margin-bottom: 16px;
  }

  .vision-description h4,
  .vision-text h4,
  .vision-objects h4,
  .review-section h4 {
    margin: 0 0 8px;
    font-size: 13px;
    font-weight: 600;
    color: #d4d4d8;
  }

  .vision-description p {
    margin: 0;
    font-size: 13px;
    line-height: 1.7;
    color: var(--text-secondary);
  }

  .vision-text pre {
    margin: 0;
    padding: 12px;
    background: var(--bg-tertiary);
    border-radius: 8px;
    font-size: 12px;
    line-height: 1.5;
    color: #d4d4d8;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .vision-objects .object-list,
  .issue-list,
  .suggestion-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .object-tag {
    padding: 4px 10px;
    background: rgba(139, 92, 246, 0.15);
    border: 1px solid rgba(139, 92, 246, 0.3);
    border-radius: 12px;
    font-size: 12px;
    color: #a78bfa;
  }

  .review-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    background: rgba(255, 255, 255, 0.02);
    border-radius: 8px;
    margin-bottom: 16px;
  }

  .review-status {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 600;
  }

  .review-status svg {
    width: 14px;
    height: 14px;
  }

  .review-status.approved {
    background: rgba(16, 185, 129, 0.15);
    color: var(--color-success-500);
  }

  .review-status.rejected {
    background: rgba(239, 68, 68, 0.15);
    color: var(--color-danger-500);
  }

  .review-risk {
    padding: 4px 10px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 500;
  }

  .review-risk.low {
    background: rgba(16, 185, 129, 0.1);
    color: var(--color-success-500);
  }

  .review-risk.medium {
    background: rgba(251, 191, 36, 0.1);
    color: #fbbf24;
  }

  .review-risk.high {
    background: rgba(239, 68, 68, 0.1);
    color: var(--color-danger-500);
  }

  .issue-list {
    flex-direction: column;
  }

  .issue-item {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 10px 12px;
    background: rgba(239, 68, 68, 0.05);
    border: 1px solid rgba(239, 68, 68, 0.1);
    border-radius: 8px;
  }

  .issue-icon {
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(239, 68, 68, 0.2);
    border-radius: 50%;
    font-size: 11px;
    font-weight: 700;
    color: var(--color-danger-500);
    flex-shrink: 0;
  }

  .issue-item p {
    margin: 0;
    font-size: 13px;
    color: #d4d4d8;
    line-height: 1.5;
  }

  .suggestion-item {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 10px 12px;
    background: rgba(59, 130, 246, 0.05);
    border: 1px solid rgba(59, 130, 246, 0.1);
    border-radius: 8px;
  }

  .suggestion-icon {
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(59, 130, 246, 0.2);
    border-radius: 50%;
    font-size: 11px;
    font-weight: 700;
    color: #60a5fa;
    flex-shrink: 0;
  }

  .suggestion-item p {
    margin: 0;
    font-size: 13px;
    color: #d4d4d8;
    line-height: 1.5;
  }

  .empty-hint {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 150px;
    color: #52525b;
    font-size: 13px;
  }

  /* 日志 */
  .logs-container {
    flex: 1;
    min-height: 200px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 14px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 12px;
  }

  .log-entry {
    display: flex;
    gap: 10px;
    padding: 6px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  }

  .log-time {
    color: #52525b;
    min-width: 65px;
    font-size: 11px;
  }

  .log-icon {
    width: 14px;
    height: 14px;
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

  .log-entry.info .log-message { color: var(--text-secondary); }
  .log-entry.success .log-message { color: #34d399; }
  .log-entry.warning .log-message { color: #fbbf24; }
  .log-entry.error .log-message { color: #f87171; }
  .log-entry.thinking .log-message { color: #a78bfa; font-style: italic; }

  .log-entry.success .log-icon svg { color: #34d399; }
  .log-entry.warning .log-icon svg { color: #fbbf24; }
  .log-entry.error .log-icon svg { color: #f87171; }
  .log-entry.thinking .log-icon svg { color: #a78bfa; }

  /* 响应式 */
  @media (max-width: 900px) {
    .page-content {
      grid-template-columns: 1fr;
    }

    .config-panel {
      border-right: none;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      max-height: 50vh;
    }
  }
</style>