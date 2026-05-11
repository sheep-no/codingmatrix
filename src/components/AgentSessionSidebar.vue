<template>
  <div class="agent-session-sidebar">
    <div class="sidebar-header">
      <h4>会话</h4>
      <button class="btn-icon" title="新建会话" @click="$emit('create')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19"/>
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
      </button>
    </div>

    <div class="session-list">
      <div
        v-for="session in sessions"
        :key="session.session_id"
        :class="['session-item', { active: session.session_id === activeId }]"
        @click="$emit('select', session)"
      >
        <div class="session-icon">
          <svg v-if="session.session_type === 'react'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 16v-4"/>
            <path d="M12 8h.01"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <div class="session-info">
          <span class="session-name">{{ session.session_type === 'react' ? 'ReAct' : '标准' }}</span>
          <span class="session-model">{{ formatModel(session.model_key) }}</span>
        </div>
        <span class="session-time">{{ formatTime(session.created_at) }}</span>
        <button
          v-if="showDelete"
          class="btn-delete"
          title="删除会话"
          @click.stop="$emit('delete', session.session_id)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          </svg>
        </button>
      </div>

      <div v-if="sessions.length === 0" class="empty-state">
        暂无会话，点击 + 新建
      </div>
    </div>
  </div>
</template>

<script setup>
  defineProps({
    sessions: { type: Array, default: () => [] },
    activeId: { type: String, default: '' },
    showDelete: { type: Boolean, default: true }
  })

  defineEmits(['create', 'select', 'delete'])

  function formatModel(key) {
    const map = {
      'deepseek-r1-qwen3-8b': 'DeepSeek R1',
      'qwen3-8b': 'Qwen 3',
      'qwen2.5-7b': 'Qwen 2.5',
      'glm-z1-9b': 'GLM-Z1',
      'glm-4-9b': 'GLM-4'
    }
    return map[key] || key?.split('/').pop()?.split('-').slice(0, 2).join('-') || '默认'
  }

  function formatTime(ts) {
    if (!ts) return ''
    const d = new Date(ts)
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }
</script>

<style scoped>
  .agent-session-sidebar {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-secondary, #16213e);
    border-right: 1px solid var(--border-color, #2d3748);
  }

  .sidebar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
  }

  .sidebar-header h4 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
  }

  .btn-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 6px;
    background: var(--accent-color, #4f46e5);
    color: white;
    cursor: pointer;
  }

  .btn-icon svg { width: 16px; height: 16px; }

  .session-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  .session-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s;
  }

  .session-item:hover { background: var(--bg-hover, #374151); }
  .session-item.active { background: var(--accent-muted, #4f46e533); border-left: 3px solid var(--accent-color, #4f46e5); }

  .session-icon {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: var(--bg-tertiary, #1f2937);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .session-icon svg { width: 16px; height: 16px; color: var(--text-secondary, #9ca3af); }

  .session-info { flex: 1; min-width: 0; }
  .session-name { display: block; font-size: 13px; font-weight: 500; }
  .session-model { display: block; font-size: 11px; color: var(--text-secondary, #9ca3af); }
  .session-time { font-size: 11px; color: var(--text-secondary, #9ca3af); flex-shrink: 0; }

  .btn-delete {
    display: none;
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
  }

  .session-item:hover .btn-delete { display: flex; align-items: center; justify-content: center; }
  .btn-delete:hover { background: #ef444422; color: #ef4444; }
  .btn-delete svg { width: 14px; height: 14px; }

  .empty-state {
    text-align: center;
    padding: 40px 16px;
    color: var(--text-secondary, #9ca3af);
    font-size: 13px;
  }
</style>
