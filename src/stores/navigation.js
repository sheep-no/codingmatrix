import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

const TOOL_KEYS = [
  'showChartEditor',
  'showNginxConfig',
  'showDockerConfig',
  'showSystemInfo',
  'showSystemMonitor',
  'showVirtualGirl',
  'showServiceManager',
  'showTaskQueue',
  'showPPTGenerator',
  'showImageGenerator',
  'showEphemeralWorkflow',
  'showAicloud'
]

function getStoredToolState() {
  try {
    const saved = localStorage.getItem('navigationState')
    if (saved) {
      return JSON.parse(saved)
    }
  } catch {
    // ignore
  }
  return null
}

const initialState = getStoredToolState() || {}

function getDefaultValue(key) {
  if (key === 'showProjectGenerator') return false
  return Boolean(initialState[key] || false)
}

export const useNavigationStore = defineStore(
  'navigation',
  () => {
    const showChartEditor = ref(getDefaultValue('showChartEditor'))
    const showNginxConfig = ref(getDefaultValue('showNginxConfig'))
    const showDockerConfig = ref(getDefaultValue('showDockerConfig'))
    const showSystemInfo = ref(getDefaultValue('showSystemInfo'))
    const showSystemMonitor = ref(getDefaultValue('showSystemMonitor'))
    const showVirtualGirl = ref(getDefaultValue('showVirtualGirl'))
    const showServiceManager = ref(getDefaultValue('showServiceManager'))
    const showProjectGenerator = ref(false)
    const showTaskQueue = ref(getDefaultValue('showTaskQueue'))
    const showPPTGenerator = ref(getDefaultValue('showPPTGenerator'))
    const showImageGenerator = ref(getDefaultValue('showImageGenerator'))
    const showEphemeralWorkflow = ref(getDefaultValue('showEphemeralWorkflow'))
    const showAicloud = ref(getDefaultValue('showAicloud'))

    const isCollapsed = ref(initialState.isCollapsed || false)
    const isBottomInputCollapsed = ref(
      initialState.isBottomInputCollapsed !== undefined
        ? Boolean(initialState.isBottomInputCollapsed)
        : false
    )

    const toolRefs = {
      showChartEditor,
      showNginxConfig,
      showDockerConfig,
      showSystemInfo,
      showSystemMonitor,
      showVirtualGirl,
      showServiceManager,
      showTaskQueue,
      showPPTGenerator,
      showImageGenerator,
      showEphemeralWorkflow,
      showAicloud
    }

    function showTool(toolName) {
      hideAllTools()
      switch (toolName) {
        case 'projectGenerator':
          showProjectGenerator.value = true
          break
        case 'chartEditor':
          showChartEditor.value = true
          break
        case 'nginxConfig':
          showNginxConfig.value = true
          break
        case 'dockerConfig':
          showDockerConfig.value = true
          break
        case 'systemInfo':
          showSystemInfo.value = true
          break
        case 'systemMonitor':
          showSystemMonitor.value = true
          break
        case 'virtualGirl':
          showVirtualGirl.value = true
          break
        case 'serviceManager':
          showServiceManager.value = true
          break
        case 'taskQueue':
          showTaskQueue.value = true
          break
        case 'pptGenerator':
          showPPTGenerator.value = true
          break
        case 'imageGenerator':
          showImageGenerator.value = true
          break
        case 'ephemeralWorkflow':
          showEphemeralWorkflow.value = true
          break
        case 'aicloud':
          showAicloud.value = true
          break
      }
      saveNavigationToStorage()
    }

    function hideTool(toolName) {
      switch (toolName) {
        case 'projectGenerator':
          showProjectGenerator.value = false
          break
        case 'chartEditor':
          showChartEditor.value = false
          break
        case 'nginxConfig':
          showNginxConfig.value = false
          break
        case 'dockerConfig':
          showDockerConfig.value = false
          break
        case 'systemInfo':
          showSystemInfo.value = false
          break
        case 'systemMonitor':
          showSystemMonitor.value = false
          break
        case 'virtualGirl':
          showVirtualGirl.value = false
          break
        case 'serviceManager':
          showServiceManager.value = false
          break
        case 'taskQueue':
          showTaskQueue.value = false
          break
        case 'pptGenerator':
          showPPTGenerator.value = false
          break
        case 'imageGenerator':
          showImageGenerator.value = false
          break
        case 'ephemeralWorkflow':
          showEphemeralWorkflow.value = false
          break
        case 'aicloud':
          showAicloud.value = false
          break
      }
      saveNavigationToStorage()
    }

    function hideAllTools() {
      showProjectGenerator.value = false
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
          showChartEditor: Boolean(showChartEditor.value),
          showNginxConfig: Boolean(showNginxConfig.value),
          showDockerConfig: Boolean(showDockerConfig.value),
          showSystemInfo: Boolean(showSystemInfo.value),
          showSystemMonitor: Boolean(showSystemMonitor.value),
          showVirtualGirl: Boolean(showVirtualGirl.value),
          showServiceManager: Boolean(showServiceManager.value),
          showTaskQueue: Boolean(showTaskQueue.value),
          showPPTGenerator: Boolean(showPPTGenerator.value),
          showImageGenerator: Boolean(showImageGenerator.value),
          showEphemeralWorkflow: Boolean(showEphemeralWorkflow.value),
          showAicloud: Boolean(showAicloud.value),
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
            if (key === 'showProjectGenerator') return
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
      } catch {
        localStorage.removeItem('navigationState')
      }
      return false
    }

    function clearNavigationStorage() {
      localStorage.removeItem('navigationState')
    }

    const activeTool = computed(() => {
      if (showChartEditor.value) return 'chartEditor'
      if (showNginxConfig.value) return 'nginxConfig'
      if (showDockerConfig.value) return 'dockerConfig'
      if (showSystemInfo.value) return 'systemInfo'
      if (showSystemMonitor.value) return 'systemMonitor'
      if (showVirtualGirl.value) return 'virtualGirl'
      if (showServiceManager.value) return 'serviceManager'
      if (showTaskQueue.value) return 'taskQueue'
      if (showPPTGenerator.value) return 'pptGenerator'
      if (showImageGenerator.value) return 'imageGenerator'
      if (showEphemeralWorkflow.value) return 'ephemeralWorkflow'
      if (showAicloud.value) return 'aicloud'
      return null
    })

    return {
      showChartEditor,
      showNginxConfig,
      showDockerConfig,
      showSystemInfo,
      showSystemMonitor,
      showVirtualGirl,
      showServiceManager,
      showProjectGenerator,
      showTaskQueue,
      showPPTGenerator,
      showImageGenerator,
      showEphemeralWorkflow,
      showAicloud,
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
