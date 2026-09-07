<template>
  <div class="state-card state-card-loading" role="status" :aria-label="label">
    <span class="state-spinner" aria-hidden="true"></span>
    <span>{{ label }}</span>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, default: '正在加载...' }
})
</script>

<style scoped>
.state-card { display: flex; align-items: center; justify-content: center; gap: var(--spacing-3); min-height: 120px; padding: var(--spacing-6); color: var(--content-secondary); }
.state-spinner { width: 20px; height: 20px; border: 2px solid var(--control-border); border-top-color: var(--accent-primary); border-radius: 50%; animation: state-spin 0.8s linear infinite; }
@keyframes state-spin { to { transform: rotate(360deg); } }
</style>
