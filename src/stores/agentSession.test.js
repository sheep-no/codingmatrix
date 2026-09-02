import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentSessionStore } from './agentSession'

describe('agent session store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('persists and restores a complete session snapshot', () => {
    const store = useAgentSessionStore()
    const sessionId = store.createNewSession({ generatedFiles: [{ path: 'a.js', content: '1' }] })
    store.projectPrompt = 'update the project'
    store.saveSessionState({ logs: [{ message: 'done' }], workflowStages: [{ id: 'build' }] })

    store.projectPrompt = ''
    const context = {
      _generation: {},
      _workspace: {},
      _files: {}
    }
    expect(store.switchSession(sessionId, context)).toBe(true)
    expect(store.projectPrompt).toBe('update the project')
    expect(context._files.generatedFiles).toEqual([{ path: 'a.js', content: '1' }])
    expect(context._workspace.logs).toEqual([{ message: 'done' }])
    expect(context._generation.workflowStages).toEqual([{ id: 'build' }])
  })
})
