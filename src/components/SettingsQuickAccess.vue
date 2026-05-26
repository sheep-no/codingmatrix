<template>
  <el-button 
    type="primary" 
    :icon="Setting"
    circle
    class="settings-quick-access"
    title="API Key 管理"
    @click="$router.push('/settings')"
  />
</template>

<script setup>
import { Setting } from '@element-plus/icons-vue'
</script>

<style scoped>
.settings-quick-access {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.settings-quick-access:hover {
  transform: scale(1.05);
  transition: transform 0.3s;
}
</style>
