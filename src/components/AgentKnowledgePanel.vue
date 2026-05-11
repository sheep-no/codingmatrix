<template>
  <div class="agent-knowledge-panel">
    <div class="panel-header">
      <h4>知识库</h4>
      <button class="btn-icon-sm" title="刷新" @click="loadKnowledge">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
      </button>
    </div>

    <div class="knowledge-list">
      <div v-for="item in items" :key="item.id" class="knowledge-item">
        <div class="item-content">{{ item.content }}</div>
        <div class="item-meta">
          <span class="badge">{{ item.category || '通用' }}</span>
          <span class="usage">使用 {{ item.usage_count || 0 }} 次</span>
          <button class="btn-delete" title="删除" @click="$emit('delete', item.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>

      <div v-if="items.length === 0" class="empty-state">
        暂无知识条目
      </div>
    </div>

    <div class="add-knowledge">
      <input
        v-model="newContent"
        placeholder="添加新知识..."
        class="input-field"
        @keydown.enter="addKnowledge"
      />
      <select v-model="newCategory" class="select-field">
        <option value="general">通用</option>
        <option value="code">代码</option>
        <option value="config">配置</option>
        <option value="api">API</option>
      </select>
      <button :disabled="!newContent.trim() || loading" class="btn-add" @click="addKnowledge">
        {{ loading ? '...' : '添加' }}
      </button>
    </div>
  </div>
</template>

<script setup>
  import { ref } from 'vue'

  const props = defineProps({
    items: { type: Array, default: () => [] }
  })

  const emit = defineEmits(['add', 'delete', 'refresh'])

  const newContent = ref('')
  const newCategory = ref('general')
  const loading = ref(false)

  async function loadKnowledge() {
    emit('refresh')
  }

  async function addKnowledge() {
    if (!newContent.value.trim() || loading.value) return
    loading.value = true
    emit('add', {
      content: newContent.value.trim(),
      category: newCategory.value
    })
    newContent.value = ''
    loading.value = false
  }
</script>

<style scoped>
  .agent-knowledge-panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-secondary, #16213e);
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
  }

  .panel-header h4 { margin: 0; font-size: 14px; }

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

  .knowledge-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  .knowledge-item {
    padding: 12px;
    border-radius: 8px;
    background: var(--bg-tertiary, #1f2937);
    margin-bottom: 8px;
  }

  .item-content {
    font-size: 13px;
    line-height: 1.5;
    margin-bottom: 8px;
    white-space: pre-wrap;
  }

  .item-meta {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .badge {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    background: var(--accent-color, #4f46e5);
    color: white;
  }

  .usage { font-size: 11px; color: var(--text-secondary, #9ca3af); }

  .btn-delete {
    margin-left: auto;
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-delete:hover { background: #ef444422; color: #ef4444; }
  .btn-delete svg { width: 14px; height: 14px; }

  .empty-state {
    text-align: center;
    padding: 40px 16px;
    color: var(--text-secondary, #9ca3af);
    font-size: 13px;
  }

  .add-knowledge {
    display: flex;
    gap: 8px;
    padding: 12px;
    border-top: 1px solid var(--border-color, #2d3748);
  }

  .input-field {
    flex: 1;
    padding: 8px 12px;
    border-radius: 6px;
    border: 1px solid var(--border-color, #2d3748);
    background: var(--bg-tertiary, #1f2937);
    color: var(--text-primary, #e0e0e0);
    font-size: 13px;
  }

  .input-field:focus { outline: none; border-color: var(--accent-color, #4f46e5); }

  .select-field {
    padding: 8px;
    border-radius: 6px;
    border: 1px solid var(--border-color, #2d3748);
    background: var(--bg-tertiary, #1f2937);
    color: var(--text-primary, #e0e0e0);
    font-size: 13px;
  }

  .btn-add {
    padding: 8px 16px;
    border-radius: 6px;
    border: none;
    background: var(--accent-color, #4f46e5);
    color: white;
    font-size: 13px;
    cursor: pointer;
    white-space: nowrap;
  }

  .btn-add:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
