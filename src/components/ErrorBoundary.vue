<script setup>
  import { ref, onErrorCaptured, computed } from 'vue'

  const props = defineProps({
    componentName: {
      type: String,
      default: '组件'
    }
  })

  const emit = defineEmits(['error', 'retry'])

  const error = ref(null)
  const showError = ref(false)
  const isDev = computed(() => import.meta.env.DEV)

  onErrorCaptured((err, instance, info) => {
    error.value = err
    showError.value = true

    // 开发环境下打印详细错误
    if (isDev.value) {
      console.error(`[ErrorBoundary] ${props.componentName} 捕获到错误:`, err)
      console.error(`[ErrorBoundary] 错误信息:`, info)
    }

    emit('error', { error: err, info, component: props.componentName })

    // 阻止错误继续向上传播
    return false
  })

  const handleRetry = () => {
    error.value = null
    showError.value = false
    emit('retry')
  }
</script>

<template>
  <div v-if="showError" class="error-boundary-fallback">
    <div class="error-content">
      <div class="error-icon">⚠️</div>
      <h3>{{ componentName }} 加载失败</h3>
      <p v-if="isDev" class="error-message">
        {{ error?.message || '未知错误' }}
      </p>
      <p v-else class="error-message">组件渲染时发生错误，请尝试刷新页面</p>
      <div class="error-actions">
        <button class="retry-btn" @click="handleRetry">重试</button>
        <button class="refresh-btn" @click="() => window.location.reload()">刷新页面</button>
      </div>
    </div>
  </div>
  <slot v-else />
</template>

<style scoped>
  .error-boundary-fallback {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 200px;
    padding: 2rem;
    background: var(--color-bg-tertiary, #f5f5f5);
    border-radius: 8px;
    border: 1px solid var(--color-border, #e0e0e0);
  }

  .error-content {
    text-align: center;
    max-width: 400px;
  }

  .error-icon {
    font-size: 3rem;
    margin-bottom: 1rem;
  }

  h3 {
    color: var(--color-text-primary, #333);
    margin: 0 0 0.5rem;
    font-size: 1.25rem;
  }

  .error-message {
    color: var(--color-text-secondary, #666);
    margin: 0 0 1.5rem;
    font-size: 0.875rem;
    word-break: break-word;
    background: var(--color-bg-secondary, #fff);
    padding: 0.75rem;
    border-radius: 4px;
    font-family: monospace;
  }

  .error-actions {
    display: flex;
    gap: 0.75rem;
    justify-content: center;
  }

  .retry-btn,
  .refresh-btn {
    padding: 0.5rem 1.25rem;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .retry-btn {
    background: var(--color-primary, #0066ff);
    color: white;
  }

  .retry-btn:hover {
    background: var(--color-primary-hover, #0052cc);
  }

  .refresh-btn {
    background: var(--color-bg-secondary, #fff);
    color: var(--color-text-primary, #333);
    border: 1px solid var(--color-border, #e0e0e0);
  }

  .refresh-btn:hover {
    background: var(--color-bg-hover, #f0f0f0);
  }
</style>
