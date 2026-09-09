<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible" class="keyboard-shortcuts-overlay" @click.self="handleOverlayClick">
        <div class="keyboard-shortcuts-modal">
          <div class="modal-header">
            <h2 class="modal-title">快捷键</h2>
            <button class="modal-close" aria-label="关闭" @click="close">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <div v-for="(group, index) in shortcutGroups" :key="index" class="shortcut-group">
              <h3 class="group-title">{{ group.title }}</h3>
              <div class="shortcut-list">
                <div
                  v-for="(shortcut, idx) in group.items"
                  :key="idx"
                  class="shortcut-item"
                >
                  <div class="shortcut-keys">
                    <kbd v-for="(key, kIdx) in shortcut.keys" :key="kIdx" class="kbd">{{ key }}</kbd>
                  </div>
                  <span class="shortcut-desc">{{ shortcut.description }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <p class="footer-tip">按 <kbd class="kbd">Esc</kbd> 关闭此窗口</p>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const shortcutGroups = computed(() => [
  {
    title: '通用',
    items: [
      { keys: ['Ctrl', 'K'], description: '聚焦输入框' },
      { keys: ['Ctrl', 'Enter'], description: '发送消息' },
      { keys: ['Ctrl', 'N'], description: '新建会话' },
      { keys: ['Esc'], description: '关闭工具面板/弹窗' }
    ]
  },
  {
    title: '导航',
    items: [
      { keys: ['Ctrl', 'B'], description: '切换侧边栏' },
      { keys: ['Ctrl', 'Shift', 'L'], description: '切换侧边栏折叠状态' },
      { keys: ['/'], description: '聚焦搜索框' },
      { keys: ['?'], description: '显示快捷键帮助' }
    ]
  }
])

function close() {
  emit('close')
}

function handleOverlayClick() {
  close()
}

function handleKeydown(e) {
  if (e.key === 'Escape' && props.visible) {
    e.stopPropagation()
    close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.keyboard-shortcuts-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.keyboard-shortcuts-modal {
  background: var(--bg-primary, #fff);
  border-radius: 16px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  width: 90%;
  max-width: 560px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border-color, #e2e8f0);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
}

.modal-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary, #1e293b);
}

.modal-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary, #64748b);
  transition: all 0.2s;
}

.modal-close:hover {
  background: var(--bg-secondary, #f1f5f9);
  color: var(--text-primary, #1e293b);
}

.modal-close svg {
  width: 18px;
  height: 18px;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}

.shortcut-group {
  margin-bottom: 24px;
}

.shortcut-group:last-child {
  margin-bottom: 0;
}

.group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #64748b);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 12px 0;
}

.shortcut-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.shortcut-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--bg-secondary, #f8fafc);
  transition: background 0.2s;
}

.shortcut-item:hover {
  background: var(--bg-tertiary, #f1f5f9);
}

.shortcut-keys {
  display: flex;
  gap: 6px;
  align-items: center;
}

.kbd {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
  padding: 0 8px;
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #cbd5e1);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  color: var(--text-primary, #1e293b);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.shortcut-desc {
  font-size: 14px;
  color: var(--text-primary, #1e293b);
}

.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--border-color, #e2e8f0);
  text-align: center;
}

.footer-tip {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary, #64748b);
}

.footer-tip .kbd {
  margin: 0 4px;
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .keyboard-shortcuts-modal,
.modal-leave-active .keyboard-shortcuts-modal {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.modal-enter-from .keyboard-shortcuts-modal,
.modal-leave-to .keyboard-shortcuts-modal {
  transform: scale(0.95);
  opacity: 0;
}
</style>
