import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getUsers } = vi.hoisted(() => ({ getUsers: vi.fn() }))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() }
}))

vi.mock('@/utils/api/index', () => ({
  api: {
    getUsers,
    createUser: vi.fn(),
    updateUser: vi.fn(),
    resetUserPassword: vi.fn(),
    deleteUser: vi.fn()
  }
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => ({ userId: 1 })
}))

import UserManagement from './UserManagement.vue'

describe('UserManagement 弹窗可访问性（FRESCAN-63）', () => {
  beforeEach(() => {
    getUsers.mockReset()
    getUsers.mockResolvedValue({ users: [], total: 0, page: 1, page_size: 10 })
  })

  it('创建用户弹窗暴露 dialog 语义并支持 Escape 关闭', async () => {
    const wrapper = mount(UserManagement, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('button.create-user-btn').trigger('click')

    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.attributes('aria-modal')).toBe('true')
    expect(dialog.attributes('aria-labelledby')).toBe('create-user-dialog-title')
    expect(wrapper.get('#create-user-dialog-title').text()).toBe('创建用户')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
