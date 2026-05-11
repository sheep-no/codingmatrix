<script setup>
  import { useToast } from '@/composables/useToast'

  const { toasts, remove } = useToast()
</script>

<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast"
          :class="`toast-${toast.type}`"
          @click="remove(toast.id)"
        >
          <span class="toast-icon">
            <template v-if="toast.type === 'success'">&#10004;</template>
            <template v-else-if="toast.type === 'error'">&#10008;</template>
            <template v-else-if="toast.type === 'warning'">&#9888;</template>
            <template v-else>&#9432;</template>
          </span>
          <span class="toast-message">{{ toast.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
  .toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-width: 400px;
  }

  .toast {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    border-radius: 8px;
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: 0 4px 12px var(--shadow-md);
    cursor: pointer;
    font-size: 14px;
    border-left: 4px solid transparent;
  }

  .toast-success {
    border-left-color: var(--color-green-500);
  }

  .toast-error {
    border-left-color: var(--color-red-500);
  }

  .toast-warning {
    border-left-color: var(--color-yellow-500);
  }

  .toast-info {
    border-left-color: var(--color-blue-500);
  }

  .toast-icon {
    font-size: 18px;
    flex-shrink: 0;
  }

  .toast-message {
    flex: 1;
  }

  .toast-enter-active {
    transition: all 0.3s ease-out;
  }

  .toast-leave-active {
    transition: all 0.2s ease-in;
  }

  .toast-enter-from {
    opacity: 0;
    transform: translateX(100%);
  }

  .toast-leave-to {
    opacity: 0;
    transform: translateX(100%);
  }
</style>
