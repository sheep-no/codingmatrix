import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
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
  it('supports shared navigation, keyboard session switching and native file controls', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/agent', component: { template: '<div />' } },
        { path: '/capabilities', component: { template: '<div />' } },
        { path: '/docs', component: { template: '<div />' } },
        { path: '/settings', component: { template: '<div />' } }
      ]
    })
    await router.push('/agent')
    await router.isReady()
    const wrapper = mount(AgentSidebar, { props: baseProps, global: { plugins: [router] } })

    await wrapper.find('.session-item').trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('switch-session')).toEqual([['session-1']])
    expect(wrapper.find('.category-header').element.tagName).toBe('BUTTON')
    expect(wrapper.find('.category-header').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.file-item').element.tagName).toBe('BUTTON')
    expect(wrapper.findAll('.workbench-nav-link')).toHaveLength(5)
  })
})
