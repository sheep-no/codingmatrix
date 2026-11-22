import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  post: vi.fn(),
  delete: vi.fn(),
  deleteChatHistory: vi.fn(),
  logout: vi.fn()
}))

const userState = vi.hoisted(() => ({
  isLoggedIn: true,
  username: 'tester',
  isSuperUser: false,
  restoreUser: vi.fn(() => false),
  ensureSession: vi.fn(() => Promise.resolve(false)),
  clearUser: vi.fn()
}))

const chatDbMock = vi.hoisted(() => ({
  deleteConversation: vi.fn()
}))

const routerPushMock = vi.hoisted(() => vi.fn())

vi.mock('@/utils/api/index', () => ({ api: apiMock }))
vi.mock('@/utils/chatDatabase', () => ({ chatDB: chatDbMock }))
vi.mock('@/stores/user', () => ({
  useUserStore: () => userState
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPushMock })
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
          template: `<div class="virtual-history">
            <div v-for="item in items" :key="item.id" class="history-item">
              {{ item.title || item.prompt }}
              <button class="history-delete" @click="$emit('delete', item)">删除</button>
            </div>
          </div>`
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
    apiMock.deleteChatHistory.mockReset()
    apiMock.deleteChatHistory.mockResolvedValue(jsonResponse({ ok: true }))
    apiMock.logout.mockReset()
    apiMock.logout.mockResolvedValue(true)
    chatDbMock.deleteConversation.mockReset()
    chatDbMock.deleteConversation.mockResolvedValue(true)
    userState.isLoggedIn = true
    userState.restoreUser.mockReturnValue(false)
    userState.ensureSession.mockReset()
    userState.ensureSession.mockResolvedValue(false)
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

  it('lists Nginx config in the toolkit menu', async () => {
    const wrapper = mountLeftlist()
    await wrapper.get('#toolkit').trigger('click')
    const labels = wrapper.findAll('[role="menuitem"]').map(node => node.text())
    expect(labels.some(text => text.includes('Nginx 配置'))).toBe(true)
    expect(labels.some(text => text.includes('Docker 配置'))).toBe(true)
    wrapper.unmount()
  })

  it('工具集工作台入口统一走路由跳转，不再开新标签', async () => {
    const wrapper = mountLeftlist()
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    for (const label of ['图表编辑器', 'PPT 生成', 'AI 绘画', '临时工作流']) {
      if (!wrapper.find('#toolkit-menu').exists()) {
        await wrapper.get('#toolkit').trigger('click')
      }
      routerPushMock.mockClear()
      const item = wrapper.findAll('[role="menuitem"]').find(node => node.text().includes(label))
      await item.trigger('click')
      expect(routerPushMock, `${label} 应使用路由跳转`).toHaveBeenCalledTimes(1)
    }

    expect(openSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
    wrapper.unmount()
  })

  it('工具集菜单使用浮层定位并限制在视口内', async () => {
    const wrapper = mountLeftlist()
    await wrapper.get('#toolkit').trigger('click')
    const menu = wrapper.get('#toolkit-menu')
    expect(menu.attributes('style')).toContain('top:')
    expect(menu.attributes('style')).toContain('max-height:')

    wrapper.vm.clearActiveHistory()
    wrapper.unmount()
  })

  it('移动端地址栏收起只改变高度时不关闭已展开的工具集（回归）', async () => {
    const wrapper = mountLeftlist()
    await wrapper.get('#toolkit').trigger('click')
    expect(wrapper.get('#toolkit-menu').exists()).toBe(true)

    const originalWidth = window.innerWidth
    window.innerWidth = originalWidth
    window.dispatchEvent(new Event('resize'))
    await flushPromises()
    expect(wrapper.get('#toolkit-menu').exists()).toBe(true)

    window.innerWidth = originalWidth - 120
    window.dispatchEvent(new Event('resize'))
    await flushPromises()
    expect(wrapper.find('#toolkit-menu').exists()).toBe(false)

    window.innerWidth = originalWidth
    wrapper.unmount()
  })

  it('provides a task queue entry so the mounted tool is reachable（FRESCAN-64）', async () => {
    const wrapper = mountLeftlist()
    await wrapper.get('#toolkit').trigger('click')
    const labels = wrapper.findAll('[role="menuitem"]').map(node => node.text())
    expect(labels.some(text => text.includes('任务队列'))).toBe(true)

    const entry = wrapper.findAll('[role="menuitem"]').find(node => node.text().includes('任务队列'))
    await entry.trigger('click')
    expect(wrapper.emitted('useTool')).toEqual([['taskQueue']])
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

  it('冷启动只有 refresh cookie 时等 ensureSession 成功后再加载历史（回归）', async () => {
    apiMock.post.mockResolvedValue(jsonResponse({
      items: [{ id: 31, conversation_id: 9, title: '冷启动历史', prompt: '冷启动历史' }],
      total: 1
    }))
    userState.restoreUser.mockReturnValue(false)
    userState.ensureSession.mockResolvedValue(true)

    const wrapper = mountLeftlist()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(500)
    await flushPromises()

    expect(userState.ensureSession).toHaveBeenCalled()
    expect(apiMock.post).toHaveBeenCalledWith('/history', {
      prompt_keyword: '',
      limit: 50,
      offset: 0
    })
    expect(wrapper.get('.history-item').text()).toContain('冷启动历史')
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

  it('删除会话时通过导出的 chatDB 单例清理 IndexedDB（FRESCAN-59）', async () => {
    apiMock.post.mockResolvedValue(jsonResponse({
      items: [{ id: 21, conversation_id: 7, title: '待删除会话', prompt: '待删除会话' }],
      total: 1
    }))
    const wrapper = mountLeftlist()
    await openSearchBox(wrapper)
    await wrapper.get('.search-input').setValue('待删除')
    await wrapper.get('.search-btn').trigger('click')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    await wrapper.get('.history-delete').trigger('click')
    await flushPromises()

    expect(apiMock.deleteChatHistory).toHaveBeenCalledWith([7])
    expect(chatDbMock.deleteConversation).toHaveBeenCalledWith(7)
    expect(wrapper.findAll('.history-item')).toHaveLength(0)
    wrapper.unmount()
  })

  it('侧边栏退出时通知服务端吊销令牌并清理本地登录态', async () => {
    const wrapper = mountLeftlist()
    await flushAfterLogout(wrapper)

    expect(apiMock.logout).toHaveBeenCalledTimes(1)
    expect(userState.clearUser).toHaveBeenCalled()
    expect(wrapper.emitted('logout')).toHaveLength(1)
    wrapper.unmount()
  })
})

async function flushAfterLogout(wrapper) {
  await wrapper.get('.logout-btn').trigger('click')
  await flushPromises()
}
