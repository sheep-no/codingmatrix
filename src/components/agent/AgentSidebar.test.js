import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentSidebar from './AgentSidebar.vue'

const baseProps = {
  sessions: [{ id: 'session-1', mode: 'create', filesCount: 2, timestamp: Date.now() }],
  sessionId: '',
  hasFiles: true,
  fileCount: 1,
  categories: [{ name: '源代码', icon: '', expanded: true, files: [{ path: 'src/main.js' }] }]
}

describe('AgentSidebar accessibility', () => {
  it('supports keyboard session switching and native file controls', async () => {
    const wrapper = mount(AgentSidebar, { props: baseProps })

    await wrapper.find('.session-item').trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('switch-session')).toEqual([['session-1']])
    expect(wrapper.find('.category-header').element.tagName).toBe('BUTTON')
    expect(wrapper.find('.category-header').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.file-item').element.tagName).toBe('BUTTON')
  })
})
