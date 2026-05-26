<script setup>
  import { computed } from 'vue'

  const props = defineProps({
    item: { type: Object, required: true },
    isActive: { type: Boolean, default: false },
    searchKeyword: { type: String, default: '' }
  })

  const emit = defineEmits(['select', 'delete'])

  const displayTitle = computed(() => {
    const text = props.item.title || props.item.prompt?.slice(0, 30) || ''
    if (!props.searchKeyword) return text
    return highlightText(text, props.searchKeyword)
  })

  function highlightText(text, keyword) {
    if (!keyword) return text
    const regex = new RegExp(`(${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
    return text.replace(regex, '<mark>$1</mark>')
  }

  function handleClick() {
    emit('select', props.item)
  }

  function handleDelete(event) {
    event.stopPropagation()
    emit('delete', props.item)
  }
</script>

<template>
  <li class="history-item" :class="{ active: isActive }" @click="handleClick">
    <span class="icon-svg-sm">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
      </svg>
    </span>
    <span class="item-text" v-html="displayTitle"></span>
    <button
      class="delete-btn"
      aria-label="删除会话"
      title="删除会话"
      @click="handleDelete"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="3 6 5 6 21 6"></polyline>
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
        <line x1="10" y1="11" x2="10" y2="17"></line>
        <line x1="14" y1="11" x2="14" y2="17"></line>
      </svg>
    </button>
  </li>
</template>

<style scoped>
  .history-item {
    position: relative;
  }

  .delete-btn {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    opacity: 0;
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    color: var(--text-secondary);
    transition: all 0.2s;
  }

  .delete-btn:hover {
    background: var(--bg-hover);
    color: var(--error);
  }

  .delete-btn svg {
    width: 14px;
    height: 14px;
  }

  .history-item:hover .delete-btn {
    opacity: 1;
  }

  .history-item.active .delete-btn {
    opacity: 1;
  }
</style>
