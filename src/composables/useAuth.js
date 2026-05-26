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
      const response = await api.post('/auth/register', { username, email, password })

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

  function logout() {
    userStore.clearUser()
    window.location.reload()
  }

  async function refreshToken() {
    if (isRefreshing.value) return false

    isRefreshing.value = true
    try {
      const success = await userStore.refreshAccessToken()
      return success
    } catch {
      return false
    } finally {
      isRefreshing.value = false
    }
  }

  async function updateProfile(updates) {
    try {
      const response = await api.put('/auth/profile', updates)

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || '更新失败')
      }

      const data = await response.json()
      userStore.setUser(data)
      return { success: true }
    } catch (err) {
      showError(err.message || '更新失败，请稍后重试')
      return { success: false, error: err.message }
    }
  }

  return {
    login,
    register,
    logout,
    refreshToken,
    updateProfile,
    isLoggedIn: userStore.isLoggedIn,
    user: userStore,
    isRefreshing
  }
}
