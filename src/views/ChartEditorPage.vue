<template>
  <div class="chart-editor-page">
    <!-- 头部 -->
    <div class="editor-header" :class="{ 'dark-theme': isDarkTheme }">
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
        <button class="header-btn" :disabled="!canUndo" aria-label="撤销" title="撤销 (Ctrl/⌘ + Z)" @click="undo">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <polyline points="9 14 4 9 9 4" />
            <path d="M4 9h9a7 7 0 0 1 7 7v1" />
          </svg>
        </button>
        <button class="header-btn" :disabled="!canRedo" aria-label="重做" title="重做 (Ctrl/⌘ + Shift + Z)" @click="redo">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <polyline points="15 14 20 9 15 4" />
            <path d="M20 9h-9a7 7 0 0 0-7 7v1" />
          </svg>
        </button>
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
        <button class="header-btn" :disabled="selectedChartIndex === null" aria-label="导出当前图表" @click="exportChart">
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
            <span class="upload-hint">支持 xlsx, xls, csv, json，单文件不超过 2 MB</span>
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
                <span class="data-meta">
                  <template v-if="source.needsRelink">需要重新选择文件 · </template>
                  <template v-else>{{ source.data.length }} 行 · </template>{{ source.fields.length }} 字段
                  <template v-if="source.missingValues"> · {{ source.missingValues }} 处缺失</template>
                </span>
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
              <option v-for="field in availableFields" :key="field" :value="field">{{ field }}</option>
            </select>
          </div>
          <div class="field-group">
            <label>Y 轴</label>
            <select v-model="config.yAxis" @change="updateChart">
              <option value="">选择字段</option>
              <option v-for="field in availableFields" :key="field" :value="field">{{ field }}</option>
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
          <kbd v-if="currentDataSource" class="toolbar-kbd">Ctrl/⌘ + Enter</kbd>
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
          :disabled="dataSources.length === 0"
          aria-label="导出项目配置"
          @click="exportProject"
        >
          <span>导出项目</span>
        </button>
        <button class="toolbar-btn" aria-label="导入项目配置" @click="projectFileInput?.click()">
          <input ref="projectFileInput" type="file" accept="application/json,.json" style="display: none" @change="handleProjectImport" />
          <span>导入项目</span>
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
const projectFileInput = ref(null)
const isDarkTheme = ref(false)
const dataSources = ref([])
const selectedDataSourceIndex = ref(null)
const selectedChartIndex = ref(null)
const charts = ref([])
const chartRefs = ref([])
let chartIdCounter = 0
let dataSourceIdCounter = 0
let chartInstances = {}
let draftSaveTimer = null
let historySaveTimer = null
let draftStorageWarningShown = false
let applyingHistory = false
let historyDirty = false

const historySnapshots = ref([])
const historyIndex = ref(-1)

const MAX_FILE_SIZE = 2 * 1024 * 1024
const SUPPORTED_FILE_TYPES = new Set(['xlsx', 'xls', 'csv', 'json'])
const DRAFT_VERSION = 1
const DRAFT_TTL_MS = 2 * 24 * 60 * 60 * 1000
const PROJECT_VERSION = 1
const getDraftStorageKey = () => {
  try {
    return `chart-editor-draft-v${DRAFT_VERSION}:${localStorage.getItem('username') || 'anonymous'}`
  } catch {
    return `chart-editor-draft-v${DRAFT_VERSION}:anonymous`
  }
}
const draftStorageKey = getDraftStorageKey()

