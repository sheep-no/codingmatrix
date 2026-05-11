<template>
  <div class="agent-file-tree">
    <div class="tree-header">
      <h4>项目文件</h4>
      <div class="tree-actions">
        <button class="btn-icon-sm" title="刷新" @click="$emit('refresh')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
        </button>
        <button class="btn-icon-sm" title="下载项目" @click="$emit('download')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
        </button>
      </div>
    </div>

    <div class="tree-content">
      <div
        v-for="item in flatTree"
        :key="item.path"
        :class="['tree-item', { active: item.path === activePath, 'is-folder': item.isFolder }]"
        :style="{ paddingLeft: item.depth * 16 + 12 + 'px' }"
        @click="handleClick(item)"
      >
        <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <template v-if="item.isFolder">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </template>
          <template v-else>
            <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
            <polyline points="13 2 13 9 20 9"/>
          </template>
        </svg>
        <span class="file-name">{{ item.name }}</span>
        <button
          v-if="!item.isFolder"
          class="btn-delete-file"
          title="删除文件"
          @click.stop="$emit('delete', item.path)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <div v-if="flatTree.length === 0" class="empty-state">
        暂无文件
      </div>
    </div>

    <div v-if="fileCount" class="tree-footer">
      {{ fileCount }} 个文件, {{ folderCount }} 个目录
    </div>
  </div>
</template>

<script setup>
  import { computed } from 'vue'

  const props = defineProps({
    files: { type: Array, default: () => [] },
    activePath: { type: String, default: '' }
  })

  defineEmits(['select', 'delete', 'refresh', 'download'])

  const flatTree = computed(() => {
    const result = []
    function flatten(items, depth = 0) {
      for (const item of items) {
        result.push({ ...item, depth })
        if (item.children) flatten(item.children, depth + 1)
      }
    }
    flatten(props.files)
    return result
  })

  const fileCount = computed(() => props.files.filter(f => !f.isFolder).length)
  const folderCount = computed(() => props.files.filter(f => f.isFolder).length)

  function handleClick(item) {
    if (!item.isFolder) {
      const emit = defineEmits(['select', 'delete', 'refresh', 'download'])
      emit('select', item.path)
    }
  }
</script>

<style scoped>
  .agent-file-tree {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-secondary, #16213e);
    border-right: 1px solid var(--border-color, #2d3748);
  }

  .tree-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
  }

  .tree-header h4 { margin: 0; font-size: 14px; }

  .tree-actions { display: flex; gap: 4px; }

  .btn-icon-sm {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
  }

  .btn-icon-sm:hover { background: var(--bg-hover, #374151); }
  .btn-icon-sm svg { width: 14px; height: 14px; }

  .tree-content { flex: 1; overflow-y: auto; padding: 8px 0; }

  .tree-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    cursor: pointer;
    transition: background 0.15s;
    font-size: 13px;
  }

  .tree-item:hover { background: var(--bg-hover, #374151); }
  .tree-item.active { background: var(--accent-muted, #4f46e533); color: var(--accent-color, #4f46e5); }

  .file-icon { width: 16px; height: 16px; flex-shrink: 0; opacity: 0.7; }
  .is-folder .file-icon { opacity: 1; }
  .file-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .btn-delete-file {
    display: none;
    width: 20px;
    height: 20px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    flex-shrink: 0;
  }

  .tree-item:hover .btn-delete-file { display: flex; align-items: center; justify-content: center; }
  .btn-delete-file:hover { background: #ef444422; color: #ef4444; }
  .btn-delete-file svg { width: 12px; height: 12px; }

  .tree-footer {
    padding: 8px 16px;
    font-size: 11px;
    color: var(--text-secondary, #9ca3af);
    border-top: 1px solid var(--border-color, #2d3748);
  }

  .empty-state {
    text-align: center;
    padding: 40px 16px;
    color: var(--text-secondary, #9ca3af);
    font-size: 13px;
  }
</style>
