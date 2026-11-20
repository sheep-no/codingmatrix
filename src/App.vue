<script setup>
  import { onMounted, onBeforeUnmount, ref } from 'vue'
  import { initTheme } from '@/utils/theme'
  import { useToast } from '@/composables/useToast'
  import ErrorBoundary from '@/components/ErrorBoundary.vue'
  import AppLoading from '@/components/AppLoading.vue'

  const isLoading = ref(true)
  const initializationStatus = ref('loading')
  const initializationError = ref('')
  const appLoadingRef = ref(null)
  const { error: showError } = useToast()

  // 初始化兜底超时：任何依赖挂起都不能让全屏遮罩永久拦截交互。
  const INIT_TIMEOUT_MS = 10000
  let initializeAttempt = 0

  const handleSessionExpired = (event) => {
    showError(event?.detail?.message || '会话已过期，请重新登录')
  }

  const initialize = async (isRetry = false) => {
    const attempt = ++initializeAttempt
    isLoading.value = true
    initializationStatus.value = 'loading'
    initializationError.value = ''
    initTheme()
    let timer = null
    try {
      const initialization = isRetry && window.__retryAppInitialization
        ? window.__retryAppInitialization()
        : window.__appInitialization
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('应用初始化超时，请重试')), INIT_TIMEOUT_MS)
      })
      await Promise.race([Promise.resolve(initialization || undefined), timeout])
      if (attempt !== initializeAttempt) return
      initializationStatus.value = 'ready'
      isLoading.value = false
    } catch (error) {
      if (attempt !== initializeAttempt) return
      initializationStatus.value = 'error'
      initializationError.value = error?.message || '应用初始化失败，请重试。'
      // 失败时必须卸载遮罩，否则它会吞掉页面所有点击，用户无法重新登录或切换账号。
      isLoading.value = false
      showError(initializationError.value)
    } finally {
      if (timer) clearTimeout(timer)
    }
  }

  onMounted(() => {
    initialize()
    window.addEventListener('session-expired', handleSessionExpired)
  })
  onBeforeUnmount(() => {
    appLoadingRef.value?.reset()
    window.removeEventListener('session-expired', handleSessionExpired)
  })
</script>

<template>
  <div id="app" class="app-container" role="application" aria-label="CodingMatrix">
    <AppLoading
      ref="appLoadingRef"
      :visible="isLoading"
      :status="initializationStatus"
      :error="initializationError"
      @retry="initialize(true)"
    />
    <ErrorBoundary component-name="主应用">
      <router-view />
    </ErrorBoundary>
  </div>
</template>

<style scoped>
  .app-container {
    width: 100%;
    height: 100dvh;
    background: var(--gradient-bg, var(--bg-secondary));
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
</style>
