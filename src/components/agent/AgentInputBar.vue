<template>
  <div class="agent-input-bar">
    <div class="input-row">
      <div class="input-left">
        <select
          v-if="dynamicModels && dynamicModels.length > 0"
          :value="selectedProviderModel"
          class="model-select"
          @change="$emit('update:selectedProviderModel', $event.target.value)"
        >
          <option value="">默认模型</option>
          <optgroup v-for="group in groupedDynamicModels" :key="group.provider" :label="group.provider">
            <option v-for="m in group.models" :key="m.provider_id + ':' + m.model_id" :value="m.provider_id + '::' + m.model_id">
              {{ m.model_id }}
            </option>
          </optgroup>
        </select>
      </div>
      <div class="input-center">
        <textarea
          ref="textareaRef"
          :value="prompt"
          :placeholder="placeholderText"
          class="prompt-textarea"
          data-testid="agent-prompt-input"
          rows="1"
          @input="onInput"
          @keydown="onKeydown"
        />
      </div>
      <div class="input-right">
        <button
          v-if="!generating"
          class="btn-send"
          type="button"
          aria-label="发送需求"
          :disabled="!prompt.trim()"
          @click="$emit('generate')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
        <button
          v-else
          class="btn-stop"
          type="button"
          aria-label="停止生成"
          @click="$emit('stop')"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
        </button>
      </div>
    </div>
    <div class="input-hint">
      <span v-if="!generating">Ctrl+Enter 发送，Esc 停止</span>
      <span v-else class="generating-hint">正在生成...</span>
      <div v-if="hasFiles" class="input-actions">
        <button class="action-btn" @click="$emit('regenerate')">重新生成</button>
        <button class="action-btn" @click="$emit('clear')">清空</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, nextTick, watch } from 'vue'

const props = defineProps({
  prompt: { type: String, default: '' },
  placeholderText: { type: String, default: '描述你的项目需求...' },
  generating: { type: Boolean, default: false },
  hasFiles: { type: Boolean, default: false },
  dynamicModels: { type: Array, default: () => [] },
  selectedProviderModel: { type: String, default: '' }
})

const emit = defineEmits(['update:prompt', 'update:selectedProviderModel', 'generate', 'regenerate', 'clear', 'stop'])

const textareaRef = ref(null)

const groupedDynamicModels = computed(() => {
  const groups = {}
  for (const m of (props.dynamicModels || [])) {
    if (!groups[m.provider_name]) {
      groups[m.provider_name] = { provider: m.provider_name, models: [] }
    }
    groups[m.provider_name].models.push(m)
  }
  return Object.values(groups)
})

function onInput(event) {
  emit('update:prompt', event.target.value)
  autoResize()
}

function onKeydown(event) {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault()
    if (!props.prompt.trim() || props.generating) return
    emit('generate')
  }
  if (event.key === 'Escape' && props.generating) {
    event.preventDefault()
    emit('stop')
  }
}

function autoResize() {
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
      textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 120) + 'px'
    }
  })
}

watch(() => props.prompt, () => autoResize())
</script>

<style scoped>
.agent-input-bar {
  padding: 12px 16px;
  background: var(--surface-app);
  border-top: 1px solid var(--control-border);
}
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.input-left {
  flex-shrink: 0;
}
.model-select {
  padding: 8px 10px;
  border: 1px solid var(--control-border);
  border-radius: 8px;
  font-size: 12px;
  background: var(--surface-subtle);
  color: var(--content-primary);
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}
.model-select:focus { border-color: var(--control-border-focus); }
.input-center {
  flex: 1;
  min-width: 0;
}
.prompt-textarea {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--control-border);
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;
  background: var(--surface-subtle);
  color: var(--content-primary);
  resize: none;
  outline: none;
  transition: border-color 0.15s;
  min-height: 42px;
  max-height: 120px;
}
.prompt-textarea:focus { border-color: var(--control-border-focus); }
.prompt-textarea::placeholder { color: var(--content-muted); }
.input-right {
  flex-shrink: 0;
}
.btn-send, .btn-stop {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: all var(--motion-fast);
}
.btn-send {
  background: var(--accent-primary);
  color: white;
}
.btn-send:hover:not(:disabled) { background: var(--accent-primary-hover); }
.btn-send:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-stop {
  background: var(--status-danger);
  color: white;
}
.btn-stop:hover { background: color-mix(in srgb, var(--status-danger) 85%, black); }
.input-hint {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
  padding: 0 4px;
  font-size: 11px;
  color: var(--text-tertiary);
}
.generating-hint { color: var(--accent-primary); }
.input-actions {
  display: flex;
  gap: 8px;
}
.action-btn {
  padding: 2px 8px;
  border: 1px solid var(--control-border);
  border-radius: 6px;
  font-size: 11px;
  background: transparent;
  color: var(--content-secondary);
  cursor: pointer;
  transition: all var(--motion-fast);
}
.action-btn:hover { background: var(--surface-subtle); border-color: var(--control-border-focus); color: var(--accent-primary); }
</style>
