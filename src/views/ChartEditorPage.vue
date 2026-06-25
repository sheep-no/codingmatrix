<template>
  <div class="chart-editor-page">
    <!-- 头部 -->
    <div class="editor-header">
      <div class="header-left">
        <button class="back-btn" aria-label="返回" @click="goBack">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
        </button>
        <div class="title-block">
          <h2>图表编辑器</h2>
          <span class="subtitle">导入数据 · 配置字段 · 一键导出</span>
        </div>
        <div v-if="charts.length > 0" class="header-stats">
          <span class="stat-badge">{{ charts.length }} 图表</span>
          <span class="stat-badge">{{ dataSources.length }} 数据源</span>
        </div>
      </div>
      <div class="header-right">
        <button class="header-btn" :aria-label="isDarkTheme ? '切换为浅色' : '切换为深色'" @click="toggleTheme">
          <svg v-if="!isDarkTheme" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" />
            <line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" />
            <line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
        </button>
        <button class="header-btn" :disabled="charts.length === 0" aria-label="导出当前图表" @click="exportChart">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="editor-content" :class="{ 'dark-theme': isDarkTheme }">
      <!-- 左侧面板 -->
      <div class="left-panel">
        <!-- 数据导入 -->
        <div class="panel-card">
          <h3 class="card-title">数据源</h3>
          <div class="upload-area" @dragover.prevent @drop.prevent="handleFileDrop" @click="handleUploadClick">
            <input ref="fileInput" type="file" accept=".xlsx,.xls,.csv,.json" multiple style="display: none" @change="handleFileSelect" />
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <p>拖拽或点击上传</p>
            <span class="upload-hint">支持 xlsx, csv, json</span>
          </div>
          <div v-if="dataSources.length > 0" class="data-list">
            <div
              v-for="(source, index) in dataSources"
              :key="index"
              class="data-item"
              :class="{ active: selectedDataSourceIndex === index }"
              @click="selectDataSource(index)"
            >
              <div class="data-item-info">
                <span class="data-name">{{ source.name }}</span>
                <span class="data-meta">{{ source.data.length }} 行</span>
              </div>
              <button class="data-remove" aria-label="删除数据源" @click.stop="removeDataSource(index)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- 图表类型 -->
        <div v-if="dataSources.length > 0" class="panel-card">
          <h3 class="card-title">图表类型</h3>
          <div class="chart-type-grid">
            <div
              v-for="type in basicChartTypes"
              :key="type.value"
              class="chart-type-card"
              :class="{ active: config.chartType === type.value }"
              @click="selectChartType(type.value)"
            >
              <svg v-if="type.icon === 'bar'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
              </svg>
              <svg v-else-if="type.icon === 'line'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <polyline points="3 17 9 11 13 15 17 9 21 13" />
              </svg>
              <svg v-else-if="type.icon === 'area'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M3 20 L3 12 L9 8 L15 14 L21 6 L21 20 Z" />
              </svg>
              <svg v-else-if="type.icon === 'pie'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M21.21 15.89A10 10 0 1 1 8 2.83" /><path d="M22 12A10 10 0 0 0 12 2v10z" />
              </svg>
              <svg v-else-if="type.icon === 'scatter'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <circle cx="6" cy="8" r="2" /><circle cx="12" cy="5" r="2" /><circle cx="18" cy="10" r="2" /><circle cx="10" cy="16" r="2" /><circle cx="16" cy="14" r="2" />
              </svg>
              <svg v-else-if="type.icon === 'radar'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5" />
              </svg>
              <span>{{ type.label }}</span>
            </div>
          </div>
        </div>

        <!-- 字段配置 -->
        <div v-if="currentDataSource" class="panel-card">
          <h3 class="card-title">字段配置</h3>
          <div class="field-group">
            <label>X 轴</label>
            <select v-model="config.xAxis" @change="updateChart">
              <option value="">选择字段</option>
              <option v-for="field in currentDataSource.fields" :key="field" :value="field">{{ field }}</option>
            </select>
          </div>
          <div class="field-group">
            <label>Y 轴</label>
            <select v-model="config.yAxis" @change="updateChart">
              <option value="">选择字段</option>
              <option v-for="field in currentDataSource.fields" :key="field" :value="field">{{ field }}</option>
            </select>
          </div>
          <div class="field-group">
            <label>聚合</label>
            <select v-model="config.aggregate" @change="updateChart">
              <option value="sum">求和</option>
              <option value="avg">平均值</option>
              <option value="count">计数</option>
              <option value="max">最大值</option>
              <option value="min">最小值</option>
              <option value="none">不聚合</option>
            </select>
          </div>
        </div>

        <!-- 样式配置 -->
        <div v-if="dataSources.length > 0" class="panel-card">
          <h3 class="card-title">样式</h3>
          <div class="field-group">
            <label>标题</label>
            <input v-model="config.title" type="text" placeholder="图表标题" @input="updateChart" />
          </div>
          <div class="field-group">
            <label>颜色</label>
            <div class="color-picker">
              <input v-model="config.color" type="color" @input="updateChart" />
              <span>{{ config.color }}</span>
            </div>
          </div>
          <div class="toggle-row">
            <span>显示图例</span>
            <label class="toggle-switch">
              <input v-model="config.showLegend" type="checkbox" @change="updateChart" />
              <span class="toggle-slider"></span>
            </label>
          </div>
          <div class="toggle-row">
            <span>显示数值</span>
            <label class="toggle-switch">
              <input v-model="config.showLabel" type="checkbox" @change="updateChart" />
              <span class="toggle-slider"></span>
            </label>
          </div>
          <div class="toggle-row">
            <span>平滑曲线</span>
            <label class="toggle-switch">
              <input v-model="config.smooth" type="checkbox" @change="updateChart" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>
      </div>

      <!-- 右侧预览区 -->
      <div class="right-panel">
        <div v-if="charts.length === 0" class="preview-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" aria-hidden="true">
            <line x1="18" y1="20" x2="18" y2="10" />
            <line x1="12" y1="20" x2="12" y2="4" />
            <line x1="6" y1="20" x2="6" y2="14" />
          </svg>
          <h3>导入数据开始创建图表</h3>
          <p>上传 Excel、CSV 或 JSON 文件</p>
        </div>
        <div v-else class="charts-preview">
          <div
            v-for="(chart, index) in charts"
            :key="chart.id"
            class="chart-preview-item"
            :class="{ active: selectedChartIndex === index }"
            @click="selectedChartIndex = index"
          >
            <div class="chart-preview-header">
              <span class="chart-preview-title">{{ chart.title || '图表 ' + (index + 1) }}</span>
              <div class="chart-preview-actions">
                <button class="chart-action" aria-label="导出此图表" title="导出 PNG" @click.stop="exportSingleChart(index)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                </button>
                <button class="chart-remove" aria-label="删除图表" @click.stop="removeChart(index)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>
            <div :ref="el => setChartRef(el, index)" class="chart-container"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部工具栏 -->
    <div class="editor-bottom-toolbar" :class="{ 'dark-theme': isDarkTheme }">
      <div class="toolbar-left">
        <span class="toolbar-status">
          <span v-if="dataSources.length === 0" class="status-dot status-idle"></span>
          <span v-else-if="charts.length === 0" class="status-dot status-warn"></span>
          <span v-else class="status-dot status-ready"></span>
          <span class="status-text">{{ statusText }}</span>
        </span>
      </div>
      <div class="toolbar-center">
        <button
          class="toolbar-btn toolbar-btn-primary"
          :disabled="!currentDataSource || !config.xAxis || !config.yAxis"
          aria-label="添加图表"
          @click="addChart"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="16" />
            <line x1="8" y1="12" x2="16" y2="12" />
          </svg>
          <span>添加图表</span>
          <kbd v-if="currentDataSource" class="toolbar-kbd">Enter</kbd>
        </button>
        <button
          class="toolbar-btn"
          :disabled="charts.length === 0"
          aria-label="导出全部图表"
          @click="exportAllCharts"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          <span>导出全部</span>
        </button>
        <button
          class="toolbar-btn"
          :disabled="charts.length === 0"
          aria-label="清空所有图表"
          @click="clearAllCharts"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <line x1="10" y1="11" x2="10" y2="17" />
            <line x1="14" y1="11" x2="14" y2="17" />
          </svg>
          <span>清空</span>
        </button>
      </div>
      <div class="toolbar-right">
        <button class="toolbar-btn toolbar-btn-ghost" aria-label="返回首页" @click="goBack">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            <polyline points="9 22 9 12 15 12 15 22" />
          </svg>
          <span>返回首页</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import {
  LineChart, BarChart, PieChart, ScatterChart, RadarChart, GaugeChart
} from 'echarts/charts'
import {
  GridComponent, TitleComponent, TooltipComponent, LegendComponent, ToolboxComponent, DataZoomComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import * as XLSX from 'xlsx'

echarts.use([
  GridComponent, TitleComponent, TooltipComponent, LegendComponent,
  ToolboxComponent, DataZoomComponent, LineChart, BarChart, PieChart,
  ScatterChart, RadarChart, GaugeChart, CanvasRenderer
])

const router = useRouter()
const fileInput = ref(null)
const isDarkTheme = ref(false)
const dataSources = ref([])
const selectedDataSourceIndex = ref(null)
const selectedChartIndex = ref(0)
const charts = ref([])
const chartRefs = ref([])
let chartIdCounter = 0
let chartInstances = {}

const config = ref({
  chartType: 'bar',
  title: '',
  xAxis: '',
  yAxis: '',
  showLegend: true,
  showLabel: false,
  smooth: true,
  color: '#3b82f6',
  aggregate: 'sum',
  animation: { enabled: true, duration: 1000, easing: 'cubicOut' }
})

const currentDataSource = computed(() => {
  if (selectedDataSourceIndex.value === null) return null
  return dataSources.value[selectedDataSourceIndex.value]
})

const statusText = computed(() => {
  if (dataSources.value.length === 0) return '请先导入数据'
  if (charts.value.length === 0) return '配置字段后点击"添加图表"'
  return `已创建 ${charts.value.length} 个图表`
})

const basicChartTypes = [
  { value: 'bar', label: '柱状图', icon: 'bar' },
  { value: 'line', label: '折线图', icon: 'line' },
  { value: 'area', label: '面积图', icon: 'area' },
  { value: 'pie', label: '饼图', icon: 'pie' },
  { value: 'scatter', label: '散点图', icon: 'scatter' },
  { value: 'radar', label: '雷达图', icon: 'radar' },
]

const setChartRef = (el, index) => {
  if (el) chartRefs.value[index] = el
}

const goBack = () => {
  if (window.opener) {
    window.close()
  } else {
    router.push('/')
  }
}

const selectDataSource = index => {
  selectedDataSourceIndex.value = index
  const source = dataSources.value[index]
  if (source && source.fields.length > 0) {
    if (!config.value.xAxis) config.value.xAxis = source.fields[0]
    if (config.value.yAxis === '' || !source.fields.includes(config.value.yAxis)) {
      config.value.yAxis = source.fields[1] || source.fields[0]
    }
  }
  updateChart()
}

const removeDataSource = index => {
  dataSources.value.splice(index, 1)
  if (selectedDataSourceIndex.value === index) {
    selectedDataSourceIndex.value = dataSources.value.length > 0 ? 0 : null
  }
  updateChart()
}

const handleUploadClick = () => fileInput.value?.click()

const handleFileSelect = e => {
  for (const file of e.target.files) processFile(file)
  e.target.value = ''
}

const handleFileDrop = e => {
  for (const file of e.dataTransfer.files) processFile(file)
}

const processFile = async file => {
  const ext = file.name.split('.').pop().toLowerCase()
  const reader = new FileReader()

  if (ext === 'json') {
    reader.onload = e => {
      try {
        const data = JSON.parse(e.target.result)
        const arr = Array.isArray(data) ? data : [data]
        const fields = arr.length > 0 ? Object.keys(arr[0]) : []
        dataSources.value.push({ name: file.name, data: arr, fields })
        if (selectedDataSourceIndex.value === null) {
          selectedDataSourceIndex.value = dataSources.value.length - 1
          selectDataSource(selectedDataSourceIndex.value)
        } else {
          updateChart()
        }
        ElMessage.success(`已导入 ${file.name}（${arr.length} 行）`)
      } catch (err) {
        ElMessage.error('JSON 解析失败')
      }
    }
    reader.readAsText(file)
  } else {
    reader.onload = e => {
      try {
        const wb = XLSX.read(e.target.result, { type: 'array' })
        const ws = wb.Sheets[wb.SheetNames[0]]
        const data = XLSX.utils.sheet_to_json(ws)
        const fields = data.length > 0 ? Object.keys(data[0]) : []
        dataSources.value.push({ name: file.name, data, fields })
        if (selectedDataSourceIndex.value === null) {
          selectedDataSourceIndex.value = dataSources.value.length - 1
          selectDataSource(selectedDataSourceIndex.value)
        } else {
          updateChart()
        }
        ElMessage.success(`已导入 ${file.name}（${data.length} 行）`)
      } catch (err) {
        ElMessage.error('文件解析失败')
      }
    }
    reader.readAsArrayBuffer(file)
  }
}

const selectChartType = type => {
  config.value.chartType = type
  updateChart()
}

const addChart = () => {
  if (!currentDataSource.value) {
    ElMessage.warning('请先导入数据')
    return
  }
  if (!config.value.xAxis || !config.value.yAxis) {
    ElMessage.warning('请先选择 X 轴和 Y 轴字段')
    return
  }
  const newChart = {
    id: ++chartIdCounter,
    chartType: config.value.chartType,
    title: config.value.title || `图表 ${charts.value.length + 1}`,
    xAxis: config.value.xAxis,
    yAxis: config.value.yAxis,
    color: config.value.color,
    showLegend: config.value.showLegend,
    showLabel: config.value.showLabel,
    smooth: config.value.smooth,
    aggregate: config.value.aggregate
  }
  charts.value.push(newChart)
  selectedChartIndex.value = charts.value.length - 1
  nextTick(() => renderChart(charts.value.length - 1))
  ElMessage.success(`已添加：${newChart.title}`)
}

const removeChart = index => {
  if (chartInstances[index]) {
    chartInstances[index].dispose()
    delete chartInstances[index]
  }
  charts.value.splice(index, 1)
  if (selectedChartIndex.value >= charts.value.length) {
    selectedChartIndex.value = Math.max(0, charts.value.length - 1)
  } else if (selectedChartIndex.value > index) {
    selectedChartIndex.value -= 1
  }
}

const clearAllCharts = async () => {
  if (charts.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定要清空全部 ${charts.value.length} 个图表吗？`, '清空图表', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  Object.values(chartInstances).forEach(c => c.dispose())
  chartInstances = {}
  charts.value = []
  selectedChartIndex.value = 0
  ElMessage.success('已清空全部图表')
}

const updateChart = () => {
  renderChart(selectedChartIndex.value)
}

const renderChart = index => {
  if (index === null || index < 0 || index >= charts.value.length) return
  if (!currentDataSource.value) return

  const chart = charts.value[index]
  const el = chartRefs.value[index]
  if (!el) return

  if (!chartInstances[index]) {
    chartInstances[index] = echarts.init(el)
  }

  const instance = chartInstances[index]
  const data = currentDataSource.value.data

  const aggregated = aggregateData(data, chart)
  const option = buildChartOption(chart, aggregated)
  instance.setOption(option, true)
}

const aggregateData = (data, chart) => {
  if (!chart.xAxis || !chart.yAxis || chart.aggregate === 'none') {
    return data.map(d => ({ name: d[chart.xAxis], value: Number(d[chart.yAxis]) || 0 }))
  }

  const groups = {}
  data.forEach(d => {
    const key = d[chart.xAxis]
    if (!groups[key]) groups[key] = []
    groups[key].push(Number(d[chart.yAxis]) || 0)
  })

  return Object.entries(groups).map(([name, values]) => {
    let value
    switch (chart.aggregate) {
      case 'sum': value = values.reduce((a, b) => a + b, 0); break
      case 'avg': value = values.reduce((a, b) => a + b, 0) / values.length; break
      case 'count': value = values.length; break
      case 'max': value = Math.max(...values); break
      case 'min': value = Math.min(...values); break
      default: value = values[0]
    }
    return { name, value }
  })
}

const buildChartOption = (chart, data) => {
  const names = data.map(d => d.name)
  const values = data.map(d => d.value)

  const baseOption = {
    animation: chart.animation?.enabled ?? true,
    animationDuration: chart.animation?.duration ?? 1000,
    tooltip: { trigger: 'axis' },
    grid: { left: '12%', right: '8%', bottom: '12%', top: '18%', containLabel: true },
    xAxis: { type: 'category', data: names, axisTick: { alignWithLabel: true } },
    yAxis: { type: 'value' },
  }

  let series
  switch (chart.chartType) {
    case 'bar':
      series = [{ type: 'bar', data: values, itemStyle: { color: chart.color } }]
      break
    case 'line':
      series = [{ type: 'line', data: values, smooth: chart.smooth, itemStyle: { color: chart.color } }]
      break
    case 'area':
      series = [{ type: 'line', data: values, smooth: chart.smooth, areaStyle: {}, itemStyle: { color: chart.color } }]
      break
    case 'scatter':
      series = [{ type: 'scatter', data: values, itemStyle: { color: chart.color } }]
      break
    case 'pie':
      baseOption.xAxis = null
      baseOption.yAxis = null
      series = [{ type: 'pie', data: data.map(d => ({ name: d.name, value: d.value })), itemStyle: { color: chart.color } }]
      break
    case 'radar':
      baseOption.xAxis = null
      baseOption.yAxis = null
      baseOption.radar = { indicator: names.map(n => ({ name: n, max: Math.max(...values) * 1.2 })) }
      series = [{ type: 'radar', data: [{ value: values, name: chart.title }] }]
      break
    default:
      series = [{ type: 'bar', data: values, itemStyle: { color: chart.color } }]
  }

  baseOption.series = series

  if (chart.showLegend && chart.chartType !== 'pie' && chart.chartType !== 'radar') {
    baseOption.legend = { data: [chart.title || '数据'] }
  }

  return baseOption
}

const exportChart = () => exportSingleChart(selectedChartIndex.value)

const exportSingleChart = index => {
  if (index === null || index < 0 || index >= charts.value.length) return
  const instance = chartInstances[index]
  if (!instance) return
  const url = instance.getDataURL({ type: 'png', pixelRatio: 2 })
  const a = document.createElement('a')
  a.href = url
  a.download = (charts.value[index]?.title || `chart-${index + 1}`) + '.png'
  a.click()
  ElMessage.success(`已导出：${a.download}`)
}

const exportAllCharts = async () => {
  if (charts.value.length === 0) return
  for (let i = 0; i < charts.value.length; i++) {
    exportSingleChart(i)
    await new Promise(r => setTimeout(r, 200))
  }
}

const toggleTheme = () => {
  isDarkTheme.value = !isDarkTheme.value
}

const handleKeydown = e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    addChart()
  }
}

watch(selectedChartIndex, (newVal, oldVal) => {
  if (newVal >= 0 && newVal < charts.value.length) {
    const chart = charts.value[newVal]
    config.value.chartType = chart.chartType
    config.value.title = chart.title
    config.value.xAxis = chart.xAxis
    config.value.yAxis = chart.yAxis
    config.value.color = chart.color
    config.value.showLegend = chart.showLegend
    config.value.showLabel = chart.showLabel
    config.value.smooth = chart.smooth
    config.value.aggregate = chart.aggregate
    nextTick(() => renderChart(newVal))
  }
})

watch(() => charts.value.length, (newLen, oldLen) => {
  if (newLen < oldLen) {
    nextTick(() => {
      charts.value.forEach((_, i) => renderChart(i))
    })
  }
})

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  Object.values(chartInstances).forEach(c => c.dispose())
  chartInstances = {}
})
</script>

<style scoped>
.chart-editor-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  overflow: hidden;
}

/* 头部 */
.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
  flex-shrink: 0;
  height: 64px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
  min-width: 0;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.back-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--color-primary-300);
}

.back-btn svg {
  width: 18px;
  height: 18px;
}

.title-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.title-block h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.subtitle {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.2;
}

.header-stats {
  display: flex;
  gap: 8px;
}

.stat-badge {
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border-radius: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.header-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
}

.header-btn:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--color-primary-300);
}

.header-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.header-btn svg {
  width: 18px;
  height: 18px;
}

/* 主内容 */
.editor-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

/* 左侧面板 */
.left-panel {
  width: 300px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  border-right: 1px solid var(--border-color);
  overflow-y: auto;
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.panel-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 16px;
}

.card-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 上传区域 */
.upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
  border: 2px dashed var(--border-color);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
}

.upload-area:hover {
  border-color: var(--color-primary-400);
  background: var(--color-primary-50);
}

.upload-area svg {
  width: 32px;
  height: 32px;
  margin-bottom: 8px;
  color: var(--text-tertiary);
}

.upload-area p {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.upload-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 数据列表 */
.data-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
}

.data-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.data-item:hover { background: var(--bg-secondary); }
.data-item.active { background: var(--color-primary-100); }

.data-item-info { display: flex; flex-direction: column; }
.data-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.data-meta { font-size: 11px; color: var(--text-tertiary); }

.data-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s ease;
}

.data-item:hover .data-remove { opacity: 1; }
.data-remove:hover { background: var(--color-danger-100); color: var(--color-danger-600); }
.data-remove svg { width: 14px; height: 14px; }

/* 图表类型网格 */
.chart-type-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.chart-type-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.chart-type-card:hover { border-color: var(--color-primary-300); }
.chart-type-card.active {
  background: var(--color-primary-100);
  border-color: var(--color-primary-500);
  color: var(--color-primary-600);
}

.chart-type-card svg { width: 24px; height: 24px; }
.chart-type-card span { font-size: 12px; }

/* 字段配置 */
.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.field-group label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.field-group select, .field-group input[type="text"] {
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 13px;
}

.field-group select:focus, .field-group input:focus {
  outline: none;
  border-color: var(--color-primary-500);
}

/* 颜色选择器 */
.color-picker {
  display: flex;
  align-items: center;
  gap: 8px;
}

.color-picker input[type="color"] {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  padding: 0;
}

.color-picker span { font-size: 13px; color: var(--text-secondary); }

/* 切换开关 */
.toggle-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}

.toggle-row span { font-size: 13px; color: var(--text-secondary); }

.toggle-switch {
  position: relative;
  width: 40px;
  height: 22px;
}

.toggle-switch input { opacity: 0; width: 0; height: 0; }

.toggle-slider {
  position: absolute;
  inset: 0;
  background: var(--bg-tertiary);
  border-radius: 11px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  left: 3px;
  bottom: 3px;
  background: var(--bg-primary);
  border-radius: 50%;
  transition: all 0.2s ease;
}

.toggle-switch input:checked + .toggle-slider { background: var(--color-primary-500); }
.toggle-switch input:checked + .toggle-slider::before { transform: translateX(18px); }

/* 右侧预览 */
.right-panel {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  color: var(--text-tertiary);
}

.preview-empty svg { width: 80px; height: 80px; margin-bottom: 20px; opacity: 0.3; }
.preview-empty h3 { font-size: 18px; margin: 0 0 8px; color: var(--text-secondary); }
.preview-empty p { margin: 0; font-size: 14px; }

.charts-preview {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.chart-preview-item {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
}

.chart-preview-item.active {
  border-color: var(--color-primary-400);
  box-shadow: 0 0 0 3px var(--color-primary-100);
}

.chart-preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
}

.chart-preview-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.chart-preview-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.chart-action, .chart-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.2s ease;
}

.chart-action:hover { background: var(--color-primary-100); color: var(--color-primary-600); }
.chart-remove:hover { background: var(--color-danger-100); color: var(--color-danger-600); }
.chart-action svg, .chart-remove svg { width: 16px; height: 16px; }

.chart-container {
  width: 100%;
  height: 400px;
}

/* 底部工具栏 */
.editor-bottom-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
  flex-shrink: 0;
  gap: 16px;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.04);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 0 0 auto;
}

.toolbar-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  font-size: 12px;
  color: var(--text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-idle { background: var(--text-tertiary); }
.status-warn { background: var(--warning); box-shadow: 0 0 6px var(--warning); }
.status-ready { background: var(--success); box-shadow: 0 0 6px var(--success); }

.status-text { white-space: nowrap; }

.toolbar-center {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  justify-content: center;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

.toolbar-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.toolbar-btn:hover:not(:disabled) {
  border-color: var(--color-primary-300);
  background: var(--bg-tertiary);
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
}

.toolbar-btn:active:not(:disabled) {
  transform: translateY(0);
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toolbar-btn svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.toolbar-btn-primary {
  background: var(--color-primary-500);
  border-color: var(--color-primary-500);
  color: white;
  font-weight: 600;
}

.toolbar-btn-primary:hover:not(:disabled) {
  background: var(--color-primary-600);
  border-color: var(--color-primary-600);
  color: white;
}

.toolbar-btn-ghost {
  background: transparent;
  border-color: transparent;
}

.toolbar-btn-ghost:hover:not(:disabled) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
}

.toolbar-kbd {
  display: inline-block;
  padding: 2px 6px;
  margin-left: 4px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, monospace;
  line-height: 1;
}

.toolbar-btn:not(.toolbar-btn-primary) .toolbar-kbd {
  background: var(--bg-tertiary);
}

/* 暗色模式 */
.dark-theme {
  --bg-primary: #1a1a2e;
  --bg-secondary: #16213e;
  --bg-tertiary: #0f3460;
  --border-color: #2a2a4a;
  --text-primary: #e0e0e0;
  --text-secondary: #a0a0b0;
  --text-tertiary: #606080;
}

.dark-theme .chart-type-card.active {
  background: #2a2a4a;
}

.dark-theme .upload-area:hover {
  background: #0f3460;
}

.dark-theme .editor-bottom-toolbar {
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.3);
}

/* 响应式 */
@media (max-width: 900px) {
  .editor-content { flex-direction: column; }
  .left-panel { width: 100%; border-right: none; border-bottom: 1px solid var(--border-color); max-height: 50vh; }
  .chart-type-grid { grid-template-columns: repeat(6, 1fr); }
  .editor-bottom-toolbar { flex-direction: column; align-items: stretch; gap: 8px; }
  .toolbar-center { justify-content: stretch; }
  .toolbar-center .toolbar-btn { flex: 1; justify-content: center; }
}

@media (max-width: 600px) {
  .editor-header { padding: 8px 12px; height: 56px; }
  .title-block h2 { font-size: 16px; }
  .subtitle { display: none; }
  .header-stats { display: none; }
  .toolbar-btn span:not(.toolbar-kbd) { display: none; }
}
</style>
