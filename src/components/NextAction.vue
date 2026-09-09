<template>
  <div v-if="label" class="next-action">
    <span>{{ label }}</span>
    <button v-if="actionLabel" type="button" @click="$emit('action')">{{ actionLabel }}</button>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, default: '' },
  actionLabel: { type: String, default: '' }
})

defineEmits(['action'])
</script>

<style scoped>
.next-action { display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-3); padding: var(--spacing-3) var(--spacing-4); border: 1px solid var(--control-border); border-radius: var(--radius-md); color: var(--content-secondary); }
.next-action button { min-height: var(--control-min-size); padding: 0 var(--spacing-3); border: 0; border-radius: var(--radius-sm); background: var(--accent-primary); color: var(--content-inverse); cursor: pointer; }
</style>
