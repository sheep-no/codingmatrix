/**
 * API 系统管理模块
 */
export function createAdminClient(client) {
  return {
    // ========== 用户管理 ==========
    async getUsers(params = {}) {
      try {
        const response = await client.get('/v2/users', params)
        if (response.ok) {
          return await response.json()
        }
        return { users: [] }
      } catch (error) {
        return { users: [] }
      }
    },

    async createUser(userData) {
      const response = await client.post('/v2/users', userData)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Create user failed')
      }
    },

    async updateUser(userId, updateData) {
      const response = await client.put(`/v2/users/${userId}`, updateData)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Update user failed')
      }
    },

    async deleteUser(userId) {
      const response = await client.delete(`/v2/users/${userId}`)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Delete user failed')
      }
    },

    async resetUserPassword(userId, newPassword) {
      const response = await client.post(`/v2/users/${userId}/reset-password`, {
        password: newPassword
      })
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Reset password failed')
      }
    },

    // ========== 服务管理 ==========
    async getServices() {
      try {
        const response = await client.get('/v2/services')
        if (response.ok) {
          return await response.json()
        }
        return { services: [] }
      } catch (error) {
        return { services: [] }
      }
    },

    async startGuard(guardData) {
      try {
        const response = await client.post('/v2/services/start', guardData)
        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Start failed')
        }
      } catch (error) {
        throw error
      }
    },

    async renameService(port, processSignature, newName) {
      try {
        const response = await client.post('/v2/services/rename', {
          port,
          process_signature: processSignature,
          new_name: newName
        })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async updateFuseConfig(port, processSignature, fuseConfig) {
      try {
        const response = await client.post('/v2/services/fuse', {
          port,
          process_signature: processSignature,
          fuse_config: fuseConfig
        })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async getFuseStatus(serviceName) {
      try {
        const response = await client.get('/v2/services/fuse-status', { service_name: serviceName })
        if (response.ok) {
          return await response.json()
        }
        return { fuse_status: null }
      } catch (error) {
        return { fuse_status: null }
      }
    },

    async checkHealth(port) {
      try {
        const response = await client.get('/v2/services/health', { port })
        if (response.ok) {
          return await response.json()
        }
        return { status: 'unknown' }
      } catch (error) {
        return { status: 'error' }
      }
    },

    async checkHealthAll() {
      try {
        const servicesResponse = await this.getServices()
        if (!servicesResponse.services) {
          return { services: [] }
        }

        const services = servicesResponse.services
        const healthChecks = await Promise.all(
          services.map(async service => {
            try {
              const response = await client.get('/v2/services/health', { port: service.port })
              if (response.ok) {
                const health = await response.json()
                return { ...service, ...health }
              }
            } catch (e) {}
            return { ...service, status: 'unknown' }
          })
        )

        return { services: healthChecks }
      } catch (error) {
        return { services: [] }
      }
    },

    // ========== 系统状态 ==========
    async getSystemStatus() {
      try {
        const response = await client.get('/v2/system/status')
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async getSystemInfo() {
      try {
        const response = await client.get('/v2/system/info')
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    // ========== Nginx 配置 ==========
    async getNginxConfig() {
      try {
        const response = await client.get('/v2/nginx/config')
        if (response.ok) {
          return await response.json()
        }
        return { config: '' }
      } catch (error) {
        return { config: '' }
      }
    },

    async updateNginxConfig(config) {
      try {
        const response = await client.post('/v2/nginx/config', { config })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async validateNginxConfig(config) {
      try {
        const response = await client.post('/v2/nginx/validate', { config })
        if (response.ok) {
          return await response.json()
        }
        return { valid: false }
      } catch (error) {
        return { valid: false }
      }
    },

    async reloadNginx() {
      try {
        const response = await client.post('/v2/nginx/reload', {})
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async checkNginxConfig(config) {
      try {
        const response = await client.post('/v2/nginx/check', { config })
        if (response.ok) {
          return await response.json()
        }
        return { valid: false }
      } catch (error) {
        return { valid: false }
      }
    },

    // ========== 系统日志 ==========
    async getSystemLogs(params = {}) {
      try {
        const response = await client.get('/v2/system/logs', params)
        if (response.ok) {
          return await response.json()
        }
        return { logs: [] }
      } catch (error) {
        return { logs: [] }
      }
    },

    async clearSystemLogs() {
      try {
        const response = await client.post('/v2/system/logs/clear', {})
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    // ========== 数据库 ==========
    async getDatabaseStatus() {
      try {
        const response = await client.get('/v2/system/database')
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async optimizeDatabase() {
      try {
        const response = await client.post('/v2/system/database/optimize', {})
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    // ========== WebSocket 统计 ==========
    async getWebSocketStats() {
      try {
        const response = await client.get('/v2/system/websocket')
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    // ========== 日志配置 ==========
    async getLogConfig() {
      try {
        const response = await client.get('/v2/system/log-config')
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async updateLogLevel(level, loggerName = 'app') {
      try {
        const response = await client.post('/v2/system/log-level', {
          level,
          logger_name: loggerName
        })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async updateGlobalLogLevel(level) {
      return this.updateLogLevel(level, 'app')
    },

    // ========== 内存统计 ==========
    async getMemoryStats() {
      try {
        const response = await client.get('/v2/system/memory')
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    // ========== 备份管理 ==========
    async createBackup() {
      try {
        const response = await client.post('/v2/system/backup', {})
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async listBackups() {
      try {
        const response = await client.get('/v2/system/backups')
        if (response.ok) {
          return await response.json()
        }
        return { backups: [] }
      } catch (error) {
        return { backups: [] }
      }
    },

    async downloadBackup(timestamp) {
      try {
        const response = await client.get('/v2/system/backup/download', { timestamp })
        if (response.ok) {
          const blob = await response.blob()
          const url = window.URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `backup_${timestamp}.zip`
          document.body.appendChild(a)
          a.click()
          document.body.removeChild(a)
          window.URL.revokeObjectURL(url)
          return true
        }
        return false
      } catch (error) {
        return false
      }
    },

    async restoreBackup(backupData) {
      try {
        const response = await client.post('/v2/system/backup/restore', backupData)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async deleteBackup(filename) {
      try {
        const response = await client.post('/v2/system/backup/delete', { filename })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    // ========== 限流配置 ==========
    async getRateLimitStats() {
      try {
        const response = await client.get('/v2/system/rate-limit')
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async updateGlobalRateLimit(limit, window) {
      try {
        const response = await client.post('/v2/system/rate-limit/global', { limit, window })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async updateIpRateLimit(limit, window) {
      try {
        const response = await client.post('/v2/system/rate-limit/ip', { limit, window })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async updateUserRateLimit(limit, window) {
      try {
        const response = await client.post('/v2/system/rate-limit/user', { limit, window })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async updateEndpointRateLimit(endpoint, limit, window) {
      try {
        const response = await client.post('/v2/system/rate-limit/endpoint', {
          endpoint,
          limit,
          window
        })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async deleteEndpointRateLimit(endpoint) {
      try {
        const response = await client.delete('/v2/system/rate-limit/endpoint', { endpoint })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async toggleRateLimit(enabled) {
      try {
        const response = await client.post('/v2/system/rate-limit/toggle', { enabled })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    }
  }
}

export default { createAdminClient }
