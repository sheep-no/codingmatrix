<template>
  <div class="theme-switcher" role="radiogroup" aria-label="外观主题">
    <button
      class="theme-btn"
      type="button"
      role="radio"
      :aria-checked="currentTheme === 'theme-light'"
      :class="{ active: currentTheme === 'theme-light' }"
      title="白天"
      aria-label="白天"
      @click="setTheme('theme-light')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
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
      type="button"
      role="radio"
      :aria-checked="currentTheme === 'theme-dark'"
      :class="{ active: currentTheme === 'theme-dark' }"
      title="夜晚"
      aria-label="夜晚"
      @click="setTheme('theme-dark')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    </button>
    <button
      class="theme-btn"
      type="button"
      role="radio"
      :aria-checked="currentTheme === 'theme-auto'"
      :class="{ active: currentTheme === 'theme-auto' }"
      title="随系统"
      aria-label="随系统"
      @click="setTheme('theme-auto')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 2a10 10 0 0 1 0 20" />
        <path d="M12 8v4l2 2" />
      </svg>
    </button>
  </div>
</template>

<script setup>
  import { ref, onMounted } from 'vue'
  import { applyTheme, getStoredTheme, initTheme } from '@/utils/theme'

  const currentTheme = ref('theme-light')

  const setTheme = themeId => {
    currentTheme.value = themeId
    applyTheme(themeId, true)
    initTheme()
  }

  onMounted(() => {
    const saved = getStoredTheme()
    currentTheme.value = saved
    initTheme()
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
    background: color-mix(in srgb, var(--accent-primary) 16%, var(--bg-secondary));
    border-color: var(--accent-primary);
    color: var(--accent-primary);
  }

  .theme-btn svg {
    width: 20px;
    height: 20px;
  }
</style>
