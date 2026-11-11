import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

function getStoredToolState() {
  try {
    const saved = localStorage.getItem('navigationState')
    if (saved) {
      return JSON.parse(saved)
    }
  } catch (e) {
    console.debug('[navigation] 加载导航状态失败:', e.message)
  }
  return null
}

const initialState = getStoredToolState() || {}

function getDefaultValue(key) {
  return Boolean(initialState[key] || false)
}

export const useNavigationStore = defineStore(
  'navigation',
  () => {
    const showNginxConfig = ref(getDefaultValue('showNginxConfig'))
    const showDockerConfig = ref(getDefaultValue('showDockerConfig'))
    const showVirtualGirl = ref(getDefaultValue('showVirtualGirl'))
    const showTaskQueue = ref(getDefaultValue('showTaskQueue'))

    const isCollapsed = ref(initialState.isCollapsed || false)
    const isBottomInputCollapsed = ref(
      initialState.isBottomInputCollapsed !== undefined
        ? Boolean(initialState.isBottomInputCollapsed)
        : false
    )

    const toolRefs = {
      showNginxConfig,
      showDockerConfig,
      showVirtualGirl,
      showTaskQueue
    }

    function showTool(toolName) {
      hideAllTools()
      switch (toolName) {
        case 'nginxConfig':
          showNginxConfig.value = true
          break
        case 'dockerConfig':
          showDockerConfig.value = true
          break
        case 'virtualGirl':
          showVirtualGirl.value = true
          break
        case 'taskQueue':
          showTaskQueue.value = true
          break
      }
      saveNavigationToStorage()
    }

    function hideTool(toolName) {
      switch (toolName) {
        case 'nginxConfig':
          showNginxConfig.value = false
          break
        case 'dockerConfig':
          showDockerConfig.value = false
          break
        case 'virtualGirl':
          showVirtualGirl.value = false
          break
        case 'taskQueue':
          showTaskQueue.value = false
          break
      }
      saveNavigationToStorage()
    }

    function hideAllTools() {
      Object.values(toolRefs).forEach(ref => {
        ref.value = false
      })
    }

    function toggleCollapse() {
      isCollapsed.value = !isCollapsed.value
      saveNavigationToStorage()
    }

    function setCollapsed(collapsed) {
      isCollapsed.value = collapsed
      saveNavigationToStorage()
    }

    function toggleBottomInputCollapsed() {
      isBottomInputCollapsed.value = !isBottomInputCollapsed.value
      saveNavigationToStorage()
    }

    function setBottomInputCollapsed(collapsed) {
      isBottomInputCollapsed.value = collapsed
      saveNavigationToStorage()
    }

    function saveNavigationToStorage() {
      try {
        const state = {
          showNginxConfig: Boolean(showNginxConfig.value),
          showDockerConfig: Boolean(showDockerConfig.value),
          showVirtualGirl: Boolean(showVirtualGirl.value),
          showTaskQueue: Boolean(showTaskQueue.value),
          isCollapsed: Boolean(isCollapsed.value),
          isBottomInputCollapsed: Boolean(isBottomInputCollapsed.value),
          timestamp: Date.now()
        }
        localStorage.setItem('navigationState', JSON.stringify(state))
      } catch (err) {
        // ignore storage errors
      }
    }

    function restoreNavigationFromStorage() {
      try {
        const savedState = localStorage.getItem('navigationState')
        if (savedState) {
          const state = JSON.parse(savedState)
          Object.keys(state).forEach(key => {
            if (key === 'timestamp') return
            if (toolRefs[key]) {
              toolRefs[key].value = Boolean(state[key])
            } else if (key === 'isCollapsed') {
              isCollapsed.value = Boolean(state[key])
            } else if (key === 'isBottomInputCollapsed') {
              isBottomInputCollapsed.value = Boolean(state[key])
            }
          })
          return true
        }
      } catch (e) {
        console.debug('[navigation] 状态已损坏，重置:', e.message)
        localStorage.removeItem('navigationState')
      }
      return false
    }

    function clearNavigationStorage() {
      localStorage.removeItem('navigationState')
    }

    const activeTool = computed(() => {
      if (showNginxConfig.value) return 'nginxConfig'
      if (showDockerConfig.value) return 'dockerConfig'
      if (showVirtualGirl.value) return 'virtualGirl'
      if (showTaskQueue.value) return 'taskQueue'
      return null
    })

    return {
      showNginxConfig,
      showDockerConfig,
      showVirtualGirl,
      showTaskQueue,
      isCollapsed,
      isBottomInputCollapsed,
      activeTool,
      showTool,
      hideTool,
      hideAllTools,
      toggleCollapse,
      setCollapsed,
      toggleBottomInputCollapsed,
      setBottomInputCollapsed,
      saveNavigationToStorage,
      restoreNavigationFromStorage,
      clearNavigationStorage
    }
  },
  {
    persist: {
      key: 'navigation-store',
      storage: localStorage,
      paths: ['isCollapsed', 'isBottomInputCollapsed']
    }
  }
)
