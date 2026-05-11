<template>
  <div class="agent-project-preview">
    <div class="preview-header">
      <div class="url-bar">
        <button class="btn-icon-sm" title="刷新" @click="refresh">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
        </button>
        <input
          v-model="previewUrl"
          class="url-input"
          placeholder="输入预览 URL..."
          @keydown.enter="refresh"
        />
        <button class="btn-icon-sm" title="在新标签页打开" @click="openExternal">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </button>
      </div>
      <div class="preview-device">
        <button
          v-for="device in devices"
          :key="device.key"
          :class="['device-btn', { active: currentDevice === device.key }]"
          @click="currentDevice = device.key"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" v-html="device.icon" />
        </button>
      </div>
    </div>

    <div class="preview-content" :class="'device-' + currentDevice">
      <iframe
        v-if="previewUrl"
        :src="previewUrl"
        frameborder="0"
        class="preview-frame"
      ></iframe>
      <div v-else class="preview-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
          <line x1="8" y1="21" x2="16" y2="21"/>
          <line x1="12" y1="17" x2="12" y2="21"/>
        </svg>
        <p>启动预览以查看项目效果</p>
        <button class="btn-primary" @click="$emit('startPreview')">
          启动预览
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref } from 'vue'

  const props = defineProps({
    url: { type: String, default: '' }
  })

  const emit = defineEmits(['startPreview'])

  const previewUrl = ref(props.url)
  const currentDevice = ref('desktop')

  const devices = [
    {
      key: 'desktop',
      icon: '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>'
    },
    {
      key: 'tablet',
      icon: '<rect x="4" y="2" width="16" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18.01"/>'
    },
    {
      key: 'mobile',
      icon: '<rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18.01"/>'
    }
  ]

  function refresh() {
    const iframe = document.querySelector('.preview-frame')
    if (iframe) iframe.src = iframe.src
  }

  function openExternal() {
    if (previewUrl.value) window.open(previewUrl.value, '_blank')
  }
</script>

<style scoped>
  .agent-project-preview {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-secondary, #16213e);
  }

  .preview-header {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
  }

  .url-bar {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: 8px;
    background: var(--bg-tertiary, #1f2937);
    border: 1px solid var(--border-color, #2d3748);
  }

  .url-input {
    flex: 1;
    border: none;
    background: transparent;
    color: var(--text-primary, #e0e0e0);
    font-size: 13px;
    font-family: monospace;
  }

  .url-input:focus { outline: none; }

  .btn-icon-sm {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    flex-shrink: 0;
  }

  .btn-icon-sm:hover { background: var(--bg-hover, #374151); }
  .btn-icon-sm svg { width: 14px; height: 14px; }

  .preview-device {
    display: flex;
    gap: 4px;
  }

  .device-btn {
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .device-btn:hover { background: var(--bg-hover, #374151); }
  .device-btn.active { background: var(--accent-muted, #4f46e533); color: var(--accent-color, #4f46e5); }
  .device-btn svg { width: 18px; height: 18px; }

  .preview-content {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-tertiary, #1f2937);
    overflow: hidden;
  }

  .device-desktop .preview-frame { width: 100%; height: 100%; }
  .device-tablet .preview-frame { width: 768px; height: 90%; border-radius: 12px; border: 1px solid var(--border-color, #2d3748); }
  .device-mobile .preview-frame { width: 375px; height: 90%; border-radius: 16px; border: 1px solid var(--border-color, #2d3748); }

  .preview-frame { width: 100%; height: 100%; background: white; }

  .preview-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    color: var(--text-secondary, #9ca3af);
  }

  .preview-empty svg { width: 64px; height: 64px; opacity: 0.3; margin-bottom: 16px; }
  .preview-empty p { font-size: 14px; margin-bottom: 16px; }

  .btn-primary {
    padding: 8px 20px;
    border-radius: 6px;
    border: none;
    background: var(--accent-color, #4f46e5);
    color: white;
    font-size: 13px;
    cursor: pointer;
  }
</style>
