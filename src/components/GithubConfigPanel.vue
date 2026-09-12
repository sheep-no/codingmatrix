<template>
  <div class="github-config-panel">
    <h3>GitHub 项目保存配置</h3>
    
    <div class="config-section">
      <label class="switch">
        <input 
          v-model="useGithub" 
          type="checkbox" 
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
          v-model="githubUsername"
          type="text"
          placeholder="your-github-username"
          @blur="saveUsername"
        />
      </div>

      <div class="form-group">
        <label for="github-token">GitHub Personal Access Token</label>
        <input
          id="github-token"
          v-model="githubToken"
          type="password"
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
          [WARNING] 请完成 GitHub 配置
        </div>
        
        <!-- 连接状态显示 -->
        <div v-if="connectionStatus" class="connection-status" :class="connectionStatus.type">
          {{ connectionStatus.message }}
        </div>
      </div>

      <button 
        class="test-button"
        :disabled="!isConfigured"
        @click="testConnection"
      >
        测试连接
      </button>
      <ul v-if="repos.length" class="repo-list">
        <li v-for="repo in repos" :key="repo.full_name">
          <button type="button" class="repo-button" @click="loadBranches(repo)">
            {{ repo.full_name }}
          </button>
        </li>
      </ul>
      <div v-if="branches.length" class="branch-list">
        <button
          v-for="branch in branches"
          :key="branch.name"
          type="button"
          class="branch-button"
          @click="loadCommits(branch.name)"
        >
          {{ branch.name }}
        </button>
      </div>
      <ul v-if="commits.length" class="commit-list">
        <li v-for="commit in commits" :key="commit.sha">
          {{ commit.message }}
        </li>
      </ul>
    </div>

    <div v-else class="offline-info">
      <p>当前使用本地 Git 保存项目。所有操作将在本地进行。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useGithubStore } from '@/stores/github'
import { ElMessage } from 'element-plus'
import { createGithubClient } from '@/utils/api/github'

const githubStore = useGithubStore()
const githubClient = createGithubClient()

const useGithub = ref(false)
const githubUsername = ref('')
const githubToken = ref('')
const connectionStatus = ref(null)

const repos = ref([])
const branches = ref([])
const commits = ref([])
const selectedRepo = ref(null)

// 计算属性
const isConfigured = computed(() => {
  return useGithub.value && githubUsername.value && githubToken.value
})

// 监听配置变化，自动测试连接
watch(isConfigured, async (newVal) => {
  if (newVal) {
    await autoTestConnection()
  }
})

// 生命周期钩子
onMounted(() => {
  useGithub.value = githubStore.useGithub
  githubUsername.value = githubStore.githubUsername
  githubToken.value = githubStore.githubToken

  // 如果已配置，自动测试连接
  if (isConfigured.value) {
    autoTestConnection()
  }
})

// 方法
const onUseGithubChange = () => {
  githubStore.setUseGithub(useGithub.value)
}

const saveUsername = () => {
  githubStore.setGithubUsername(githubUsername.value)
  if (isConfigured.value) {
    autoTestConnection()
  }
}

const saveToken = () => {
  githubStore.setGithubToken(githubToken.value)
  if (isConfigured.value) {
    autoTestConnection()
  }
}

const autoTestConnection = async () => {
  try {
    if (githubUsername.value && githubToken.value) {
      await githubClient.setGithubConfig({
        username: githubUsername.value,
        token: githubToken.value,
        use_github: useGithub.value
      })
    }
    const result = await githubClient.verifyGithub()
    connectionStatus.value = {
      type: result.verified ? 'success' : 'warning',
      message: result.message || (result.verified ? 'GitHub 连接正常' : '用户名与 Token 不匹配')
    }
    return result.verified === true
  } catch (error) {
    connectionStatus.value = {
      type: 'error',
      message: error.response?.data?.detail || 'GitHub 验证失败，请先保存配置'
    }
    return false
  }
}

const testConnection = async () => {
  repos.value = []
  branches.value = []
  commits.value = []
  selectedRepo.value = null
  const verified = await autoTestConnection()
  if (!verified) {
    ElMessage.warning(connectionStatus.value?.message || 'GitHub 验证未通过')
    return
  }
  try {
    const data = await githubClient.listRepos()
    repos.value = data.repos || []
    ElMessage.success('GitHub 连接测试成功')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '仓库列表读取失败')
  }
}

const loadBranches = async (repo) => {
  selectedRepo.value = repo
  branches.value = []
  commits.value = []
  try {
    const data = await githubClient.listBranches(repo.owner, repo.name)
    branches.value = data.branches || []
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '分支列表读取失败')
  }
}

const loadCommits = async (sha) => {
  if (!selectedRepo.value) return
  commits.value = []
  try {
    const data = await githubClient.listCommits(
      selectedRepo.value.owner,
      selectedRepo.value.name,
      sha
    )
    commits.value = data.commits || []
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '提交列表读取失败')
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

.status, .connection-status {
  padding: 8px 12px;
  border-radius: 4px;
  font-weight: 500;
  margin-bottom: 8px;
}

.status.success, .connection-status.success {
  background: rgba(46, 204, 113, 0.1);
  color: #2ecc71;
}

.status.warning, .connection-status.warning {
  background: rgba(241, 196, 15, 0.1);
  color: #f1c40f;
}

.connection-status.error {
  background: rgba(231, 76, 60, 0.1);
  color: #e74c3c;
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
.repo-list,
.commit-list {
  margin: 12px 0 0;
  padding-left: 18px;
}

.repo-button,
.branch-button {
  margin: 4px 8px 0 0;
  padding: 4px 8px;
  cursor: pointer;
}
</style>
