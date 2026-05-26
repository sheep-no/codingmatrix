<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="$emit('update:modelValue', false)">
      <div class="modal-content version-modal"><div class="modal-header"><h3>版本历史</h3><button class="modal-close" @click="$emit('update:modelValue', false)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg></button></div>
        <div class="modal-body">
          <div v-for="(snap, i) in snapshots" :key="'s'+i" class="version-item">
            <div class="version-header"><span class="version-label">{{ snap.tag || '快照' }}</span><span class="version-time">{{ new Date(snap.timestamp).toLocaleString() }}</span></div>
            <pre class="version-code">{{ snap.message || '快照记录' }}</pre>
            <div class="version-actions"><button class="btn btn-sm btn-outline" @click="$emit('rollback', snap.tag)">回滚到此快照</button></div>
          </div>
          <div v-if="!snapshots?.length" class="empty-versions"><p>暂无版本记录和快照</p></div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
defineProps({
  modelValue: Boolean,
  snapshots: { type: Array, default: () => [] },
  file: { type: Object, default: null },
  fileVersions: { type: Object, default: () => ({}) }
})
defineEmits(['update:modelValue', 'rollback', 'restore', 'viewDiff'])
</script>
