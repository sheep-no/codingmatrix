import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export const useNavigationStore = defineStore(
  'navigation',
  () => {
    // 工具面板显示状态
    const showChartEditor = ref(false)
    const showNginxConfig = ref(false)
    const showDockerConfig = ref(false)
    const showSystemInfo = ref(false)
    const showSystemMonitor = ref(false)
    const showVirtualGirl = ref(false)
    const showServiceManager = ref(false)
    const showProjectGenerator = ref(false)
    const showTaskQueue = ref(false)
    const showPPTGenerator = ref(false)
    const showImageGenerator = ref(false)
    const showEphemeralWorkflow = ref(false)
    const showAicloud = ref(false)

    // 侧边栏折叠状态
    const isCollapsed = ref(false)

    // 底部输入框折叠状态
    const isBottomInputCollapsed = ref(false)

    /**
     * 显示指定的工具面板
     */
    function showTool(toolName) {
      // 隐藏所有面板
      hideAllTools()

      // 显示指定面板
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

      // 保存状态
      saveNavigationToStorage()
    }

    /**
     * 隐藏指定的工具面板
     */
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

      // 保存状态
      saveNavigationToStorage()
    }

    /**
     * 隐藏所有工具面板
     */
    function hideAllTools() {
      showProjectGenerator.value = false
      showChartEditor.value = false
      showNginxConfig.value = false
      showDockerConfig.value = false
      showSystemInfo.value = false
      showSystemMonitor.value = false
      showVirtualGirl.value = false
      showServiceManager.value = false
      showTaskQueue.value = false
      showPPTGenerator.value = false
      showImageGenerator.value = false
      showEphemeralWorkflow.value = false
      showAicloud.value = false
    }

    /**
     * 切换侧边栏折叠状态
     */
    function toggleCollapse() {
      isCollapsed.value = !isCollapsed.value
      saveNavigationToStorage()
    }

    /**
     * 设置侧边栏折叠状态
     */
    function setCollapsed(collapsed) {
      isCollapsed.value = collapsed
      saveNavigationToStorage()
    }

    /**
     * 保存导航状态到 localStorage
     */
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
          isCollapsed: Boolean(isCollapsed.value),
          isBottomInputCollapsed: Boolean(isBottomInputCollapsed.value),
          timestamp: Date.now()
        }
        localStorage.setItem('navigationState', JSON.stringify(state))
      } catch (err) {
        console.warn('[WARN] Cannot save navigation state to localStorage:', err)
      }
    }

    /**
     * 从 localStorage 恢复导航状态
     */
    function restoreNavigationFromStorage() {
      try {
        const savedState = localStorage.getItem('navigationState')
        if (savedState) {
          const state = JSON.parse(savedState)

          // 恢复状态（强制转换为 Boolean）
          showChartEditor.value = Boolean(state.showChartEditor)
          showNginxConfig.value = Boolean(state.showNginxConfig)
          showDockerConfig.value = Boolean(state.showDockerConfig)
          showSystemInfo.value = Boolean(state.showSystemInfo)
          showSystemMonitor.value = Boolean(state.showSystemMonitor)
          showVirtualGirl.value = Boolean(state.showVirtualGirl)
          showServiceManager.value = Boolean(state.showServiceManager)
          showTaskQueue.value = Boolean(state.showTaskQueue)
          showPPTGenerator.value = Boolean(state.showPPTGenerator)
          showImageGenerator.value = Boolean(state.showImageGenerator)
          isCollapsed.value = Boolean(state.isCollapsed)
          isBottomInputCollapsed.value =
            state.isBottomInputCollapsed !== undefined
              ? Boolean(state.isBottomInputCollapsed)
              : false

          return true
        }
      } catch (err) {
        console.error('[ERR] Restore navigation state failed:', err)
        localStorage.removeItem('navigationState')
      }
      return false
    }

    /**
     * 清除 localStorage 中的导航状态
     */
    function clearNavigationStorage() {
      localStorage.removeItem('navigationState')
    }

    /**
     * 获取当前激活的工具名称
     */
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

    // 切换底部输入框折叠状态
    function toggleBottomInputCollapsed() {
      isBottomInputCollapsed.value = !isBottomInputCollapsed.value
      saveNavigationToStorage()
    }

    // 设置底部输入框折叠状态
    function setBottomInputCollapsed(collapsed) {
      isBottomInputCollapsed.value = collapsed
      saveNavigationToStorage()
    }

    return {
      // 状态
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

      // 方法
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
