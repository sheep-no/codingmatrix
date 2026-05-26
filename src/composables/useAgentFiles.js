import { ref, computed, reactive } from 'vue'
import hljs from 'highlight.js'

const languageMap = {
  'js': 'JavaScript', 'jsx': 'React JSX', 'ts': 'TypeScript', 'tsx': 'React TSX',
  'vue': 'Vue', 'py': 'Python', 'java': 'Java', 'go': 'Go', 'rb': 'Ruby', 'php': 'PHP',
  'cs': 'C#', 'cpp': 'C++', 'c': 'C', 'h': 'Header', 'html': 'HTML', 'css': 'CSS',
  'scss': 'SCSS', 'sass': 'Sass', 'json': 'JSON', 'xml': 'XML', 'yaml': 'YAML',
  'yml': 'YAML', 'md': 'Markdown', 'txt': 'Text', 'sql': 'SQL', 'sh': 'Shell',
  'bash': 'Bash', 'dockerfile': 'Dockerfile', 'makefile': 'Makefile', 'env': 'Environment',
  'gitignore': 'Git Ignore'
}

const fileTypeMap = {
  'js': 'JavaScript', 'jsx': 'React JSX', 'ts': 'TypeScript', 'tsx': 'React TSX',
  'vue': 'Vue Component', 'py': 'Python', 'java': 'Java', 'go': 'Go', 'rb': 'Ruby',
  'php': 'PHP', 'cs': 'C#', 'cpp': 'C++', 'c': 'C', 'h': 'Header', 'html': 'HTML',
  'css': 'CSS', 'scss': 'SCSS', 'sass': 'Sass', 'json': 'JSON', 'xml': 'XML',
  'yaml': 'YAML', 'yml': 'YAML', 'md': 'Markdown', 'txt': 'Text', 'sql': 'SQL',
  'sh': 'Shell', 'bash': 'Bash', 'dockerfile': 'Dockerfile', 'makefile': 'Makefile', 'env': 'Environment'
}

const hljsLangMap = {
  'javascript': 'javascript', 'typescript': 'typescript', 'vue': 'html', 'html': 'html',
  'css': 'css', 'scss': 'scss', 'python': 'python', 'java': 'java', 'go': 'go',
  'json': 'json', 'yaml': 'yaml', 'xml': 'xml', 'markdown': 'markdown',
  'shell': 'bash', 'sql': 'sql'
}

const templates = {
  'vue-fastapi': {
    name: 'Vue + FastAPI',
    desc: '全栈项目',
    prompt: '一个带用户登录功能的 Vue 3 + FastAPI 项目，包含前后端代码、Docker 配置和完整的测试用例。'
  },
  'react-django': {
    name: 'React + Django',
    desc: '全栈项目',
    prompt: '一个 React + Django 全栈项目，包含 REST API、用户认证、数据库模型和前端组件。'
  },
  'nextjs-fastapi': {
    name: 'Next.js + FastAPI',
    desc: '现代全栈',
    prompt: '使用 Next.js 14 (App Router) + FastAPI 构建的现代全栈应用，支持 SSR 和 API 路由。'
  },
  'flutter-flask': {
    name: 'Flutter + Flask',
    desc: '移动应用',
    prompt: '一个 Flutter 移动应用 + Flask 后端，包含 RESTful API、SQLite 数据库和 Material Design UI。'
  },
  'springboot-react': {
    name: 'Spring Boot + React',
    desc: '企业级全栈',
    prompt: 'Spring Boot 后端 + React 前端的企业级应用，包含 JPA、安全认证和 REST API。'
  },
  'express-vue': {
    name: 'Express + Vue',
    desc: '轻量全栈',
    prompt: 'Express.js + Vue 3 的轻量级全栈项目，包含 MongoDB 集成和 JWT 认证。'
  }
}

