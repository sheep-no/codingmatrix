import { describe, expect, it } from 'vitest'
import { normalizeAgentRole } from './useAgentStreaming'

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
