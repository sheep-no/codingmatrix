<script setup>
  import { onMounted, onBeforeUnmount, ref } from 'vue'
  import { initTheme } from '@/utils/theme'
  import ErrorBoundary from '@/components/ErrorBoundary.vue'
  import AppLoading from '@/components/AppLoading.vue'

  const isLoading = ref(true)
  const initializationStatus = ref('loading')
  const initializationError = ref('')
  const appLoadingRef = ref(null)

  const initialize = async (isRetry = false) => {
    initializationStatus.value = 'loading'
    initializationError.value = ''
    initTheme()
    try {
      const initialization = isRetry && window.__retryAppInitialization
        ? window.__retryAppInitialization()
        : window.__appInitialization
      await (initialization || Promise.resolve())
      initializationStatus.value = 'ready'
      isLoading.value = false
    } catch (error) {
      initializationStatus.value = 'error'
      initializationError.value = error?.message || '应用初始化失败，请重试。'
    }
  }

  onMounted(() => initialize())
  onBeforeUnmount(() => appLoadingRef.value?.reset())
</script>

<template>
  <div id="app" class="app-container" role="application" aria-label="AI 助手应用">
    <AppLoading
      ref="appLoadingRef"
      :visible="isLoading"
      :status="initializationStatus"
      :error="initializationError"
      @retry="initialize"
    />
    <ErrorBoundary component-name="主应用">
      <router-view />
    </ErrorBoundary>
  </div>
</template>

<style scoped>
  .app-container {
    width: 100%;
    height: 100vh;
    background: var(--bg-secondary);
    background: var(--gradient-bg);
    overflow: hidden;
  }
</style>
