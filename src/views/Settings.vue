<template>
  <div class="settings-page">
    <h1 class="page-title">设置</h1>
    <div class="settings-tabs">
      <button :class="['tab', { active: currentTab === 'providers' }]" @click="currentTab = 'providers'">
        🌐 自定义供应商
      </button>
      <button :class="['tab', { active: currentTab === 'apikey' }]" @click="currentTab = 'apikey'">
        🔑 API Key 管理
      </button>
      <button :class="['tab', { active: currentTab === 'agent' }]" @click="currentTab = 'agent'">
        🤖 Agent 模型配置
      </button>
    </div>
    <div class="settings-content">
      <DynamicProviderManager v-if="currentTab === 'providers'" />
      <APIKeyManager v-else-if="currentTab === 'apikey'" />
      <AgentModelConfig v-else />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import DynamicProviderManager from '@/components/settings/DynamicProviderManager.vue'
import APIKeyManager from '@/components/settings/APIKeyManager.vue'
import AgentModelConfig from '@/components/settings/AgentModelConfig.vue'

const currentTab = ref('providers')
</script>

<style scoped>
.settings-page { padding: 24px; max-width: 1200px; margin: 0 auto; }
.page-title { font-size: 24px; margin-bottom: 24px; color: #303133; }
.settings-tabs { display: flex; gap: 8px; margin-bottom: 24px; border-bottom: 2px solid #e0e0e0; }
.tab { padding: 12px 24px; background: transparent; border: none; border-bottom: 3px solid transparent; cursor: pointer; font-size: 16px; color: #606266; transition: all 0.3s; }
.tab:hover { color: #409eff; }
.tab.active { color: #409eff; border-bottom-color: #409eff; font-weight: 600; }
.settings-content { background: #fff; border-radius: 8px; box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1); }
</style>
