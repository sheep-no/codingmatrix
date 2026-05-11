<template>
  <div class="input-wrapper" :class="{ 'input-error': error }">
    <label v-if="label" :for="id" class="input-label">
      {{ label }}
      <span v-if="required" class="required">*</span>
    </label>

    <div class="input-container" :class="{ 'input-with-icon': icon || $slots.icon }">
      <span v-if="icon || $slots.icon" class="input-icon">
        <slot name="icon">{{ icon }}</slot>
      </span>

      <input
        :id="id"
        ref="inputRef"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :required="required"
        :class="['input-field', `input-${size}`]"
        :aria-invalid="!!error"
        :aria-describedby="error ? `${id}-error` : undefined"
        @input="handleInput"
        @focus="$emit('focus', $event)"
        @blur="$emit('blur', $event)"
      />

      <button
        v-if="clearable && modelValue"
        class="input-clear"
        aria-label="清除内容"
        @click="handleClear"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>

    <p v-if="error" :id="`${id}-error`" class="input-error-message">
      {{ error }}
    </p>

    <p v-if="helperText && !error" class="input-helper">
      {{ helperText }}
    </p>
  </div>
</template>

<script setup>
  import { ref, computed } from 'vue'

  const props = defineProps({
    modelValue: { type: [String, Number], default: '' },
    type: { type: String, default: 'text' },
    label: { type: String, default: '' },
    placeholder: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
    required: { type: Boolean, default: false },
    clearable: { type: Boolean, default: false },
    icon: { type: String, default: '' },
    size: {
      type: String,
      default: 'md',
      validator: v => ['sm', 'md', 'lg'].includes(v)
    },
    error: { type: String, default: '' },
    helperText: { type: String, default: '' },
    id: {
      type: String,
      default: () => `input-${Math.random().toString(36).substr(2, 9)}`
    }
  })

  const emit = defineEmits(['update:modelValue', 'input', 'focus', 'blur', 'clear'])

  const inputRef = ref(null)

  const handleInput = e => {
    emit('update:modelValue', e.target.value)
    emit('input', e)
  }

  const handleClear = () => {
    emit('update:modelValue', '')
    emit('clear')
    inputRef.value?.focus()
  }
</script>

<style scoped>
  .input-wrapper {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-1);
  }

  .input-label {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: var(--spacing-1);
  }

  .required {
    color: var(--color-danger-500);
  }

  .input-container {
    position: relative;
    display: flex;
    align-items: center;
  }

  .input-field {
    width: 100%;
    padding: var(--spacing-2) var(--spacing-4);
    font-size: var(--text-base);
    color: var(--text-primary);
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    transition: all var(--transition-fast);
    outline: none;
  }

  .input-field::placeholder {
    color: var(--text-tertiary);
  }

  .input-field:focus {
    border-color: var(--color-blue-500);
    box-shadow: 0 0 0 3px var(--color-blue-100);
  }

  .input-field:disabled {
    background: var(--bg-tertiary);
    cursor: not-allowed;
    opacity: 0.6;
  }

  .input-with-icon .input-field {
    padding-left: var(--spacing-10);
  }

  .input-icon {
    position: absolute;
    left: var(--spacing-3);
    color: var(--text-tertiary);
    display: flex;
    align-items: center;
    pointer-events: none;
  }

  .input-clear {
    position: absolute;
    right: var(--spacing-2);
    width: 24px;
    height: 24px;
    border-radius: var(--radius-sm);
    border: none;
    background: transparent;
    cursor: pointer;
    color: var(--text-tertiary);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all var(--transition-fast);
  }

  .input-clear:hover {
    background: var(--bg-tertiary);
    color: var(--text-secondary);
  }

  .input-clear svg {
    width: 16px;
    height: 16px;
  }

  .input-error .input-field {
    border-color: var(--color-danger-500);
  }

  .input-error-message {
    font-size: var(--text-xs);
    color: var(--color-danger-500);
    margin: 0;
  }

  .input-helper {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    margin: 0;
  }

  /* Sizes */
  .input-sm .input-field {
    padding: var(--spacing-1) var(--spacing-3);
    font-size: var(--text-sm);
  }

  .input-lg .input-field {
    padding: var(--spacing-3) var(--spacing-5);
    font-size: var(--text-lg);
  }
</style>
