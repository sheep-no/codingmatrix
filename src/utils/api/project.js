/**
 * 项目生成 API 客户端 (v5.0.2 全量补全)
 */
import { createBaseClient, apiUrl } from './base'

export function createProjectClient(baseClient) {
  const client = baseClient || createBaseClient()

  return {
    async generateProject(data) {
      const response = await client.post('/agent/generate', data)
      if (response.ok) {
        return response
      }
      throw new Error('生成项目失败')
    },

    async generateProjectStream(data) {
      const response = await client.post('/agent/orchestrate/stream', data)
      if (response.ok) {
        return response
      }
      throw new Error('流式生成项目失败')
    },

    async stopSession(sessionId) {
      const response = await client.post(`/agent/session/${sessionId}/action?action=cancel`)
      if (response.ok) {
        return await response.json()
      }
      throw new Error('停止会话失败')
    },

    async deleteSession(sessionId) {
      const response = await client.delete(`/agent/sessions/${sessionId}`)
      if (response.ok) {
        return await response.json()
      }
      throw new Error('删除会话失败')
    },

    async submitDecision(sessionId, decisions) {
      const response = await client.post(`/agent/session/${sessionId}/decision`, decisions)
      if (response.ok) {
        return await response.json()
      }
      throw new Error('提交决策失败')
    },

    async listSavedProjects() {
      const response = await client.get('/agent/saved')
      if (response.ok) {
        return await response.json()
      }
      throw new Error('获取项目列表失败')
    },

    async getSavedProjects() {
      return this.listSavedProjects()
    },

    async loadProject(projectId) {
      const response = await client.get(`/agent/saved/${projectId}`)
      if (response.ok) {
        return await response.json()
      }
      throw new Error('加载项目失败')
    },

    async deleteProject(projectId) {
      const response = await client.delete(`/agent/saved/${projectId}`)
      if (response.ok) {
        return await response.json()
      }
      throw new Error('删除项目失败')
    },

    async saveProject(name, description, projectData) {
      const response = await client.post('/agent/save', {
        name,
        description,
        project_data: projectData
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('保存项目失败')
    },

    downloadProject(projectPath) {
      return `${apiUrl}/agent/generate/download/${encodeURIComponent(projectPath)}`
    },

    async getProjectFiles(params) {
      const response = await client.get('/agent/generate/files', params)
      if (response.ok) {
        return await response.json()
      }
      throw new Error('获取项目文件列表失败')
    },

    async readProjectFile(params) {
      const response = await client.get('/agent/generate/read', params)
      if (response.ok) {
        return await response.json()
      }
      throw new Error('读取文件内容失败')
    },

    async deleteProjectFile(params) {
      const response = await client.delete('/agent/generate/file', params)
      if (response.ok) {
        return await response.json()
      }
      throw new Error('删除项目文件失败')
    },

    async modifyProject(data) {
      const response = await client.post('/agent/modify', data)
      if (response.ok) {
        return response
      }
      throw new Error('增量修改项目失败')
    },

    async modifyProjectStream(data, signal) {
      const response = await client.stream('/agent/modify', data, signal)
      if (response.ok) {
        return response
      }
      throw new Error('流式增量修改失败')
    },

    async analyzeComplexity(requirement) {
      const response = await client.post('/agent/analyze_complexity', {
        requirement: requirement
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('复杂度分析失败')
    },

    async downloadProject(projectPath) {
      const response = await client.get(`/agent/generate/download/${encodeURIComponent(projectPath)}`)
      if (response.ok) {
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'project.zip'
        a.click()
        window.URL.revokeObjectURL(url)
      } else {
        throw new Error('下载项目失败')
      }
    },

    async evaluateRequirement(requirement, api_key_token) {
      const response = await client.post('/agent/evaluate', {
        requirement: requirement,
        api_key_token: api_key_token
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('需求评价失败')
    }
  }
}
