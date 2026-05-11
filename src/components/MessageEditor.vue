<script setup>
  import { ref, watch, nextTick } from 'vue'

  const props = defineProps({
    message: { type: String, default: '' },
    visible: { type: Boolean, default: false }
  })

  const emit = defineEmits(['save', 'cancel'])

  const editMessage = ref(props.message)
  const textareaRef = ref(null)

  watch(
    () => props.visible,
    async val => {
      if (val) {
        editMessage.value = props.message
        await nextTick()
        textareaRef.value?.focus()
      }
    }
  )

  function handleSave() {
    if (editMessage.value.trim()) {
      emit('save', editMessage.value.trim())
    }
  }

  function handleCancel() {
    emit('cancel')
  }

  function handleKeydown(e) {
    if (e.key === 'Enter' && e.ctrlKey) {
      e.preventDefault()
      handleSave()
    } else if (e.key === 'Escape') {
      handleCancel()
    }
  }
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="visible" class="message-editor-overlay" @click.self="handleCancel">
        <div class="message-editor">
          <div class="editor-header">
            <h3>编辑消息</h3>
            <button class="close-btn" @click="handleCancel">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          <textarea
            ref="textareaRef"
            v-model="editMessage"
            class="editor-textarea"
            placeholder="编辑你的消息..."
            rows="6"
            @keydown="handleKeydown"
          ></textarea>

          <div class="editor-footer">
            <span class="editor-hint">Ctrl+Enter 保存，Esc 取消</span>
            <div class="editor-actions">
              <button class="btn btn-cancel" @click="handleCancel">取消</button>
              <button class="btn btn-save" :disabled="!editMessage.trim()" @click="handleSave">
                保存
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
  .message-editor-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    backdrop-filter: blur(2px);
  }

  .message-editor {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 12px;
    width: 90%;
    max-width: 600px;
    padding: 24px;
    box-shadow: 0 8px 32px var(--shadow-lg);
  }

  .editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .editor-header h3 {
    margin: 0;
    font-size: 18px;
    color: var(--color-text);
  }

  .close-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: transparent;
    color: var(--color-text-secondary);
    cursor: pointer;
    border-radius: 6px;
    transition: background 0.2s;
  }

  .close-btn:hover {
    background: var(--color-surface-hover);
  }

  .close-btn svg {
    width: 20px;
    height: 20px;
  }

  .editor-textarea {
    width: 100%;
    padding: 12px;
    border: 1px solid var(--color-border);
    border-radius: 8px;
    background: var(--color-surface-elevated);
    color: var(--color-text);
    font-size: 14px;
    line-height: 1.6;
    resize: vertical;
    min-height: 120px;
    font-family: inherit;
  }

  .editor-textarea:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px var(--color-primary-alpha);
  }

  .editor-footer {
    margin-top: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .editor-hint {
    font-size: 12px;
    color: var(--color-text-tertiary);
  }

  .editor-actions {
    display: flex;
    gap: 8px;
  }

  .btn {
    padding: 8px 16px;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    cursor: pointer;
    transition:
      background 0.2s,
      transform 0.1s;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-cancel {
    background: var(--color-surface-elevated);
    color: var(--color-text);
    border: 1px solid var(--color-border);
  }

  .btn-cancel:hover:not(:disabled) {
    background: var(--color-surface-hover);
  }

  .btn-save {
    background: var(--color-primary);
    color: white;
  }

  .btn-save:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px var(--color-primary-alpha);
  }

  .modal-fade-enter-active,
  .modal-fade-leave-active {
    transition: opacity 0.2s ease;
  }

  .modal-fade-enter-from,
  .modal-fade-leave-to {
    opacity: 0;
  }
</style>
