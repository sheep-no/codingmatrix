<template>
  <div class="left-panel">
    <div class="input-section">
      <div class="section-header"><h2>项目需求</h2></div>

      <div class="mode-switcher">
        <button :class="{ active: mode === 'create' }" class="mode-btn" @click="$emit('update:mode', 'create')">新建项目</button>
        <button :class="{ active: mode === 'modify' }" :disabled="!hasFiles" class="mode-btn" @click="$emit('update:mode', 'modify')">增量修改</button>
        <button :class="{ active: mode === 'debug' }" :disabled="!hasFiles" class="mode-btn" @click="$emit('update:mode', 'debug')">调试修复</button>
      </div>

      <textarea :value="prompt" :placeholder="placeholderText" class="prompt-textarea" rows="8" @input="$emit('update:prompt', $event.target.value)" />

      <!-- 模型选择器 -->
      <div v-if="dynamicModels.length > 0" class="model-selector">
        <label class="model-selector-label">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          使用自定义模型（可选）
        </label>
        <select :value="selectedProviderModel" class="model-select" @change="$emit('update:selectedProviderModel', $event.target.value)">
          <option value="">系统默认模型</option>
          <optgroup v-for="group in groupedDynamicModels" :key="group.provider" :label="group.provider">
            <option v-for="m in group.models" :key="m.provider_id + ':' + m.model_id" :value="m.provider_id + '::' + m.model_id">
              {{ m.model_id }}
            </option>
          </optgroup>
        </select>
      </div>

      <div v-if="!hasFiles" class="quick-templates">
        <h3>快速模板</h3>
        <div class="template-grid">
          <div class="template-item" @click="$emit('select-template', 'vue-fastapi')">
            <div class="template-icon" style="background: #42b883">文件</div>
            <div class="template-info"><div class="template-name">Vue + FastAPI</div><div class="template-desc">全栈项目</div></div>
          </div>
          <div class="template-item" @click="$emit('select-template', 'react-django')">
            <div class="template-icon" style="background: #61dafb">React</div>
            <div class="template-info"><div class="template-name">React + Django</div><div class="template-desc">全栈项目</div></div>
          </div>
          <div class="template-item" @click="$emit('select-template', 'nextjs')">
            <div class="template-icon" style="background: #000">Next</div>
            <div class="template-info"><div class="template-name">Next.js</div><div class="template-desc">全栈项目</div></div>
          </div>
          <div class="template-item" @click="$emit('select-template', 'flask')">
            <div class="template-icon" style="background: #000">Flask</div>
            <div class="template-info"><div class="template-name">Flask</div><div class="template-desc">轻量项目</div></div>
          </div>
        </div>
      </div>

      <div class="action-buttons">
        <button v-if="mode === 'create'" class="btn btn-primary" :disabled="!prompt.trim() || generating" @click="$emit('generate')">
          <span v-if="!generating">开始生成</span><span v-else>生成中...</span>
        </button>
        <button v-if="mode === 'modify'" class="btn btn-primary" :disabled="!prompt.trim() || generating" @click="$emit('incremental-generate')">
          <span v-if="!generating">增量更新</span><span v-else>更新中...</span>
        </button>
        <button v-if="mode === 'debug'" class="btn btn-warning" :disabled="!prompt.trim() || generating" @click="$emit('debug')">
          <span v-if="!generating">开始修复</span><span v-else>修复中...</span>
        </button>
        <button v-if="hasFiles" class="btn btn-outline btn-regenerate" @click="$emit('regenerate')">重新生成</button>
        <button v-if="hasFiles" class="btn btn-outline btn-clear" @click="$emit('clear')">清空</button>
        <button v-if="generating" class="btn btn-danger" @click="$emit('stop')">停止</button>
      </div>
    </div>

    <div v-if="hasFiles" class="files-section">
      <div class="section-header">
        <h2>项目文件</h2>
        <div class="file-stats"><span class="total-badge">总计: {{ fileCount }}</span></div>
      </div>

      <div class="file-filter-bar">
        <div class="search-box">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="search-icon">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input :value="searchQuery" type="text" placeholder="搜索文件..." class="file-search-input" @input="$emit('update:searchQuery', $event.target.value)" />
        </div>
        <select :value="filterType" class="file-filter-select" @change="$emit('update:filterType', $event.target.value)">
          <option value="all">全部类型</option>
          <option value="javascript">JavaScript</option>
          <option value="typescript">TypeScript</option>
          <option value="vue">Vue</option>
          <option value="python">Python</option>
          <option value="html">HTML</option>
          <option value="css">CSS</option>
          <option value="json">JSON</option>
        </select>
      </div>

      <div class="file-tree">
        <div v-for="category in categories" :key="category.name">
          <div class="category-header" @click="$emit('toggle-category', category.name)">
            <span class="category-icon">{{ category.icon }}</span>
            <span class="category-name">{{ category.name }}</span>
            <span class="category-count">({{ category.files.length }})</span>
            <span class="expand-icon">{{ category.expanded ? '▼' : '▶' }}</span>
          </div>
          <div v-show="category.expanded" class="category-files">
            <div
v-for="file in category.files" :key="file.path" class="file-item"
              :class="{ selected: selectedPath === file.path }" @click="$emit('select-file', file)">
              <span class="file-icon">{{ getFileIcon(file.path) }}</span>
              <span class="file-name">{{ getFileName(file.path) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  mode: { type: String, required: true },
  prompt: { type: String, required: true },
  placeholderText: { type: String, required: true },
  generating: { type: Boolean, required: true },
  hasFiles: { type: Boolean, required: true },
  fileCount: { type: Number, required: true },
  categories: { type: Array, required: true },
  searchQuery: { type: String, required: true },
  filterType: { type: String, required: true },
  selectedPath: { type: String, default: '' },
  dynamicModels: { type: Array, default: () => [] },
  selectedProviderModel: { type: String, default: '' }
})
const emit = defineEmits(['update:mode', 'update:prompt', 'update:searchQuery', 'update:filterType', 'update:selectedProviderModel', 'generate', 'incremental-generate', 'debug', 'regenerate', 'clear', 'stop', 'select-template', 'toggle-category', 'select-file'])

const groupedDynamicModels = computed(() => {
  const groups = {}
  for (const m of props.dynamicModels) {
    if (!groups[m.provider_name]) {
      groups[m.provider_name] = { provider: m.provider_name, models: [] }
    }
    groups[m.provider_name].models.push(m)
  }
  return Object.values(groups)
})

function getFileIcon(filePath) {
  const ext = filePath.split('.').pop().toLowerCase()
  const iconMap = { vue: '文件', jsx: 'React', tsx: 'React', js: 'JS', ts: 'TS', py: 'Python', java: 'Java', go: 'Go', html: 'HTML', css: 'CSS', json: 'JSON', md: 'MD' }
  return iconMap[ext] || '文件'
}

function getFileName(filePath) {
  return filePath.split('/').pop()
}
</script>

<style scoped>
.model-selector {
  margin: 8px 0 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.model-selector-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
}
.model-select {
  padding: 6px 8px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 13px;
  background: #fff;
  cursor: pointer;
}
.model-select:hover { border-color: #409eff; }
.model-select:focus { border-color: #409eff; outline: none; }
</style>
