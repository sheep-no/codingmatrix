<template>
  <div class="settings-page">
    <h1 class="page-title">设置</h1>
    <div class="settings-tabs" role="tablist" aria-label="设置分类">
      <button id="settings-tab-providers" :class="['tab', { active: currentTab === 'providers' }]" role="tab" aria-controls="settings-panel" :aria-selected="currentTab === 'providers'" :tabindex="currentTab === 'providers' ? 0 : -1" @click="currentTab = 'providers'" @keydown="handleTabKey">
        <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        自定义供应商
      </button>
      <button id="settings-tab-apikey" :class="['tab', { active: currentTab === 'apikey' }]" role="tab" aria-controls="settings-panel" :aria-selected="currentTab === 'apikey'" :tabindex="currentTab === 'apikey' ? 0 : -1" @click="currentTab = 'apikey'" @keydown="handleTabKey">
        <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
        API Key 管理
      </button>
      <button id="settings-tab-agent" :class="['tab', { active: currentTab === 'agent' }]" role="tab" aria-controls="settings-panel" :aria-selected="currentTab === 'agent'" :tabindex="currentTab === 'agent' ? 0 : -1" @click="currentTab = 'agent'" @keydown="handleTabKey">
        <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>
        Agent 模型配置
      </button>
      <button v-if="isSuperUser" id="settings-tab-admin" :class="['tab', { active: currentTab === 'admin' }]" role="tab" aria-controls="settings-panel" :aria-selected="currentTab === 'admin'" :tabindex="currentTab === 'admin' ? 0 : -1" @click="currentTab = 'admin'" @keydown="handleTabKey">
        <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
        系统模型管理
      </button>
      <button v-if="isSuperUser" id="settings-tab-unified" :class="['tab', { active: currentTab === 'unified' }]" role="tab" aria-controls="settings-panel" :aria-selected="currentTab === 'unified'" :tabindex="currentTab === 'unified' ? 0 : -1" @click="currentTab = 'unified'" @keydown="handleTabKey">
        <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="9" x2="15" y2="9"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="12" y2="17"/></svg>
        统一模型配置 (v2)
      </button>
    </div>
    <div id="settings-panel" class="settings-content" role="tabpanel" :aria-labelledby="`settings-tab-${currentTab}`" tabindex="0">
      <DynamicProviderManager v-if="currentTab === 'providers'" />
      <APIKeyManager v-else-if="currentTab === 'apikey'" />
      <AgentModelConfig v-else-if="currentTab === 'agent'" />
      <AdminModelManager v-else-if="currentTab === 'admin' && isSuperUser" />
      <UnifiedModelConfig v-else-if="currentTab === 'unified' && isSuperUser" />
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
import UnifiedModelConfig from '@/components/settings/UnifiedModelConfig.vue'

const route = useRoute()
const userStore = useUserStore()
const isSuperUser = computed(() => userStore.isSuperUser)
const currentTab = ref('providers')

function handleTabKey(event) {
  const tabs = [...event.currentTarget.parentElement.querySelectorAll('[role="tab"]')]
  const index = tabs.indexOf(event.currentTarget)
  let next = index
  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % tabs.length
  if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + tabs.length) % tabs.length
  if (event.key === 'Home') next = 0
  if (event.key === 'End') next = tabs.length - 1
  if (next === index) return
  event.preventDefault()
  tabs[next].click()
  tabs[next].focus()
}

onMounted(() => {
  const allowedTabs = ['providers', 'apikey', 'agent', 'admin', 'unified']
  if (allowedTabs.includes(route.query.tab) && (['admin', 'unified'].includes(route.query.tab) ? isSuperUser.value : true)) {
    currentTab.value = route.query.tab
  }
})
</script>

<style scoped>
.settings-page { padding: 32px; max-width: 1200px; margin: 0 auto; min-height: 100vh; overflow-y: auto; box-sizing: border-box; color: var(--text-primary); }
.page-title { font-size: 24px; margin-bottom: 24px; color: #303133; }
.settings-tabs { display: flex; gap: 8px; margin-bottom: 24px; border-bottom: 1px solid var(--border-color); overflow-x: auto; scrollbar-width: thin; }
.tab { flex: 0 0 auto; padding: 13px 18px; background: transparent; border: none; border-bottom: 3px solid transparent; cursor: pointer; font-size: 15px; color: var(--text-secondary); transition: all 0.2s; display: flex; align-items: center; gap: 8px; }
.tab:hover { color: #409eff; }
.tab.active { color: #409eff; border-bottom-color: #409eff; font-weight: 600; }
.tab-icon { width: 18px; height: 18px; }
.settings-content { min-width: 0; background: var(--bg-primary); border-radius: 12px; box-shadow: var(--shadow-sm, 0 2px 12px rgba(0, 0, 0, 0.1)); }
.tab:focus-visible, .settings-content:focus-visible { outline: 2px solid var(--color-primary, #409eff); outline-offset: 3px; }
@media (max-width: 600px) {
  .settings-page { padding: 20px 16px; }
  .page-title { font-size: 22px; margin-bottom: 18px; }
  .settings-tabs { margin-right: -16px; padding-right: 16px; }
  .tab { padding: 12px 14px; font-size: 14px; }
}
</style>