const toFiniteNumber = value => {
  if (value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

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

const selectedChart = computed(() => {
  if (selectedChartIndex.value === null) return null
  return charts.value[selectedChartIndex.value] || null
})

const canUndo = computed(() => historyIndex.value > 0)
const canRedo = computed(() => historyIndex.value >= 0 && historyIndex.value < historySnapshots.value.length - 1)

const availableFields = computed(() => selectedChart.value?.fields || currentDataSource.value?.fields || [])

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
  if (selectedChart.value?.dataSourceId !== source.id) {
    selectedChartIndex.value = null
    config.value.xAxis = source.fields[0] || ''
    config.value.yAxis = source.fields[1] || source.fields[0] || ''
  }
}

const removeDataSource = index => {
  flushPendingHistory()
  const source = dataSources.value[index]
  charts.value = charts.value.filter(chart => {
    if (chart.dataSourceId !== source?.id) return true
    chartInstances[chart.id]?.dispose()
    delete chartInstances[chart.id]
    return false
  })
  dataSources.value.splice(index, 1)
  if (dataSources.value.length === 0) {
    selectedDataSourceIndex.value = null
  } else if (selectedDataSourceIndex.value === index) {
    selectedDataSourceIndex.value = Math.min(index, dataSources.value.length - 1)
  } else if (selectedDataSourceIndex.value > index) {
    selectedDataSourceIndex.value -= 1
  }

  if (selectedChartIndex.value !== null) {
    selectedChartIndex.value = charts.value.length > 0
      ? Math.min(selectedChartIndex.value, charts.value.length - 1)
      : null
  }
  if (!selectedChart.value && currentDataSource.value) {
    config.value.xAxis = currentDataSource.value.fields[0] || ''
    config.value.yAxis = currentDataSource.value.fields[1] || currentDataSource.value.fields[0] || ''
  }
}

const handleUploadClick = () => fileInput.value?.click()

const handleFileSelect = e => {
  for (const file of e.target.files) processFile(file)
  e.target.value = ''
}

const handleFileDrop = e => {
  for (const file of e.dataTransfer.files) processFile(file)
}

const downloadJson = (payload, fileName) => {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  URL.revokeObjectURL(url)
}

const exportProject = () => {
  if (dataSources.value.length === 0) return
  const state = createSerializableState({ includeData: false })
  downloadJson({
    type: 'chart-editor-project',
    version: PROJECT_VERSION,
    exportedAt: Date.now(),
    ...state
  }, 'chart-editor-project.json')
  ElMessage.success('项目配置已导出')
}

const handleProjectImport = e => {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return

  const reader = new FileReader()
  reader.onerror = () => ElMessage.error('项目配置读取失败')
  reader.onload = event => {
    try {
      const project = JSON.parse(event.target.result)
      if (
        project.type !== 'chart-editor-project' ||
        project.version !== PROJECT_VERSION ||
        !Array.isArray(project.dataSources) ||
        !Array.isArray(project.charts)
      ) {
        throw new Error('项目配置格式不兼容')
      }

      flushPendingHistory()
      applySerializableState({
        ...project,
        dataSources: project.dataSources.map(source => ({ ...source, data: [], needsRelink: true }))
      })
      resetHistory()
      saveDraft()
      ElMessage.success('项目配置已导入，请重新选择原始数据文件')
    } catch (error) {
      ElMessage.error(error instanceof SyntaxError ? '项目配置 JSON 解析失败' : error.message)
    }
  }
  reader.readAsText(file)
}

const processFile = async file => {
  const ext = file.name.split('.').pop().toLowerCase()
  if (!SUPPORTED_FILE_TYPES.has(ext)) {
    ElMessage.error(`不支持的文件格式：.${ext}`)
    return
  }
  if (file.size > MAX_FILE_SIZE) {
    ElMessage.error(`${file.name} 超过 2 MB，请精简后重试`)
    return
  }

  const reader = new FileReader()
  reader.onerror = () => ElMessage.error(`无法读取 ${file.name}`)

  if (ext === 'json') {
    reader.onload = e => {
      try {
        const data = JSON.parse(e.target.result)
        addDataSource(file.name, Array.isArray(data) ? data : [data])
      } catch (error) {
        ElMessage.error(error instanceof SyntaxError ? 'JSON 解析失败' : error.message)
      }
    }
    reader.readAsText(file)
  } else {
    reader.onload = e => {
      try {
        const wb = XLSX.read(e.target.result, { type: 'array' })
        const ws = wb.Sheets[wb.SheetNames[0]]
        const data = XLSX.utils.sheet_to_json(ws)
        addDataSource(file.name, data)
      } catch (error) {
        ElMessage.error(error.message || '文件解析失败')
      }
    }
    reader.readAsArrayBuffer(file)
  }
}

const addDataSource = (name, data) => {
  if (data.length === 0) throw new Error('文件中没有可用数据')
  if (data.some(row => !row || typeof row !== 'object' || Array.isArray(row))) {
    throw new Error('每一行数据都必须是字段对象')
  }

  const fields = [...new Set(data.flatMap(row => Object.keys(row)))]
  if (fields.length === 0) throw new Error('文件中没有可用字段')
  const missingValues = data.reduce(
    (total, row) => total + fields.filter(field => row[field] === null || row[field] === undefined || row[field] === '').length,
    0
  )

  const pendingIndex = dataSources.value.findIndex(source => source.needsRelink && source.name === name)
  if (pendingIndex >= 0) {
    const pendingSource = dataSources.value[pendingIndex]
    if (JSON.stringify(pendingSource.fields) !== JSON.stringify(fields)) {
      ElMessage.warning(`${name} 的字段头已变化，请选择原始文件`)
      return
    }
    flushPendingHistory()
    dataSources.value[pendingIndex] = {
      ...pendingSource,
      data,
      fields,
      missingValues,
      needsRelink: false
    }
    charts.value.forEach(chart => {
      if (chart.dataSourceId === pendingSource.id) {
        chart.sourceData = data
      }
    })
    selectedDataSourceIndex.value = pendingIndex
    if (selectedChartIndex.value === null) selectDataSource(pendingIndex)
    else updateChart()
    ElMessage.success(`已重新关联 ${name}（${data.length} 行，${fields.length} 字段）`)
    return
  }

  flushPendingHistory()
  dataSources.value.push({ id: ++dataSourceIdCounter, name, data, fields, missingValues, needsRelink: false })
  if (selectedDataSourceIndex.value === null) {
    selectedDataSourceIndex.value = dataSources.value.length - 1
    selectDataSource(selectedDataSourceIndex.value)
  } else {
    updateChart()
  }

  const summary = `已导入 ${name}（${data.length} 行，${fields.length} 字段）`
  if (missingValues > 0) {
    ElMessage.warning(`${summary}，发现 ${missingValues} 处缺失值`)
  } else {
    ElMessage.success(summary)
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
  if (config.value.aggregate !== 'count') {
    const numericValues = currentDataSource.value.data
      .map(row => toFiniteNumber(row[config.value.yAxis]))
      .filter(value => value !== null)
    if (numericValues.length === 0) {
      ElMessage.warning(`字段“${config.value.yAxis}”没有可绘制的数值`)
      return
    }
  }
  flushPendingHistory()
  const newChart = {
    id: ++chartIdCounter,
    dataSourceId: currentDataSource.value.id,
    dataSourceName: currentDataSource.value.name,
    sourceData: currentDataSource.value.data,
    fields: [...currentDataSource.value.fields],
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
  flushPendingHistory()
  const chart = charts.value[index]
  if (chart && chartInstances[chart.id]) {
    chartInstances[chart.id].dispose()
    delete chartInstances[chart.id]
  }
  charts.value.splice(index, 1)
  chartRefs.value.splice(index, 1)
  if (charts.value.length === 0) {
    selectedChartIndex.value = null
  } else if (selectedChartIndex.value === index) {
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
  flushPendingHistory()
  Object.values(chartInstances).forEach(c => c.dispose())
  chartInstances = {}
  charts.value = []
  selectedChartIndex.value = null
  ElMessage.success('已清空全部图表')
}

const updateChart = event => {
  const chart = selectedChart.value
  if (!chart) return

  if (config.value.aggregate !== 'count') {
    const source = dataSources.value.find(item => item.id === chart.dataSourceId)
    const hasNumericValue = source?.data
      .some(row => toFiniteNumber(row[config.value.yAxis]) !== null)
    if (!hasNumericValue) {
      ElMessage.warning(`字段“${config.value.yAxis}”没有可绘制的数值`)
      config.value.yAxis = chart.yAxis
      if (event?.target?.tagName === 'SELECT') event.target.value = chart.yAxis
      return
    }
  }

  Object.assign(chart, {
    chartType: config.value.chartType,
    title: config.value.title,
    xAxis: config.value.xAxis,
    yAxis: config.value.yAxis,
    color: config.value.color,
    showLegend: config.value.showLegend,
    showLabel: config.value.showLabel,
    smooth: config.value.smooth,
    aggregate: config.value.aggregate
  })
  renderChart(selectedChartIndex.value)
}

const renderChart = index => {
  if (index === null || index < 0 || index >= charts.value.length) return
  const chart = charts.value[index]
  const el = chartRefs.value[index]
  if (!el) return

  if (!chartInstances[chart.id]) {
    chartInstances[chart.id] = echarts.init(el)
  }

  const instance = chartInstances[chart.id]
  const data = chart.sourceData

  const aggregated = aggregateData(data, chart)
  const option = buildChartOption(chart, aggregated)
  instance.setOption(option, true)
}

const handleResize = () => {
  Object.values(chartInstances).forEach(instance => instance.resize())
}

const aggregateData = (data, chart) => {
  if (!chart.xAxis || !chart.yAxis || chart.aggregate === 'none') {
    return data.map(d => {
      const value = toFiniteNumber(d[chart.yAxis])
      return { name: d[chart.xAxis], value }
    })
  }

  const groups = new Map()
  data.forEach(d => {
    const key = d[chart.xAxis]
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(d[chart.yAxis])
  })

  return [...groups.entries()].map(([name, values]) => {
    const numericValues = values.map(toFiniteNumber).filter(value => value !== null)
    let value
    switch (chart.aggregate) {
      case 'sum': value = numericValues.length ? numericValues.reduce((a, b) => a + b, 0) : null; break
      case 'avg': value = numericValues.length ? numericValues.reduce((a, b) => a + b, 0) / numericValues.length : null; break
      case 'count': value = values.length; break
      case 'max': value = numericValues.length ? Math.max(...numericValues) : null; break
      case 'min': value = numericValues.length ? Math.min(...numericValues) : null; break
      default: value = numericValues[0] ?? null
    }
    return { name, value }
  })
}

const buildChartOption = (chart, data) => {
  const names = data.map(d => d.name)
  const values = data.map(d => d.value)
  const seriesName = chart.title || '数据'
  const label = { show: chart.showLabel }
  const textColor = isDarkTheme.value ? '#e0e0e0' : '#303133'
  const mutedColor = isDarkTheme.value ? '#a0a0b0' : '#909399'

  const baseOption = {
    animation: chart.animation?.enabled ?? true,
    animationDuration: chart.animation?.duration ?? 1000,
    animationEasing: chart.animation?.easing ?? 'cubicOut',
    title: { text: seriesName, left: 'center', textStyle: { color: textColor } },
    tooltip: { trigger: 'axis' },
    grid: { left: '12%', right: '8%', bottom: '12%', top: '18%', containLabel: true },
    xAxis: { type: 'category', data: names, axisTick: { alignWithLabel: true }, axisLabel: { color: mutedColor }, axisLine: { lineStyle: { color: mutedColor } } },
    yAxis: { type: 'value', axisLabel: { color: mutedColor }, axisLine: { lineStyle: { color: mutedColor } }, splitLine: { lineStyle: { color: isDarkTheme.value ? '#2a2a4a' : '#ebeef5' } } },
  }

  let series
  switch (chart.chartType) {
    case 'bar':
      series = [{ name: seriesName, type: 'bar', data: values, label, itemStyle: { color: chart.color } }]
      break
    case 'line':
      series = [{ name: seriesName, type: 'line', data: values, smooth: chart.smooth, label, itemStyle: { color: chart.color } }]
      break
    case 'area':
      series = [{ name: seriesName, type: 'line', data: values, smooth: chart.smooth, areaStyle: {}, label, itemStyle: { color: chart.color } }]
      break
    case 'scatter':
      {
        const scatterData = data.map(item => {
          const numericX = toFiniteNumber(item.name)
          return [numericX ?? item.name, item.value]
        })
        const hasNumericXAxis = scatterData.every(([x]) => typeof x === 'number')
        baseOption.xAxis = hasNumericXAxis
          ? { type: 'value' }
          : { type: 'category', data: names, axisTick: { alignWithLabel: true } }
        baseOption.tooltip = { trigger: 'item' }
        series = [{ name: seriesName, type: 'scatter', data: scatterData, label, itemStyle: { color: chart.color } }]
      }
      break
    case 'pie':
      baseOption.xAxis = null
      baseOption.yAxis = null
      baseOption.tooltip = { trigger: 'item' }
      series = [{
        name: seriesName,
        type: 'pie',
        data: data.map(d => ({ name: d.name, value: d.value })),
        label,
        itemStyle: { color: names.map((_, index) => index === 0 ? chart.color : ['#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4'][index % 5]) }
      }]
      break
    case 'radar':
      baseOption.xAxis = null
      baseOption.yAxis = null
      baseOption.tooltip = { trigger: 'item' }
      baseOption.radar = { indicator: names.map(n => ({ name: n, max: Math.max(1, ...values.map(Math.abs)) * 1.2 })) }
      series = [{
        name: seriesName,
        type: 'radar',
        data: [{ value: values, name: seriesName }],
        label,
        itemStyle: { color: chart.color },
        lineStyle: { color: chart.color }
      }]
      break
    default:
      series = [{ name: seriesName, type: 'bar', data: values, label, itemStyle: { color: chart.color } }]
  }

  baseOption.series = series

  baseOption.legend = {
    show: chart.showLegend,
    data: chart.chartType === 'pie' ? names : [seriesName]
  }

  return baseOption
}

const exportChart = () => exportSingleChart(selectedChartIndex.value)

const exportSingleChart = index => {
  if (index === null || index < 0 || index >= charts.value.length) return
  const chart = charts.value[index]
  const instance = chartInstances[chart.id]
  if (!instance) return
  const url = instance.getDataURL({ type: 'png', pixelRatio: 2 })
  const a = document.createElement('a')
  a.href = url
  a.download = (chart.title || `chart-${index + 1}`) + '.png'
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
  flushPendingHistory()
  isDarkTheme.value = !isDarkTheme.value
  nextTick(() => charts.value.forEach((_, index) => renderChart(index)))
}

const createSerializableState = ({ includeData = true } = {}) => ({
  version: DRAFT_VERSION,
  savedAt: Date.now(),
  expiresAt: Date.now() + DRAFT_TTL_MS,
  dataSources: dataSources.value.map(source => ({
    ...source,
    data: includeData ? source.data : [],
    needsRelink: includeData ? Boolean(source.needsRelink) : true
  })),
  charts: charts.value.map(chart => ({ ...chart, sourceData: undefined })),
  selectedDataSourceIndex: selectedDataSourceIndex.value,
  selectedChartIndex: selectedChartIndex.value,
  config: config.value,
  isDarkTheme: isDarkTheme.value
})

const applySerializableState = state => {
  Object.values(chartInstances).forEach(instance => instance.dispose())
  chartInstances = {}
  dataSources.value = state.dataSources
  charts.value = state.charts
    .map(chart => {
      const source = dataSources.value.find(item => item.id === chart.dataSourceId)
      return source ? { ...chart, sourceData: source.data } : null
    })
    .filter(Boolean)
  selectedDataSourceIndex.value = dataSources.value.length > 0 && Number.isInteger(state.selectedDataSourceIndex)
    ? Math.min(state.selectedDataSourceIndex, dataSources.value.length - 1)
    : null
  selectedChartIndex.value = charts.value.length > 0 && Number.isInteger(state.selectedChartIndex)
    ? Math.min(state.selectedChartIndex, charts.value.length - 1)
    : null
  config.value = { ...config.value, ...state.config }
  isDarkTheme.value = Boolean(state.isDarkTheme)
  dataSourceIdCounter = Math.max(0, ...dataSources.value.map(source => Number(source.id) || 0))
  chartIdCounter = Math.max(0, ...charts.value.map(chart => Number(chart.id) || 0))
  nextTick(() => charts.value.forEach((_, index) => renderChart(index)))
}

const saveDraft = () => {
  try {
    localStorage.setItem(draftStorageKey, JSON.stringify(createSerializableState({ includeData: false })))
  } catch {
    if (!draftStorageWarningShown) {
      draftStorageWarningShown = true
      ElMessage.warning('本地草稿空间不足，请减少导入数据量')
    }
  }
}

const scheduleDraftSave = () => {
  clearTimeout(draftSaveTimer)
  draftSaveTimer = setTimeout(saveDraft, 250)
}

const recordHistory = () => {
  if (applyingHistory || !historyDirty) return
  const snapshot = JSON.stringify(createSerializableState())
  historyDirty = false
  if (historySnapshots.value[historyIndex.value] === snapshot) return

  const nextSnapshots = historySnapshots.value.slice(0, historyIndex.value + 1)
  nextSnapshots.push(snapshot)
  if (nextSnapshots.length > 50) nextSnapshots.shift()
  historySnapshots.value = nextSnapshots
  historyIndex.value = nextSnapshots.length - 1
}

const scheduleHistoryRecord = () => {
  if (applyingHistory) return
  historyDirty = true
  clearTimeout(historySaveTimer)
  historySaveTimer = setTimeout(recordHistory, 250)
}

const resetHistory = () => {
  clearTimeout(historySaveTimer)
  historyDirty = false
  historySnapshots.value = [JSON.stringify(createSerializableState())]
  historyIndex.value = 0
}

const flushPendingHistory = () => {
  clearTimeout(historySaveTimer)
  recordHistory()
}

const applyHistoryAt = index => {
  const snapshot = historySnapshots.value[index]
  if (!snapshot) return
  applyingHistory = true
  historyDirty = false
  historyIndex.value = index
  applySerializableState(JSON.parse(snapshot))
  saveDraft()
  nextTick(() => { applyingHistory = false })
}

const undo = () => {
  flushPendingHistory()
  if (canUndo.value) applyHistoryAt(historyIndex.value - 1)
}

const redo = () => {
  flushPendingHistory()
  if (canRedo.value) applyHistoryAt(historyIndex.value + 1)
}

const restoreDraft = () => {
  try {
    const stored = localStorage.getItem(draftStorageKey)
    if (!stored) return
    const draft = JSON.parse(stored)
    if (draft.version !== DRAFT_VERSION || !Array.isArray(draft.dataSources) || !Array.isArray(draft.charts)) return
    if (!Number.isFinite(draft.expiresAt) || draft.expiresAt <= Date.now()) {
      localStorage.removeItem(draftStorageKey)
      return
    }

    applySerializableState({
      ...draft,
      dataSources: draft.dataSources.map(source => ({ ...source, data: [], needsRelink: true }))
    })
    if (draft.dataSources.length > 0) {
      ElMessage.warning('图表配置已恢复，请重新选择原始数据文件')
    }
  } catch {
    ElMessage.warning('本地草稿读取失败，新修改仍可正常保存')
  }
}

const handleKeydown = e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
    e.preventDefault()
    e.shiftKey ? redo() : undo()
    return
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
    e.preventDefault()
    redo()
    return
  }
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    addChart()
  }
}

watch(selectedChartIndex, newVal => {
  if (Number.isInteger(newVal) && newVal >= 0 && newVal < charts.value.length) {
    const chart = charts.value[newVal]
    const sourceIndex = dataSources.value.findIndex(source => source.id === chart.dataSourceId)
    if (sourceIndex >= 0) selectedDataSourceIndex.value = sourceIndex
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

watch(
  [dataSources, charts, selectedDataSourceIndex, selectedChartIndex, config, isDarkTheme],
  scheduleDraftSave,
  { deep: true }
)

watch([dataSources, charts, isDarkTheme], scheduleHistoryRecord, { deep: true })

onMounted(() => {
  restoreDraft()
  resetHistory()
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  clearTimeout(draftSaveTimer)
  clearTimeout(historySaveTimer)
  saveDraft()
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', handleResize)
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
  .data-remove { opacity: 1; width: 32px; height: 32px; }
}
</style>
