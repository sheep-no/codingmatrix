import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentWorkspace from './AgentWorkspace.vue'

const baseProps = {
  stages: [],
  overallProgress: 0,
  decisions: [],
  decisionAnswers: {},
  executionSteps: [{ category: 'write', description: '写入文件', timestamp: Date.now() }],
  logs: [{ level: 'info', message: '日志内容', timestamp: Date.now() }]
}

describe('AgentWorkspace merged section accessibility', () => {
  it('exposes keyboard toggles for execution steps and logs', async () => {
    const wrapper = mount(AgentWorkspace, { props: baseProps })

    const headers = wrapper.findAll('.merged-section-header')
    expect(headers).toHaveLength(2)

    const steps = headers[0]
    expect(steps.attributes('role')).toBe('button')
    expect(steps.attributes('tabindex')).toBe('0')
    expect(steps.attributes('aria-expanded')).toBe('false')
    expect(steps.attributes('aria-label')).toBe('展开或收起执行步骤')

    await steps.trigger('keydown', { key: 'Enter' })
    expect(steps.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.steps-list-merged').exists()).toBe(true)

    await steps.trigger('keydown', { key: ' ' })
    expect(steps.attributes('aria-expanded')).toBe('false')

    const logs = headers[1]
    await logs.trigger('keydown', { key: ' ' })
    expect(logs.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.logs-container-merged').exists()).toBe(true)
  })
})
