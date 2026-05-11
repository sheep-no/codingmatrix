<template>
  <div class="loading-spinner" :class="[`size-${size}`, `color-${color}`]">
    <svg class="spinner-svg" viewBox="0 0 24 24" :width="spinnerSize" :height="spinnerSize">
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        stroke-width="3"
        fill="none"
        :stroke-dasharray="dashArray"
        :stroke-dashoffset="dashOffset"
      />
    </svg>
    <span v-if="text" class="spinner-text">{{ text }}</span>
  </div>
</template>

<script setup>
  import { computed } from 'vue'

  const props = defineProps({
    size: {
      type: String,
      default: 'md',
      validator: v => ['sm', 'md', 'lg'].includes(v)
    },
    color: {
      type: String,
      default: 'primary',
      validator: v => ['primary', 'success', 'warning', 'danger', 'white'].includes(v)
    },
    text: {
      type: String,
      default: ''
    }
  })

  const spinnerSize = computed(() => {
    const sizes = { sm: '16px', md: '24px', lg: '32px' }
    return sizes[props.size]
  })

  const dashArray = computed(() => {
    const arrays = { sm: '31.4 31.4', md: '31.4 31.4', lg: '31.4 31.4' }
    return arrays[props.size]
  })

  const dashOffset = computed(() => {
    const offsets = { sm: '0', md: '0', lg: '0' }
    return offsets[props.size]
  })
</script>

<style scoped>
  .loading-spinner {
    display: inline-flex;
    align-items: center;
    gap: var(--spacing-2, 8px);
  }

  .spinner-svg {
    animation: spin 1s linear infinite;
  }

  .spinner-text {
    font-size: var(--text-sm, 13px);
    color: inherit;
    opacity: 0.8;
  }

  .size-sm .spinner-text {
    font-size: var(--text-xs, 12px);
  }
  .size-lg .spinner-text {
    font-size: var(--text-base, 14px);
  }

  .color-primary {
    color: var(--primary-500, #3b82f6);
  }
  .color-success {
    color: var(--color-success-500, #10b981);
  }
  .color-warning {
    color: var(--color-warning-500, #f59e0b);
  }
  .color-danger {
    color: var(--color-danger-500, #ef4444);
  }
  .color-white {
    color: #ffffff;
  }

  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
</style>