export function useAgentFiles() {
  const generatedFiles = ref([])
  const selectedFile = ref(null)
  const fileDiffs = ref([])
  const fileVersions = ref({})
  const fileSearchQuery = ref('')
  const fileFilterType = ref('all')

  const fileCategories = ref([
    { name: '前端', icon: '前端', expanded: true,
      files: computed(() => generatedFiles.value.filter(f => isFrontendFile(f.path))) },
    { name: '后端', icon: '后端', expanded: true,
      files: computed(() => generatedFiles.value.filter(f => !isFrontendFile(f.path) && !isBackendTestFile(f.path))) },
    { name: '测试', icon: '测试', expanded: true,
      files: computed(() => generatedFiles.value.filter(f => isBackendTestFile(f.path))) },
    { name: '配置', icon: '配置', expanded: true,
      files: computed(() => generatedFiles.value.filter(f => isConfigFile(f.path))) }
  ])

  const filteredFiles = computed(() => {
    let files = generatedFiles.value
    if (fileSearchQuery.value) {
      const query = fileSearchQuery.value.toLowerCase()
      files = files.filter(f => f.path.toLowerCase().includes(query))
    }
    if (fileFilterType.value !== 'all') {
      files = files.filter(f => {
        const lang = getLanguage(f.path).toLowerCase()
        return lang.includes(fileFilterType.value.toLowerCase())
      })
    }
    return files
  })

  const flattenFileTree = computed(() => {
    return generatedFiles.value.map(file => ({
      name: file.path ? file.path.split('/').pop() : file.name || 'unknown',
      path: file.path, content: file.content
    }))
  })

  function isFrontendFile(filePath) {
    const patterns = ['src/components', 'src/views', 'src/pages', '.vue', '.jsx', '.tsx', '.css', '.scss', '.html', '.js', '.ts']
    return patterns.some(p => filePath.includes(p))
  }

  function isBackendTestFile(filePath) {
    const patterns = ['test', 'spec', '__tests__']
    return patterns.some(p => filePath.includes(p)) && !isFrontendFile(filePath)
  }

  function isConfigFile(filePath) {
    const patterns = ['config', '.json', '.yaml', '.yml', '.env', 'Dockerfile', 'docker-compose', '.gitignore']
    return patterns.some(p => filePath.includes(p))
  }

  function getFileIcon(filePath) {
    const ext = filePath.split('.').pop().toLowerCase()
    const iconMap = {
      'vue': '文件', 'jsx': 'React', 'tsx': 'React', 'js': 'JS', 'ts': 'TS',
      'py': 'Python', 'java': 'Java', 'go': 'Go', 'html': 'HTML', 'css': 'CSS',
      'json': 'JSON', 'md': 'MD'
    }
    return iconMap[ext] || '文件'
  }

  function toggleCategory(categoryName) {
    const category = fileCategories.value.find(c => c.name === categoryName)
    if (category) category.expanded = !category.expanded
  }

  function selectFile(file) {
    selectedFile.value = file
  }

  function getLanguage(filePath) {
    if (!filePath) return 'Unknown'
    const fileName = filePath.split('/').pop().toLowerCase()
    const ext = fileName.split('.').pop().toLowerCase()
    if (fileName === 'dockerfile') return 'Dockerfile'
    if (fileName === 'makefile') return 'Makefile'
    if (fileName.startsWith('.gitignore') || fileName === 'gitignore') return 'Git Ignore'
    return languageMap[ext] || ext.toUpperCase()
  }

  function getFileType(filePath) {
    if (!filePath) return ''
    const ext = filePath.split('.').pop().toLowerCase()
    return fileTypeMap[ext] || ext.toUpperCase()
  }

  function getFileName(filePath) {
    return filePath.split('/').pop()
  }

  function formatFileSize(content) {
    if (!content) return '0 B'
    const bytes = new Blob([content]).size
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  function getLineCount(content) {
    if (!content) return 0
    return content.split('\n').length
  }

  function hasFileDiff(filePath) {
    return fileDiffs.value.some(d => d.path === filePath)
  }

  function getHighlightedCode() {
    if (!selectedFile.value || !selectedFile.value.content) return '<pre><code></code></pre>'
    const lang = getLanguage(selectedFile.value.path).toLowerCase()
    const hljsLang = hljsLangMap[lang] || 'plaintext'
    const result = hljs.highlight(selectedFile.value.content, { language: hljsLang })
    return `<pre><code class="hljs language-${hljsLang}">${result.value}</code></pre>`
  }

  function clearAll() {
    generatedFiles.value = []
    fileDiffs.value = []
    selectedFile.value = null
    fileVersions.value = {}
    fileSearchQuery.value = ''
    fileFilterType.value = 'all'
  }

  return reactive({
    generatedFiles, selectedFile, fileDiffs, fileVersions,
    fileSearchQuery, fileFilterType, fileCategories,
    filteredFiles, flattenFileTree,
    isFrontendFile, isBackendTestFile, isConfigFile,
    getFileIcon, toggleCategory, selectFile, getLanguage,
    getFileType, getFileName, formatFileSize, getLineCount,
    hasFileDiff, getHighlightedCode, clearAll, templates
  })
}
