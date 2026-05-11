<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :class="[
      'btn',
      `btn-${variant}`,
      `btn-${size}`,
      { 'btn-loading': loading, 'btn-disabled': disabled }
    ]"
    :aria-label="ariaLabel"
    :aria-disabled="disabled || loading"
    @click="handleClick"
  >
    <span v-if="loading" class="btn-spinner">
      <svg class="animate-spin" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25" />
        <path
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          class="opacity-75"
        />
      </svg>
    </span>
    <span class="btn-content">
      <slot />
    </span>
  </button>
</template>

<script setup>
  const props = defineProps({
    type: { type: String, default: 'button' },
    variant: {
      type: String,
      default: 'primary',
      validator: v => ['primary', 'secondary', 'success', 'warning', 'danger', 'ghost'].includes(v)
    },
    size: {
      type: String,
      default: 'md',
      validator: v => ['sm', 'md', 'lg'].includes(v)
    },
    disabled: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    ariaLabel: { type: String, default: '' }
  })

  const emit = defineEmits(['click'])

  const handleClick = e => {
    if (!props.disabled && !props.loading) {
      emit('click', e)
    }
  }
</script>

<style scoped>
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--spacing-2);
    font-weight: 600;
    border: none;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all var(--transition-base);
    white-space: nowrap;
  }

  .btn:disabled,
  .btn-disabled {
    opacity: 0.5;
    cursor: not-allowed;
    pointer-events: none;
  }

  /* Variants */
  .btn-primary {
    background: var(--gradient-primary);
    color: white;
    box-shadow: var(--shadow-sm);
  }

  .btn-primary:hover:not(:disabled) {
    box-shadow: var(--shadow-md);
    transform: translateY(-1px);
  }

  .btn-secondary {
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
  }

  .btn-secondary:hover:not(:disabled) {
    background: var(--bg-secondary);
  }

  .btn-success {
    background: var(--gradient-success);
    color: white;
  }

  .btn-warning {
    background: var(--gradient-warning);
    color: white;
  }

  .btn-danger {
    background: var(--gradient-danger);
    color: white;
  }

  .btn-ghost {
    background: transparent;
    color: var(--text-secondary);
  }

  .btn-ghost:hover:not(:disabled) {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  /* Sizes */
  .btn-sm {
    padding: var(--spacing-1) var(--spacing-3);
    font-size: var(--text-xs);
  }

  .btn-md {
    padding: var(--spacing-2) var(--spacing-4);
    font-size: var(--text-sm);
  }

  .btn-lg {
    padding: var(--spacing-3) var(--spacing-6);
    font-size: var(--text-base);
  }

  /* Loading */
  .btn-spinner {
    display: inline-flex;
  }

  .btn-spinner svg {
    width: 1em;
    height: 1em;
  }

  .animate-spin {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
</style>
