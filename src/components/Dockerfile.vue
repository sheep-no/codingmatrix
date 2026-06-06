<template>
  <div v-if="visible" class="docker-config-overlay" @click.self="$emit('close')">
    <div class="docker-config-modal">
      <div class="modal-header">
        <h2>多服务 Docker 配置</h2>
        <div class="header-actions">
          <button class="import-btn" title="导入配置" @click="importConfig">
            <span>[IMPORT]</span> Import
          </button>
          <button class="export-btn" title="导出配置" @click="exportConfig">
            <span>📤</span> 导出
          </button>
          <button class="close-btn" @click="$emit('close')">×</button>
        </div>
      </div>

      <div class="modal-body">
        <!-- 配置类型选择 -->
        <div class="config-type-selector">
          <h3>生成模式</h3>
          <div class="type-buttons">
            <button :class="{ active: outputMode === 'single' }" @click="outputMode = 'single'">
              单 Dockerfile
            </button>
            <button :class="{ active: outputMode === 'compose' }" @click="outputMode = 'compose'">
              Docker Compose
            </button>
          </div>
        </div>

        <!-- 服务列表 -->
        <div class="services-section">
          <div class="section-header">
            <h3>服务列表</h3>
            <div class="section-actions">
              <button class="add-service-btn" @click="addService"><span>+</span> 添加服务</button>
              <button class="apply-template-btn" @click="showTemplates = !showTemplates">
                <span>[LIST]</span> Apply Template
              </button>
            </div>
          </div>

          <!-- 模板选择器 -->
          <div v-if="showTemplates" class="templates-selector">
            <h4>选择应用模板</h4>
            <div class="template-categories">
              <div class="template-category">
                <h5>前端应用</h5>
                <div class="template-buttons">
                  <button
                    v-for="template in frontendTemplates"
                    :key="template.id"
                    @click="applyTemplate(template)"
                  >
                    {{ template.name }}
                  </button>
                </div>
              </div>
              <div class="template-category">
                <h5>后端 API</h5>
                <div class="template-buttons">
                  <button
                    v-for="template in backendTemplates"
                    :key="template.id"
                    @click="applyTemplate(template)"
                  >
                    {{ template.name }}
                  </button>
                </div>
              </div>
              <div class="template-category">
                <h5>数据库</h5>
                <div class="template-buttons">
                  <button
                    v-for="template in databaseTemplates"
                    :key="template.id"
                    @click="applyTemplate(template)"
                  >
                    {{ template.name }}
                  </button>
                </div>
              </div>
              <div class="template-category">
                <h5>完整架构</h5>
                <div class="template-buttons">
                  <button
                    v-for="template in composeTemplates"
                    :key="template.id"
                    @click="applyTemplate(template)"
                  >
                    {{ template.name }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 服务卡片列表 -->
          <div class="service-cards">
            <div
              v-for="(service, index) in services"
              :key="service.id"
              class="service-card"
              :class="{
                active: activeServiceId === service.id,
                dragging: draggingServiceId === service.id
              }"
              draggable="true"
              @click="selectService(service.id)"
              @dragstart="onDragStart($event, index)"
              @dragover="onDragOver($event)"
              @drop="onDrop($event, index)"
            >
              <div class="service-card-header">
                <div class="service-info">
                  <span class="service-icon">{{ getAppIcon(service.appType) }}</span>
                  <span class="service-name">{{ service.name || `服务 ${index + 1}` }}</span>
                  <span class="service-type-badge">{{ appTypeLabels[service.appType] }}</span>
                </div>
                <div class="service-actions">
                  <button class="icon-btn" title="重命名" @click.stop="editServiceName(service)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                    </svg>
                  </button>
                  <button
                    class="icon-btn"
                    title="Duplicate service"
                    @click.stop="duplicateService(index)"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                  </button>
                  <button
                    class="icon-btn delete-btn"
                    title="Delete service"
                    @click.stop="removeService(index)"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <polyline points="3 6 5 6 21 6" />
                      <path
                        d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
                      />
                    </svg>
                  </button>
                </div>
              </div>

              <!-- 服务配置预览 -->
              <div class="service-preview">
                <div class="preview-item">
                  <span class="label">镜像:</span>
                  <code class="value">{{ service.image }}</code>
                </div>
                <div v-if="service.ports" class="preview-item">
                  <span class="label">端口:</span>
                  <span class="value">{{ service.ports }}</span>
                </div>
                <div class="service-preview-hint">点击配置详情</div>
              </div>
            </div>
          </div>

          <!-- 项目配置 -->
          <div v-if="outputMode === 'compose'" class="project-config-section">
            <h3>项目配置</h3>
            <div class="config-form project-config">
              <div class="form-row">
                <div class="form-group">
                  <label>项目名称</label>
                  <input v-model="projectInfo.name" type="text" placeholder="my-project" />
                </div>
                <div class="form-group">
                  <label>Compose 版本</label>
                  <select v-model="projectInfo.version">
                    <option value="3.8">3.8</option>
                    <option value="3.7">3.7</option>
                    <option value="3.6">3.6</option>
                    <option value="3.5">3.5</option>
                  </select>
                </div>
              </div>
              <div class="form-group">
                <label>网络模式</label>
                <select v-model="projectInfo.networkMode">
                  <option value="">使用自定义网络</option>
                  <option value="bridge">bridge (默认)</option>
                  <option value="host">host (主机网络)</option>
                  <option value="none">none (无网络)</option>
                </select>
              </div>
            </div>

            <!-- 网络配置 -->
            <div v-if="projectInfo.customNetworks.length > 0" class="networks-config">
              <h4>网络配置</h4>
              <div class="network-items">
                <div
                  v-for="(network, idx) in projectInfo.customNetworks"
                  :key="idx"
                  class="network-item"
                >
                  <div class="network-name">
                    <label>网络名称</label>
                    <input v-model="network.name" type="text" :placeholder="`network-${idx + 1}`" />
                  </div>
                  <div class="network-driver">
                    <label>驱动</label>
                    <select v-model="network.driver">
                      <option value="bridge">bridge</option>
                      <option value="overlay">overlay</option>
                      <option value="macvlan">macvlan</option>
                      <option value="ipvlan">ipvlan</option>
                    </select>
                  </div>
                  <button
                    v-if="projectInfo.customNetworks.length > 1"
                    class="remove-network-btn"
                    @click="removeNetwork(idx)"
                  >
                    <span>×</span>
                  </button>
                </div>
              </div>
              <button class="add-network-btn" @click="addNetwork"><span>+</span> 添加网络</button>
            </div>
          </div>
        </div>

        <!-- 服务详情配置面板 -->
        <div v-if="activeService" class="service-detail-panel">
          <div class="detail-header">
            <h3>当前服务: {{ activeService.name }}</h3>
            <div class="detail-actions">
              <button class="toggle-accordion-btn" @click="showDetailConfig = !showDetailConfig">
                {{ showDetailConfig ? '收起' : '展开' }}
              </button>
            </div>
          </div>

          <div class="detail-content" :class="{ expanded: showDetailConfig }">
            <!-- 基础配置 -->
            <div class="detail-section">
              <h4>基础配置</h4>
              <div class="config-form">
                <div class="form-group">
                  <label>服务名称</label>
                  <input
                    v-model="activeService.name"
                    type="text"
                    placeholder="web"
                    class="medium-input"
                  />
                </div>
                <div class="form-group">
                  <label>基础镜像</label>
                  <input
                    v-model="activeService.image"
                    type="text"
                    placeholder="node:18-alpine"
                    class="wide-input"
                  />
                  <small class="help-text">如 node:18-alpine, python:3.9, nginx:alpine</small>
                </div>
                <div class="form-group">
                  <label>镜像标签（可选）</label>
                  <input v-model="activeService.imageTag" type="text" placeholder="latest" />
                </div>
                <div class="form-group">
                  <label>工作目录</label>
                  <input
                    v-model="activeService.workDir"
                    type="text"
                    placeholder="/app"
                    class="code-input"
                  />
                </div>
                <div class="form-group">
                  <label>用户（可选）</label>
                  <input v-model="activeService.user" type="text" placeholder="留空使用 root" />
                </div>
                <div
                  v-if="activeService.appType === 'web' || activeService.appType === 'api'"
                  class="form-group"
                >
                  <label>启动命令</label>
                  <input
                    v-model="activeService.command"
                    type="text"
                    placeholder="npm start"
                    class="wide-input"
                  />
                  <small class="help-text">如 npm start, python app.py, java -jar app.jar</small>
                </div>
              </div>
            </div>

            <!-- 端口配置 -->
            <div class="detail-section">
              <h4>端口配置</h4>
              <div class="config-form">
                <div class="ports-config">
                  <div v-for="(port, idx) in activeService.ports" :key="idx" class="port-item">
                    <div class="port-row">
                      <div class="port-field host-port">
                        <label>主机</label>
                        <input v-model="port.host" type="number" placeholder="8080" />
                      </div>
                      <div class="port-arrow">→</div>
                      <div class="port-field container-port">
                        <label>容器</label>
                        <input v-model="port.container" type="number" placeholder="80" />
                      </div>
                      <div class="port-field protocol">
                        <label>协议</label>
                        <select v-model="port.protocol">
                          <option value="tcp">TCP</option>
                          <option value="udp">UDP</option>
                        </select>
                      </div>
                      <button
                        v-if="activeService.ports.length > 1"
                        class="remove-port-btn"
                        @click="removePort(idx)"
                      >
                        <span>×</span>
                      </button>
                    </div>
                  </div>
                  <button class="add-port-btn" @click="addPort"><span>+</span> 添加端口映射</button>
                </div>
              </div>
            </div>

            <!-- 环境变量 -->
            <div class="detail-section">
              <h4>环境变量</h4>
              <div class="env-config">
                <div v-for="(env, idx) in activeService.environment" :key="idx" class="env-row">
                  <div class="env-field">
                    <label>变量名</label>
                    <input
                      v-model="env.name"
                      type="text"
                      placeholder="NODE_ENV"
                      class="env-name-input"
                    />
                    <span class="equals-sign">=</span>
                    <input
                      v-model="env.value"
                      type="text"
                      placeholder="production"
                      class="env-value-input"
                    />
                    <button
                      v-if="activeService.environment.length > 0"
                      class="remove-env-btn"
                      @click="removeEnv(idx)"
                    >
                      <span>×</span>
                    </button>
                  </div>
                </div>
                <button class="add-env-btn" @click="addEnv"><span>+</span> 添加环境变量</button>
              </div>
            </div>

            <!-- 卷挂载 -->
            <div class="detail-section">
              <h4>存储卷</h4>
              <div class="volumes-config">
                <div v-for="(volume, idx) in activeService.volumes" :key="idx" class="volume-row">
                  <div class="volume-type">
                    <label>类型</label>
                    <select v-model="volume.type">
                      <option value="bind">绑定挂载</option>
                      <option value="volume">命名卷</option>
                    </select>
                  </div>
                  <div class="volume-source">
                    <label>
                      {{ volume.type === 'bind' ? '主机路径' : '卷名称' }}
                    </label>
                    <input
                      v-model="volume.source"
                      :placeholder="volume.type === 'bind' ? '/host/path' : 'data-volume'"
                      class="code-input"
                    />
                  </div>
                  <div class="volume-arrow">→</div>
                  <div class="volume-dest">
                    <label>容器路径</label>
                    <input
                      v-model="volume.dest"
                      type="text"
                      placeholder="/container/path"
                      class="code-input"
                    />
                  </div>
                  <div v-if="volume.type === 'bind'" class="volume-mode">
                    <label>模式</label>
                    <select v-model="volume.mode">
                      <option value="rw">读写 (rw)</option>
                      <option value="ro">只读 (ro)</option>
                    </select>
                  </div>
                  <button
                    v-if="activeService.volumes.length > 0"
                    class="remove-volume-btn"
                    @click="removeVolume(idx)"
                  >
                    <span>×</span>
                  </button>
                </div>
                <button class="add-volume-btn" @click="addVolume"><span>+</span> 添加卷</button>
              </div>
            </div>

            <!-- 服务依赖 -->
            <div v-if="outputMode === 'compose'" class="detail-section">
              <h4>服务依赖（启动顺序）</h4>
              <div class="depends-config">
                <div class="dependencies-list">
                  <div
                    v-for="(dependency, idx) in activeService.dependsOn"
                    :key="idx"
                    class="dep-chip"
                  >
                    <span class="dep-name">{{ dependency }}</span>
                    <button
                      v-if="activeService.dependsOn.length > 0"
                      class="remove-dep-btn"
                      @click="removeDependency(idx)"
                    >
                      <span>×</span>
                    </button>
                  </div>
                </div>
                <div class="add-dependency-section">
                  <select
                    v-model="selectedDependencyToAdd"
                    placeholder="选择依赖服务..."
                    class="dependency-select"
                  >
                    <option v-for="service in services" :key="service.id" :value="service.name">
                      {{ service.name || `服务 ${services.indexOf(service) + 1}` }}
                    </option>
                    <option value="" disabled>选择依赖...</option>
                  </select>
                  <button
                    class="add-dep-btn"
                    :disabled="!selectedDependencyToAdd"
                    @click="addDependency"
                  >
                    <span>+</span> 添加
                  </button>
                </div>
              </div>
            </div>

            <!-- 高级选项 -->
            <div class="detail-section">
              <h4>高级选项</h4>
              <div class="checkbox-group">
                <label>
                  <input v-model="activeService.restart" type="checkbox" />
                  自动重启
                </label>
                <label v-if="activeService.restart">
                  <select v-model="activeService.restartPolicy">
                    <option value="always">always</option>
                    <option value="unless-stopped">unless-stopped</option>
                    <option value="on-failure">on-failure</option>
                  </select>
                </label>
                <label>
                  <input v-model="activeService.detach" type="checkbox" />
                  后台运行 (-d)
                </label>
              </div>

              <div class="form-group" style="margin-top: 15px">
                <label>健康检查</label>
                <input
                  v-model="activeService.healthcheck"
                  type="text"
                  placeholder='["CMD", "curl -f http://localhost:5000 || exit 1"]'
                  class="code-input"
                />
                <small class="help-text"
                  >例如: ["CMD-SHELL", "curl -f http://localhost || exit 1"]</small
                >
              </div>

              <div class="form-group">
                <label>健康检查间隔（秒）</label>
                <input v-model="activeService.healthcheckInterval" type="number" placeholder="30" />
              </div>

              <div class="form-group">
                <label>健康检查超时（秒）</label>
                <input v-model="activeService.healthcheckTimeout" type="number" placeholder="10" />
              </div>

              <div class="form-group">
                <label>重试次数</label>
                <input v-model="activeService.healthcheckRetries" type="number" placeholder="3" />
              </div>
            </div>
          </div>
        </div>

        <!-- 配置预览 -->
        <div class="config-preview">
          <div class="preview-header">
            <h3>配置预览</h3>
            <div class="preview-actions">
              <button class="action-btn" title="复制配置" @click="copyConfig">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                <span>复制</span>
              </button>
              <button class="action-btn" title="下载配置" @click="downloadConfig">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                <span>下载</span>
              </button>
            </div>
          </div>
          <pre class="config-content">{{ generatedConfig }}</pre>
        </div>
      </div>
    </div>

    <!-- 隐藏的文件输入，用于导入配置 -->
    <input
      ref="fileInput"
      type="file"
      accept=".conf,.json,.dockerfile,.yml,.yaml"
      style="display: none"
      @change="handleFileImport"
    />
  </div>
