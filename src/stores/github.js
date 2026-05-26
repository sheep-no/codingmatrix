import { ref } from 'vue'
import { defineStore } from 'pinia'

function simpleHexEncode(str) {
  let hex = ''
  for (let i = 0; i < str.length; i++) {
    hex += str.charCodeAt(i).toString(16).padStart(2, '0')
  }
  return hex
}

function simpleHexDecode(hex) {
  let str = ''
  for (let i = 0; i < hex.length; i += 2) {
    str += String.fromCharCode(parseInt(hex.substr(i, 2), 16))
  }
  return str
}

function getStoredToken() {
  const stored = localStorage.getItem('github_token')
  if (!stored) return ''
  try {
    return simpleHexDecode(stored)
  } catch {
    return ''
  }
}

export const useGithubStore = defineStore(
  'github',
  () => {
    const githubUsername = ref(localStorage.getItem('github_username') || '')
    const githubToken = ref(getStoredToken())
    const useGithub = ref(localStorage.getItem('use_github') === 'true')

    function setGithubUsername(username) {
      githubUsername.value = username
      localStorage.setItem('github_username', username)
    }

    function setGithubToken(token) {
      if (token) {
        const encodedToken = simpleHexEncode(token)
        localStorage.setItem('github_token', encodedToken)
        githubToken.value = token
      } else {
        localStorage.removeItem('github_token')
        githubToken.value = ''
      }
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
      localStorage.removeItem('github_token')
      localStorage.removeItem('use_github')
    }

    function getGithubConfig() {
      return {
        username: githubUsername.value,
        token: githubToken.value,
        useGithub: useGithub.value
      }
    }

    function isGithubConfigured() {
      return useGithub.value && githubUsername.value && githubToken.value
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
      paths: ['githubUsername', 'githubToken', 'useGithub']
    }
  }
)
