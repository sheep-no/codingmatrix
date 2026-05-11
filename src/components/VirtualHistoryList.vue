<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import HistoryItem from './HistoryItem.vue'

const props = defineProps({
  items: { type: Array, required: true },
  activeId: { type: [Number, String, null], default: null },
  isLoading: { type: Boolean, default: false },
  searchKeyword: { type: String, default: '' },
  estimatedItemHeight: { type: Number, default: 48 },
  loadMoreThreshold: { type: Number, default: 5 }
})

const emit = defineEmits(['select', 'loadMore'])

const containerRef = ref(null)
const scrollTop = ref(0)
const containerHeight = ref(0)
const isScrollingToBottom = ref(false)

const totalHeight = computed(() => props.items.length * props.estimatedItemHeight)

const visibleRange = computed(() => {
  const start = Math.floor(scrollTop.value / props.estimatedItemHeight)
  const visibleCount = Math.ceil(containerHeight.value / props.estimatedItemHeight)
  const buffer = 5
  const startIndex = Math.max(0, start - buffer)
  const endIndex = Math.min(props.items.length, start + visibleCount + buffer)
  return { startIndex, endIndex }
})

const visibleItems = computed(() => {
  const { startIndex, endIndex } = visibleRange.value
  return props.items.slice(startIndex, endIndex).map((item, index) => ({
    ...item,
    _virtualIndex: startIndex + index,
    _top: (startIndex + index) * props.estimatedItemHeight
  }))
})

const spacerTop = computed(() => visibleRange.value.startIndex * props.estimatedItemHeight)
const spacerBottom = computed(
  () => totalHeight.value - (visibleRange.value.endIndex * props.estimatedItemHeight)
)

const handleScroll = () => {
  if (!containerRef.value) return
  scrollTop.value = containerRef.value.scrollTop

  const { scrollTop: st, scrollHeight, clientHeight } = containerRef.value
  if (scrollHeight - st - clientHeight < props.loadMoreThreshold * props.estimatedItemHeight) {
    if (!props.isLoading && !isScrollingToBottom.value) {
      emit('loadMore')
    }
  }
}

const handleResize = () => {
  if (containerRef.value) {
    containerHeight.value = containerRef.value.clientHeight
  }
}

const scrollToBottom = async () => {
  if (!containerRef.value) return
  isScrollingToBottom.value = true
  await nextTick()
  containerRef.value.scrollTop = containerRef.value.scrollHeight
  setTimeout(() => {
    isScrollingToBottom.value = false
  }, 100)
}

const handleSelect = item => {
  emit('select', item)
}

defineExpose({ scrollToBottom })

onMounted(() => {
  handleResize()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

watch(
  () => props.items.length,
  (newLen, oldLen) => {
    if (newLen > oldLen && oldLen > 0 && containerRef.value) {
      const { scrollTop: st, scrollHeight, clientHeight } = containerRef.value
      const isNearBottom = scrollHeight - st - clientHeight < 200
      if (isNearBottom) {
        scrollToBottom()
      }
    }
  }
)
</script>

<template>
  <div ref="containerRef" class="virtual-list-container" @scroll="handleScroll">
    <div class="virtual-list-spacer-top" :style="{ height: `${spacerTop}px` }"></div>
    <div
      v-for="item in visibleItems"
      :key="item.id"
      class="virtual-list-item"
      :style="{
        height: `${estimatedItemHeight}px`,
        transform: `translateY(${item._top}px)`
      }"
    >
      <HistoryItem
        :item="item"
        :is-active="item.id === activeId"
        :search-keyword="searchKeyword"
        @select="handleSelect"
      />
    </div>
    <div class="virtual-list-spacer-bottom" :style="{ height: `${spacerBottom}px` }"></div>
    <div v-if="isLoading" class="virtual-list-loading">
      <span>加载中...</span>
    </div>
  </div>
</template>

<style scoped>
.virtual-list-container {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  position: relative;
  padding-right: 2px;
}

.virtual-list-spacer-top,
.virtual-list-spacer-bottom {
  width: 100%;
}

.virtual-list-item {
  position: absolute;
  left: 0;
  right: 0;
  width: 100%;
}

.virtual-list-loading {
  text-align: center;
  padding: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