</template>

<script setup>
  import { ref, computed, watch } from 'vue'

  const props = defineProps({
    visible: {
      type: Boolean,
      default: false
    }
  })

  const emit = defineEmits(['close'])

  // 状态
  const outputMode = ref('compose')
  const showTemplates = ref(false)
  const showDetailConfig = ref(true)
  const selectedDependencyToAdd = ref('')
  const validationMessage = ref('')
  const fileInput = ref(null)

  // 服务列表
  const services = ref([
    {
      id: 1,
      name: '前端应用',
      appType: 'web',
      image: 'node:18-alpine',
      imageTag: '',
      workDir: '/app',
      user: 'node',
      command: 'npm run dev',
      ports: [{ host: 3000, container: 3000, protocol: 'tcp' }],
      environment: [
        { name: 'NODE_ENV', value: 'production' },
        { name: 'PORT', value: '3000' }
      ],
      volumes: [],
      dependsOn: [],
      restart: 'unless-stopped',
      restartPolicy: 'unless-stopped',
      detach: true,
      healthcheck: '',
      healthcheckInterval: 30,
      healthcheckTimeout: 10,
      healthcheckRetries: 3
    },
    {
      id: 2,
      name: '后端API',
      appType: 'api',
      image: 'python:3.9-slim',
      imageTag: '',
      workDir: '/app',
      user: '',
      command: 'python app.py',
      ports: [{ host: 5000, container: 5000, protocol: 'tcp' }],
      environment: [
        { name: 'PYTHONUNBUFFERED', value: '1' },
        { name: 'APP_ENV', value: 'production' }
      ],
      volumes: [{ type: 'bind', source: './data', dest: '/app/data', mode: 'rw' }],
      dependsOn: [],
      restart: 'unless-stopped',
      restartPolicy: 'unless-stopped',
      detach: true,
      healthcheck: '',
      healthcheckInterval: 30,
      healthcheckTimeout: 10,
      healthcheckRetries: 3
    },
    {
      id: 3,
      name: 'MySQL数据库',
      appType: 'database',
      image: 'mysql:8.0',
      imageTag: '',
      workDir: '',
      user: 'mysql',
      command: '',
      ports: [{ host: 3306, container: 3306, protocol: 'tcp' }],
      environment: [
        { name: 'MYSQL_ROOT_PASSWORD', value: 'password' },
        { name: 'MYSQL_DATABASE', value: 'myapp' }
      ],
      volumes: [{ type: 'volume', source: 'mysql-data', dest: '/var/lib/mysql' }],
      dependsOn: [],
      restart: 'always',
      restartPolicy: 'always',
      detach: true,
      healthcheck:
        '["CMD", "mysqladmin ping -h localhost -u root -p$MYSQL_ROOT_PASSWORD || exit 1"]',
      healthcheckInterval: 10,
      healthcheckTimeout: 5,
      healthcheckRetries: 3
    }
  ])

  const activeServiceId = ref(null)
  const activeService = computed({
    get() {
      return services.value.find(s => s.id === activeServiceId.value)
    },
    set(value) {
      if (value) {
        activeServiceId.value = value.id
        showDetailConfig.value = true
      } else {
        activeServiceId.value = null
      }
    }
  })

  // 项目配置
  const projectInfo = ref({
    name: 'my-project',
    version: '3.8',
    networkMode: '',
    customNetworks: [
      { name: 'frontend', driver: 'bridge' },
      { name: 'backend', driver: 'bridge' }
    ]
  })

  // 应用类型标签
  const appTypeLabels = {
    web: '前端',
    api: '后端',
    worker: '任务',
    database: '数据库',
    proxy: '代理',
    cache: '缓存',
    queue: '队列'
  }

  // 应用图标
  const getAppIcon = appType => {
    const icons = {
      web: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,
      api: '[API]',
      worker: '[WORKER]',
      database: '[DATABASE]',
      proxy: '[PROXY]',
      cache: '[CACHE]',
      queue: '[QUEUE]'
    }
    return icons[appType] || ''
  }

  // 模板
  const frontendTemplates = [
    {
      id: 'react-multi',
      name: 'React + Docker Compose',
      services: [
        {
          name: '前端',
          appType: 'web',
          image: 'node:18-alpine',
          command: 'npm run dev',
          ports: [{ host: 3000, container: 3000, protocol: 'tcp' }],
          environment: [{ name: 'NODE_ENV', value: 'production' }]
        },
        {
          name: 'Nginx代理',
          appType: 'proxy',
          image: 'nginx:alpine',
          ports: [{ host: 80, container: 80, protocol: 'tcp' }],
          volumes: [{ type: 'bind', source: './nginx.conf', dest: '/etc/nginx/nginx.conf:ro' }]
        }
      ]
    },
    {
      id: 'vue-fullstack',
      name: 'Vue 全栈',
      services: [
        {
          name: '前端',
          appType: 'web',
          image: 'node:18-alpine',
          command: 'npm run dev',
          ports: [{ host: 8080, container: 8080, protocol: 'tcp' }],
          environment: [{ name: 'NODE_ENV', value: 'production' }]
        },
        {
          name: 'Nginx',
          appType: 'proxy',
          image: 'nginx:alpine',
          ports: [{ host: 80, container: 80, protocol: 'tcp' }],
          dependsOn: ['Web']
        }
      ]
    }
  ]

  const backendTemplates = [
    {
      id: 'python-compose',
      name: 'Python Compose',
      services: [
        {
          name: 'Python应用',
          appType: 'api',
          image: 'python:3.9-slim',
          command: 'python app.py',
          ports: [{ host: 5000, container: 5000, protocol: 'tcp' }]
        },
        {
          name: 'Redis',
          appType: 'cache',
          image: 'redis:7-alpine',
          ports: [{ host: 6379, container: 6379, protocol: 'tcp' }],
          dependsOn: ['Python应用'],
          restart: 'always'
        },
        {
          name: 'MySQL',
          appType: 'database',
          image: 'mysql:8.0',
          ports: [{ host: 3306, container: 3306, protocol: 'tcp' }],
          environment: [
            { name: 'MYSQL_ROOT_PASSWORD', value: 'password' },
            { name: 'MYSQL_DATABASE', value: 'mydb' }
          ],
          volumes: [{ type: 'volume', source: 'mysql-data', dest: '/var/lib/mysql' }]
        }
      ]
    },
    {
      id: 'node-cluster',
      name: 'Node.js 集群',
      services: [
        {
          name: 'API服务1',
          appType: 'api',
          image: 'node:18-alpine',
          command: 'npm start',
          ports: [{ host: 3001, container: 3000, protocol: 'tcp' }]
        },
        {
          name: 'API服务2',
          appType: 'api',
          image: 'node:18-alpine',
          command: 'npm start',
          ports: [{ host: 3002, container: 3000, protocol: 'tcp' }]
        },
        {
          name: 'Redis队列',
          appType: 'queue',
          image: 'redis:7-alpine',
          ports: [{ host: 6379, container: 6379, protocol: 'tcp' }],
          restart: 'always'
        }
      ]
    }
  ]

  const databaseTemplates = [
    {
      id: 'mysql-cluster',
      name: 'MySQL 主从',
      services: [
        {
          name: 'MySQL主',
          appType: 'database',
          image: 'mysql:8.0',
          ports: [{ host: 3306, container: 3306, protocol: 'tcp' }],
          environment: [{ name: 'MYSQL_ROOT_PASSWORD', value: 'password' }],
          volumes: [{ type: 'volume', source: 'mysql-master-data', dest: '/var/lib/mysql' }]
        },
        {
          name: 'MySQL从',
          appType: 'database',
          image: 'mysql:8.0',
          command:
            '--server-id=mysql-slave --master-host=MySQL主 --master-user=root --master-password=password',
          environment: [{ name: 'MYSQL_ROOT_PASSWORD', value: 'password' }],
          volumes: [{ type: 'volume', source: 'mysql-slave-data', dest: '/var/lib/mysql' }],
          dependsOn: ['MySQL主']
        }
      ]
    },
    {
      id: 'mongodb-replica',
      name: 'MongoDB 副本集',
      services: [
        {
          name: 'MongoDB主',
          appType: 'database',
          image: 'mongo:6',
          ports: [{ host: 27017, container: 27017, protocol: 'tcp' }],
          volumes: [{ type: 'volume', source: 'mongo-master-data', dest: '/data/db' }]
        },
        {
          name: 'MongoDB从',
          appType: 'database',
          image: 'mongo:6',
          ports: [{ host: 27018, container: 27017, protocol: 'tcp' }],
          volumes: [{ type: 'volume', source: 'mongo-slave-data', dest: '/data/db' }],
          dependsOn: ['MongoDB主']
        }
      ]
    }
  ]

  const composeTemplates = [
    {
      id: 'microservices',
      name: '微服务架构',
      services: [
        {
          name: 'API网关',
          appType: 'proxy',
          image: 'nginx:alpine',
          ports: [{ host: 80, container: 80, protocol: 'tcp' }]
        },
        {
          name: '用户服务',
          appType: 'api',
          image: 'node:18-alpine',
          ports: [{ host: 3001, container: 3000, protocol: 'tcp' }],
          environment: [{ name: 'JWT_SECRET', value: 'your-secret-here' }]
        },
        {
          name: '订单服务',
          appType: 'api',
          image: 'node:18-alpine',
          ports: [{ host: 3002, container: 3000, protocol: 'tcp' }],
          environment: [{ name: 'JWT_SECRET', value: 'your-secret-here' }],
          dependsOn: ['用户服务', 'Redis队列']
        },
        {
          name: 'Redis队列',
          appType: 'queue',
          image: 'redis:7-alpine',
          ports: [{ host: 6379, container: 6379, protocol: 'tcp' }],
          dependsOn: ['订单服务'],
          restart: 'always'
        },
        {
          name: 'PostgreSQL',
          appType: 'database',
          image: 'postgres:14',
          ports: [{ host: 5432, container: 5432, protocol: 'tcp' }],
          environment: [{ name: 'POSTGRES_PASSWORD', value: 'password' }],
          volumes: [{ type: 'volume', source: 'postgres-data', dest: '/var/lib/postgresql/data' }],
          restart: 'always'
        }
      ]
    },
    {
      id: 'fullstack-ci-cd',
      name: 'CI/CD 工具链',
      services: [
        {
          name: 'GitLab',
          appType: 'web',
          image: 'gitlab/gitlab-ce:latest',
          ports: [{ host: 9500, container: 80, protocol: 'tcp' }],
          volumes: [{ type: 'volume', source: 'gitlab-data', dest: '/var/opt/gitlab' }],
          restart: 'always'
        },
        {
          name: 'Jenkins',
          appType: 'web',
          image: 'jenkins/jenkins:lts',
          ports: [{ host: 9090, container: 8080, protocol: 'tcp' }],
          volumes: [{ type: 'volume', source: 'jenkins-home', dest: '/var/jenkins_home' }],
          restart: 'always'
        },
        {
          name: 'Nexus',
          appType: 'proxy',
          image: 'sonatype/nexus3:latest',
          ports: [{ host: 8081, container: 8081, protocol: 'tcp' }],
          volumes: [{ type: 'volume', source: 'nexus-data', dest: '/nexus-data' }],
          restart: 'always'
        }
      ]
    }
  ]

  // 方法
  const selectService = serviceId => {
    activeService.value = services.value.find(s => s.id === serviceId)
  }

  const addService = () => {
    const newService = {
      id: Date.now(),
      name: `服务 ${services.value.length + 1}`,
      appType: 'web',
      image: 'node:18-alpine',
      imageTag: '',
      workDir: '/app',
      user: 'node',
      command: 'npm start',
      ports: [{ host: 3000 + services.value.length, container: 3000, protocol: 'tcp' }],
      environment: [{ name: 'NODE_ENV', value: 'production' }],
      volumes: [],
      dependsOn: [],
      restart: 'unless-stopped',
      restartPolicy: 'unless-stopped',
      detach: true,
      healthcheck: '',
      healthcheckInterval: 30,
      healthcheckTimeout: 10,
      healthcheckRetries: 3
    }
    services.value.push(newService)
    activeService.value = newService
  }

  const removeService = index => {
    if (services.value.length > 1) {
      const removedService = services.value[index]
      // 移除依赖
      services.value.forEach(service => {
        service.dependsOn = service.dependsOn.filter(d => d !== removedService.name)
      })
      services.value.splice(index, 1)
      if (activeServiceId.value === removedService.id) {
        activeService.value = null
      }
    }
  }

  const duplicateService = index => {
    const original = services.value[index]
    const duplicate = JSON.parse(JSON.stringify(original))
    delete duplicate.id
    duplicate.name = `${original.name} 副本`
    // 为每个服务设置不冲突的端口
    if (duplicate.ports && duplicate.ports.length > 0) {
      duplicate.ports[0].host += 100
    }
    services.value.push(duplicate)
    activeService.value = duplicate
  }

  const editServiceName = service => {
    const newName = prompt('请输入新的服务名称', service.name)
    if (newName && newName !== service.name) {
      // 更新所有依赖中的引用
      services.value.forEach(s => {
        const depIndex = s.dependsOn.indexOf(service.name)
        if (depIndex !== -1) {
          s.dependsOn.splice(depIndex, 1)
          s.dependsOn.push(newName)
        }
      })
      service.name = newName
    }
  }

  // 拖拽排序
  const draggingServiceId = ref(null)

  const onDragStart = (event, index) => {
    draggingServiceId.value = services.value[index].id
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('index', index)
  }

  const onDragOver = event => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }

  const onDrop = (event, targetIndex) => {
    event.preventDefault()
    const sourceIndex = parseInt(event.dataTransfer.getData('index'))
    if (sourceIndex === targetIndex) return

    const moved = services.value[sourceIndex]
    services.value.splice(sourceIndex, 1)
    services.value.splice(targetIndex, 0, moved)
    draggingServiceId.value = null
  }

  // 服务配置方法
  const addPort = () => {
    if (activeService.value) {
      if (!activeService.value.ports) {
        activeService.value.ports = []
      }
      activeService.value.ports.push({ host: '', container: '', protocol: 'tcp' })
    }
  }

  const removePort = index => {
    if (activeService.value && activeService.value.ports.length > 1) {
      activeService.value.ports.splice(index, 1)
    }
  }

  const addEnv = () => {
    if (activeService.value) {
      if (!activeService.value.environment) {
        activeService.value.environment = []
      }
      activeService.value.environment.push({ name: '', value: '' })
    }
  }

  const removeEnv = index => {
    if (activeService.value && activeService.value.environment.length > 0) {
      activeService.value.environment.splice(index, 1)
    }
  }

  const addVolume = () => {
    if (activeService.value) {
      if (!activeService.value.volumes) {
        activeService.value.volumes = []
      }
      activeService.value.volumes.push({
        type: 'bind',
        source: './data',
        dest: '/app/data',
        mode: 'rw'
      })
    }
  }

  const removeVolume = index => {
    if (activeService.value && activeService.value.volumes.length > 0) {
      activeService.value.volumes.splice(index, 1)
    }
  }

  const addDependency = () => {
    if (activeService.value && selectedDependencyToAdd.value) {
      if (!activeService.value.dependsOn.includes(selectedDependencyToAdd.value)) {
        activeService.value.dependsOn.push(selectedDependencyToAdd.value)
      }
      selectedDependencyToAdd.value = ''
    }
  }

  const removeDependency = index => {
    if (activeService.value && activeService.value.dependsOn.length > 0) {
      const removedDep = activeService.value.dependsOn[index]
      activeService.value.dependsOn.splice(index, 1)
      // 移除依赖关系
      services.value.forEach(service => {
        if (service.dependsOn.includes(removedDep)) {
          service.dependsOn = service.dependsOn.filter(d => d !== removedDep)
        }
      })
    }
  }

  // 网络配置方法
  const addNetwork = () => {
    projectInfo.value.customNetworks.push({ name: '', driver: 'bridge' })
  }

  const removeNetwork = index => {
    projectInfo.value.customNetworks.splice(index, 1)
  }

  // 应用模板
  const applyTemplate = template => {
    if (template.services) {
      // 替换服务列表
      const newServices = template.services.map((s, idx) => ({
        ...s,
        id: Date.now() + idx,
        name: s.name || `服务 ${idx + 1}`,
        ports: s.ports || [{ host: 3000, container: 3000, protocol: 'tcp' }],
        environment: s.environment || [],
        volumes: s.volumes || [],
        dependsOn: s.dependsOn || []
      }))
      services.value = newServices
      activeService.value = newServices[0]
    } else {
      // 单个服务模板
      Object.assign(activeService.value, template.data)
    }
    showTemplates.value = false
    validationMessage.value = `✓ 已应用"${template.name}"模板`
    setTimeout(() => {
      validationMessage.value = ''
    }, 3000)
  }

  // 生成配置
  const generatedConfig = computed(() => {
    if (outputMode.value === 'compose') {
      return generateDockerCompose()
    } else {
      return generateSingleDockerfile()
    }
  })

  // 生成完整的 Docker Compose
  const generateDockerCompose = () => {
    let compose = `version: "${projectInfo.value.version}"\n\n`

    // 生成服务
    compose += `services:\n`
    services.value.forEach(service => {
      compose += `  ${service.name || 'service'}:\n`
      compose += `    image: ${service.image}`
      if (service.imageTag) {
        compose += `:${service.imageTag}`
      }
      compose += `\n`

      if (service.workDir) {
        compose += `    working_dir: ${service.workDir}\n`
      }

      if (service.user) {
        compose += `    user: ${service.user}\n`
      }

      if (service.ports && service.ports.length > 0) {
        compose += `    ports:\n`
        service.ports.forEach(port => {
          compose += `      - "${port.host}:${port.container}/${port.protocol}"\n`
        })
      }

      if (service.environment && service.environment.length > 0) {
        compose += `    environment:\n`
        service.environment.forEach(env => {
          if (env.name && env.value) {
            compose += `      - ${env.name}=${env.value}\n`
          }
        })
      }

      if (service.volumes && service.volumes.length > 0) {
        compose += `    volumes:\n`
        service.volumes.forEach(volume => {
          if (volume.type === 'bind') {
            compose += `      - ${volume.source}:${volume.dest}:${volume.mode}\n`
          } else if (volume.type === 'volume') {
            compose += `      - ${volume.source}:${volume.dest}\n`
          }
        })
      }

      if (service.dependsOn && service.dependsOn.length > 0) {
        compose += `    depends_on:\n`
        compose += `      - ${service.dependsOn.join('\n      - ')}\n`
      }

      if (service.restart && service.restart !== 'no') {
        compose += `    restart: ${service.restart}\n`
      }

      if (service.command) {
        compose += `    command: ${service.command}\n`
      }

      if (service.healthcheck) {
        compose += `    healthcheck:\n`
        compose += `      ${service.healthcheck}\n`
        if (service.healthcheckInterval) {
          compose += `      interval: ${service.healthcheckInterval}s\n`
        }
        if (service.healthcheckTimeout) {
          compose += `      timeout: ${service.healthcheckTimeout}s\n`
        }
        if (service.healthcheckRetries) {
          compose += `      retries: ${service.healthcheckRetries}\n`
        }
      }

      compose += `\n`
    })

    // 生成网络
    if (projectInfo.value.customNetworks.length > 0 || projectInfo.value.networkMode) {
      compose += `networks:\n`

      if (projectInfo.value.networkMode) {
        compose += `  default:\n`
        compose += `    driver: ${projectInfo.value.networkMode}\n`
      } else {
        projectInfo.value.customNetworks.forEach(network => {
          compose += `  ${network.name}:\n`
          compose += `    driver: ${network.driver}\n`
        })
      }

      // 为每个服务分配网络
      services.value.forEach(service => {
        if (projectInfo.value.networkMode) {
          compose += `  ${service.name}:\n`
          compose += `    networks:\n`
          compose += `      - default\n`
        } else if (service.networks && service.networks.length > 0) {
          compose += `  ${service.name}:\n`
          compose += `    networks:\n`
          service.networks.forEach(net => {
            compose += `      - ${net}\n`
          })
        }
      })
      compose += `\n`
    }

    // 生成卷
    const volumeDeclarations = new Set()
    services.value.forEach(service => {
      if (service.volumes) {
        service.volumes.forEach(volume => {
          if (volume.type === 'volume') {
            volumeDeclarations.add(volume.source)
          }
        })
      }
    })

    if (volumeDeclarations.size > 0) {
      compose += `volumes:\n`
      volumeDeclarations.forEach(vol => {
        compose += `  ${vol}:\n`
      })
      compose += `\n`
    }

    return compose
  }

  // 生成单个 Dockerfile
  const generateSingleDockerfile = () => {
    if (!activeService.value) return '请先选择一个服务'

    const service = activeService.value
    let dockerfile = ''

    // FROM 指令
    dockerfile += `FROM ${service.image}`
    if (service.imageTag) {
      dockerfile += `:${service.imageTag}`
    }
    dockerfile += ` AS builder\n\n`

    // WORKDIR
    if (service.workDir) {
      dockerfile += `WORKDIR ${service.workDir}\n`
    }

    // USER
    if (service.user) {
      dockerfile += `USER ${service.user}\n`
    }

    // 复制文件（如果有卷，假设为bind挂载）
    if (service.volumes && service.volumes.length > 0) {
      service.volumes.forEach(volume => {
        if (volume.type === 'bind') {
          dockerfile += `COPY ${volume.source} ${volume.dest}\n`
        }
      })
    }

    // 安装依赖（根据镜像判断）
    if (service.image.includes('node')) {
      dockerfile += `COPY package*.json ./\n`
      dockerfile += `RUN npm install --production\n`
    } else if (service.image.includes('python')) {
      dockerfile += `COPY requirements.txt ./\n`
      dockerfile += `RUN pip install --no-cache-dir -r requirements.txt\n`
    } else if (service.image.includes('php')) {
      dockerfile += `RUN apt-get update && apt-get install -y php extensions\n`
    }

    // 环境变量
    if (service.environment && service.environment.length > 0) {
      service.environment.forEach(env => {
        if (env.name && env.value) {
          dockerfile += `ENV ${env.name}=${env.value}\n`
        }
      })
    }

    // EXPOSE
    if (service.ports && service.ports.length > 0) {
      const exposedPorts = service.ports.map(p => p.container).join(' ')
      dockerfile += `EXPOSE ${exposedPorts}\n`
    }

    // HEALTHCHECK
    if (service.healthcheck) {
      dockerfile += `HEALTHCHECK ${service.healthcheck}\n`
      if (service.healthcheckInterval) {
        dockerfile += `HEALTHCHECK --interval=${service.healthcheckInterval}s\n`
      }
      if (service.healthcheckTimeout) {
        dockerfile += `HEALTHCHECK --timeout=${service.healthcheckTimeout}s\n`
      }
      if (service.healthcheckRetries) {
        dockerfile += `HEALTHCHECK --retries=${service.healthcheckRetries}\n`
      }
    }

    // CMD
    if (service.command) {
      if (service.command.length > 0) {
        // 检查是否是数组格式
        if (service.command.includes('[')) {
          dockerfile += `CMD ${service.command}\n`
        } else {
          // 简单的命令，用数组格式包装
          dockerfile += `CMD ["sh", "-c", "${service.command}"]\n`
        }
      }
    }

    return dockerfile
  }

  // 复制配置
  const copyConfig = async () => {
    try {
      await navigator.clipboard.writeText(generatedConfig.value)
      validationMessage.value = '✓ 配置已复制到剪贴板'
      setTimeout(() => {
        validationMessage.value = ''
      }, 3000)
    } catch (err) {
      validationMessage.value = '✗ 复制失败: ' + err.message
    }
  }

  // 下载配置
  const downloadConfig = () => {
    const filename = outputMode.value === 'compose' ? 'docker-compose.yml' : 'Dockerfile'
    const blob = new Blob([generatedConfig.value], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    validationMessage.value = `✓ ${filename} 已下载`
    setTimeout(() => {
      validationMessage.value = ''
    }, 3000)
  }

  // 导入配置
  const importConfig = () => {
    fileInput.value.click()
  }

  // 处理文件导入
  const handleFileImport = event => {
    const file = event.target.files[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = e => {
      const content = e.target.result

      try {
        if (file.name.endsWith('.json')) {
          const importedData = JSON.parse(content)
          if (importedData.services) {
            services.value = importedData.services
          }
          if (importedData.projectInfo) {
            projectInfo.value = importedData.projectInfo
          }
          validationMessage.value = '✓ 配置导入成功'
        } else {
          validationMessage.value = '✓ 配置文件已读取（仅 JSON 格式的多服务配置导入）'
        }
      } catch (error) {
        validationMessage.value = '✗ 导入失败: ' + error.message
      }

      setTimeout(() => {
        validationMessage.value = ''
      }, 3000)

      fileInput.value.value = ''
    }

    reader.readAsText(file)
  }

  // 导出配置
  const exportConfig = () => {
    const exportData = {
      version: '1.0',
      timestamp: new Date().toISOString(),
      outputMode: outputMode.value,
      projectInfo: projectInfo.value,
      services: services.value
    }

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'docker-multi-service-config.json'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    validationMessage.value = '✓ 多服务配置已导出'
    setTimeout(() => {
      validationMessage.value = ''
    }, 3000)
  }
</script>

<style scoped>
  .docker-config-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
  }

  .docker-config-modal {
    background: var(--bg-primary);
    border-radius: 12px;
    width: 95%;
    max-width: 1400px;
    max-height: 95vh;
    overflow-y: auto;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 30px;
    border-bottom: 1px solid var(--border-color);
    background: var(--gradient-primary);
    color: white;
  }

  .modal-header h2 {
    margin: 0;
    font-size: 24px;
  }

  .header-actions {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .import-btn,
  .export-btn {
    padding: 8px 16px;
    background: rgba(255, 255, 255, 0.15);
    border: 1px solid rgba(255, 255, 255, 0.3);
    color: white;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.3s;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .import-btn:hover,
  .export-btn:hover {
    background: rgba(255, 255, 255, 0.25);
    transform: translateY(-1px);
  }

  .close-btn {
    background: rgba(255, 255, 255, 0.15);
    border: none;
    color: white;
    font-size: 24px;
    line-height: 1;
    cursor: pointer;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition:
      background-color 0.2s ease,
      opacity 0.2s ease;
    outline: none;
    padding: 0;
    margin: 0;
  }

  .close-btn:hover {
    background: rgba(255, 255, 255, 0.3);
  }

  .close-btn:active {
    background: rgba(255, 255, 255, 0.1);
  }

  .modal-body {
    padding: 30px;
  }

  /* 配置类型选择 */
  .config-type-selector {
    padding: 20px;
    border-bottom: 2px solid var(--border-color);
    margin-bottom: 20px;
  }

  .config-type-selector h3 {
    margin: 0 0 15px 0;
    color: var(--text-primary);
    font-size: 18px;
  }

  .type-buttons {
    display: flex;
    gap: 15px;
  }

  .type-buttons button {
    padding: 12px 24px;
    border: 2px solid var(--border-color);
    background: var(--bg-primary);
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.3s;
    font-weight: 500;
  }

  .type-buttons button:hover:not(.active) {
    border-color: var(--primary);
    color: var(--primary);
    background: var(--bg-secondary);
  }

  .type-buttons button.active {
    background: var(--gradient-primary);
    border-color: var(--primary);
    color: white;
  }

  /* 服务列表 */
  .services-section {
    margin-bottom: 20px;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: 0 0 20px 0;
  }

  .section-header h3 {
    margin: 0;
    color: var(--text-primary);
    font-size: 20px;
    font-weight: 600;
  }

  .section-actions {
    display: flex;
    gap: 10px;
  }

  .add-service-btn {
    padding: 10px 20px;
    background: var(--gradient-success);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.3s;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .add-service-btn:hover {
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
  }

  .apply-template-btn {
    padding: 10px 20px;
    background: var(--bg-primary);
    border: 2px solid var(--text-secondary);
    color: var(--text-secondary);
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.3s;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .apply-template-btn:hover {
    background: var(--slate-100);
    border-color: var(--text-secondary);
  }

  /* 模板选择器 */
  .templates-selector {
    background: var(--gradient-primary);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
  }

  .templates-selector h4 {
    margin: 0 0 15px 0;
    color: white;
    font-size: 16px;
    font-weight: 600;
  }

  .template-categories {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
  }

  .template-category h5 {
    margin: 0 0 10px 0;
    color: rgba(255, 255, 255, 0.8);
    font-size: 14px;
  }

  .template-buttons {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .template-buttons button {
    padding: 10px 16px;
    background: rgba(255, 255, 255, 0.15);
    border: none;
    color: white;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.2s;
    text-align: left;
  }

  .template-buttons button:hover {
    background: rgba(255, 255, 255, 0.25);
    transform: translateY(-2px);
  }

  /* 服务卡片 */
  .service-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 15px;
    margin-bottom: 20px;
  }

  .service-card {
    background: var(--bg-primary);
    border: 2px solid var(--border-color);
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.3s;
    overflow: hidden;
  }

  .service-card:hover {
    border-color: var(--primary);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
    transform: translateY(-2px);
  }

  .service-card.dragging {
    opacity: 0.5;
    transform: scale(0.98);
  }

  .service-card.active {
    border-color: var(--primary);
    box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
  }

  .service-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
  }

  .service-info {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .service-icon {
    font-size: 24px;
  }

  .service-name {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .service-type-badge {
    padding: 4px 10px;
    background: var(--gradient-primary);
    color: white;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
  }

  .service-actions {
    display: flex;
    gap: 5px;
  }

  .icon-btn {
    width: 32px;
    height: 32px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    cursor: pointer;
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }

  .icon-btn:hover {
    background: var(--slate-100);
    border-color: var(--primary);
  }

  .icon-btn:active {
    transform: scale(0.95);
  }

  .delete-btn:hover {
    background: var(--danger-100);
    border-color: var(--danger);
  }

  .service-preview {
    padding: 15px;
    background: var(--bg-secondary);
  }

  .preview-item {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 13px;
  }

  .preview-item .label {
    color: var(--text-secondary);
    font-weight: 500;
    min-width: 60px;
  }

  .preview-item code,
  .preview-item .value {
    background: var(--bg-primary);
    color: var(--text-primary);
    padding: 4px 10px;
    border-radius: 4px;
    font-family: 'Courier New', monospace;
    font-size: 12px;
  }

  .service-preview-hint {
    text-align: center;
    color: var(--text-tertiary);
    font-size: 12px;
    padding-top: 10px;
  }

  /* 详细配置面板 */
  .service-detail-panel {
    background: var(--bg-secondary);
    border: 2px solid var(--border-color);
    border-radius: 12px;
    margin-bottom: 20px;
  }

  .detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15px 20px;
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-secondary);
  }

  .detail-header h3 {
    margin: 0;
    color: var(--text-primary);
    font-size: 18px;
    font-weight: 600;
  }

  .detail-actions {
    display: flex;
    gap: 10px;
  }

  .toggle-accordion-btn {
    padding: 6px 12px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    transition: all 0.3s;
  }

  .toggle-accordion-btn:hover {
    background: var(--slate-100);
    border-color: var(--text-secondary);
  }

  .detail-content {
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.3s ease-out;
  }

  .detail-content.expanded {
    max-height: 2000px;
    overflow: visible;
  }

  .detail-section {
    padding: 20px;
    margin-bottom: 25px;
  }

  .detail-section:last-child {
    margin-bottom: 0;
  }

  .detail-section h4 {
    margin: 0 0 15px 0;
    color: var(--text-primary);
    font-size: 16px;
    font-weight: 600;
    border-bottom: 2px solid var(--border-color);
    padding-bottom: 10px;
  }

  /* 配置表单 */
  .config-form {
    background: var(--bg-primary);
  }

  .config-form .form-row {
    display: flex;
    gap: 15px;
    margin-bottom: 15px;
  }

  .form-group {
    margin-bottom: 15px;
  }

  .form-group label {
    display: block;
    margin-bottom: 6px;
    color: var(--text-primary);
    font-weight: 500;
    font-size: 14px;
  }

  .form-group input,
  .form-group select {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 14px;
    transition: all 0.3s;
  }

  .form-group input:focus,
  .form-group select:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  .wide-input {
    font-family: 'Courier New', monospace;
  }

  .medium-input {
    width: 50%;
  }

  .code-input {
    font-family: 'Courier New', monospace;
    background: var(--bg-primary);
    color: var(--text-primary);
  }

  .form-group small.help-text {
    display: block;
    margin-top: 5px;
    color: var(--text-secondary);
    font-size: 12px;
  }

  /* 端口配置 */
  .ports-config {
    background: var(--bg-secondary);
    padding: 15px;
    border-radius: 8px;
  }

  .port-item {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .port-row {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .port-field {
    flex: 1;
  }

  .port-field label {
    display: block;
    margin-bottom: 4px;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .port-field input {
    width: 100%;
    padding: 8px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 13px;
  }

  .port-arrow {
    color: var(--text-tertiary);
    font-size: 18px;
  }

  .add-port-btn,
  .remove-port-btn {
    padding: 6px 12px;
    background: var(--primary);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    align-self: center;
    margin-top: 10px;
  }

  .add-port-btn:hover {
    background: var(--color-primary-700);
  }

  .remove-port-btn {
    background: var(--danger);
  }

  /* 环境变量 */
  .env-config {
    background: var(--bg-secondary);
    padding: 15px;
    border-radius: 8px;
  }

  .env-row {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .env-field {
    display: flex;
    gap: 10px;
    align-items: stretch;
    flex: 1;
  }

  .env-name-input {
    width: 40%;
  }

  .env-value-input {
    width: 40%;
  }

  .equals-sign {
    color: var(--text-tertiary);
    font-size: 18px;
    font-weight: 600;
  }

  .remove-env-btn {
    background: var(--danger);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    padding: 4px 8px;
    font-size: 14px;
  }

  .add-env-btn {
    padding: 6px 12px;
    background: var(--success);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    margin-top: 10px;
  }

  .add-env-btn:hover {
    background: var(--success-hover);
  }

  /* 卷配置 */
  .volumes-config {
    background: var(--bg-secondary);
    padding: 15px;
    border-radius: 8px;
  }

  .volume-row {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .volume-type,
  .volume-source,
  .volume-dest,
  .volume-mode {
    flex: 1;
  }

  .volume-type select,
  .volume-mode select {
    width: 100px;
  }

  .volume-arrow {
    color: var(--text-tertiary);
    font-size: 18px;
  }

  .remove-volume-btn {
    background: var(--danger);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    padding: 4px 8px;
    font-size: 14px;
  }

  .add-volume-btn {
    padding: 6px 12px;
    background: var(--success);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    margin-top: 10px;
  }

  .add-volume-btn:hover {
    background: var(--success-hover);
  }

  /* 依赖配置 */
  .depends-config {
    background: var(--bg-secondary);
    padding: 15px;
    border-radius: 8px;
  }

  .dependencies-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 15px;
  }

  .dep-chip {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: var(--gradient-primary);
    color: white;
    border-radius: 16px;
    font-size: 13px;
  }

  .dep-name {
    font-weight: 500;
  }

  .remove-dep-btn {
    background: rgba(239, 68, 68, 0.1);
    color: white;
    border: none;
    border-radius: 50%;
    cursor: pointer;
    font-size: 14px;
    padding: 2px 6px;
    margin-left: 4px;
  }

  .add-dependency-section {
    display: flex;
    gap: 10px;
    margin-top: 15px;
  }

  .dependency-select {
    flex: 1;
    padding: 8px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
  }

  .add-dep-btn {
    padding: 8px 12px;
    background: var(--success);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
  }

  /* 项目配置 */
  .project-config-section {
    background: var(--gradient-bg);
    border: 2px solid var(--border-color);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
  }

  .project-config-section h3 {
    margin: 0 0 15px 0;
    color: var(--text-primary);
    font-size: 18px;
  }

  .form-row {
    display: flex;
    gap: 15px;
  }

  .form-row .form-group {
    flex: 1;
  }

  /* 网络配置 */
  .networks-config {
    margin-top: 15px;
  }

  .network-items {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .network-item {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .network-name,
  .network-driver {
    flex: 1;
  }

  .network-name input,
  .network-driver select {
    width: 100%;
    padding: 8px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
  }

  .remove-network-btn {
    background: var(--danger);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    padding: 4px 8px;
    font-size: 14px;
  }

  .add-network-btn {
    padding: 6px 12px;
    background: var(--success);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    margin-top: 10px;
  }

  /* 高级选项 */
  .detail-section .checkbox-group {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
    margin-top: 15px;
  }

  .detail-section .checkbox-group label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 14px;
  }

  .detail-section .checkbox-group input[type='checkbox'] {
    width: 18px;
    height: 18px;
    cursor: pointer;
  }

  /* 配置预览 */
  .config-preview {
    margin-bottom: 20px;
  }

  .preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }

  .preview-header h3 {
    margin: 0;
    color: var(--text-primary);
    font-size: 18px;
  }

  .preview-actions {
    display: flex;
    gap: 8px;
  }

  .action-btn {
    padding: 8px 16px;
    background: var(--gradient-primary);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.3s;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .action-btn:hover {
    background: linear-gradient(135deg, #5a67d8 0%, #6b4190 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  }

  .config-content {
    background: var(--bg-primary);
    color: var(--text-primary);
    padding: 20px;
    border-radius: 8px;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
    max-height: 500px;
    overflow-y: auto;
    white-space: pre-wrap;
  }

  /* 滚动条样式 */
  .modal-body::-webkit-scrollbar,
  .config-content::-webkit-scrollbar {
    width: 10px;
  }

  .modal-body::-webkit-scrollbar-track,
  .config-content::-webkit-scrollbar-track {
    background: var(--bg-tertiary);
    border-radius: 5px;
  }

  .modal-body::-webkit-scrollbar-thumb,
  .config-content::-webkit-scrollbar-thumb {
    background: #888;
    border-radius: 5px;
  }

  .modal-body::-webkit-scrollbar-thumb:hover,
  .config-content::-webkit-scrollbar-thumb:hover {
    background: #555;
  }

  /* 响应式设计 */
  @media (max-width: 768px) {
    .docker-config-modal {
      width: 95%;
      max-height: 95vh;
    }

    .service-cards {
      grid-template-columns: 1fr;
    }

    .form-row {
      flex-direction: column;
    }

    .template-categories {
      grid-template-columns: 1fr;
    }

    .service-card-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 10px;
    }
  }
</style>
