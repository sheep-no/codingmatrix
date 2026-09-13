import { ref } from 'vue'
import { defineStore } from 'pinia'

function purgeStoredToken() {
  sessionStorage.removeItem('github_token')
  localStorage.removeItem('github_token')
  try {
    const persisted = JSON.parse(localStorage.getItem('github-store') || '{}')
    if (persisted.githubToken) {
      delete persisted.githubToken
      localStorage.setItem('github-store', JSON.stringify(persisted))
    }
  } catch {
    localStorage.removeItem('github-store')
  }
}

export const useGithubStore = defineStore(
  'github',
  () => {
    purgeStoredToken()
    const githubUsername = ref(localStorage.getItem('github_username') || '')
    const githubToken = ref('')
    const useGithub = ref(localStorage.getItem('use_github') === 'true')

    function setGithubUsername(username) {
      githubUsername.value = username
      localStorage.setItem('github_username', username)
    }

    function setGithubToken(token) {
      githubToken.value = token || ''
    }

    function setUseGithub(enabled) {
      useGithub.value = enabled
      localStorage.setItem('use_github', enabled ? 'true' : 'false')
    }

    function clearGithubConfig() {
      githubUsername.value = ''
      githubToken.value = ''
      useGithub.value = false

      localStorage.removeItem('github_username')
      sessionStorage.removeItem('github_token')
      localStorage.removeItem('github_token')
      localStorage.removeItem('use_github')
    }

    function getGithubConfig() {
      return {
        username: githubUsername.value,
        token: '',
        useGithub: useGithub.value
      }
    }

    function isGithubConfigured() {
      return useGithub.value && !!githubUsername.value
    }

    return {
      githubUsername,
      githubToken,
      useGithub,
      setGithubUsername,
      setGithubToken,
      setUseGithub,
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
