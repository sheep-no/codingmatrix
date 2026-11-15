import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ModelSelector from './ModelSelector.vue'

const FREE_MODEL = {
  id: 'qwen3-8b',
  name: 'Qwen3 8B',
  provider: 'siliconflow',
  max_context: 131072,
  is_free: true,
  cost_per_1m_input: 0,
  tags: ['通用']
}

const PAID_MODEL = {
  id: 'paid-model',
  name: 'Paid Model',
  provider: 'siliconflow',
  max_context: 32768,
  is_free: false,
  cost_per_1m_input: 2.5,
  tags: []
}

async function openSelector(props = {}) {
  const wrapper = mount(ModelSelector, {
    props: { models: [FREE_MODEL, PAID_MODEL], groupByProvider: false, ...props }
  })
  await wrapper.get('.selector-trigger').trigger('click')
  return wrapper
}

describe('ModelSelector 价格与免费标记', () => {
  it('免费模型显示「免费」标签且不显示价格', async () => {
    const wrapper = await openSelector()
    const freeItem = wrapper.findAll('.model-item')[0]
    expect(freeItem.get('.meta-item.free').text()).toBe('免费')
    expect(freeItem.find('.meta-item.cost').exists()).toBe(false)
  })

  it('付费模型显示单价且不显示「免费」标签', async () => {
    const wrapper = await openSelector()
    const paidItem = wrapper.findAll('.model-item')[1]
    expect(paidItem.get('.meta-item.cost').text()).toBe('¥2.5/1M')
    expect(paidItem.find('.meta-item.free').exists()).toBe(false)
  })

  it('上下文长度使用 max_context 渲染', async () => {
    const wrapper = await openSelector()
    expect(wrapper.findAll('.model-item')[0].get('.meta-item.context').text()).toBe('128k')
  })

  it('缺少 max_context 时回退到 context_length', async () => {
    const wrapper = await openSelector({
      models: [{ id: 'custom', name: 'Custom', provider: 'p', context_length: 65536, is_free: true }]
    })
    expect(wrapper.get('.meta-item.context').text()).toBe('64k')
  })
})
