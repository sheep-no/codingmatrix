<template>
  <div class="theme-switcher">
    <button
      class="theme-btn"
      :class="{ active: currentTheme === 'theme-light' }"
      title="明亮模式"
      @click="setTheme('theme-light')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="5" />
        <line x1="12" y1="1" x2="12" y2="3" />
        <line x1="12" y1="21" x2="12" y2="23" />
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
        <line x1="1" y1="12" x2="3" y2="12" />
        <line x1="21" y1="12" x2="23" y2="12" />
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
      </svg>
    </button>
    <button
      class="theme-btn"
      :class="{ active: currentTheme === 'theme-default' }"
      title="默认模式"
      @click="setTheme('theme-default')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 2a10 10 0 0 1 0 20" />
      </svg>
    </button>
    <button
      class="theme-btn"
      :class="{ active: currentTheme === 'theme-dark' }"
      title="暗色模式"
      @click="setTheme('theme-dark')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    </button>
    <button
      class="theme-btn"
      :class="{ active: currentTheme === 'theme-auto' }"
      title="跟随系统"
      @click="setTheme('theme-auto')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
        <line x1="8" y1="21" x2="16" y2="21" />
        <line x1="12" y1="17" x2="12" y2="21" />
      </svg>
    </button>
  </div>
</template>

<script setup>
  import { ref, onMounted } from 'vue'
  import { applyTheme, getStoredTheme, getPreferredSystemTheme } from '@/utils/theme'

  const currentTheme = ref('theme-default')

  const setTheme = themeId => {
    currentTheme.value = themeId
    applyTheme(themeId, true)
  }

  onMounted(() => {
    const saved = getStoredTheme()
    currentTheme.value = saved
    applyTheme(saved, false)
  })
</script>

<style scoped>
  .theme-switcher {
    display: flex;
    gap: 4px;
    padding: 6px;
    background: var(--bg-secondary);
    border-radius: 10px;
    border: 1px solid var(--border-color);
  }

  .theme-btn {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 2px solid transparent;
    border-radius: 8px;
    cursor: pointer;
    color: var(--text-secondary);
    transition: all 0.2s ease;
  }

  .theme-btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .theme-btn.active {
    background: var(--color-primary-100);
    border-color: var(--color-primary-500);
    color: var(--color-primary-600);
  }

  .theme-btn svg {
    width: 20px;
    height: 20px;
  }

  .theme-dark .theme-btn.active {
    background: var(--color-primary-900);
    border-color: var(--color-primary-400);
    color: var(--color-primary-300);
  }
</style>
