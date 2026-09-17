import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import Dockerfile from './Dockerfile.vue'

describe('Dockerfile config modal', () => {
  it('shows the add-service action and full service names', () => {
    const wrapper = mount(Dockerfile, { props: { visible: true } })
    expect(wrapper.get('.add-service-btn').text()).toContain('添加服务')
    expect(wrapper.findAll('.service-name').map((node) => node.text())).toEqual([
      '前端应用',
      '后端 API',
      'MySQL 数据库',
    ])
    expect(wrapper.findAll('.service-name').map((node) => node.attributes('title'))).toEqual([
      '前端应用',
      '后端 API',
      'MySQL 数据库',
    ])
  })
})
