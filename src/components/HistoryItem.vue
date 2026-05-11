<script setup>
  import { computed } from 'vue'

  const props = defineProps({
    item: { type: Object, required: true },
    isActive: { type: Boolean, default: false },
    searchKeyword: { type: String, default: '' }
  })

  const emit = defineEmits(['select'])

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
</script>

<template>
  <li class="history-item" :class="{ active: isActive }" @click="handleClick">
    <span class="icon-svg-sm">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
      </svg>
    </span>
    <span class="item-text" v-html="displayTitle"></span>
  </li>
</template>
