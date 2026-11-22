<script setup>
  import { onMounted, onBeforeUnmount, ref } from 'vue'
  import { initTheme } from '@/utils/theme'
  import { useToast } from '@/composables/useToast'
  import ErrorBoundary from '@/components/ErrorBoundary.vue'
  import AppLoading from '@/components/AppLoading.vue'

  // 同一标签页只展示一次首屏遮罩：sessionStorage 在整页重载后仍然保留，
  // 因此即使外部因素反复 reload，也不会每次都用遮罩吞掉用户第一次点击。
  const INITIALIZED_FLAG = 'app-initialized'
  const hasInitialized = (() => {
    try {
      return sessionStorage.getItem(INITIALIZED_FLAG) === '1'
    } catch {
      return false
    }
  })()

  const isLoading = ref(!hasInitialized)
  const initializationStatus = ref(hasInitialized ? 'ready' : 'loading')
  const initializationError = ref('')
  const appLoadingRef = ref(null)
  const { error: showError } = useToast()

  // 遮罩只负责视觉过渡，最多展示 3 秒；初始化本身在后台继续，
  // 任何依赖挂起或失败都不能让用户失去可操作性。
  const MAX_OVERLAY_MS = 3000
  const INIT_TIMEOUT_MS = 8000
  let initStarted = false
  let initSettled = false
  let initAttempt = 0
  let overlayTimer = null
  let initTimer = null

  const handleSessionExpired = (event) => {
    showError(event?.detail?.message || '会话已过期，请重新登录')
  }

  const rememberInitialized = () => {
    try {
      sessionStorage.setItem(INITIALIZED_FLAG, '1')
    } catch {
      // 隐私模式等禁用存储时忽略，仅影响下次重载是否展示遮罩
    }
  }

  const hideOverlay = () => {
    if (!isLoading.value) return
    isLoading.value = false
    // 遮罩撤下即记为已初始化，本次实现与后续整页重载都不会再弹。
    rememberInitialized()
    if (overlayTimer) {
      clearTimeout(overlayTimer)
      overlayTimer = null
    }
  }

  // 初始化结果只结算一次；遮罩可能已因超时或用户交互提前撤下，
  // 但失败仍然要通过 toast 告知用户。
  const settleInitialization = (attempt, status, message = '') => {
    // 重试后旧请求的晚到结果直接丢弃，避免覆盖新请求的状态。
    if (attempt !== initAttempt || initSettled) return
    initSettled = true
    initializationStatus.value = status
    initializationError.value = message
    if (initTimer) {
      clearTimeout(initTimer)
      initTimer = null
    }
    hideOverlay()
    if (status === 'error') showError(message)
  }

  const initialize = async (isRetry = false) => {
    // 同一文档内重复调用是幂等的；重试由用户显式触发。
    if (initStarted && !isRetry) return
    initStarted = true
    const attempt = ++initAttempt

    if (isRetry) {
      initSettled = false
      clearTimeout(overlayTimer)
      overlayTimer = null
      clearTimeout(initTimer)
      initTimer = null
      initializationError.value = ''
      initializationStatus.value = 'loading'
      isLoading.value = true
    }
    initTheme()

    // 无论初始化是否完成，遮罩最多展示 MAX_OVERLAY_MS。
    if (isLoading.value && !overlayTimer) {
      overlayTimer = setTimeout(hideOverlay, MAX_OVERLAY_MS)
    }

    try {
      const initialization = isRetry && window.__retryAppInitialization
        ? window.__retryAppInitialization()
        : window.__appInitialization
      const timeout = new Promise((_, reject) => {
        initTimer = setTimeout(() => reject(new Error('应用初始化超时，请重试')), INIT_TIMEOUT_MS)
      })
      await Promise.race([Promise.resolve(initialization || undefined), timeout])
      settleInitialization(attempt, 'ready')
    } catch (error) {
      const message = error?.message || '应用初始化失败，请重试。'
      settleInitialization(attempt, 'error', message)
    }
  }

  // 初始化期间用户仍应能操作页面：首次交互立即撤下遮罩，
  // 初始化继续在后台完成，避免第一次点击被遮罩吞掉。
  const dismissLoadingOverlay = () => {
    if (isLoading.value && initializationStatus.value === 'loading') {
      hideOverlay()
    }
  }

  onMounted(() => {
    initialize()
    window.addEventListener('session-expired', handleSessionExpired)
    window.addEventListener('pointerdown', dismissLoadingOverlay, { capture: true, passive: true })
    window.addEventListener('touchstart', dismissLoadingOverlay, { capture: true, passive: true })
    window.addEventListener('keydown', dismissLoadingOverlay, { capture: true })
  })
  onBeforeUnmount(() => {
    appLoadingRef.value?.reset()
    if (overlayTimer) clearTimeout(overlayTimer)
    if (initTimer) clearTimeout(initTimer)
    window.removeEventListener('session-expired', handleSessionExpired)
    window.removeEventListener('pointerdown', dismissLoadingOverlay, { capture: true })
    window.removeEventListener('touchstart', dismissLoadingOverlay, { capture: true })
    window.removeEventListener('keydown', dismissLoadingOverlay, { capture: true })
  })
</script>

<template>
  <div class="app-container" role="application" aria-label="CodingMatrix">
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
