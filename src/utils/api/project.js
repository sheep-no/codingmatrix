/**
 * 项目生成 API 客户端 (v5.0.2 全量补全)
 */
import { createBaseClient } from './base'

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
      // 429 并发限制：解析结构化错误信息
      if (response.status === 429) {
        try {
          const errorData = await response.json()
          const detail = errorData.detail || errorData
          const err = new Error(detail.message || '已达到并发会话限制')
          err.code = 429
          err.activeSessions = detail.active_sessions || []
          err.currentCount = detail.current_count || 0
          err.limit = detail.limit || 0
          throw err
        } catch (e) {
          if (e.code === 429) throw e
          const err = new Error('已达到并发会话限制，请停止或删除现有项目后再创建新项目')
          err.code = 429
          throw err
        }
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

    async getAgentModelContext(sessionId) {
      const response = await client.get(`/agent/sessions/${sessionId}/model-context`)
      if (response.ok) return await response.json()
      throw new Error('获取模型上下文失败')
    },

    async updateAgentModelContext(sessionId, context) {
      const response = await client.put(`/agent/sessions/${sessionId}/model-context`, context)
      if (response.ok) return await response.json()
      if (response.status === 409) return { conflict: true }
      throw new Error('更新模型上下文失败')
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
      const queryString = new URLSearchParams(params).toString()
      const response = await client.delete(`/agent/generate/file?${queryString}`)
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

    async uploadProjectZip(file, projectName = '') {
      const formData = new FormData()
      formData.append('file', file)
      const query = projectName ? `?project_name=${encodeURIComponent(projectName)}` : ''
      const response = await client.request(`/agent/projects/upload-zip${query}`, {
        method: 'POST',
        body: formData
      })
      if (!response.ok) throw new Error(`上传项目失败 (${response.status})`)
      return response.json()
    },

    async listUploadedProjects() {
      const response = await client.get('/agent/projects/user-uploads')
      if (!response.ok) throw new Error(`获取上传项目失败 (${response.status})`)
      return response.json()
    },

    async deleteUploadedProject(projectName) {
      const response = await client.delete(`/agent/projects/user-uploads/${encodeURIComponent(projectName)}`)
      if (!response.ok) throw new Error(`删除上传项目失败 (${response.status})`)
      return response.json()
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
    },

    // ========== 搜索会话 ==========
    async searchSessions(keyword, limit = 20, offset = 0) {
      try {
        const response = await client.post('/agent/search_sessions', {
          keyword,
          limit,
          offset
        })
        if (response.ok) {
          return await response.json()
        }
        return { sessions: [], total: 0 }
      } catch (error) {
        console.error('搜索会话失败:', error)
        return { sessions: [], total: 0 }
      }
    },

    // ========== 完成会话 ==========
    async completeSession(sessionId) {
      try {
        const response = await client.post(`/agent/complete/${sessionId}`)
        if (response.ok) {
          return await response.json()
        }
        throw new Error('完成会话失败')
      } catch (error) {
        console.error('完成会话失败:', error)
        throw error
      }
    },

    // ========== 停止会话（使用独立端点） ==========
    async stopSessionDirect(sessionId) {
      try {
        const response = await client.post(`/agent/stop/${sessionId}`)
        if (response.ok) {
          return await response.json()
        }
        throw new Error('停止会话失败')
      } catch (error) {
        console.error('停止会话失败:', error)
        throw error
      }
    }
  }
}
