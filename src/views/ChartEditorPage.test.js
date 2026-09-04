import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  instances: [],
  routerPush: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush })
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: mocks.success,
    warning: mocks.warning,
    error: mocks.error
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
      resize: vi.fn(),
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

enableAutoUnmount(afterEach)

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
    mocks.warning.mockClear()
    mocks.error.mockClear()
    localStorage.clear()
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
    expect(option.title).toMatchObject({ text: '月度销售' })
    expect(option.legend).toMatchObject({ show: true, data: ['Jan', 'Feb'] })
  })

  it('removes charts bound to a deleted data source', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'sales.json', [{ month: 'Jan', sales: 10 }])
    await addChart(wrapper)

    await wrapper.get('.data-remove').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.data-item')).toHaveLength(0)
    expect(wrapper.findAll('.chart-preview-item')).toHaveLength(0)
    expect(mocks.instances[0].dispose).toHaveBeenCalledOnce()
  })

  it('handles special category keys during aggregation', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'special.json', [
      { category: 'constructor', value: 2 },
      { category: '__proto__', value: 3 }
    ])
    await addChart(wrapper)

    const option = mocks.instances[0].setOption.mock.calls.at(-1)[0]
    expect(option.xAxis.data).toEqual(['constructor', '__proto__'])
  })

  it('rejects changing an existing chart to a non-numeric measure', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'labels.json', [
      { category: 'A', value: 1, status: 'ready' }
    ])
    await addChart(wrapper)

    const yAxis = wrapper.findAll('.field-group select')[1]
    await yAxis.setValue('status')
    await flushPromises()

    expect(yAxis.element.value).toBe('value')
    expect(mocks.warning).toHaveBeenCalledWith('字段“status”没有可绘制的数值')
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

  it('exports the selected chart from its id-keyed ECharts instance', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'sales.json', [{ month: 'Jan', sales: 10 }])
    await addChart(wrapper)

    await wrapper.get('.chart-action').trigger('click')

    expect(mocks.instances[0].getDataURL).toHaveBeenCalledWith({ type: 'png', pixelRatio: 2 })
    expect(mocks.success).toHaveBeenCalledWith('已导出：图表 1.png')
  })

  it('maps numeric scatter fields to x-y points on value axes', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'correlation.json', [
      { temperature: 18, sales: 12 },
      { temperature: 24, sales: 19 }
    ])
    await addChart(wrapper)

    await wrapper.findAll('.chart-type-card')[4].trigger('click')

    const option = mocks.instances[0].setOption.mock.calls.at(-1)[0]
    expect(option.xAxis).toEqual({ type: 'value' })
    expect(option.series[0]).toMatchObject({
      type: 'scatter',
      data: [[18, 12], [24, 19]]
    })
  })

  it('collects fields from every row and reports missing values', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'mixed.json', [
      { month: 'Jan', sales: 10 },
      { month: 'Feb', profit: 3 }
    ])

    const options = wrapper.findAll('.field-group select').at(0).findAll('option').map(option => option.text())
    expect(options).toEqual(['选择字段', 'month', 'sales', 'profit'])
    expect(wrapper.get('.data-meta').text()).toContain('2 处缺失')
    expect(mocks.warning).toHaveBeenCalledWith(expect.stringContaining('发现 2 处缺失值'))
  })

  it('rejects a chart when the selected measure has no numeric values', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'labels.json', [{ category: 'A', status: 'ready' }])

    await addChart(wrapper)

    expect(wrapper.findAll('.chart-preview-item')).toHaveLength(0)
    expect(mocks.warning).toHaveBeenCalledWith('字段“status”没有可绘制的数值')
  })

  it('restores data sources and charts from the local draft', async () => {
    const firstWrapper = mount(ChartEditorPage)
    await uploadJson(firstWrapper, 'sales.json', [{ month: 'Jan', sales: 10 }])
    await addChart(firstWrapper)
    firstWrapper.unmount()

    const restoredWrapper = mount(ChartEditorPage)
    await flushPromises()

    expect(restoredWrapper.findAll('.data-item')).toHaveLength(1)
    expect(restoredWrapper.findAll('.chart-preview-item')).toHaveLength(1)
    expect(restoredWrapper.get('.data-name').text()).toBe('sales.json')
    expect(mocks.instances.at(-1).setOption).toHaveBeenCalled()
  })

  it('rejects files larger than the import limit', async () => {
    const wrapper = mount(ChartEditorPage)
    const input = wrapper.get('input[type="file"]')
    const file = new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'large.csv', { type: 'text/csv' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })

    await input.trigger('change')

    expect(wrapper.findAll('.data-item')).toHaveLength(0)
    expect(mocks.error).toHaveBeenCalledWith('large.csv 超过 2 MB，请精简后重试')
  })

  it('rejects empty structured data', async () => {
    const wrapper = mount(ChartEditorPage)
    const input = wrapper.get('input[type="file"]')
    const file = new File(['[]'], 'empty.json', { type: 'application/json' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })

    await input.trigger('change')
    await flushPromises()

    expect(wrapper.findAll('.data-item')).toHaveLength(0)
    await vi.waitFor(() => expect(mocks.error).toHaveBeenCalledWith('文件中没有可用数据'))
  })

  it('undoes and redoes chart removal', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'sales.json', [{ month: 'Jan', sales: 10 }])
    await addChart(wrapper)
    await vi.waitFor(() => expect(wrapper.get('[aria-label="撤销"]').attributes('disabled')).toBeUndefined())

    await wrapper.get('.chart-remove').trigger('click')
    await wrapper.get('[aria-label="撤销"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.chart-preview-item')).toHaveLength(1)
    expect(wrapper.get('[aria-label="重做"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[aria-label="重做"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.chart-preview-item')).toHaveLength(0)
  })

  it('supports keyboard undo and redo shortcuts', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'sales.json', [{ month: 'Jan', sales: 10 }])
    await addChart(wrapper)
    await vi.waitFor(() => expect(wrapper.get('[aria-label="撤销"]').attributes('disabled')).toBeUndefined())

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true }))
    await flushPromises()
    expect(wrapper.findAll('.chart-preview-item')).toHaveLength(0)
    expect(wrapper.findAll('.data-item')).toHaveLength(1)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, shiftKey: true }))
    await flushPromises()
    expect(wrapper.findAll('.chart-preview-item')).toHaveLength(1)
  })

  it('drops the redo branch after editing an undone state', async () => {
    const wrapper = mount(ChartEditorPage)
    await uploadJson(wrapper, 'sales.json', [{ month: 'Jan', sales: 10 }])
    await addChart(wrapper)
    await vi.waitFor(() => expect(wrapper.get('[aria-label="撤销"]').attributes('disabled')).toBeUndefined())

    await wrapper.get('.chart-remove').trigger('click')
    await wrapper.get('[aria-label="撤销"]').trigger('click')
    await flushPromises()
    await wrapper.get('input[placeholder="图表标题"]').setValue('新的历史分支')
    await vi.waitFor(() => expect(wrapper.get('[aria-label="重做"]').attributes('disabled')).toBeDefined())

    expect(wrapper.get('.chart-preview-title').text()).toBe('新的历史分支')
  })
})
