import { ref, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { useToast } from '@/composables/useToast'
import { api } from '@/utils/api/index'

export function useAuth() {
  const userStore = useUserStore()
  const { error: showError } = useToast()
  const isRefreshing = ref(false)

  onMounted(() => {
    userStore.restoreUser()
  })

  async function login(email, password) {
    try {
      const data = await api.login({ email, password })

      userStore.setUser(data)
      
      return { success: true }
    } catch (err) {
      showError(err.message || '登录失败，请稍后重试')
      return { success: false, error: err.message }
    }
  }

  async function register(username, email, password) {
    try {
      const response = await api.post('/register', { username, email, password })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || '注册失败')
      }

      return { success: true }
    } catch (err) {
      showError(err.message || '注册失败，请稍后重试')
      return { success: false, error: err.message }
    }
  }

  async function logout() {
    try {
      await api.logout()
    } catch (e) {
      // 后端吊销失败不应阻塞本地登出
      console.warn('[useAuth] 后端登出失败:', e?.message || e)
    }
    userStore.clearUser()
    window.location.reload()
  }

  async function refreshToken() {
    if (isRefreshing.value) return false

    isRefreshing.value = true
    try {
      const success = await userStore.refreshAccessToken()
      return success
    } catch (e) {
      console.warn('[useAuth] Token 刷新失败:', e.message)
      return false
    } finally {
      isRefreshing.value = false
    }
  }

  return {
    login,
    register,
    logout,
    refreshToken,
    isLoggedIn: userStore.isLoggedIn,
    user: userStore,
    isRefreshing
  }
}
