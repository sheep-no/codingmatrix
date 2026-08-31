import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import HistoryItem from './HistoryItem.vue'

describe('HistoryItem', () => {
  it('renders untrusted titles as text while preserving highlights', () => {
    const wrapper = mount(HistoryItem, {
      props: {
        item: { title: '<img src=x onerror=alert(1)> hello' },
        searchKeyword: 'hello'
      }
    })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('mark').text()).toBe('hello')
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
  })
})
