<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="$emit('update:modelValue', false)">
      <div class="modal-content">
        <div class="modal-header">
          <h3>导入项目</h3>
          <button class="modal-close" @click="$emit('update:modelValue', false)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="upload-zone" @dragover.prevent @drop.prevent="onDrop" @click="$refs.fileInput.click()">
            <input ref="fileInput" type="file" accept=".zip" style="display:none" @change="onFileChange" />
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>
            <p>拖拽 ZIP 文件到此处，或点击上传</p>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'upload'])

const onFileChange = (e) => { const f = e.target.files[0]; if (f) emit('upload', f) }
const onDrop = (e) => { const f = e.dataTransfer.files[0]; if (f && f.name.endsWith('.zip')) emit('upload', f) }
</script>
