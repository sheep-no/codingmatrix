/**
 * API 项目生成模块
 */
export function createProjectClient(client) {
  return {
    async getSavedProjects() {
      try {
        const response = await client.get('/agent/saved')
        if (response.ok) {
          const data = await response.json()
          return data.projects || []
        }
        return []
      } catch (error) {
        console.error('Failed to load saved projects:', error)
        return []
      }
    },

    async saveProject(name, description, projectData) {
      try {
        const response = await client.post('/agent/save', {
          name,
          description,
          project_data: projectData
        })
        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Save project failed')
        }
      } catch (error) {
        console.error('Save project error:', error)
        throw error
      }
    },

    async loadProject(projectId) {
      try {
        const response = await client.get(`/agent/saved/${projectId}`)
        if (response.ok) {
          return await response.json()
        } else {
          throw new Error('Project not found')
        }
      } catch (error) {
        console.error('Load project error:', error)
        throw error
      }
    },

    async deleteProject(projectId) {
      const response = await client.delete(`/agent/saved/${projectId}`)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Delete project failed')
      }
    },

    async getProjectFiles(projectPath) {
      try {
        const response = await client.get(
          `/agent/generate/files?project_path=${encodeURIComponent(projectPath)}`
        )
        if (response.ok) {
          return await response.json()
        } else {
          throw new Error('Failed to get project files')
        }
      } catch (error) {
        console.error('Get project files error:', error)
        throw error
      }
    },

    async readProjectFile(projectPath, filePath) {
      try {
        const response = await client.get(
          `/agent/generate/read?project_path=${encodeURIComponent(projectPath)}&file_path=${encodeURIComponent(filePath)}`
        )
        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Failed to read file')
        }
      } catch (error) {
        console.error('Read project file error:', error)
        throw error
      }
    },

    async deleteProjectFile(projectPath, filePath) {
      try {
        const response = await client.delete(
          `/agent/generate/file?project_path=${encodeURIComponent(projectPath)}&file_path=${encodeURIComponent(filePath)}`
        )
        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Failed to delete file')
        }
      } catch (error) {
        console.error('Delete project file error:', error)
        throw error
      }
    },

    async downloadProject(projectPath) {
      return `/api/v1/agent/generate/download/${encodeURIComponent(projectPath)}`
    },

    async generateProjectStream(
      requirement,
      projectType = 'auto',
      sessionId = null,
      onChunk = null,
      signal = null
    ) {
      return client.stream(
        '/agent/generate_stream',
        {
          requirement,
          project_type: projectType,
          session_id: sessionId
        },
        signal
      )
    },

    async generateProject(requirement, projectType = 'auto', sessionId = null) {
      try {
        const response = await client.post('/agent/generate', {
          requirement,
          project_type: projectType,
          session_id: sessionId
        })
        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Generate failed')
        }
      } catch (error) {
        throw error
      }
    },

    async getGenerationTaskStatus(taskId) {
      try {
        const response = await client.get(`/agent/generate/status/${taskId}`)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    }
  }
}

export default { createProjectClient }
