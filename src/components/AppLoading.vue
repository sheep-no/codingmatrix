<template>
  <Teleport to="body">
    <Transition name="app-loading">
      <div v-if="visible" class="app-loading-overlay">
        <div class="app-loading-container">
          <div class="app-loading-logo">
            <div class="logo-ring logo-ring-1"></div>
            <div class="logo-ring logo-ring-2"></div>
            <div class="logo-ring logo-ring-3"></div>
            <div class="logo-core">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
            </div>
          </div>
          <div class="app-loading-text">
            <span v-for="(char, i) in loadingText" :key="i" class="loading-word" :style="{ animationDelay: `${i * 0.1}s` }">
              {{ char }}
            </span>
          </div>
          <div class="app-loading-progress">
            <div class="progress-bar" :style="{ width: progress + '%' }"></div>
          </div>
          <div v-if="status === 'error'" class="app-loading-error" role="alert">
            <span>{{ error || '应用初始化失败，请重试。' }}</span>
            <button type="button" @click="emit('retry')">重试</button>
          </div>
          <div v-else class="app-loading-tip">{{ tipText }}</div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  status: {
    type: String,
    default: 'loading'
  },
  error: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['retry'])

const loadingText = '正在加载'
const progress = ref(0)
const tipText = ref('初始化应用资源...')

const tips = [
  '初始化应用资源...',
  '加载组件模块...',
  '准备用户界面...',
  '即将完成...'
]

let progressTimer = null
let tipTimer = null

onMounted(() => {
  if (props.visible) {
    startProgress()
  }
})

onBeforeUnmount(() => {
  if (progressTimer) clearInterval(progressTimer)
  if (tipTimer) clearInterval(tipTimer)
  progressTimer = null
  tipTimer = null
})

const startProgress = () => {
  resetTimers()
  progress.value = 0
  let tipIndex = 0

  progressTimer = setInterval(() => {
    if (progress.value < 90) {
      progress.value += Math.random() * 15 + 5
      if (progress.value > 90) progress.value = 90
    }
  }, 300)

  tipTimer = setInterval(() => {
    tipIndex = (tipIndex + 1) % tips.length
    tipText.value = tips[tipIndex]
  }, 1200)
}

const reset = () => {
  resetTimers()
  progress.value = 0
  tipText.value = tips[0]
}

const resetTimers = () => {
  if (progressTimer) clearInterval(progressTimer)
  if (tipTimer) clearInterval(tipTimer)
  progressTimer = null
  tipTimer = null
}

const complete = () => {
  progress.value = 100
  resetTimers()
}

watch(() => props.visible, visible => {
  if (visible) startProgress()
  else complete()
})

watch(() => props.status, status => {
  if (status === 'ready') complete()
})

onBeforeUnmount(resetTimers)

defineExpose({ reset, startProgress, complete })
</script>

<style scoped>
.app-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
}

.app-loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 32px;
}

.app-loading-logo {
  position: relative;
  width: 80px;
  height: 80px;
}

.logo-ring {
  position: absolute;
  border-radius: 50%;
  border: 2px solid var(--primary-400);
  opacity: 0.4;
  animation: pulseRing 2s ease-out infinite;
}

.logo-ring-1 {
  inset: 0;
  animation-delay: 0s;
}

.logo-ring-2 {
  inset: -10px;
  border-color: var(--primary-300);
  animation-delay: 0.3s;
}

.logo-ring-3 {
  inset: -20px;
  border-color: var(--primary-200);
  animation-delay: 0.6s;
}

.logo-core {
  position: absolute;
  inset: 10px;
  background: var(--gradient-primary);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-xl), 0 0 30px var(--primary-500);
}

.logo-core svg {
  width: 28px;
  height: 28px;
  color: white;
}

.app-loading-text {
  display: flex;
  gap: 2px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.loading-word {
  display: inline-block;
  animation: wordFade 1.5s ease-in-out infinite;
}

.app-loading-progress {
  width: 200px;
  height: 4px;
  background: var(--slate-200);
  border-radius: 2px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--gradient-primary);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.app-loading-tip {
  font-size: 13px;
  color: var(--text-tertiary);
  font-weight: 500;
  min-height: 20px;
}

.app-loading-error {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  max-width: 320px;
  color: var(--status-danger);
  text-align: center;
}

.app-loading-error button {
  min-height: var(--control-min-size);
  padding: 0 var(--spacing-3);
  border: 1px solid var(--status-danger);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--status-danger);
  cursor: pointer;
}

@keyframes pulseRing {
  0% {
    transform: scale(1);
    opacity: 0.4;
  }
  100% {
    transform: scale(1.5);
    opacity: 0;
  }
}

@keyframes wordFade {
  0%, 100% {
    opacity: 0.5;
    transform: translateY(0);
  }
  50% {
    opacity: 1;
    transform: translateY(-2px);
  }
}

.app-loading-enter-active,
.app-loading-leave-active {
  transition: opacity 0.4s ease;
}

.app-loading-enter-from,
.app-loading-leave-to {
  opacity: 0;
}
</style>
