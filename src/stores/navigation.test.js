import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useNavigationStore } from './navigation'

describe('navigation store activeTool', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('showTool(projectGenerator) 会被 activeTool 反映（FESTATE-06）', () => {
    const store = useNavigationStore()

    store.showTool('projectGenerator')

    expect(store.showProjectGenerator).toBe(true)
    expect(store.activeTool).toBe('projectGenerator')
  })

  it('activeTool 为只读 computed，不应被赋值覆盖', () => {
    const store = useNavigationStore()

    store.showTool('imageGenerator')
    expect(store.activeTool).toBe('imageGenerator')

    store.activeTool = 'projectGenerator'
    expect(store.activeTool).toBe('imageGenerator')
  })
})
