<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="close" @keydown="onKeydown">
      <div ref="dialogRef" class="modal-content" role="dialog" aria-modal="true" aria-labelledby="upload-modal-title" tabindex="-1">
        <div class="modal-header">
          <h3 id="upload-modal-title">导入项目</h3>
          <button class="modal-close" type="button" aria-label="关闭导入项目窗口" @click="close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="upload-zone" role="button" tabindex="0" @dragover.prevent @drop.prevent="onDrop" @click="openFilePicker" @keydown.enter="openFilePicker" @keydown.space.prevent="openFilePicker">
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
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'upload'])
const dialogRef = ref(null)
const fileInput = ref(null)
let previousFocus = null

const close = () => emit('update:modelValue', false)
const openFilePicker = () => fileInput.value?.click()

const onKeydown = (event) => {
  if (event.key === 'Escape') {
    close()
    return
  }
  if (event.key !== 'Tab') return
  const focusable = [...dialogRef.value.querySelectorAll('button, [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])')]
  if (focusable.length === 0) {
    event.preventDefault()
    dialogRef.value.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.modelValue, async (open) => {
  if (open) {
    previousFocus = document.activeElement
    await nextTick()
    dialogRef.value?.focus()
  } else {
    previousFocus?.focus?.()
    previousFocus = null
  }
}, { immediate: true })

onBeforeUnmount(() => previousFocus?.focus?.())

const onFileChange = (e) => { const f = e.target.files[0]; if (f) emit('upload', f) }
const onDrop = (e) => { const f = e.dataTransfer.files[0]; if (f && f.name.endsWith('.zip')) emit('upload', f) }
</script>
