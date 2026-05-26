<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="$emit('update:modelValue', false)">
      <div class="modal-content settings-modal">
        <div class="modal-header"><h3>设置</h3><button class="modal-close" @click="$emit('update:modelValue', false)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg></button></div>
        <div class="modal-body">
          <div class="settings-section"><h4>AI 模型配置</h4>
            <div class="settings-grid">
              <div class="setting-item"><label>架构设计模型</label><select v-model="localSettings.models.architecture" class="setting-select"><option>Qwen3-Plus</option><option>Qwen3-Coder</option><option>DeepSeek-V3</option><option>GPT-4o</option></select></div>
              <div class="setting-item"><label>前端代码模型</label><select v-model="localSettings.models.frontend" class="setting-select"><option>Qwen3-Coder</option><option>Qwen3-Plus</option><option>DeepSeek-V3</option><option>Claude 3.5 Sonnet</option></select></div>
              <div class="setting-item"><label>后端代码模型</label><select v-model="localSettings.models.backend" class="setting-select"><option>Qwen3-Coder</option><option>Qwen3-Plus</option><option>DeepSeek-V3</option><option>Claude 3.5 Sonnet</option></select></div>
              <div class="setting-item"><label>测试代码模型</label><select v-model="localSettings.models.test" class="setting-select"><option>Qwen3-Coder</option><option>Qwen3-Plus</option><option>DeepSeek-V3</option></select></div>
              <div class="setting-item"><label>代码审查模型</label><select v-model="localSettings.models.review" class="setting-select"><option>Qwen3-Plus</option><option>Qwen3-Coder</option><option>DeepSeek-V3</option><option>GPT-4o</option></select></div>
            </div>
          </div>
          <div class="settings-section"><h4>生成配置</h4>
            <div class="settings-grid">
              <div class="setting-item"><label>最大并行数</label><input v-model.number="localSettings.maxConcurrent" type="number" min="1" max="10" class="setting-input" /></div>
              <div class="setting-item toggle-item"><label>代码审查</label><input v-model="localSettings.enableReview" type="checkbox" /></div>
              <div class="setting-item toggle-item"><label>验证检查</label><input v-model="localSettings.enableValidation" type="checkbox" /></div>
              <div class="setting-item toggle-item"><label>错误恢复</label><input v-model="localSettings.enableErrorRecovery" type="checkbox" /></div>
              <div class="setting-item toggle-item"><label>Spec-First</label><input v-model="localSettings.specFirst" type="checkbox" /></div>
              <div class="setting-item toggle-item"><label>依赖图构建</label><input v-model="localSettings.dependencyGraph" type="checkbox" /></div>
              <div class="setting-item toggle-item"><label>记忆增强</label><input v-model="localSettings.enableMemory" type="checkbox" /></div>
            </div>
          </div>
          <div v-if="concurrentLimits.recommended" class="settings-section"><h4>后端并发限制</h4>
            <div class="settings-grid"><div v-for="(val, k) in concurrentLimits.recommended" :key="k" class="setting-item"><label>{{ k }}</label><div class="limit-value">{{ val }}</div></div></div>
          </div>
          <div v-if="cacheStats.total_keys !== undefined" class="settings-section"><h4>缓存统计</h4>
            <div class="settings-grid">
              <div class="setting-item"><label>总缓存键数</label><div class="limit-value">{{ cacheStats.total_keys || 0 }}</div></div>
              <div class="setting-item"><label>命中率</label><div class="limit-value">{{ cacheStats.hit_rate ? Math.round(cacheStats.hit_rate * 100) + '%' : 'N/A' }}</div></div>
            </div>
            <button class="btn btn-sm btn-danger" @click="$emit('clear-cache')">清除缓存</button>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="$emit('export')">导出性能</button>
          <button class="btn btn-outline" @click="$emit('copy', localSettings)">复制配置</button>
          <button class="btn btn-primary" @click="$emit('save', localSettings)">保存</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({ modelValue: Boolean, settings: { type: Object, required: true }, concurrentLimits: { type: Object, required: true }, cacheStats: { type: Object, required: true } })
const emit = defineEmits(['update:modelValue', 'save', 'copy', 'export', 'clear-cache'])

// Local editable copy
const localSettings = ref(JSON.parse(JSON.stringify(props.settings)))

// Sync with parent when modal opens
watch(() => props.modelValue, (open) => {
  if (open) localSettings.value = JSON.parse(JSON.stringify(props.settings))
})
</script>

<style scoped>
.settings-modal { max-width: 900px; }
.settings-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.setting-item { background: var(--bg-tertiary); padding: 10px; border-radius: 8px; }
.setting-item label { display: block; font-size: 11px; color: var(--text-secondary); margin-bottom: 6px; }
.setting-select, .setting-input { width: 100%; padding: 6px 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-primary); color: var(--text-primary); font-size: 12px; }
.toggle-item { display: flex; align-items: center; justify-content: space-between; }
.limit-value { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600; }
.btn-outline { background: transparent; border: 1px solid var(--border-color); color: var(--text-primary); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-danger { background: var(--danger); color: white; }
.btn-primary { background: var(--primary); color: white; }
</style>
