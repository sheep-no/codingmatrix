<template>
  <div v-if="message.reasoning?.trim()" class="thinking-section markdown-body">
    <template v-if="hasGroups">
      <details
        v-for="(data, agent) in message.thinkingGroups"
        :key="agent"
        class="thinking-details"
        :open="message.isStreaming || message.thinkingOpen !== false"
      >
        <summary class="thinking-summary" :aria-label="`${agent} 思考过程，点击展开或收起`">
          <div class="thinking-indicator">
            <div v-if="message.isStreaming" class="thinking-pulse" aria-hidden="true"></div>
            <InfoIcon v-else />
            <span>{{ agent }} 思考过程</span>
            <span v-if="data.model" class="thinking-model">({{ data.model }})</span>
          </div>
          <ChevronIcon />
        </summary>
        <div class="thinking-content" v-html="renderMarkdown(data.content)"></div>
      </details>
    </template>
    <details v-else class="thinking-details" :open="message.isStreaming || message.thinkingOpen !== false">
      <summary class="thinking-summary" aria-label="深度思考过程，点击展开或收起">
        <div class="thinking-indicator">
          <div v-if="message.isStreaming" class="thinking-pulse" aria-hidden="true"></div>
          <InfoIcon v-else />
          <span>{{ message.isStreaming ? '正在思考...' : '深度思考过程' }}</span>
        </div>
        <ChevronIcon />
      </summary>
      <div class="thinking-content" v-html="renderMarkdown(message.reasoning)"></div>
    </details>
  </div>
</template>

<script setup>
import { computed, h } from 'vue'

const props = defineProps({
  message: { type: Object, required: true },
  renderMarkdown: { type: Function, required: true }
})

const hasGroups = computed(() => Object.keys(props.message.thinkingGroups || {}).length > 0)
const InfoIcon = () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'aria-hidden': 'true' }, [
  h('circle', { cx: 12, cy: 12, r: 10 }),
  h('path', { d: 'M12 16v-4' }),
  h('path', { d: 'M12 8h.01' })
])
const ChevronIcon = () => h('svg', { class: 'chevron', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'aria-hidden': 'true' }, [
  h('polyline', { points: '6 9 12 15 18 9' })
])
</script>

<style scoped>
.thinking-section { margin-bottom: 14px; }
.thinking-details { overflow: hidden; background: transparent; border: 0; border-left: 2px solid color-mix(in srgb, #c45c26 50%, var(--accent-primary)); border-radius: 0; padding-left: 12px; }
.thinking-details:hover { border-color: #c45c26; }
.thinking-pulse { width: 6px; height: 6px; border-radius: 50%; background: var(--accent-primary); animation: thinking-pulse 1.4s ease-in-out infinite; }
.thinking-summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 0 8px; color: var(--text-tertiary); font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; list-style: none; cursor: pointer; }
.thinking-summary::marker { display: none; }
.thinking-summary:hover { color: var(--text-secondary); }
.thinking-indicator { display: flex; align-items: center; gap: 8px; }
.thinking-indicator svg, .chevron { width: 14px; height: 14px; }
.thinking-indicator svg { opacity: 0.8; }
.thinking-model { margin-left: 4px; color: var(--content-muted); font-size: 11px; font-weight: normal; }
.chevron { transition: transform var(--motion-fast); }
.thinking-details[open] .chevron { transform: rotate(180deg); }
.thinking-content { padding: 4px 0 8px; color: var(--text-secondary); font-size: 13px; line-height: 1.7; background: transparent; border-top: 0; }
@keyframes thinking-pulse { 0%, 100% { opacity: 0.8; transform: scale(1); } 50% { opacity: 1; transform: scale(1.2); } }
</style>
