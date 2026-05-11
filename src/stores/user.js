import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useTokenManager } from '@/utils/tokenManager'

export const useUserStore = defineStore(
  'user',
  () => {
    // Token 管理
    const tokenManager = useTokenManager()

    // 用户状态
    const isLoggedIn = ref(false)
    const username = ref('')
    const email = ref('')
    const permissionLevel = ref('normal') // normal, admin, superadmin

    // 计算属性：是否为管理员及以上
    const isAdmin = computed(() => ['admin', 'superadmin'].includes(permissionLevel.value))
    // 计算属性：是否为超级管理员
    const isSuperUser = computed(() => permissionLevel.value === 'superadmin')

    /**
     * 获取访问令牌
     */
    function getAccessToken() {
      return tokenManager.getToken()
    }

    /**
     * 检查 token 是否有效
     */
    function isTokenValid() {
      return tokenManager.isTokenValid()
    }

    /**
     * 设置用户信息（登录后调用）
     */
    function setUser(data) {
      isLoggedIn.value = true
      username.value = data.username || ''
      email.value = data.email || ''
      permissionLevel.value = data.permission_level || 'normal'

      // 保存 access token 到内存中
      if (data.access_token) {
        tokenManager.setToken(data.access_token, data.expires_in || 1800)
        localStorage.setItem('access_token', data.access_token)
      }

      // 保存非敏感信息到 localStorage
      localStorage.setItem('username', data.username || '')
      localStorage.setItem('email', data.email || '')
      localStorage.setItem('permission_level', data.permission_level || 'normal')
    }

    /**
     * 清除用户信息（退出登录时调用）
     */
    function clearUser() {
      isLoggedIn.value = false
      username.value = ''
      email.value = ''
      permissionLevel.value = 'normal'

      // 清除内存中的 token
      tokenManager.clearToken()

      // 从 localStorage 清除
      localStorage.removeItem('access_token')
      localStorage.removeItem('username')
      localStorage.removeItem('email')
      localStorage.removeItem('permission_level')
    }

    /**
     * 从 localStorage 恢复用户信息（应用初始化时调用）
     * 注意：access token 不会恢复，需要通过 refresh token 重新获取
     */
    function restoreUser() {
      const storedUsername = localStorage.getItem('username')
      const storedEmail = localStorage.getItem('email')

      if (storedUsername) {
        isLoggedIn.value = true
        username.value = storedUsername
        email.value = storedEmail || ''
        permissionLevel.value = localStorage.getItem('permission_level') || 'normal'

        // 尝试刷新 access token
        tokenManager.refreshAccessToken().then(success => {
          if (success) {
            console.log('[OK] Token refreshed, user restored')
          } else {
            console.warn('[WARN] Token refresh failed, please re-login')
            clearUser()
          }
        })

        return true
      }

      return false
    }

    /**
     * 刷新访问令牌
     */
    async function refreshAccessToken() {
      return await tokenManager.refreshAccessToken()
    }

    /**
     * 更新用户名
     */
    function updateUsername(newUsername) {
      username.value = newUsername
      localStorage.setItem('username', newUsername)
    }

    /**
     * 从 token 中解析权限级别
     */
    function getPermissionFromToken() {
      const token = tokenManager.getToken()
      if (!token) return 'normal'

      try {
        const payload = JSON.parse(atob(token.split('.')[1]))
        return payload.permission_level || 'normal'
      } catch (error) {
        console.error('解析 token 失败:', error)
        return 'normal'
      }
    }

    return {
      // 状态
      isLoggedIn,
      username,
      email,
      permissionLevel,
      isAdmin,
      isSuperUser,

      // 方法
      getAccessToken,
      isTokenValid,
      setUser,
      clearUser,
      restoreUser,
      refreshAccessToken,
      updateUsername,
      getPermissionFromToken
    }
  },
  {
    persist: {
      key: 'user-store',
      storage: localStorage,
      paths: ['isLoggedIn', 'username', 'email', 'permissionLevel']
    }
  }
)
