import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  post: vi.fn(),
  delete: vi.fn()
}))

const userState = vi.hoisted(() => ({
  isLoggedIn: true,
  username: 'tester',
  isSuperUser: false,
  restoreUser: vi.fn(() => false),
  clearUser: vi.fn()
}))

vi.mock('@/utils/api/index', () => ({ api: apiMock }))
vi.mock('@/stores/user', () => ({
  useUserStore: () => userState
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() })
}))
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn() },
  ElMessageBox: { confirm: vi.fn() }
}))

import Leftlist from './leftlist.vue'

function jsonResponse(data, ok = true) {
  return {
    ok,
    status: ok ? 200 : 500,
    json: vi.fn().mockResolvedValue(data)
  }
}

function mountLeftlist() {
  return mount(Leftlist, {
    attachTo: document.body,
    global: {
      stubs: {
        ThemeSwitcher: true,
        LoginDialog: true,
        VirtualHistoryList: {
          props: ['items', 'searchKeyword'],
          template: '<div class="virtual-history"><div v-for="item in items" :key="item.id" class="history-item">{{ item.title || item.prompt }}</div></div>'
        }
      }
    }
  })
}

async function openSearchBox(wrapper) {
  await wrapper.get('#toolkit').trigger('click')
  const item = wrapper.findAll('[role="menuitem"]').find(node => node.text().includes('搜索历史'))
  await item.trigger('click')
}

describe('搜索历史记录', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    apiMock.post.mockReset()
    apiMock.delete.mockReset()
    userState.isLoggedIn = true
    userState.restoreUser.mockReturnValue(false)
    apiMock.post.mockResolvedValue(jsonResponse({ items: [], total: 0 }))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('opens the search box from the toolkit', async () => {
    const wrapper = mountLeftlist()
    await openSearchBox(wrapper)

    expect(wrapper.get('.search-box').exists()).toBe(true)
    expect(wrapper.get('.search-input').attributes('placeholder')).toBe('搜索历史记录...')
    wrapper.unmount()
  })

  it('posts prompt_keyword to /history and renders matches', async () => {
    apiMock.post.mockResolvedValue(jsonResponse({
      items: [{ id: 11, conversation_id: 3, title: '检索规划', prompt: '怎么做检索规划' }],
      total: 1
    }))
    const wrapper = mountLeftlist()
    await openSearchBox(wrapper)
    await wrapper.get('.search-input').setValue('检索')
    await wrapper.get('.search-btn').trigger('click')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/history', {
      prompt_keyword: '检索',
      limit: 50,
      offset: 0
    })
    expect(wrapper.get('.history-item').text()).toContain('检索规划')
    wrapper.unmount()
  })

  it('shows a panel error and retries the failed search', async () => {
    apiMock.post
      .mockRejectedValueOnce(new Error('服务暂不可用'))
      .mockResolvedValueOnce(jsonResponse({
        items: [{ id: 12, conversation_id: 4, title: '联网搜索', prompt: '联网搜索' }],
        total: 1
      }))
    const wrapper = mountLeftlist()
    await openSearchBox(wrapper)
    await wrapper.get('.search-input').setValue('联网')
    await wrapper.get('.search-btn').trigger('click')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(wrapper.text()).toContain('服务暂不可用')
    await wrapper.get('.error-state button').trigger('click')
    await flushPromises()
    expect(apiMock.post).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.history-item').text()).toContain('联网搜索')
    wrapper.unmount()
  })

  it('clears the keyword and reloads the full history list', async () => {
    apiMock.post
      .mockResolvedValueOnce(jsonResponse({
        items: [{ id: 13, conversation_id: 5, title: '匹配项', prompt: '匹配项' }],
        total: 1
      }))
      .mockResolvedValueOnce(jsonResponse({
        items: [
          { id: 13, conversation_id: 5, title: '匹配项', prompt: '匹配项' },
          { id: 14, conversation_id: 6, title: '全部会话', prompt: '全部会话' }
        ],
        total: 2
      }))
    const wrapper = mountLeftlist()
    await openSearchBox(wrapper)
    await wrapper.get('.search-input').setValue('匹配')
    await wrapper.get('.search-btn').trigger('click')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    await wrapper.get('.clear-btn').trigger('click')
    await flushPromises()
    expect(wrapper.get('.search-input').element.value).toBe('')
    expect(apiMock.post).toHaveBeenLastCalledWith('/history', {
      prompt_keyword: '',
      limit: 50,
      offset: 0
    })
    expect(wrapper.findAll('.history-item')).toHaveLength(2)
    wrapper.unmount()
  })
})
