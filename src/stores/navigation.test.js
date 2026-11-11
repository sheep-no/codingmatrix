import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useNavigationStore } from './navigation'

describe('navigation store activeTool', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('showTool(taskQueue) 会被 activeTool 反映', () => {
    const store = useNavigationStore()

    store.showTool('taskQueue')

    expect(store.showTaskQueue).toBe(true)
    expect(store.activeTool).toBe('taskQueue')
  })

  it('activeTool 为只读 computed，不应被赋值覆盖', () => {
    const store = useNavigationStore()

    store.showTool('virtualGirl')
    expect(store.activeTool).toBe('virtualGirl')

    store.activeTool = 'taskQueue'
    expect(store.activeTool).toBe('virtualGirl')
  })

  it('已卸载工具的历史导航状态不会在恢复时重新挂载（FRESCAN-64）', () => {
    localStorage.setItem('navigationState', JSON.stringify({
      showImageGenerator: true,
      showAicloud: true,
      showProjectGenerator: true,
      showTaskQueue: true
    }))
    const store = useNavigationStore()

    store.restoreNavigationFromStorage()

    expect(store.showTaskQueue).toBe(true)
    expect(store.showImageGenerator).toBeUndefined()
    expect(store.showAicloud).toBeUndefined()
    expect(store.showProjectGenerator).toBeUndefined()
  })
})
