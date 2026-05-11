<script setup>
  import { onMounted, ref } from 'vue'
  import { initTheme } from '@/utils/theme'
  import ErrorBoundary from '@/components/ErrorBoundary.vue'
  import AppLoading from '@/components/AppLoading.vue'

  const isLoading = ref(true)
  const appLoadingRef = ref(null)

  onMounted(() => {
    initTheme()

    setTimeout(() => {
      isLoading.value = false
    }, 800)
  })
</script>

<template>
  <div id="app" class="app-container" role="application" aria-label="AI 助手应用">
    <AppLoading ref="appLoadingRef" :visible="isLoading" />
    <ErrorBoundary component-name="主应用">
      <router-view />
    </ErrorBoundary>
  </div>
</template>

<style scoped>
  .app-container {
    width: 100%;
    height: 100vh;
    background: #f8fafc;
    background: var(--gradient-bg);
    overflow: hidden;
  }
</style>
