/**
 * API 系统管理模块
 * 用户管理路由前缀: /api/v2/Controller
 * 服务/配置路由前缀: /api/v2
 */
export function createAdminClient(client) {
  return {
    // ========== 用户管理 ==========
    async getUsers(params = {}) {
      try {
        const response = await client.get('/api/v2/Controller/users', params)
        if (response.ok) {
          return await response.json()
        }
        return { users: [] }
      } catch (error) {
        return { users: [] }
      }
    },

    async createUser(userData) {
      const response = await client.post('/api/v2/Controller/create_user', userData)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Create user failed')
      }
    },

    async updateUser(userId, updateData) {
      const response = await client.patch(`/api/v2/Controller/update_user/${userId}`, updateData)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Update user failed')
      }
    },

    async deleteUser(userId) {
      const response = await client.delete(`/api/v2/Controller/delete_user/${userId}`)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Delete user failed')
      }
    },

    async resetUserPassword(userId, newPassword) {
      const response = await client.post(`/api/v2/Controller/${userId}/reset-password`, {
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
        const response = await client.get('/api/v2/Controller/services')
        if (response.ok) {
          return await response.json()
        }
        return { services: [] }
      } catch (error) {
        return { services: [] }
      }
    },

    async startGuard(guardData) {
      const response = await client.post('/api/v2/Controller/guard/start', guardData)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Start failed')
      }
    },

    async renameService(port, processSignature, newName) {
      const params = new URLSearchParams({
        process_signature: processSignature,
        new_name: newName
      })
      const response = await client.put(`/api/v2/Controller/service/${port}/rename?${params}`)
      if (!response.ok) {
        throw new Error(`Rename service failed (${response.status})`)
      }
      return await response.json()
    },

    async updateFuseConfig(port, processSignature, fuseConfig) {
      const params = new URLSearchParams({
        process_signature: processSignature,
        fuse_enabled: String(fuseConfig.fuse_enabled),
        fuse_cooldown: String(fuseConfig.fuse_cooldown),
        fuse_retry_times: String(fuseConfig.fuse_retry_times)
      })
      const response = await client.put(`/api/v2/Controller/service/${port}/fuse-config?${params}`)
      if (!response.ok) {
        throw new Error(`Update fuse config failed (${response.status})`)
      }
      return await response.json()
    },

    async getFuseStatus(serviceName) {
      try {
        const response = await client.get(`/api/v2/Controller/service/${encodeURIComponent(serviceName)}/fuse-status`)
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
        const response = await client.get(`/api/v2/Controller/health/${port}`)
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
              const response = await client.get(`/api/v2/Controller/health/${service.port}`)
              if (response.ok) {
                const health = await response.json()
                return { ...service, ...health }
              }
            } catch (e) {
              console.debug('[admin] 健康检查失败（服务不可达）:', e.message)
            }
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
        const response = await client.get('/api/v2/Controller/admin/stats')
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
        const response = await client.get('/api/v2/Controller/admin/config')
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async getDockerContainers() {
      try {
        const response = await client.get('/api/v2/Controller/admin/docker/containers')
        if (response.ok) {
          return await response.json()
        }
        return { containers: [] }
      } catch (error) {
        return { containers: [] }
      }
    },

    // ========== Nginx 配置 ==========
    async getNginxConfig(configName) {
      try {
        const response = await client.get('/api/v2/nginx/config', { name: configName })
        if (response.ok) {
          return await response.json()
        }
        return { config: '' }
      } catch (error) {
        return { config: '' }
      }
    },

    async checkNginxConfig(config) {
      try {
        const response = await client.post('/api/v2/nginx/check', { config })
        if (response.ok) {
          return await response.json()
        }
        return { valid: false }
      } catch (error) {
        return { valid: false }
      }
    },

    async generateNginxConfig(configData) {
      try {
        const response = await client.post('/api/v2/nginx/generate', configData)
        if (response.ok) {
          return await response.json()
        }
        return { config: '' }
      } catch (error) {
        return { config: '' }
      }
    },

    async deployNginxConfig(config) {
      try {
        const response = await client.post('/api/v2/nginx/deploy', { config })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async listNginxBackups() {
      try {
        const response = await client.get('/api/v2/nginx/backups')
        if (response.ok) {
          return await response.json()
        }
        return { backups: [] }
      } catch (error) {
        return { backups: [] }
      }
    },

    async deleteNginxBackup(backupName) {
      try {
        const response = await client.delete(`/api/v2/nginx/backup/${backupName}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    // ========== 配置管理 ==========
    async getSystemConfig() {
      const response = await client.get('/api/v2/admin/config')
      if (!response.ok) {
        throw new Error(`Get system config failed (${response.status})`)
      }
      return await response.json()
    },

    async getAdminConfig() {
      try {
        const response = await client.get('/api/v2/Controller/admin/config')
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async getAdminConfigByKey(key) {
      try {
        const response = await client.get(`/api/v2/Controller/admin/config/${key}`)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async updateAdminConfig(configData) {
      try {
        const response = await client.post('/api/v2/admin/config', configData)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async updateAdminConfigByKey(key, value) {
      try {
        const response = await client.put(`/api/v2/Controller/admin/config/${key}`, { value: String(value) })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async batchUpdateAdminConfig(configs) {
      try {
        const response = await client.put('/api/v2/Controller/admin/config/batch', { configs })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    // ========== 系统日志 ==========
    async getSystemLogs(params = {}) {
      try {
        const response = await client.get('/api/v2/Controller/admin/log-config', params)
        if (response.ok) {
          return await response.json()
        }
        return { logs: [] }
      } catch (error) {
        return { logs: [] }
      }
    },

    // ========== WebSocket 统计 ==========
    async getWebSocketStats() {
      try {
        const response = await client.get('/api/v2/Controller/admin/ws-stats')
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
        const response = await client.get('/api/v2/Controller/admin/log-config')
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
        const params = new URLSearchParams({ level, logger_name: loggerName })
        const response = await client.put(`/api/v2/Controller/admin/log-config/level?${params}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async updateGlobalLogLevel(level) {
      try {
        const params = new URLSearchParams({ level })
        const response = await client.put(`/api/v2/Controller/admin/log-config/global-level?${params}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    // ========== 内存统计 ==========
    async getMemoryStats() {
      try {
        const response = await client.get('/api/v2/Controller/admin/memory')
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
        const response = await client.get('/api/v2/Controller/admin/backup')
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
        const response = await client.get('/api/v2/Controller/admin/backup/list')
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
        const response = await client.get(`/api/v2/Controller/admin/backup/${timestamp}`)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async restoreBackup(backupData) {
      try {
        const response = await client.post('/api/v2/Controller/admin/backup/restore', backupData)
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
        const response = await client.delete(`/api/v2/Controller/admin/backup/${filename}`)
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
        const response = await client.get('/api/v2/Controller/admin/rate-limit')
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
        const response = await client.put('/api/v2/Controller/admin/rate-limit/global', { limit, window })
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
        const response = await client.put('/api/v2/Controller/admin/rate-limit/ip', { limit, window })
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
        const response = await client.put('/api/v2/Controller/admin/rate-limit/user', { limit, window })
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
        const response = await client.put('/api/v2/Controller/admin/rate-limit/endpoint', {
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
        const response = await client.delete(`/api/v2/Controller/admin/rate-limit/endpoint/${endpoint}`)
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
        const params = new URLSearchParams({ enabled: String(enabled) })
        const response = await client.put(`/api/v2/Controller/admin/rate-limit/enabled?${params}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    // ========== 超级管理员: 用户并发限制 ==========
    async updateUserConcurrentLimit(userId, limit) {
      try {
        const response = await client.post('/api/v2/admin/user-limit', { user_id: userId, limit })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async removeUserConcurrentLimit(userId) {
      try {
        const response = await client.delete(`/api/v2/admin/user-limit/${userId}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async getConcurrentLimitHistory(limit = 50) {
      try {
        const response = await client.get('/agent/concurrent-limits/history', { limit })
        if (response.ok) {
          return await response.json()
        }
        return { history: [] }
      } catch (error) {
        return { history: [] }
      }
    },

    async updateSystemConfig(configData) {
      try {
        const response = await client.post('/api/v2/admin/config', configData)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async saveRoleLimits(roleLimits) {
      const updates = await Promise.all(
        Object.entries(roleLimits).map(async ([role, limit]) => {
          const response = await client.post('/api/v2/admin/config', {
            path: `system_config.user_concurrent_limits.default_tiers.${role}`,
            value: limit
          })
          if (!response.ok) {
            throw new Error(`Save role limit failed (${response.status})`)
          }
          return response.json()
        })
      )
      return { success: true, updates }
    }
  }
}

export default { createAdminClient }
