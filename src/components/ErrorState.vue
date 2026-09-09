<template>
  <div class="state-card state-card-error" role="alert">
    <strong>{{ title }}</strong>
    <p>{{ message }}</p>
    <button v-if="retryable" type="button" class="state-action" @click="$emit('retry')">{{ retryLabel }}</button>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '加载失败' },
  message: { type: String, default: '暂时无法加载内容，请稍后重试。' },
  retryable: { type: Boolean, default: true },
  retryLabel: { type: String, default: '重试' }
})
defineEmits(['retry'])
</script>

<style scoped>
.state-card { display: flex; flex-direction: column; align-items: center; gap: var(--spacing-2); min-height: 120px; padding: var(--spacing-6); text-align: center; color: var(--content-secondary); }
.state-card-error strong { color: var(--status-danger); }
.state-card p { margin: 0; }
.state-action { min-height: var(--control-min-size); padding: 0 var(--spacing-4); border: 1px solid var(--control-border); border-radius: var(--radius-md); background: var(--surface-raised); color: var(--content-primary); cursor: pointer; }
</style>
