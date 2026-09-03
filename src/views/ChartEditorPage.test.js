import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  instances: [],
  routerPush: vi.fn(),
  success: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush })
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: mocks.success,
    warning: vi.fn(),
    error: vi.fn()
  },
  ElMessageBox: {
    confirm: vi.fn(() => Promise.resolve())
  }
}))

vi.mock('echarts', () => ({
  use: vi.fn(),
  init: vi.fn(() => {
    const instance = {
      setOption: vi.fn(),
      dispose: vi.fn(),
      getDataURL: vi.fn(() => 'data:image/png;base64,test')
    }
    mocks.instances.push(instance)
    return instance
  })
}))

vi.mock('echarts/charts', () => ({
  LineChart: {},
  BarChart: {},
  PieChart: {},
  ScatterChart: {},
  RadarChart: {},
  GaugeChart: {}
}))

vi.mock('echarts/components', () => ({
  GridComponent: {},
  TitleComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  ToolboxComponent: {},
  DataZoomComponent: {}
}))

vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

import ChartEditorPage from './ChartEditorPage.vue'

async function uploadJson(wrapper, name, data) {
  const input = wrapper.get('input[type="file"]')
  const file = new File([JSON.stringify(data)], name, { type: 'application/json' })
  Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
  await input.trigger('change')
  await flushPromises()
  await vi.waitFor(() => expect(wrapper.findAll('.data-item')).toHaveLength(data.length ? 1 : 0))
}

async function addChart(wrapper) {
  await wrapper.get('.toolbar-btn-primary').trigger('click')
  await flushPromises()
}

describe('ChartEditorPage', () => {
  beforeEach(() => {
    mocks.instances.length = 0
    mocks.routerPush.mockClear()
    mocks.success.mockClear()
  })

  it('updates the selected chart configuration and ECharts options', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'sales.json', [
      { month: 'Jan', sales: 10 },
      { month: 'Feb', sales: 20 }
    ])
    await addChart(wrapper)

    await wrapper.get('input[placeholder="图表标题"]').setValue('月度销售')
    const toggles = wrapper.findAll('.toggle-switch input')
    await toggles[1].setValue(true)
    await wrapper.findAll('.chart-type-card')[3].trigger('click')

    expect(wrapper.get('.chart-preview-title').text()).toBe('月度销售')
    const option = mocks.instances[0].setOption.mock.calls.at(-1)[0]
    expect(option.series[0]).toMatchObject({ name: '月度销售', type: 'pie', label: { show: true } })
    expect(option.legend).toMatchObject({ show: true, data: ['Jan', 'Feb'] })
  })

  it('keeps charts bound to their original data and preserves instances after removal', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'first.json', [{ label: 'A', value: 1 }])
    await addChart(wrapper)

    const input = wrapper.get('input[type="file"]')
    const secondFile = new File([JSON.stringify([{ label: 'B', value: 2 }])], 'second.json', { type: 'application/json' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [secondFile] })
    await input.trigger('change')
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.findAll('.data-item')).toHaveLength(2))

    await wrapper.findAll('.data-item')[1].trigger('click')
    await addChart(wrapper)
    expect(wrapper.findAll('.chart-preview-item')).toHaveLength(2)

    await wrapper.findAll('.chart-preview-item')[0].trigger('click')
    await flushPromises()
    expect(mocks.instances[0].setOption.mock.calls.at(-1)[0].xAxis.data).toEqual(['A'])

    await wrapper.findAll('.chart-preview-item')[1].trigger('click')
    await flushPromises()
    expect(mocks.instances[1].setOption.mock.calls.at(-1)[0].xAxis.data).toEqual(['B'])

    await wrapper.findAll('.chart-remove')[0].trigger('click')
    await flushPromises()
    expect(mocks.instances[0].dispose).toHaveBeenCalledOnce()
    expect(mocks.instances[1].dispose).not.toHaveBeenCalled()
    expect(wrapper.findAll('.chart-preview-item')).toHaveLength(1)

    await wrapper.get('input[placeholder="图表标题"]').setValue('保留的图表')
    expect(mocks.instances).toHaveLength(2)
    expect(mocks.instances[1].setOption.mock.calls.at(-1)[0].series[0].name).toBe('保留的图表')
  })

  it('keeps the selected data source stable when an earlier source is removed', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'first.json', [{ label: 'A', value: 1 }])

    const input = wrapper.get('input[type="file"]')
    const secondFile = new File([JSON.stringify([{ label: 'B', value: 2 }])], 'second.json', { type: 'application/json' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [secondFile] })
    await input.trigger('change')
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.findAll('.data-item')).toHaveLength(2))

    await wrapper.findAll('.data-item')[1].trigger('click')
    await wrapper.findAll('.data-remove')[0].trigger('click')

    expect(wrapper.get('.data-item.active .data-name').text()).toBe('second.json')
    expect(wrapper.get('.toolbar-kbd').text()).toBe('Ctrl/⌘ + Enter')
  })
})
