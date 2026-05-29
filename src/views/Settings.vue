<template>
  <div class="settings-page">
    <h1 class="page-title">设置</h1>
    <div class="settings-tabs">
      <button :class="['tab', { active: currentTab === 'providers' }]" @click="currentTab = 'providers'">
        <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        自定义供应商
      </button>
      <button :class="['tab', { active: currentTab === 'apikey' }]" @click="currentTab = 'apikey'">
        <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
        API Key 管理
      </button>
      <button :class="['tab', { active: currentTab === 'agent' }]" @click="currentTab = 'agent'">
        <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>
        Agent 模型配置
      </button>
      <button v-if="isSuperUser" :class="['tab', { active: currentTab === 'admin' }]" @click="currentTab = 'admin'">
        <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
        系统模型管理
      </button>
    </div>
    <div class="settings-content">
      <DynamicProviderManager v-if="currentTab === 'providers'" />
      <APIKeyManager v-else-if="currentTab === 'apikey'" />
      <AgentModelConfig v-else-if="currentTab === 'agent'" />
      <AdminModelManager v-else-if="currentTab === 'admin' && isSuperUser" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import DynamicProviderManager from '@/components/settings/DynamicProviderManager.vue'
import APIKeyManager from '@/components/settings/APIKeyManager.vue'
import AgentModelConfig from '@/components/settings/AgentModelConfig.vue'
import AdminModelManager from '@/components/settings/AdminModelManager.vue'

const route = useRoute()
const userStore = useUserStore()
const isSuperUser = computed(() => userStore.isSuperUser)
const currentTab = ref('providers')

onMounted(() => {
  if (route.query.tab) {
    currentTab.value = route.query.tab
  }
})
</script>

<style scoped>
.settings-page { padding: 24px; max-width: 1200px; margin: 0 auto; }
.page-title { font-size: 24px; margin-bottom: 24px; color: #303133; }
.settings-tabs { display: flex; gap: 8px; margin-bottom: 24px; border-bottom: 2px solid #e0e0e0; flex-wrap: wrap; }
.tab { padding: 12px 24px; background: transparent; border: none; border-bottom: 3px solid transparent; cursor: pointer; font-size: 16px; color: #606266; transition: all 0.3s; display: flex; align-items: center; gap: 8px; }
.tab:hover { color: #409eff; }
.tab.active { color: #409eff; border-bottom-color: #409eff; font-weight: 600; }
.tab-icon { width: 18px; height: 18px; }
.settings-content { background: #fff; border-radius: 8px; box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1); }
</style>
