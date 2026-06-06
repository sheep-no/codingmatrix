<template>
  <div class="agent-sidebar">
    <!-- 会话历史 -->
    <div class="sidebar-section">
      <div class="section-header">
        <span class="section-title">会话历史</span>
        <button class="section-btn" title="新建会话" @click="$emit('new-session')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>
      </div>
      <div class="session-list">
        <div
          v-for="session in sessions"
          :key="session.id"
          class="session-item"
          :class="{ active: sessionId === session.id }"
          @click="$emit('switch-session', session.id)"
        >
          <div class="session-info">
            <span class="session-mode">{{ getModeLabel(session.mode) }}</span>
            <span class="session-meta">{{ session.filesCount }} 文件</span>
          </div>
          <div class="session-time">{{ formatTime(session.timestamp) }}</div>
          <button class="session-delete" title="删除" @click.stop="$emit('delete-session', session.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div v-if="sessions.length === 0" class="session-empty">暂无会话</div>
      </div>
    </div>

    <!-- 项目文件 -->
    <div v-if="hasFiles" class="sidebar-section sidebar-files">
      <div class="section-header">
        <span class="section-title">项目文件</span>
        <span class="file-count">{{ fileCount }}</span>
      </div>
      <div class="file-filter">
        <input
          :value="searchQuery"
          type="text"
          placeholder="搜索文件..."
          class="file-search"
          @input="$emit('update:searchQuery', $event.target.value)"
        />
      </div>
      <div class="file-tree">
        <div
          v-for="item in flatTreeItems"
          :key="item.id"
          class="tree-item"
          :class="{ selected: selectedPath === item.path, 'is-category': item.isCategory }"
        >
          <div v-if="item.isCategory" class="category-header" @click="$emit('toggle-category', item.categoryName)">
            <span class="category-icon">{{ item.icon }}</span>
            <span class="category-name">{{ item.name }}</span>
            <span class="category-count">({{ item.count }})</span>
            <span class="expand-icon">{{ item.expanded ? '▼' : '▶' }}</span>
          </div>
          <div v-else v-show="item.visible" class="file-item" @click="$emit('select-file', { path: item.path })">
            <span class="file-icon">{{ getFileIcon(item.path) }}</span>
            <span class="file-name">{{ getFileName(item.path) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  sessionId: { type: String, default: '' },
  sessions: { type: Array, default: () => [] },
  hasFiles: { type: Boolean, default: false },
  fileCount: { type: Number, default: 0 },
  categories: { type: Array, default: () => [] },
  searchQuery: { type: String, default: '' },
  selectedPath: { type: String, default: '' }
})

defineEmits(['new-session', 'switch-session', 'delete-session', 'update:searchQuery', 'toggle-category', 'select-file'])

const flatTreeItems = computed(() => {
  const items = []
  for (const category of props.categories) {
    const categoryFiles = category.files?.value ?? category.files ?? []
    items.push({
      id: `cat-${category.name}`,
      isCategory: true,
      categoryName: category.name,
      name: category.name,
      icon: category.icon,
      count: categoryFiles.length,
      expanded: category.expanded
    })
    if (category.expanded) {
      for (const file of categoryFiles) {
        items.push({
          id: `file-${file.path}`,
          isCategory: false,
          path: file.path,
          visible: true
        })
      }
    }
  }
  return items
})

function getModeLabel(mode) {
  return mode === 'create' ? '新建' : mode === 'modify' ? '修改' : '调试'
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const diff = Date.now() - timestamp
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return new Date(timestamp).toLocaleDateString()
}

function getFileIcon(filePath) {
  const ext = filePath.split('.').pop().toLowerCase()
  const iconMap = { vue: '📄', jsx: '⚛', tsx: '⚛', js: '📜', ts: '📜', py: '🐍', java: '☕', go: '🔵', html: '🌐', css: '🎨', json: '📋', md: '📝' }
  return iconMap[ext] || '📄'
}

function getFileName(filePath) {
  return filePath.split('/').pop()
}
</script>

<style scoped>
.agent-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.sidebar-section {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.sidebar-files {
  flex: 1;
  overflow: hidden;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.section-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.section-btn:hover { background: var(--bg-secondary); color: var(--primary); }
.file-count {
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-secondary);
  padding: 2px 6px;
  border-radius: 4px;
}

/* 会话列表 */
.session-list {
  overflow-y: auto;
  max-height: 200px;
}
.session-item {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s;
  gap: 8px;
}
.session-item:hover { background: var(--bg-secondary); }
.session-item.active { background: color-mix(in srgb, var(--primary), transparent 90%); }
.session-info {
  flex: 1;
  min-width: 0;
}
.session-mode {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-meta {
  font-size: 11px;
  color: var(--text-tertiary);
}
.session-time {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
}
.session-delete {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  border-radius: 4px;
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s;
}
.session-item:hover .session-delete { opacity: 1; }
.session-delete:hover { background: color-mix(in srgb, var(--danger), transparent 90%); color: var(--danger); }
.session-empty {
  padding: 16px;
  text-align: center;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 文件树 */
.file-filter {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
}
.file-search {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 12px;
  background: var(--bg-primary);
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.15s;
}
.file-search:focus { border-color: var(--primary); }
.file-tree {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}
.tree-item {
  min-height: 28px;
  display: flex;
  align-items: center;
}
.tree-item.is-category { font-weight: 500; cursor: pointer; }
.category-header {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  width: 100%;
  font-size: 12px;
  color: var(--text-secondary);
}
.category-header:hover { background: var(--bg-secondary); }
.category-icon { font-size: 12px; }
.category-name { flex: 1; }
.category-count { font-size: 11px; color: var(--text-tertiary); }
.expand-icon { font-size: 10px; color: var(--text-tertiary); }
.file-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px 4px 24px;
  cursor: pointer;
  width: 100%;
  font-size: 12px;
  color: var(--text-secondary);
  transition: background 0.15s;
}
.file-item:hover { background: var(--bg-secondary); }
.file-item.selected { background: color-mix(in srgb, var(--primary), transparent 90%); color: var(--primary); }
.file-icon { font-size: 12px; }
.file-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
