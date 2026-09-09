<template>
  <div
    class="tooltip-wrapper"
    :class="positionClass"
    @mouseenter="show"
    @mouseleave="hide"
    @focus="show"
    @blur="hide"
  >
    <div ref="triggerRef" class="tooltip-trigger">
      <slot />
    </div>
    <Teleport to="body">
      <transition name="tooltip-fade">
        <div
          v-if="isVisible"
          ref="tooltipRef"
          class="tooltip-content"
          :class="positionClass"
          :style="tooltipStyle"
          role="tooltip"
        >
          {{ content }}
          <div class="tooltip-arrow" :class="arrowClass"></div>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<script setup>
  import { ref, computed, nextTick, onUnmounted } from 'vue'

  const props = defineProps({
    content: { type: String, required: true },
    position: {
      type: String,
      default: 'top',
      validator: v => ['top', 'bottom', 'left', 'right'].includes(v)
    },
    delay: { type: Number, default: 200 }
  })

  const isVisible = ref(false)
  const triggerRef = ref(null)
  const tooltipRef = ref(null)
  const tooltipStyle = ref({})
  let showTimer = null
  let hideTimer = null

  const positionClass = computed(() => `tooltip-${props.position}`)
  const arrowClass = computed(() => `arrow-${props.position}`)

  const show = () => {
    clearTimeout(hideTimer)
    showTimer = setTimeout(async () => {
      isVisible.value = true
      await nextTick()
      updatePosition()
    }, props.delay)
  }

  const hide = () => {
    clearTimeout(showTimer)
    hideTimer = setTimeout(() => {
      isVisible.value = false
    }, 100)
  }

  const updatePosition = () => {
    if (!triggerRef.value || !tooltipRef.value) return

    const triggerRect = triggerRef.value.getBoundingClientRect()
    const tooltipRect = tooltipRef.value.getBoundingClientRect()
    const gap = 8

    let top, left

    switch (props.position) {
      case 'top':
        top = triggerRect.top - tooltipRect.height - gap
        left = triggerRect.left + (triggerRect.width - tooltipRect.width) / 2
        break
      case 'bottom':
        top = triggerRect.bottom + gap
        left = triggerRect.left + (triggerRect.width - tooltipRect.width) / 2
        break
      case 'left':
        top = triggerRect.top + (triggerRect.height - tooltipRect.height) / 2
        left = triggerRect.left - tooltipRect.width - gap
        break
      case 'right':
        top = triggerRect.top + (triggerRect.height - tooltipRect.height) / 2
        left = triggerRect.right + gap
        break
    }

    tooltipStyle.value = { top: `${top}px`, left: `${left}px` }
  }

  onUnmounted(() => {
    if (showTimer) clearTimeout(showTimer)
    if (hideTimer) clearTimeout(hideTimer)
    showTimer = null
    hideTimer = null
  })
</script>

<style scoped>
  .tooltip-wrapper {
    display: inline-block;
    position: relative;
  }

  .tooltip-trigger {
    cursor: pointer;
  }

  .tooltip-content {
    position: fixed;
    z-index: 9999;
    padding: var(--spacing-1, 4px) var(--spacing-2, 8px);
    background: var(--color-slate-800, #1e293b);
    color: var(--color-slate-50, #f8fafc);
    font-size: var(--text-xs, 12px);
    line-height: 1.4;
    border-radius: var(--radius-sm, 6px);
    white-space: nowrap;
    pointer-events: none;
    box-shadow: var(--shadow-md, 0 4px 6px -1px rgba(0, 0, 0, 0.1));
  }

  .tooltip-arrow {
    position: absolute;
    width: 6px;
    height: 6px;
    background: inherit;
  }

  .arrow-top {
    bottom: -3px;
    left: 50%;
    transform: translateX(-50%) rotate(45deg);
  }

  .arrow-bottom {
    top: -3px;
    left: 50%;
    transform: translateX(-50%) rotate(45deg);
  }

  .arrow-left {
    right: -3px;
    top: 50%;
    transform: translateY(-50%) rotate(45deg);
  }

  .arrow-right {
    left: -3px;
    top: 50%;
    transform: translateY(-50%) rotate(45deg);
  }

  .tooltip-fade-enter-active,
  .tooltip-fade-leave-active {
    transition: opacity var(--transition-fast, 150ms);
  }

  .tooltip-fade-enter-from,
  .tooltip-fade-leave-to {
    opacity: 0;
  }
</style>
