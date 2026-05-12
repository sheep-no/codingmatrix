// src/utils/api/github.js
import axios from 'axios'

const githubApi = axios.create({
  baseURL: '/api/v1/github',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器：添加认证 token
githubApi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器：处理错误
githubApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token 失效，清除本地存储并跳转到登录页
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

/**
 * 设置 GitHub 配置
 */
export const setGithubConfig = async (config) => {
  const response = await githubApi.post('/config', config)
  return response.data
}

/**
 * 获取 GitHub 配置
 */
export const getGithubConfig = async () => {
  const response = await githubApi.get('/config')
  return response.data
}

/**
 * 保存项目到 GitHub 或本地 Git
 */
export const saveProjectToGithub = async (projectData, githubConfig) => {
  const requestData = {
    project_name: projectData.name,
    project_description: projectData.description || '',
    project_data: JSON.stringify(projectData.files),
    github_config: githubConfig
  }
  
  const response = await githubApi.post('/save', requestData)
  return response.data
}

export default githubApi