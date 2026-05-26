<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="$emit('update:modelValue', false)">
      <div class="modal-content"><div class="modal-header"><h3>文件变更 - {{ diff?.path }}</h3><button class="modal-close" @click="$emit('update:modelValue', false)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg></button></div>
        <div class="modal-body">
          <div class="diff-view">
            <div class="diff-col diff-old"><div class="diff-col-header">旧内容</div><pre class="diff-code">{{ diff?.oldContent }}</pre></div>
            <div class="diff-col diff-new"><div class="diff-col-header">新内容</div><pre class="diff-code">{{ diff?.newContent }}</pre></div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
defineProps({ modelValue: Boolean, diff: { type: Object, default: null } })
defineEmits(['update:modelValue'])
</script>

<style scoped>
.diff-view { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.diff-col { background: var(--bg-tertiary); border-radius: 8px; overflow: hidden; }
.diff-col-header { padding: 8px 12px; font-size: 12px; font-weight: 600; background: var(--bg-primary); border-bottom: 1px solid var(--border-color); }
.diff-code { padding: 12px; font-size: 12px; line-height: 1.5; overflow-x: auto; white-space: pre-wrap; margin: 0; }
</style>
