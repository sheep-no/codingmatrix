<template>
  <article ref="element" class="message-wrapper" :aria-label="label">
    <slot />
  </article>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({
  message: { type: Object, required: true },
  itemKey: { type: [String, Number], required: true }
})

const emit = defineEmits(['resize'])
const element = ref(null)
let resizeObserver = null

function reportHeight() {
  const height = element.value?.getBoundingClientRect().height
  if (height > 0) emit('resize', { key: props.itemKey, height })
}

onMounted(async () => {
  await nextTick()
  reportHeight()
  if (typeof ResizeObserver === 'function') {
    resizeObserver = new ResizeObserver(entries => {
      const height = entries[0]?.borderBoxSize?.[0]?.blockSize || entries[0]?.contentRect?.height
      if (height > 0) emit('resize', { key: props.itemKey, height })
    })
    resizeObserver.observe(element.value)
  }
})

onUnmounted(() => resizeObserver?.disconnect())

const label = computed(() => {
  if (props.message.isStreaming) return 'AI 正在回复中'
  return props.message.prompt ? '用户消息' : 'AI 回复'
})
</script>

<style scoped>
.message-wrapper { margin-bottom: 24px; }
</style>
