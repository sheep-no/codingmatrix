import { describe, expect, it } from 'vitest'
import {
  markThinkingStreamEnded,
  normalizeAgentRole,
  normalizeEventTimestamp,
  resolveIncrementalStreamOptions,
} from './useAgentStreaming'

describe('agent streaming model roles', () => {
  it.each([
    ['架构师', 'architect'],
    ['前端工程师', 'frontend'],
    ['后端工程师', 'backend'],
    ['审查员', 'reviewer'],
    ['frontend_engineer', 'frontend'],
  ])('maps %s to %s', (agent, role) => {
    expect(normalizeAgentRole(agent)).toBe(role)
  })
})

describe('normalizeEventTimestamp', () => {
  it('converts unix seconds to milliseconds', () => {
    expect(normalizeEventTimestamp(1710000000)).toBe(1710000000000)
  })

  it('keeps millisecond timestamps', () => {
    expect(normalizeEventTimestamp(1710000000000)).toBe(1710000000000)
  })
})

describe('markThinkingStreamEnded', () => {
  it('clears streaming flags after generation ends', () => {
    const messages = [
      { agent: '后端工程师', phase: 'llm_output', streaming: true },
      { agent: '架构师', phase: 'llm_output', streaming: true },
    ]
    markThinkingStreamEnded(messages)
    expect(messages.every(message => message.streaming === false)).toBe(true)
  })

  it('can end a single agent stream', () => {
    const messages = [
      { agent: '后端工程师', streaming: true },
      { agent: '架构师', streaming: true },
    ]
    markThinkingStreamEnded(messages, { agent: '后端工程师' })
    expect(messages[0].streaming).toBe(false)
    expect(messages[1].streaming).toBe(true)
  })
})

describe('resolveIncrementalStreamOptions', () => {
  it('sends a boolean incremental flag and core engine when files already exist', () => {
    expect(resolveIncrementalStreamOptions(true, '1/1789218793436')).toEqual({
      incremental: true,
      engine: 'core',
      is_resume: false,
      project_path: '1/1789218793436',
    })
  })

  it('keeps incremental false for a new project', () => {
    expect(resolveIncrementalStreamOptions(false, '1/1789218793436')).toEqual({
      incremental: false,
    })
    expect(resolveIncrementalStreamOptions(true, '')).toEqual({
      incremental: false,
    })
  })
})
