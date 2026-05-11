<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="visible"
        class="modal-overlay"
        role="dialog"
        :aria-modal="true"
        @click="handleBackdropClick"
      >
        <div class="modal-container" :class="[`modal-${size}`]" role="document" @click.stop>
          <!-- Header -->
          <div class="modal-header">
            <h2 class="modal-title">
              <slot name="title">{{ title }}</slot>
            </h2>
            <button class="modal-close" aria-label="关闭对话框" @click="$emit('close')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          <!-- Body -->
          <div class="modal-body">
            <slot />
          </div>

          <!-- Footer -->
          <div v-if="$slots.footer" class="modal-footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
  defineProps({
    visible: { type: Boolean, default: false },
    title: { type: String, default: '' },
    size: {
      type: String,
      default: 'md',
      validator: v => ['sm', 'md', 'lg', 'xl'].includes(v)
    },
    closeOnBackdrop: { type: Boolean, default: true }
  })

  defineEmits(['close'])

  const handleBackdropClick = () => {
    if (props.closeOnBackdrop) {
      emit('close')
    }
  }
</script>

<style scoped>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.6);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    padding: var(--spacing-4);
  }

  .modal-container {
    background: var(--bg-primary);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-xl);
    max-height: 90vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .modal-sm {
    width: 100%;
    max-width: 400px;
  }
  .modal-md {
    width: 100%;
    max-width: 600px;
  }
  .modal-lg {
    width: 100%;
    max-width: 800px;
  }
  .modal-xl {
    width: 100%;
    max-width: 1000px;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--spacing-4) var(--spacing-6);
    border-bottom: 1px solid var(--border-color);
  }

  .modal-title {
    font-size: var(--text-xl);
    font-weight: 700;
    color: var(--text-primary);
    margin: 0;
  }

  .modal-close {
    width: 32px;
    height: 32px;
    border-radius: var(--radius-md);
    border: none;
    background: transparent;
    cursor: pointer;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all var(--transition-fast);
  }

  .modal-close:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .modal-close svg {
    width: 20px;
    height: 20px;
  }

  .modal-body {
    padding: var(--spacing-6);
    overflow-y: auto;
    flex: 1;
  }

  .modal-footer {
    padding: var(--spacing-4) var(--spacing-6);
    border-top: 1px solid var(--border-color);
    display: flex;
    justify-content: flex-end;
    gap: var(--spacing-3);
  }

  /* Transitions */
  .modal-enter-active,
  .modal-leave-active {
    transition: all var(--transition-slow);
  }

  .modal-enter-active .modal-container,
  .modal-leave-active .modal-container {
    transition: all var(--transition-slow);
  }

  .modal-enter-from,
  .modal-leave-to {
    opacity: 0;
  }

  .modal-enter-from .modal-container,
  .modal-leave-to .modal-container {
    opacity: 0;
    transform: scale(0.96) translateY(8px);
  }
</style>
