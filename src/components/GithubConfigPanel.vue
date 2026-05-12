<template>
  <div class="github-config-panel">
    <h3>GitHub 项目保存配置</h3>
    
    <div class="config-section">
      <label class="switch">
        <input 
          type="checkbox" 
          v-model="useGithub" 
          @change="onUseGithubChange"
        >
        <span class="slider"></span>
      </label>
      <span class="switch-label">使用 GitHub 保存项目</span>
      <p class="help-text">
        启用后，项目将保存到您的 GitHub 仓库。禁用时使用本地 Git。
      </p>
    </div>

    <div v-if="useGithub" class="github-form">
      <div class="form-group">
        <label for="github-username">GitHub 用户名</label>
        <input
          id="github-username"
          type="text"
          v-model="githubUsername"
          placeholder="your-github-username"
          @blur="saveUsername"
        />
      </div>

      <div class="form-group">
        <label for="github-token">GitHub Personal Access Token</label>
        <input
          id="github-token"
          type="password"
          v-model="githubToken"
          placeholder="ghp_..."
          @blur="saveToken"
        />
        <p class="help-text">
          需要 repo 权限的 Personal Access Token。
          <a href="https://github.com/settings/tokens" target="_blank">创建 Token</a>
        </p>
      </div>

      <div class="status-section">
        <div v-if="isConfigured" class="status success">
          ✓ GitHub 配置已完成
        </div>
        <div v-else class="status warning">
          ⚠️ 请完成 GitHub 配置
        </div>
      </div>

      <button 
        class="test-button"
        @click="testConnection"
        :disabled="!isConfigured"
      >
        测试连接
      </button>
    </div>

    <div v-else class="offline-info">
      <p>当前使用本地 Git 保存项目。所有操作将在本地进行。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useGithubStore } from '@/stores/github'
import { ElMessage } from 'element-plus'

const githubStore = useGithubStore()

const useGithub = ref(false)
const githubUsername = ref('')
const githubToken = ref('')

// 计算属性
const isConfigured = computed(() => {
  return useGithub.value && githubUsername.value && githubToken.value
})

// 生命周期钩子
onMounted(() => {
  // 从 store 恢复配置
  githubStore.restoreGithubConfig()
  useGithub.value = githubStore.useGithub
  githubUsername.value = githubStore.githubUsername
  githubToken.value = githubStore.githubToken
})

// 方法
const onUseGithubChange = () => {
  githubStore.setUseGithub(useGithub.value)
}

const saveUsername = () => {
  githubStore.setGithubUsername(githubUsername.value)
}

const saveToken = () => {
  githubStore.setGithubToken(githubToken.value)
}

const testConnection = async () => {
  try {
    const response = await fetch('https://api.github.com/user', {
      headers: {
        'Authorization': `token ${githubToken.value}`,
        'Accept': 'application/vnd.github.v3+json'
      }
    })

    if (response.ok) {
      const userData = await response.json()
      if (userData.login === githubUsername.value) {
        ElMessage.success('GitHub 连接测试成功！')
      } else {
        ElMessage.warning('用户名与 Token 不匹配')
      }
    } else {
      ElMessage.error('GitHub 连接失败，请检查 Token')
    }
  } catch (error) {
    ElMessage.error('网络错误：' + error.message)
  }
}
</script>

<style scoped>
.github-config-panel {
  padding: 20px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-card);
}

.config-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.switch {
  position: relative;
  display: inline-block;
  width: 50px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: .4s;
  border-radius: 24px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 4px;
  bottom: 4px;
  background-color: white;
  transition: .4s;
  border-radius: 50%;
}

input:checked + .slider {
  background-color: #409eff;
}

input:checked + .slider:before {
  transform: translateX(26px);
}

.switch-label {
  font-weight: 500;
  color: var(--text-primary);
}

.help-text {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.github-form {
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: var(--text-primary);
}

.form-group input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text-primary);
}

.form-group input:focus {
  outline: none;
  border-color: #409eff;
}

.status-section {
  margin: 16px 0;
}

.status {
  padding: 8px 12px;
  border-radius: 4px;
  font-weight: 500;
}

.status.success {
  background: rgba(46, 204, 113, 0.1);
  color: #2ecc71;
}

.status.warning {
  background: rgba(241, 196, 15, 0.1);
  color: #f1c40f;
}

.test-button {
  padding: 8px 16px;
  background: #409eff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
}

.test-button:hover:not(:disabled) {
  background: #3488e7;
}

.test-button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.offline-info {
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 6px;
  color: var(--text-secondary);
}
</style>