<template>
  <div class="workflow-dag-container">
    <div class="dag-toolbar">
      <div class="toolbar-left">
        <button class="toolbar-btn" :class="{ active: viewMode === 'graph' }" @click="viewMode = 'graph'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="5" cy="6" r="3"/><circle cx="19" cy="6" r="3"/><circle cx="12" cy="18" r="3"/>
            <line x1="8" y1="7" x2="16" y2="7"/><line x1="6" y1="8" x2="10" y2="16"/><line x1="18" y1="8" x2="14" y2="16"/>
          </svg>
          <span>图形</span>
        </button>
        <button class="toolbar-btn" :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
            <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
          </svg>
          <span>列表</span>
        </button>
      </div>
      <div class="toolbar-right">
        <button class="toolbar-btn" title="放大" @click="zoomIn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            <line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/>
          </svg>
        </button>
        <button class="toolbar-btn" title="缩小" @click="zoomOut">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            <line x1="8" y1="11" x2="14" y2="11"/>
          </svg>
        </button>
        <button class="toolbar-btn" title="适应" @click="fitView">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- 图形模式 -->
    <div v-show="viewMode === 'graph'" ref="canvasRef" class="dag-canvas" @wheel="onWheel">
      <svg
        :width="svgWidth"
        :height="svgHeight"
        :viewBox="`${-panX} ${-panY} ${svgWidth / zoom} ${svgHeight / zoom}`"
        class="dag-svg"
      >
        <defs>
          <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" :fill="edgeColor" />
          </marker>
          <filter id="node-shadow">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.3" />
          </filter>
        </defs>

        <!-- 网格背景 -->
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="var(--border-color, #2d3748)" stroke-width="0.5" opacity="0.3" />
        </pattern>
        <rect x="-1000" y="-1000" width="3000" height="3000" fill="url(#grid)" />

        <!-- 连线 -->
        <g class="dag-edges">
          <path
            v-for="edge in edges"
            :key="edge.key"
            :d="edge.path"
            :stroke="edge.color"
            stroke-width="2"
            fill="none"
            marker-end="url(#arrowhead)"
            :class="{ 'edge-running': edge.status === 'running' }"
          />
        </g>

        <!-- 节点 -->
        <g class="dag-nodes">
          <g
            v-for="node in layoutNodes"
            :key="node.id"
            :transform="`translate(${node.x}, ${node.y})`"
            :class="['dag-node', `status-${node.status}`]"
            @click="selectNode(node)"
          >
            <rect
              :width="nodeWidth"
              :height="nodeHeight"
              rx="8"
              ry="8"
              :fill="getNodeBgColor(node)"
              :stroke="getNodeBorderColor(node)"
              stroke-width="2"
              filter="url(#node-shadow)"
            />
            <!-- 类型图标 -->
            <g class="node-icon" :transform="`translate(12, 12)`">
              <rect width="28" height="28" rx="6" :fill="getIconBgColor(node)" />
              <text x="14" y="19" text-anchor="middle" font-size="14">{{ getNodeEmoji(node) }}</text>
            </g>
            <!-- 标题 -->
            <text :x="48" :y="22" class="node-title" :fill="getNodeTextColor(node)">{{ node.title }}</text>
            <!-- 类型标签 -->
            <text :x="48" :y="38" class="node-type-label">{{ getNodeTypeLabel(node.type) }}</text>
            <!-- 状态指示 -->
            <g :transform="`translate(${nodeWidth - 20}, 14)`">
              <circle r="6" :fill="getStatusColor(node.status)" />
              <circle v-if="node.status === 'running'" r="6" fill="none" :stroke="getStatusColor(node.status)" stroke-width="2">
                <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="1s" repeatCount="indefinite" />
              </circle>
            </g>
          </g>
        </g>
      </svg>
    </div>

    <!-- 列表模式 -->
    <div v-show="viewMode === 'list'" class="dag-list-view">
      <div
        v-for="(layer, idx) in layers"
        :key="idx"
        class="dag-layer"
      >
        <div class="layer-label">第 {{ idx + 1 }} 层</div>
        <div class="layer-nodes">
          <div
            v-for="node in layer"
            :key="node.id"
            :class="['list-node', `status-${node.status}`]"
            @click="selectNode(node)"
          >
            <div class="list-node-header">
              <span class="list-node-icon">{{ getNodeEmoji(node) }}</span>
              <span class="list-node-title">{{ node.title }}</span>
              <span :class="['list-node-status', `status-${node.status}`]">{{ getStatusLabel(node.status) }}</span>
            </div>
            <div class="list-node-type">{{ getNodeTypeLabel(node.type) }}</div>
            <div v-if="node.depends_on?.length" class="list-node-deps">
              依赖: {{ node.depends_on.join(', ') }}
            </div>
          </div>
        </div>
        <div v-if="idx < layers.length - 1" class="layer-arrow">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="4" x2="12" y2="20"/><polyline points="8 16 12 20 16 16"/>
          </svg>
        </div>
      </div>
    </div>

    <!-- 节点详情浮窗 -->
    <div v-if="selectedNode" class="node-detail" @click.self="selectedNode = null">
      <div class="detail-header">
        <h4>{{ selectedNode.title }}</h4>
        <button class="btn-close" @click="selectedNode = null">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
      <div class="detail-body">
        <div class="detail-item">
          <span class="detail-label">类型</span>
          <span class="detail-value">{{ getNodeTypeLabel(selectedNode.type) }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">状态</span>
          <span :class="['detail-value', `status-${selectedNode.status}`]">{{ getStatusLabel(selectedNode.status) }}</span>
        </div>
        <div v-if="selectedNode.depends_on?.length" class="detail-item">
          <span class="detail-label">依赖</span>
          <span class="detail-value">{{ selectedNode.depends_on.join(', ') }}</span>
        </div>
        <div v-if="selectedNode.params" class="detail-item detail-params">
          <span class="detail-label">参数</span>
          <pre class="detail-pre">{{ formatJson(selectedNode.params) }}</pre>
        </div>
        <div v-if="selectedNode.result" class="detail-item detail-result">
          <span class="detail-label">结果</span>
          <pre class="detail-pre">{{ formatJson(selectedNode.result) }}</pre>
        </div>
        <div v-if="selectedNode.error" class="detail-item detail-error">
          <span class="detail-label">错误</span>
          <pre class="detail-pre">{{ selectedNode.error }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'

  const props = defineProps({
    nodes: { type: Array, default: () => [] }
  })

  const emit = defineEmits(['nodeSelect'])

  const viewMode = ref('graph')
  const zoom = ref(1)
  const panX = ref(0)
  const panY = ref(0)
  const selectedNode = ref(null)
  const canvasRef = ref(null)

  const nodeWidth = 220
  const nodeHeight = 56
  const nodeGapX = 60
  const nodeGapY = 80

  const svgWidth = computed(() => Math.max(800, props.nodes.length * (nodeWidth + nodeGapX)))
  const svgHeight = computed(() => Math.max(400, layers.value.length * (nodeHeight + nodeGapY) + 200))

  const edgeColor = 'var(--text-secondary, #9ca3af)'

  // 拓扑分层
  const layers = computed(() => {
    if (props.nodes.length === 0) return []
    const nodeMap = new Map(props.nodes.map(n => [n.id, n]))
    const visited = new Set()
    const result = []

    function getLayer(nodeId) {
      if (visited.has(nodeId)) return -1
      visited.add(nodeId)
      const node = nodeMap.get(nodeId)
      if (!node || !node.depends_on?.length) return 0
      let maxDep = -1
      for (const dep of node.depends_on) {
        const depLayer = getLayer(dep)
        if (depLayer >= 0) maxDep = Math.max(maxDep, depLayer)
      }
      return maxDep + 1
    }

    const nodeLayers = new Map()
    for (const node of props.nodes) {
      const layer = getLayer(node.id)
      if (!nodeLayers.has(layer)) nodeLayers.set(layer, [])
      nodeLayers.get(layer).push(node)
    }

    const maxLayer = Math.max(...nodeLayers.keys())
    for (let i = 0; i <= maxLayer; i++) {
      result.push(nodeLayers.get(i) || [])
    }
    return result
  })

  // 布局计算
  const layoutNodes = computed(() => {
    return layers.value.flatMap((layer, layerIdx) => {
      const totalWidth = layer.length * (nodeWidth + nodeGapX) - nodeGapX
      const startX = (svgWidth.value - totalWidth) / 2
      return layer.map((node, nodeIdx) => ({
        ...node,
        x: startX + nodeIdx * (nodeWidth + nodeGapX),
        y: 60 + layerIdx * (nodeHeight + nodeGapY),
        title: node.title || node.id || `Node ${nodeIdx + 1}`
      }))
    })
  })

  // 连线计算
  const edges = computed(() => {
    const nodeMap = new Map(layoutNodes.value.map(n => [n.id, n]))
    return layoutNodes.value.flatMap(node => {
      if (!node.depends_on?.length) return []
      return node.depends_on.map(depId => {
        const source = nodeMap.get(depId)
        if (!source) return null
        return {
          key: `${depId}-${node.id}`,
          source,
          target: node,
          status: node.status,
          path: `M ${source.x + nodeWidth / 2} ${source.y + nodeHeight} C ${source.x + nodeWidth / 2} ${source.y + nodeHeight + 30}, ${node.x + nodeWidth / 2} ${node.y - 30}, ${node.x + nodeWidth / 2} ${node.y}`,
          color: node.status === 'completed' ? '#10b981' : node.status === 'running' ? '#f59e0b' : node.status === 'failed' ? '#ef4444' : 'var(--text-secondary, #6b7280)'
        }
      }).filter(Boolean)
    })
  })

  function getNodeBgColor(node) {
    const colors = {
      pending: 'var(--bg-secondary, #16213e)',
      running: 'var(--bg-secondary, #16213e)',
      completed: 'var(--bg-secondary, #16213e)',
      failed: 'var(--bg-secondary, #16213e)'
    }
    return colors[node.status] || colors.pending
  }

  function getNodeBorderColor(node) {
    const colors = {
      pending: 'var(--border-color, #2d3748)',
      running: '#f59e0b',
      completed: '#10b981',
      failed: '#ef4444'
    }
    return colors[node.status] || colors.pending
  }

  function getNodeTextColor(node) {
    return 'var(--text-primary, #e0e0e0)'
  }

  function getIconBgColor(node) {
    return 'var(--accent-muted, #4f46e533)'
  }

  function getStatusColor(status) {
    const colors = { pending: '#6b7280', running: '#f59e0b', completed: '#10b981', failed: '#ef4444' }
    return colors[status] || colors.pending
  }

  function getNodeEmoji(node) {
    const emojis = {
      web_search: '🔍', code_execution: '💻', chart_generation: '📊',
      file_processing: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`, data_analysis: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>`, api_call: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,
      text_generation: '✍️', image_generation: '🎨'
    }
    return emojis[node.type] || ''
  }

  function getNodeTypeLabel(type) {
    const labels = {
      web_search: '网络搜索', code_execution: '代码执行', chart_generation: '图表生成',
      file_processing: '文件处理', data_analysis: '数据分析', api_call: 'API 调用',
      text_generation: '文本生成', image_generation: '图像生成'
    }
    return labels[type] || type
  }

  function getStatusLabel(status) {
    const labels = { pending: '等待中', running: '执行中', completed: '已完成', failed: '失败' }
    return labels[status] || '未知'
  }

  function selectNode(node) {
    selectedNode.value = node
    emit('nodeSelect', node)
  }

  function formatJson(obj) {
    if (!obj) return ''
    return typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2)
  }

  function zoomIn() { zoom.value = Math.min(2, zoom.value * 1.2) }
  function zoomOut() { zoom.value = Math.max(0.3, zoom.value / 1.2) }
  function fitView() { zoom.value = 1; panX.value = 0; panY.value = 0 }

  function onWheel(e) {
    e.preventDefault()
    if (e.deltaY < 0) zoomIn()
    else zoomOut()
  }

  onMounted(() => {
    if (canvasRef.value) {
      canvasRef.value.addEventListener('wheel', onWheel, { passive: false })
    }
  })

  onBeforeUnmount(() => {
    if (canvasRef.value) {
      canvasRef.value.removeEventListener('wheel', onWheel)
    }
  })
</script>

<style scoped>
  .workflow-dag-container {
    position: relative;
    height: 100%;
    background: var(--bg-primary, #0f172a);
    display: flex;
    flex-direction: column;
  }

  .dag-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color, #2d3748);
    background: var(--bg-secondary, #16213e);
  }

  .toolbar-left, .toolbar-right { display: flex; gap: 4px; }

  .toolbar-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    font-size: 12px;
  }

  .toolbar-btn:hover { background: var(--bg-hover, #374151); }
  .toolbar-btn.active { background: var(--accent-muted, #4f46e533); color: var(--accent-color, #4f46e5); }
  .toolbar-btn svg { width: 16px; height: 16px; }

  .dag-canvas {
    flex: 1;
    overflow: hidden;
    cursor: grab;
  }

  .dag-svg { width: 100%; height: 100%; }

  .dag-node { cursor: pointer; }
  .dag-node:hover rect { stroke-width: 3; }

  .node-title { font-size: 13px; font-weight: 500; }
  .node-type-label { font-size: 11px; fill: var(--text-secondary, #9ca3af); }

  .edge-running { stroke-dasharray: 8 4; animation: dash 1s linear infinite; }
  @keyframes dash { to { stroke-dashoffset: -12; } }

  .dag-list-view {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

  .dag-layer { display: flex; flex-direction: column; align-items: center; }
  .layer-label { font-size: 11px; color: var(--text-secondary, #9ca3af); margin-bottom: 8px; }
  .layer-nodes { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }
  .layer-arrow { padding: 8px; color: var(--text-secondary, #9ca3af); }
  .layer-arrow svg { width: 20px; height: 20px; }

  .list-node {
    padding: 12px 16px;
    border-radius: 8px;
    background: var(--bg-secondary, #16213e);
    border: 1px solid var(--border-color, #2d3748);
    min-width: 200px;
    max-width: 300px;
    cursor: pointer;
    transition: all 0.15s;
  }

  .list-node:hover { border-color: var(--accent-color, #4f46e5); }
  .list-node.status-running { border-color: #f59e0b; }
  .list-node.status-completed { border-color: #10b981; }
  .list-node.status-failed { border-color: #ef4444; }

  .list-node-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .list-node-icon { font-size: 16px; }
  .list-node-title { font-size: 13px; font-weight: 500; flex: 1; }
  .list-node-type { font-size: 11px; color: var(--text-secondary, #9ca3af); }
  .list-node-deps { font-size: 11px; color: var(--text-secondary, #9ca3af); margin-top: 4px; }

  .list-node-status { font-size: 11px; padding: 2px 8px; border-radius: 4px; }
  .list-node-status.status-pending { background: var(--bg-tertiary, #1f2937); color: var(--text-secondary, #9ca3af); }
  .list-node-status.status-running { background: #f59e0b22; color: #f59e0b; }
  .list-node-status.status-completed { background: #10b98122; color: #10b981; }
  .list-node-status.status-failed { background: #ef444422; color: #ef4444; }

  .node-detail {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 400px;
    max-height: 80%;
    background: var(--bg-secondary, #16213e);
    border-radius: 12px;
    border: 1px solid var(--border-color, #2d3748);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    z-index: 100;
    display: flex;
    flex-direction: column;
  }

  .detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
  }

  .detail-header h4 { margin: 0; font-size: 15px; }

  .btn-close {
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-close:hover { background: var(--bg-hover, #374151); }
  .btn-close svg { width: 16px; height: 16px; }

  .detail-body { flex: 1; overflow-y: auto; padding: 16px; }
  .detail-item { margin-bottom: 16px; }
  .detail-label { display: block; font-size: 11px; color: var(--text-secondary, #9ca3af); margin-bottom: 4px; }
  .detail-value { font-size: 13px; }
  .detail-value.status-pending { color: var(--text-secondary, #9ca3af); }
  .detail-value.status-running { color: #f59e0b; }
  .detail-value.status-completed { color: #10b981; }
  .detail-value.status-failed { color: #ef4444; }

  .detail-pre {
    padding: 8px;
    background: var(--bg-tertiary, #1f2937);
    border-radius: 6px;
    font-size: 12px;
    overflow-x: auto;
    max-height: 200px;
    margin: 0;
  }

  .detail-error .detail-pre { color: #ef4444; background: #ef444411; }
</style>
