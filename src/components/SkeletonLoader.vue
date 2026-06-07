<template>
  <div class="skeleton-loader" :class="classes" :style="customStyles">
    <template v-if="type === 'text'">
      <div class="skeleton-text" :style="textStyle"></div>
    </template>
    <template v-else-if="type === 'paragraph'">
      <div v-for="i in rows" :key="i" class="skeleton-text" :style="getParagraphStyle(i)"></div>
    </template>
    <template v-else-if="type === 'card'">
      <div class="skeleton-card">
        <div class="skeleton-card-header">
          <div class="skeleton-circle" :style="circleStyle"></div>
          <div class="skeleton-text" :style="{ width: '60%' }"></div>
        </div>
        <div v-for="i in rows" :key="i" class="skeleton-text" :style="getParagraphStyle(i)"></div>
      </div>
    </template>
    <template v-else-if="type === 'list-item'">
      <div class="skeleton-list-item">
        <div class="skeleton-circle" :style="circleStyle"></div>
        <div class="skeleton-list-content">
          <div class="skeleton-text" :style="{ width: '70%' }"></div>
          <div class="skeleton-text" :style="{ width: '50%' }"></div>
        </div>
      </div>
    </template>
    <template v-else-if="type === 'circle'">
      <div class="skeleton-circle" :style="circleStyle"></div>
    </template>
    <template v-else-if="type === 'chat'">
      <div class="skeleton-chat">
        <div class="skeleton-chat-avatar">
          <div class="skeleton-circle" :style="{ width: '42px', height: '42px' }"></div>
        </div>
        <div class="skeleton-chat-body">
          <div class="skeleton-text" :style="{ width: '80px', height: '14px' }"></div>
          <div class="skeleton-chat-bubble">
            <div v-for="i in rows" :key="i" class="skeleton-text" :style="getParagraphStyle(i)"></div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  type: {
    type: String,
    default: 'text',
    validator: v => ['text', 'paragraph', 'card', 'list-item', 'circle', 'chat'].includes(v)
  },
  rows: {
    type: Number,
    default: 3
  },
  width: {
    type: String,
    default: '100%'
  },
  height: {
    type: String,
    default: ''
  },
  animated: {
    type: Boolean,
    default: true
  }
})

const classes = computed(() => ({
  [`skeleton-${props.type}`]: true,
  'skeleton-animated': props.animated
}))

const customStyles = computed(() => {
  const styles = {}
  if (props.width !== '100%') styles.width = props.width
  if (props.height) styles.height = props.height
  return styles
})

const textStyle = computed(() => ({
  width: props.width,
  height: props.height || '16px'
}))

const circleStyle = computed(() => ({
  width: props.width !== '100%' ? props.width : '40px',
  height: props.height || (props.width !== '100%' ? props.width : '40px')
}))

const getParagraphStyle = index => {
  const widths = props.type === 'paragraph'
    ? ['100%', '95%', '85%', '90%', '100%']
    : props.type === 'chat'
      ? ['90%', '75%', '60%']
      : ['100%', '90%', '80%']
  return {
    width: widths[(index - 1) % widths.length],
    height: '14px',
    marginBottom: '8px'
  }
}
</script>

<style scoped>
.skeleton-loader {
  display: inline-block;
}

.skeleton-text {
  background: linear-gradient(
    90deg,
    var(--slate-200) 0%,
    var(--slate-100) 50%,
    var(--slate-200) 100%
  );
  border-radius: var(--radius-sm);
  position: relative;
  overflow: hidden;
}

.skeleton-animated .skeleton-text::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.6) 50%,
    transparent 100%
  );
  animation: shimmer 1.8s ease-in-out infinite;
}

.skeleton-circle {
  border-radius: 50%;
  background: linear-gradient(
    90deg,
    var(--slate-200) 0%,
    var(--slate-100) 50%,
    var(--slate-200) 100%
  );
  position: relative;
  overflow: hidden;
}

.skeleton-animated .skeleton-circle::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.6) 50%,
    transparent 100%
  );
  animation: shimmer 1.8s ease-in-out infinite;
}

.skeleton-card {
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
}

.skeleton-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.skeleton-list-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.skeleton-list-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skeleton-chat {
  display: flex;
  gap: 14px;
  padding: 8px 0;
}

.skeleton-chat-avatar {
  flex-shrink: 0;
}

.skeleton-chat-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-chat-bubble {
  padding: 14px 18px;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.theme-dark .skeleton-text,
.theme-dark .skeleton-circle {
  background: linear-gradient(
    90deg,
    var(--slate-700) 0%,
    var(--slate-800) 50%,
    var(--slate-700) 100%
  );
}

.theme-dark .skeleton-animated .skeleton-text::after,
.theme-dark .skeleton-animated .skeleton-circle::after {
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.08) 50%,
    transparent 100%
  );
}
</style>
