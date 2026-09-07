import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import WorkbenchNav from './WorkbenchNav.vue'

const routes = [
  { path: '/', component: { template: '<div />' } },
  { path: '/agent', component: { template: '<div />' } },
  { path: '/capabilities', component: { template: '<div />' } },
  { path: '/docs', component: { template: '<div />' } },
  { path: '/settings', component: { template: '<div />' } }
]

async function mountNavigation(path = '/') {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  return mount(WorkbenchNav, { global: { plugins: [router] } })
}

describe('WorkbenchNav', () => {
  it('provides the shared primary navigation hierarchy', async () => {
    const wrapper = await mountNavigation('/agent')
    const links = wrapper.findAll('.workbench-nav-link')

    expect(links.map((link) => link.text())).toEqual(['会话', '项目', '能力', '文档', '设置'])
    expect(links.map((link) => link.attributes('href'))).toEqual(['/', '/agent', '/capabilities', '/docs', '/settings'])
    expect(links.every((link) => Boolean(link.attributes('aria-label')))).toBe(true)
    expect(links[1].classes()).toContain('router-link-active')
  })

  it('keeps accessible names when labels are visually collapsed', async () => {
    const wrapper = await mountNavigation()
    await wrapper.setProps({ collapsed: true })

    expect(wrapper.find('nav').classes()).toContain('workbench-nav-collapsed')
    expect(wrapper.findAll('.workbench-nav-link').map((link) => link.attributes('title'))).toEqual(['会话', '项目', '能力', '文档', '设置'])
  })
})
