import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useTokenManager } from '@/utils/tokenManager'
import { useNavigationStore } from './navigation'

// 注销时必须一并清除的跨账户浏览器状态（FRESCAN-55）
const CROSS_ACCOUNT_LOCAL_KEYS = [
  'chatState',
  'streamRequestState',
  'offlineMessageQueue',
  'aicloud_session_id'
]
const CROSS_ACCOUNT_SESSION_KEYS = ['image-generate-session-v1']

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

      // 保存 access token 到内存中（仅使用 tokenManager，不存 localStorage）
      if (data.access_token) {
        tokenManager.setToken(data.access_token, data.expires_in || 1800)
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

      // 清除按浏览器持久化的 Agent 页面数据，避免注销后
      // 同一浏览器上的其他账户复用上一账户的会话历史与提示词
      localStorage.removeItem('agent_project_sessions')
      localStorage.removeItem('project_generator_state')

      // 清除 API Key / 供应商 / 模型覆盖缓存，避免下一账户在请求完成前
      // 展示或回退使用上一账户的令牌、供应商地址与模型映射
      localStorage.removeItem('codingmatrix_apikeys')
      localStorage.removeItem('codingmatrix_rsa_public_key')
      localStorage.removeItem('codingmatrix_model_overrides')
      localStorage.removeItem('codingmatrix_providers')

      // 清除系统日志与过滤状态，避免下一账户在 WebSocket 建立前
      // 看到上一账户的日志内容与筛选条件
      localStorage.removeItem('systemLogsState')

      // 清除会话正文、流式恢复、离线待发消息与 AiCloud 会话标识，
      // 避免下一账户复用上一账户的聊天内容与生成上下文
      CROSS_ACCOUNT_LOCAL_KEYS.forEach(key => localStorage.removeItem(key))
      CROSS_ACCOUNT_SESSION_KEYS.forEach(key => sessionStorage.removeItem(key))

      // 清除工具栏持久化状态并收起当前账户已打开的工具
      try {
        const navigationStore = useNavigationStore()
        navigationStore.clearNavigationStorage()
        navigationStore.hideAllTools()
      } catch {
        // 启动期 token 刷新失败时 Pinia 可能尚未激活，至少清掉持久化键
        localStorage.removeItem('navigationState')
      }
    }

    /**
     * 从 localStorage 恢复用户信息（应用初始化时调用）
     * 注意：access token 不会恢复，需要通过 refresh token 重新获取
     */
    function restoreUser() {
      const storedUsername = localStorage.getItem('username')
      const storedEmail = localStorage.getItem('email')

      if (storedUsername) {
        username.value = storedUsername
        email.value = storedEmail || ''
        permissionLevel.value = localStorage.getItem('permission_level') || 'normal'

        if (tokenManager.getToken() && tokenManager.isTokenValid()) {
          isLoggedIn.value = true
          return true
        }

        isLoggedIn.value = false
        tokenManager.refreshAccessToken().then((ok) => {
          if (ok && tokenManager.getToken()) {
            isLoggedIn.value = true
          } else if (!tokenManager.getToken()) {
            clearUser()
          }
        }).catch(() => {
          if (!tokenManager.getToken()) {
            clearUser()
          }
        })

        return !!tokenManager.getToken()
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
