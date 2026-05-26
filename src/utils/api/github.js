// src/utils/api/github.js (v5.0.2 统一客户端模式)
import axios from 'axios'

let githubApi = null

function getGithubApi() {
  if (!githubApi) {
    githubApi = axios.create({
      baseURL: '/api/v1/github',
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json'
      }
    })

    githubApi.interceptors.request.use(
      (config) => {
        const token = window.api?._userStore?.getAccessToken?.() || localStorage.getItem('access_token')
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    githubApi.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem('access_token')
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )
  }
  return githubApi
}

export function createGithubClient() {
  const api = getGithubApi()

  return {
    async setGithubConfig(config) {
      const response = await api.post('/config', config)
      return response.data
    },

    async getGithubConfig() {
      const response = await api.get('/config')
      return response.data
    },

    async saveProjectToGithub(projectData, githubConfig) {
      const requestData = {
        project_name: projectData.name,
        project_description: projectData.description || '',
        project_data: JSON.stringify(projectData.files),
        github_config: githubConfig
      }
      const response = await api.post('/save', requestData)
      return response.data
    }
  }
}

export default { createGithubClient }