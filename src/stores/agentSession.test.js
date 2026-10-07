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

  it('converts backend model context into a restorable frontend snapshot', () => {
    const store = useAgentSessionStore()
    store.applyModelContext({
      config_version: '3.1',
      current_model: 'model-a',
      current_agent: 'architect',
      roles: { architect: 'model-a' },
      assignments: {
        architect: { model: 'model-a', calls: 2, success_rate: 95 }
      },
      fallback_history: [{ from_model: 'model-b', to_model: 'model-a' }]
    }, 4)

    expect(store.modelAssignments.architect).toEqual({
      model: 'model-a', calls: 2, successRate: 95
    })
    expect(store.getModelContextSnapshot()).toMatchObject({
      config_version: '3.1',
      current_model: 'model-a',
      current_agent: 'architect',
      expected_revision: 4,
      assignments: {
        architect: { model: 'model-a', calls: 2, success_rate: 95 }
      }
    })
  })

  it('retains explicit null model fields from the backend', () => {
    const store = useAgentSessionStore()
    store.currentModel = 'model-a'
    store.currentAgent = 'architect'

    store.applyModelContext({
      current_model: null,
      current_agent: null,
      assignments: {}
    }, 2)

    expect(store.currentModel).toBeNull()
    expect(store.currentAgent).toBeNull()
    expect(store.modelContextRevision).toBe(2)
  })

  it('filters underscore-prefixed store references out of persistence', () => {
    const store = useAgentSessionStore()
    const sessionId = store.createNewSession({ prompt: 'filter' })
    const context = { _generation: {}, _workspace: {}, _files: {} }

    // 切换前保存传整份快照（含 store 引用），持久化层须剥离下划线前缀键
    store.saveSessionState({
      _generation: { huge: 'store instance' },
      logs: [{ message: 'kept' }],
      generatedFiles: [{ path: 'a.py' }]
    })

    const persisted = JSON.parse(localStorage.getItem('agent_project_sessions'))
    const saved = persisted.find((s) => s.id === sessionId)
    expect(saved.logs).toEqual([{ message: 'kept' }])
    expect(saved._generation).toBeUndefined()
    expect(saved.filesCount).toBe(1)
    expect(context).toBeDefined()
  })
})
