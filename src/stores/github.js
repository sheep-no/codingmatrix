import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useGithubStore = defineStore(
  'github',
  () => {
    // GitHub 配置状态
    const githubUsername = ref('')
    const githubToken = ref('')
    const useGithub = ref(false) // 是否使用 GitHub 而不是离线 Git

    /**
     * 设置 GitHub 用户名
     */
    function setGithubUsername(username) {
      githubUsername.value = username
      localStorage.setItem('github_username', username)
    }

    /**
     * 设置 GitHub Token（加密存储）
     */
    function setGithubToken(token) {
      if (token) {
        // 简单的 base64 编码（实际应该使用更安全的加密）
        const encodedToken = btoa(token)
        localStorage.setItem('github_token', encodedToken)
        githubToken.value = token
      } else {
        localStorage.removeItem('github_token')
        githubToken.value = ''
      }
    }

    /**
     * 启用/禁用 GitHub 集成
     */
    function setUseGithub(enabled) {
      useGithub.value = enabled
      localStorage.setItem('use_github', enabled ? 'true' : 'false')
    }

    /**
     * 从 localStorage 恢复 GitHub 配置
     */
    function restoreGithubConfig() {
      const storedUsername = localStorage.getItem('github_username')
      const storedUseGithub = localStorage.getItem('use_github')
      
      if (storedUsername) {
        githubUsername.value = storedUsername
      }
      
      if (storedUseGithub) {
        useGithub.value = storedUseGithub === 'true'
      }
      
      // 恢复 token（如果存在）
      const storedToken = localStorage.getItem('github_token')
      if (storedToken) {
        try {
          githubToken.value = atob(storedToken)
        } catch (error) {
          console.error('Failed to decode GitHub token:', error)
          githubToken.value = ''
        }
      }
    }

    /**
     * 清除 GitHub 配置
     */
    function clearGithubConfig() {
      githubUsername.value = ''
      githubToken.value = ''
      useGithub.value = false
      
      localStorage.removeItem('github_username')
      localStorage.removeItem('github_token')
      localStorage.removeItem('use_github')
    }

    /**
     * 获取 GitHub 配置对象
     */
    function getGithubConfig() {
      return {
        username: githubUsername.value,
        token: githubToken.value,
        useGithub: useGithub.value
      }
    }

    /**
     * 检查 GitHub 配置是否完整
     */
    function isGithubConfigured() {
      return useGithub.value && githubUsername.value && githubToken.value
    }

    return {
      // 状态
      githubUsername,
      githubToken,
      useGithub,

      // 方法
      setGithubUsername,
      setGithubToken,
      setUseGithub,
      restoreGithubConfig,
      clearGithubConfig,
      getGithubConfig,
      isGithubConfigured
    }
  },
  {
    persist: {
      key: 'github-store',
      storage: localStorage,
      paths: ['githubUsername', 'useGithub']
    }
  }
)