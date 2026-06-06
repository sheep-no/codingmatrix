<template>
  <div class="resource-control">
    <div class="section-header">
      <div class="header-left">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <circle cx="12" cy="12" r="3"></circle>
          <path
            d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"
          ></path>
        </svg>
        <div>
          <h2>资源配置管理</h2>
          <p class="header-desc">管理 Docker 容器资源限制和功能开关</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="action-btn" @click="loadConfig">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M23 4v6h-6"></path>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
          </svg>
          <span>刷新</span>
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>加载配置中...</span>
    </div>

    <div v-else class="config-content">
      <!-- Docker 资源配置 -->
      <div class="config-section">
        <h3 class="section-title">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path
              d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"
            ></path>
          </svg>
          Docker 资源配置
        </h3>

        <div class="config-grid">
          <div class="config-item">
            <label>最大内存限制</label>
            <div class="input-group">
              <input
                v-model="configs.docker_max_memory"
                type="text"
                placeholder="如: 512m, 1g"
                class="config-input"
              />
              <span class="input-hint">容器最大可用内存</span>
            </div>
          </div>

          <div class="config-item">
            <label>初始内存（Reservation）</label>
            <div class="input-group">
              <input
                v-model="configs.docker_initial_memory"
                type="text"
                placeholder="如: 256m, 512m"
                class="config-input"
              />
              <span class="input-hint">容器启动时预留内存</span>
            </div>
          </div>

          <div class="config-item">
            <label>系统镜像</label>
            <div class="input-group">
              <select v-model="configs.docker_image" class="config-select">
                <option value="alpha">alpha</option>
                <option value="ubuntu">ubuntu</option>
              </select>
              <span class="input-hint">容器使用的操作系统</span>
            </div>
          </div>

          <div class="config-item">
            <label>最大容器数量</label>
            <div class="input-group">
              <input
                v-model.number="configs.docker_max_containers"
                type="number"
                min="1"
                max="20"
                class="config-input"
              />
              <span class="input-hint">同时运行的容器上限</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 功能开关 -->
      <div class="config-section">
        <h3 class="section-title">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <rect x="1" y="5" width="22" height="14" rx="7" ry="7"></rect>
            <circle cx="16" cy="12" r="3"></circle>
          </svg>
          功能开关
          <span class="section-hint">关闭功能可释放服务器资源</span>
        </h3>

        <div class="feature-grid">
          <div
            v-for="(feature, key) in featureSwitches"
            :key="key"
            class="feature-item"
            :class="{ disabled: !feature.enabled }"
          >
            <div class="feature-info">
              <span class="feature-name">{{ feature.name }}</span>
              <span class="feature-desc">{{ feature.description }}</span>
            </div>
            <label class="switch">
              <input
                v-model="feature.enabled"
                type="checkbox"
                @change="handleFeatureToggle(key, feature.enabled)"
              />
              <span class="slider"></span>
            </label>
          </div>
        </div>
      </div>

      <!-- 数据库连接池配置 -->
      <div class="config-section">
        <h3 class="section-title">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
          </svg>
          数据库连接池配置
          <span class="section-hint">优化数据库连接管理，降低内存占用</span>
        </h3>

        <div class="config-grid">
          <div class="config-item">
            <label>连接池大小</label>
            <div class="input-group">
              <input
                v-model.number="configs.db_pool_size"
                type="number"
                min="1"
                max="20"
                class="config-input"
              />
              <span class="input-hint">基础连接数（2核CPU建议3-5）</span>
            </div>
          </div>

          <div class="config-item">
            <label>最大溢出连接</label>
            <div class="input-group">
              <input
                v-model.number="configs.db_max_overflow"
                type="number"
                min="0"
                max="50"
                class="config-input"
              />
              <span class="input-hint">高峰期额外连接数</span>
            </div>
          </div>

          <div class="config-item">
            <label>连接超时（秒）</label>
            <div class="input-group">
              <input
                v-model.number="configs.db_pool_timeout"
                type="number"
                min="5"
                max="60"
                class="config-input"
              />
              <span class="input-hint">等待连接的最大时间</span>
            </div>
          </div>
        </div>

        <div class="config-tip">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="16" x2="12" y2="12"></line>
            <line x1="12" y1="8" x2="12.01" y2="8"></line>
          </svg>
          <span>修改后需要重启服务才能生效。建议：小内存服务器使用较小值。</span>
        </div>
      </div>

      <!-- 日志配置 -->
      <div class="config-section">
        <h3 class="section-title">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
            <polyline points="10 9 9 9 8 9"></polyline>
          </svg>
          日志配置
          <span class="section-hint">控制日志详细程度，减少 I/O 开销</span>
        </h3>

        <div class="config-grid">
          <div class="config-item">
            <label>全局日志级别</label>
            <div class="input-group">
              <select
                v-model="logConfig.log_level"
                class="config-select"
                @change="handleLogLevelChange"
              >
                <option value="DEBUG">DEBUG - 调试（最详细）</option>
                <option value="INFO">INFO - 信息</option>
                <option value="WARNING">WARNING - 警告</option>
                <option value="ERROR">ERROR - 错误</option>
                <option value="CRITICAL">CRITICAL - 严重</option>
              </select>
              <span class="input-hint">生产环境建议 WARNING，可减少 70% 日志量</span>
            </div>
          </div>

          <div class="config-item">
            <label>日志保留天数</label>
            <div class="input-group">
              <input
                v-model.number="configs.log_retention_days"
                type="number"
                min="1"
                max="90"
                class="config-input"
              />
              <span class="input-hint">超过天数的日志文件将被清理</span>
            </div>
          </div>

          <div class="config-item">
            <label>写入日志文件</label>
            <div class="input-group">
              <label class="switch">
                <input
                  v-model="logConfig.log_to_file"
                  type="checkbox"
                  @change="handleLogToFileChange"
                />
                <span class="slider"></span>
              </label>
              <span class="input-hint">禁用可减少磁盘 I/O</span>
            </div>
          </div>
        </div>

        <div class="log-level-presets">
          <span class="preset-label">快速设置：</span>
          <button class="preset-btn" @click="setLogLevel('DEBUG')">调试</button>
          <button class="preset-btn" @click="setLogLevel('INFO')">信息</button>
          <button class="preset-btn" @click="setLogLevel('WARNING')">警告</button>
          <button class="preset-btn" @click="setLogLevel('ERROR')">错误</button>
        </div>
      </div>

      <!-- API 限流配置 -->
      <div class="config-section">
        <h3 class="section-title">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
            <path d="M2 17l10 5 10-5"></path>
            <path d="M2 12l10 5 10-5"></path>
          </svg>
          API 限流配置
          <span class="section-hint">防止 API 过载，保护服务器资源</span>
        </h3>

        <div class="rate-limit-header">
          <label class="switch">
            <input
              v-model="rateLimitConfig.enabled"
              type="checkbox"
              @change="handleRateLimitToggle"
            />
            <span class="slider"></span>
          </label>
          <span class="rate-limit-status">{{ rateLimitConfig.enabled ? '已启用' : '已禁用' }}</span>
        </div>

        <div class="config-grid">
          <div class="config-item">
            <label>全局限流（请求数/秒）</label>
            <div class="input-group">
              <input
                v-model.number="rateLimitConfig.global_limit"
                type="number"
                min="1"
                max="10000"
                class="config-input"
              />
              <input
                v-model.number="rateLimitConfig.global_window"
                type="number"
                min="1"
                max="3600"
                class="config-input-small"
                placeholder="窗口(秒)"
              />
              <button class="config-btn" @click="updateGlobalRateLimit">更新</button>
            </div>
          </div>

          <div class="config-item">
            <label>IP 限流（请求数/秒）</label>
            <div class="input-group">
              <input
                v-model.number="rateLimitConfig.ip_limit"
                type="number"
                min="1"
                max="1000"
                class="config-input"
              />
              <input
                v-model.number="rateLimitConfig.ip_window"
                type="number"
                min="1"
                max="3600"
                class="config-input-small"
                placeholder="窗口(秒)"
              />
              <button class="config-btn" @click="updateIpRateLimit">更新</button>
            </div>
          </div>

          <div class="config-item">
            <label>用户限流（请求数/秒）</label>
            <div class="input-group">
              <input
                v-model.number="rateLimitConfig.user_limit"
                type="number"
                min="1"
                max="500"
                class="config-input"
              />
              <input
                v-model.number="rateLimitConfig.user_window"
                type="number"
                min="1"
                max="3600"
                class="config-input-small"
                placeholder="窗口(秒)"
              />
              <button class="config-btn" @click="updateUserRateLimit">更新</button>
            </div>
          </div>
        </div>

        <div v-if="rateLimitStats.current_stats" class="rate-limit-stats">
          <h4 class="stats-title">实时统计</h4>
          <div class="stats-row">
            <div class="stat-item">
              <span class="stat-label">总请求</span>
              <span class="stat-value">{{ rateLimitStats.current_stats.total_requests || 0 }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">被限流</span>
              <span class="stat-value warning">{{
                rateLimitStats.current_stats.rate_limited || 0
              }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">当前 TPS</span>
              <span class="stat-value">{{
                rateLimitStats.current_stats.current_tps?.toFixed(1) || 0
              }}</span>
            </div>
          </div>
        </div>

        <div class="config-tip">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="16" x2="12" y2="12"></line>
            <line x1="12" y1="8" x2="12.01" y2="8"></line>
          </svg>
          <span
            >限流采用多级策略：全局 > IP > 用户 > 端点。2核4G 服务器建议全局限制 1000-2000
            请求/秒。</span
          >
        </div>
      </div>

      <!-- 熔断器状态 -->
      <div class="config-section">
        <h3 class="section-title">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path
              d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"
            ></path>
            <polyline points="22,6 12,13 2,6"></polyline>
          </svg>
          熔断器状态
          <span class="section-hint">服务级和 API 级熔断监控</span>
        </h3>

        <div v-if="fuseStates.length > 0" class="fuse-list">
          <div v-for="fuse in fuseStates" :key="fuse.service_name" class="fuse-item">
            <div class="fuse-header">
              <span class="fuse-name">{{ fuse.service_name }}</span>
              <span class="fuse-badge" :class="getFuseStateClass(fuse.state)">
                {{ getFuseStateText(fuse.state) }}
              </span>
            </div>
            <div class="fuse-details">
              <div class="fuse-detail">
                <span class="detail-label">重启次数</span>
                <span class="detail-value">{{ fuse.restart_count || 0 }}</span>
              </div>
              <div class="fuse-detail">
                <span class="detail-label">熔断冷却</span>
                <span class="detail-value">{{
                  fuse.cooldown_remaining ? `${fuse.cooldown_remaining}秒` : 'N/A'
                }}</span>
              </div>
              <div class="fuse-detail">
                <span class="detail-label">熔断重试</span>
                <span class="detail-value"
                  >{{ fuse.fuse_retry_count || 0 }} / {{ fuse.fuse_retry_times || 0 }}</span
                >
              </div>
            </div>
          </div>
        </div>
        <div v-else class="fuse-empty">
          <p>暂无熔断器状态数据</p>
          <button class="refresh-btn" @click="loadFuseStates">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M23 4v6h-6"></path>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
            </svg>
            刷新
          </button>
        </div>
      </div>

      <!-- 服务器状态 -->
      <div class="config-section">
        <h3 class="section-title">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
            <line x1="8" y1="21" x2="16" y2="21"></line>
            <line x1="12" y1="17" x2="12" y2="21"></line>
          </svg>
          服务器资源状态
        </h3>

        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-icon">[PC]</span>
              <span class="stat-label">CPU</span>
            </div>
            <div class="stat-value" :class="getStatusClass(serverStats.cpu_percent)">
              {{ serverStats.cpu_percent?.toFixed(1) || 0 }}%
            </div>
            <div class="stat-bar">
              <div
                class="stat-fill"
                :style="{ width: `${serverStats.cpu_percent || 0}%` }"
                :class="getStatusClass(serverStats.cpu_percent)"
              ></div>
            </div>
          </div>

          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-icon">🧠</span>
              <span class="stat-label">内存</span>
            </div>
            <div class="stat-value" :class="getStatusClass(serverStats.memory?.percent)">
              {{ serverStats.memory?.percent?.toFixed(1) || 0 }}%
            </div>
            <div class="stat-detail">
              {{ formatBytes(serverStats.memory?.used || 0) }} /
              {{ formatBytes(serverStats.memory?.total || 0) }}
            </div>
            <div class="stat-bar">
              <div
                class="stat-fill"
                :style="{ width: `${serverStats.memory?.percent || 0}%` }"
                :class="getStatusClass(serverStats.memory?.percent)"
              ></div>
            </div>
          </div>

          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-icon">[STORAGE]</span>
              <span class="stat-label">磁盘</span>
            </div>
            <div class="stat-value" :class="getStatusClass(serverStats.disk?.percent)">
              {{ serverStats.disk?.percent?.toFixed(1) || 0 }}%
            </div>
            <div class="stat-detail">
              {{ formatBytes(serverStats.disk?.used || 0) }} /
              {{ formatBytes(serverStats.disk?.total || 0) }}
            </div>
            <div class="stat-bar">
              <div
                class="stat-fill"
                :style="{ width: `${serverStats.disk?.percent || 0}%` }"
                :class="getStatusClass(serverStats.disk?.percent)"
              ></div>
            </div>
          </div>

          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-icon">[PKG]</span>
              <span class="stat-label">Docker 容器</span>
            </div>
            <div class="stat-value">
              {{ serverStats.docker?.running || 0 }} / {{ serverStats.docker?.max_allowed || 0 }}
            </div>
            <div class="stat-detail">运行中 / 最大允许</div>
            <div class="stat-bar">
              <div
                class="stat-fill"
                :style="{ width: `${dockerUsagePercent}%` }"
                :class="getStatusClass(dockerUsagePercent)"
              ></div>
            </div>
          </div>

          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-icon">[API]</span>
              <span class="stat-label">WebSocket</span>
            </div>
            <div class="stat-value">{{ wsStats.current || 0 }} / {{ wsStats.max || 50 }}</div>
            <div class="stat-detail">当前连接 / 最大允许</div>
            <div class="stat-bar">
              <div
                class="stat-fill"
                :style="{ width: `${wsUsagePercent}%` }"
                :class="getStatusClass(wsUsagePercent)"
              ></div>
            </div>
          </div>
        </div>

        <!-- 内存详细监控 -->
        <div v-if="memoryStats.process" class="memory-details">
          <h4 class="memory-title">
            <span>🧠</span>
            内存详细监控
            <button class="refresh-btn-small" title="刷新" @click="loadMemoryStats">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M23 4v6h-6"></path>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
              </svg>
            </button>
          </h4>
          <div class="memory-grid">
            <div class="memory-item">
              <span class="memory-label">进程 RSS</span>
              <span class="memory-value">{{ memoryStats.process.rss_mb?.toFixed(1) || 0 }} MB</span>
            </div>
            <div class="memory-item">
              <span class="memory-label">进程占用</span>
              <span class="memory-value">{{ memoryStats.process.percent?.toFixed(1) || 0 }}%</span>
            </div>
            <div class="memory-item">
              <span class="memory-label">系统内存</span>
              <span class="memory-value" :class="getStatusClass(memoryStats.system.percent)">
                {{ memoryStats.system.percent?.toFixed(1) || 0 }}%
              </span>
            </div>
            <div class="memory-item">
              <span class="memory-label">系统可用</span>
              <span class="memory-value"
                >{{ memoryStats.system.available_mb?.toFixed(0) || 0 }} MB</span
              >
            </div>
          </div>
          <div v-if="memoryStats.recommendations?.suggestions?.length" class="memory-advice">
            <div
              class="advice-item"
              :class="{
                warning: memoryStats.recommendations.env_warning,
                critical: memoryStats.recommendations.env_critical
              }"
            >
              <span class="advice-icon">{{
                memoryStats.recommendations.env_critical
                  ? '🔴'
                  : memoryStats.recommendations.env_warning
                    ? '🟡'
                    : '🟢'
              }}</span>
              <span>{{ memoryStats.recommendations.suggestions[0] }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 配置备份与恢复 -->
      <div class="config-section">
        <h3 class="section-title">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
          配置备份与恢复
          <span class="section-hint">导出/导入系统配置</span>
        </h3>

        <div class="backup-actions">
          <button class="backup-btn primary" :disabled="backingUp" @click="createBackup">
            <svg
              v-if="backingUp"
              class="spin"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
            </svg>
            <span>{{ backingUp ? '备份中...' : '创建备份' }}</span>
          </button>
          <button class="backup-btn" @click="showBackupList = !showBackupList">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"
              ></path>
            </svg>
            <span>查看历史备份</span>
          </button>
        </div>

        <div v-if="backupMessage" class="backup-message" :class="backupMessageType">
          {{ backupMessage }}
        </div>

        <!-- 备份列表 -->
        <div v-if="showBackupList" class="backup-list">
          <h4>历史备份</h4>
          <div v-if="backups.length === 0" class="backup-empty">暂无备份记录</div>
          <div v-else class="backup-items">
            <div v-for="backup in backups" :key="backup.filename" class="backup-item">
              <div class="backup-info">
                <span class="backup-name">{{ backup.filename }}</span>
                <span class="backup-meta">
                  {{ formatBytes(backup.size) }} | {{ formatDate(backup.created) }}
                </span>
              </div>
              <div class="backup-actions-item">
                <button class="action-btn-small" title="下载" @click="downloadBackupItem(backup)">
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                  </svg>
                </button>
                <button class="action-btn-small" title="恢复" @click="restoreBackupItem(backup)">
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polyline points="1 4 1 10 7 10"></polyline>
                    <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path>
                  </svg>
                </button>
                <button
                  class="action-btn-small danger"
                  title="删除"
                  @click="deleteBackupItem(backup)"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polyline points="3 6 5 6 21 6"></polyline>
                    <path
                      d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
                    ></path>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 恢复确认 -->
        <div v-if="restoreConfirmBackup" class="restore-confirm">
          <div class="confirm-content">
            <p>确定要恢复备份 "{{ restoreConfirmBackup.filename }}" 吗？</p>
            <p class="confirm-warning">当前配置将被覆盖</p>
            <div class="confirm-actions">
              <button class="confirm-btn cancel" @click="restoreConfirmBackup = null">取消</button>
              <button class="confirm-btn restore" @click="confirmRestore">确认恢复</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 保存按钮 -->
      <div class="action-bar">
        <button class="save-btn" :disabled="saving" @click="saveConfig">
          <svg
            v-if="saving"
            class="spin"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
          </svg>
          <span>{{ saving ? '保存中...' : '保存配置' }}</span>
        </button>
        <span v-if="saveMessage" class="save-message" :class="saveMessageType">
          {{ saveMessage }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, reactive, computed, onMounted } from 'vue'
  import { api } from '../utils/api/index'

  const loading = ref(false)
  const saving = ref(false)
  const saveMessage = ref('')
  const saveMessageType = ref('success')

  const configs = reactive({
    docker_max_memory: '512m',
    docker_initial_memory: '256m',
    docker_image: 'alpha',
    docker_max_containers: 5,
    feature_docker_enabled: true,
    feature_aicloud_enabled: true,
    feature_project_enabled: true,
    feature_workflow_enabled: true,
    db_pool_size: 5,
    db_max_overflow: 10,
    db_pool_timeout: 10,
    log_retention_days: 7
  })

  const logConfig = reactive({
    log_level: 'INFO',
    log_to_file: true
  })

  const rateLimitConfig = reactive({
    enabled: true,
    global_limit: 1000,
    global_window: 60,
    ip_limit: 100,
    ip_window: 60,
    user_limit: 50,
    user_window: 60
  })

  const rateLimitStats = reactive({
    current_stats: null
  })

  const fuseStates = ref([])

  const featureSwitches = reactive({
    docker: { name: 'Docker 功能', description: '代码验证和沙箱运行', enabled: true },
    aicloud: { name: 'AI Cloud 功能', description: 'AI 云端处理和审查', enabled: true },
    project: { name: '项目生成功能', description: 'AI 项目代码生成', enabled: true },
    workflow: { name: '工作流功能', description: '临时工作流执行', enabled: true }
  })

  const serverStats = ref({
    cpu_percent: 0,
    memory: { percent: 0, used: 0, total: 0 },
    disk: { percent: 0, used: 0, total: 0 },
    docker: { running: 0, max_allowed: 5 }
  })

  const dockerUsagePercent = computed(() => {
    if (!serverStats.value.docker?.max_allowed) return 0
    return (serverStats.value.docker.running / serverStats.value.docker.max_allowed) * 100
  })

  const wsStats = ref({
    current: 0,
    max: 50
  })

  const wsUsagePercent = computed(() => {
    if (!wsStats.value.max) return 0
    return (wsStats.value.current / wsStats.value.max) * 100
  })

  const backups = ref([])
  const showBackupList = ref(false)
  const backingUp = ref(false)
  const backupMessage = ref('')
  const backupMessageType = ref('success')
  const restoreConfirmBackup = ref(null)

  const memoryStats = ref({
    process: { rss_mb: 0, percent: 0, vms_mb: 0, uss_mb: 0 },
    system: { total_mb: 0, available_mb: 0, used_mb: 0, percent: 0 },
    swap: { total_mb: 0, used_mb: 0, percent: 0 },
    recommendations: { env_warning: false, env_critical: false, suggestions: [] }
  })

  const loadMemoryStats = async () => {
    try {
      const response = await api.getMemoryStats()
      if (response) {
        memoryStats.value = response
      }
    } catch (error) {
      console.error('加载内存统计失败:', error)
    }
  }

  const featureKeys = {
    docker: 'feature_docker_enabled',
    aicloud: 'feature_aicloud_enabled',
    project: 'feature_project_enabled',
    workflow: 'feature_workflow_enabled'
  }

  const setLogLevel = async level => {
    try {
      const result = await api.updateGlobalLogLevel(level)
      if (result && result.status === 'success') {
        logConfig.log_level = level
        showMessage(`日志级别已设置为 ${level}`, 'success')
      }
    } catch (error) {
      console.error('设置日志级别失败:', error)
      showMessage('设置日志级别失败', 'error')
    }
  }

  const handleLogLevelChange = async () => {
    await setLogLevel(logConfig.log_level)
  }

  const handleLogToFileChange = async () => {
  }

  const loadRateLimitConfig = async () => {
    try {
      const response = await api.getRateLimitStats()
      if (response) {
        rateLimitConfig.enabled = response.enabled !== false
        rateLimitStats.current_stats = response.current_stats || null
        if (response.global_limit) {
          rateLimitConfig.global_limit = response.global_limit[0]
          rateLimitConfig.global_window = response.global_limit[1]
        }
        if (response.ip_limit) {
          rateLimitConfig.ip_limit = response.ip_limit[0]
          rateLimitConfig.ip_window = response.ip_limit[1]
        }
        if (response.user_limit) {
          rateLimitConfig.user_limit = response.user_limit[0]
          rateLimitConfig.user_window = response.user_limit[1]
        }
      }
    } catch (error) {
      console.error('加载限流配置失败:', error)
    }
  }

  const updateGlobalRateLimit = async () => {
    try {
      const result = await api.updateGlobalRateLimit(
        rateLimitConfig.global_limit,
        rateLimitConfig.global_window
      )
      if (result && result.status === 'success') {
        showMessage('全局限流已更新', 'success')
      } else {
        showMessage('更新全局限流失败', 'error')
      }
    } catch (error) {
      console.error('更新全局限流失败:', error)
      showMessage('更新全局限流失败', 'error')
    }
  }

  const updateIpRateLimit = async () => {
    try {
      const result = await api.updateIpRateLimit(
        rateLimitConfig.ip_limit,
        rateLimitConfig.ip_window
      )
      if (result && result.status === 'success') {
        showMessage('IP 限流已更新', 'success')
      } else {
        showMessage('更新 IP 限流失败', 'error')
      }
    } catch (error) {
      console.error('更新 IP 限流失败:', error)
      showMessage('更新 IP 限流失败', 'error')
    }
  }

  const updateUserRateLimit = async () => {
    try {
      const result = await api.updateUserRateLimit(
        rateLimitConfig.user_limit,
        rateLimitConfig.user_window
      )
      if (result && result.status === 'success') {
        showMessage('用户限流已更新', 'success')
      } else {
        showMessage('更新用户限流失败', 'error')
      }
    } catch (error) {
      console.error('更新用户限流失败:', error)
      showMessage('更新用户限流失败', 'error')
    }
  }

  const handleRateLimitToggle = async () => {
    try {
      const result = await api.toggleRateLimit(rateLimitConfig.enabled)
      if (result && result.status === 'success') {
        showMessage(`限流已${rateLimitConfig.enabled ? '启用' : '禁用'}`, 'success')
      } else {
        showMessage('切换限流状态失败', 'error')
        rateLimitConfig.enabled = !rateLimitConfig.enabled
      }
    } catch (error) {
      console.error('切换限流状态失败:', error)
      showMessage('切换限流状态失败', 'error')
      rateLimitConfig.enabled = !rateLimitConfig.enabled
    }
  }

  const loadFuseStates = async () => {
    try {
      const services = await api.getServices()
      if (services && services.services) {
        const states = []
        for (const service of services.services) {
          if (service.name) {
            const state = await api.getFuseStatus(service.name)
            if (state) {
              states.push(state)
            }
          }
        }
        fuseStates.value = states
      }
    } catch (error) {
      console.error('加载熔断状态失败:', error)
    }
  }

  const getFuseStateClass = state => {
    if (state === 'fused') return 'critical'
    if (state === 'normal') return 'normal'
    return 'warning'
  }

  const getFuseStateText = state => {
    const stateMap = {
      normal: '正常',
      fused: '熔断中',
      restarting: '重启中',
      unknown: '未知'
    }
    return stateMap[state] || state
  }

  const loadConfig = async () => {
    loading.value = true
    try {
      const [configResponse, logConfigResponse, rateLimitResponse] = await Promise.all([
        api.get('/api/v2/admin/config'),
        api.getLogConfig(),
        api.getRateLimitStats()
      ])
      const data = configResponse

      if (data.configs) {
        Object.assign(configs, data.configs)
      }

      if (data.feature_status) {
        Object.keys(data.feature_status).forEach(key => {
          if (featureSwitches[key]) {
            featureSwitches[key].enabled = data.feature_status[key]
          }
        })
      }

      if (logConfigResponse) {
        Object.assign(logConfig, logConfigResponse)
      }

      if (rateLimitResponse) {
        rateLimitConfig.enabled = rateLimitResponse.enabled !== false
        rateLimitStats.current_stats = rateLimitResponse.current_stats || null
        if (rateLimitResponse.global_limit) {
          rateLimitConfig.global_limit = rateLimitResponse.global_limit[0]
          rateLimitConfig.global_window = rateLimitResponse.global_limit[1]
        }
        if (rateLimitResponse.ip_limit) {
          rateLimitConfig.ip_limit = rateLimitResponse.ip_limit[0]
          rateLimitConfig.ip_window = rateLimitResponse.ip_limit[1]
        }
        if (rateLimitResponse.user_limit) {
          rateLimitConfig.user_limit = rateLimitResponse.user_limit[0]
          rateLimitConfig.user_window = rateLimitResponse.user_limit[1]
        }
      }

      await loadStats()
      await loadFuseStates()
    } catch (error) {
      console.error('加载配置失败:', error)
      showMessage('加载配置失败', 'error')
    } finally {
      loading.value = false
    }
  }

  const loadStats = async () => {
    try {
      const [statsResponse, wsResponse, memoryResponse] = await Promise.all([
        api.get('/api/v2/admin/stats'),
        api.getWebSocketStats(),
        api.getMemoryStats()
      ])
      serverStats.value = statsResponse
      if (wsResponse) {
        wsStats.value = {
          current: wsResponse.current || 0,
          max: wsResponse.max || 50
        }
      }
      if (memoryResponse) {
        memoryStats.value = memoryResponse
      }
    } catch (error) {
      console.error('加载状态失败:', error)
    }
  }

  const saveConfig = async () => {
    saving.value = true
    saveMessage.value = ''

    try {
      const updateConfigs = {
        docker_max_memory: configs.docker_max_memory,
        docker_initial_memory: configs.docker_initial_memory,
        docker_image: configs.docker_image,
        docker_max_containers: String(configs.docker_max_containers),
        db_pool_size: String(configs.db_pool_size),
        db_max_overflow: String(configs.db_max_overflow),
        db_pool_timeout: String(configs.db_pool_timeout),
        log_retention_days: String(configs.log_retention_days),
        log_level: logConfig.log_level,
        log_to_file: logConfig.log_to_file ? 'true' : 'false'
      }

      await api.put('/api/v2/admin/config/batch', {
        configs: updateConfigs
      })

      for (const key of Object.keys(featureSwitches)) {
        const configKey = featureKeys[key]
        if (configs[configKey] !== featureSwitches[key].enabled) {
          await api.put(`/api/v2/admin/config/${configKey}`, {
            value: featureSwitches[key].enabled ? 'true' : 'false'
          })
        }
      }

      showMessage('配置保存成功', 'success')
    } catch (error) {
      console.error('保存配置失败:', error)
      showMessage('保存配置失败: ' + (error.message || '未知错误'), 'error')
    } finally {
      saving.value = false
    }
  }

  const handleFeatureToggle = (feature, enabled) => {
  }

  const getStatusClass = value => {
    if (value >= 90) return 'critical'
    if (value >= 70) return 'warning'
    return 'normal'
  }

  const formatBytes = bytes => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i]
  }

  const showMessage = (msg, type) => {
    saveMessage.value = msg
    saveMessageType.value = type
    setTimeout(() => {
      saveMessage.value = ''
    }, 3000)
  }

  const showBackupMessage = (msg, type) => {
    backupMessage.value = msg
    backupMessageType.value = type
    setTimeout(() => {
      backupMessage.value = ''
    }, 5000)
  }

  const createBackup = async () => {
    backingUp.value = true
    try {
      const result = await api.createBackup()
      if (result && result.status === 'success') {
        showBackupMessage(`备份创建成功: ${result.config_count} 项配置`, 'success')
        await loadBackupList()
      } else {
        showBackupMessage('备份创建失败', 'error')
      }
    } catch (error) {
      console.error('创建备份失败:', error)
      showBackupMessage('创建备份失败', 'error')
    } finally {
      backingUp.value = false
    }
  }

  const loadBackupList = async () => {
    try {
      const result = await api.listBackups()
      if (result && result.backups) {
        backups.value = result.backups
      }
    } catch (error) {
      console.error('加载备份列表失败:', error)
    }
  }

  const downloadBackupItem = async backup => {
    try {
      const timestamp = backup.filename.replace('config_backup_', '').replace('.json', '')
      const data = await api.downloadBackup(timestamp)
      if (data) {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = backup.filename
        a.click()
        URL.revokeObjectURL(url)
        showBackupMessage('备份下载成功', 'success')
      }
    } catch (error) {
      console.error('下载备份失败:', error)
      showBackupMessage('下载备份失败', 'error')
    }
  }

  const restoreBackupItem = backup => {
    restoreConfirmBackup.value = backup
  }

  const confirmRestore = async () => {
    if (!restoreConfirmBackup.value) return

    try {
      const timestamp = restoreConfirmBackup.value.filename
        .replace('config_backup_', '')
        .replace('.json', '')
      const data = await api.downloadBackup(timestamp)
      if (data) {
        const result = await api.restoreBackup(data)
        if (result && result.status === 'success') {
          showBackupMessage(`恢复成功: ${result.restored_count} 项配置`, 'success')
          await loadConfig()
        } else {
          showBackupMessage('恢复配置失败', 'error')
        }
      }
    } catch (error) {
      console.error('恢复备份失败:', error)
      showBackupMessage('恢复备份失败', 'error')
    } finally {
      restoreConfirmBackup.value = null
    }
  }

  const deleteBackupItem = async backup => {
    try {
      const result = await api.deleteBackup(backup.filename)
      if (result && result.status === 'success') {
        showBackupMessage('备份已删除', 'success')
        await loadBackupList()
      } else {
        showBackupMessage('删除备份失败', 'error')
      }
    } catch (error) {
      console.error('删除备份失败:', error)
      showBackupMessage('删除备份失败', 'error')
    }
  }

  const formatDate = dateStr => {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    return date.toLocaleString('zh-CN')
  }

  onMounted(() => {
    loadConfig()
  })
</script>

<style scoped>
  .resource-control {
    padding: 24px;
    max-width: 1200px;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 32px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border-color);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .header-left svg {
    color: var(--primary);
  }

  .header-left h2 {
    margin: 0;
    font-size: 24px;
    color: var(--text-primary);
  }

  .header-desc {
    margin: 4px 0 0;
    font-size: 14px;
    color: var(--text-tertiary);
  }

  .action-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 20px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .action-btn:hover {
    background: var(--border-color);
  }

  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px;
    gap: 16px;
    color: var(--text-tertiary);
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--border-color);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .config-content {
    display: flex;
    flex-direction: column;
    gap: 32px;
  }

  .config-section {
    background: var(--bg-primary);
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  .section-title {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0 0 20px;
    font-size: 18px;
    color: var(--text-primary);
  }

  .section-title svg {
    color: var(--primary);
  }

  .section-hint {
    font-size: 12px;
    color: var(--text-tertiary);
    font-weight: normal;
    margin-left: auto;
  }

  .config-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 20px;
  }

  .config-item {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .config-item label {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .input-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .config-input,
  .config-select {
    padding: 10px 14px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    font-size: 14px;
    transition: all 0.2s;
  }

  .config-input:focus,
  .config-select:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  .input-hint {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px;
  }

  .feature-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
    transition: all 0.2s;
  }

  .feature-item.disabled {
    background: var(--danger-100);
  }

  .feature-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .feature-name {
    font-weight: 600;
    color: var(--text-primary);
  }

  .feature-desc {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .switch {
    position: relative;
    width: 48px;
    height: 26px;
  }

  .switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .slider {
    position: absolute;
    cursor: pointer;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: var(--bg-tertiary);
    transition: 0.3s;
    border-radius: 26px;
  }

  .slider:before {
    position: absolute;
    content: '';
    height: 20px;
    width: 20px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: 0.3s;
    border-radius: 50%;
  }

  input:checked + .slider {
    background-color: var(--success);
  }

  input:checked + .slider:before {
    transform: translateX(22px);
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
  }

  .stat-card {
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
  }

  .stat-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  .stat-icon {
    font-size: 18px;
  }

  .stat-label {
    font-size: 14px;
    color: var(--text-tertiary);
  }

  .stat-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .stat-value.warning {
    color: var(--warning);
  }

  .stat-value.critical {
    color: var(--danger);
  }

  .stat-detail {
    font-size: 12px;
    color: var(--text-tertiary);
    margin-bottom: 8px;
  }

  .stat-bar {
    height: 6px;
    background: var(--border-color);
    border-radius: 3px;
    overflow: hidden;
  }

  .stat-fill {
    height: 100%;
    background: var(--success);
    transition: width 0.3s;
  }

  .stat-fill.warning {
    background: var(--warning);
  }

  .stat-fill.critical {
    background: var(--danger);
  }

  .config-tip {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 16px;
    padding: 12px 16px;
    background: var(--warning-bg);
    border-radius: 8px;
    font-size: 13px;
    color: #92400e;
  }

  .config-tip svg {
    flex-shrink: 0;
    color: var(--warning);
  }

  .action-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding-top: 16px;
    border-top: 1px solid var(--border-color);
  }

  .save-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 32px;
    background: var(--gradient-primary);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }

  .save-btn:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
  }

  .save-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .save-message {
    font-size: 14px;
  }

  .save-message.success {
    color: var(--success);
  }

  .save-message.error {
    color: var(--danger);
  }

  .spin {
    animation: spin 1s linear infinite;
  }

  .log-level-presets {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid var(--border-color);
  }

  .preset-label {
    font-size: 13px;
    color: var(--text-tertiary);
    font-weight: 500;
  }

  .preset-btn {
    padding: 6px 14px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-primary);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .preset-btn:hover {
    background: var(--bg-tertiary);
    border-color: var(--primary);
    color: var(--primary);
  }

  .memory-details {
    margin-top: 20px;
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
    border: 1px solid var(--border-color);
  }

  .memory-title {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 12px 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .refresh-btn-small {
    margin-left: auto;
    padding: 4px 8px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--bg-primary);
    cursor: pointer;
    display: flex;
    align-items: center;
  }

  .refresh-btn-small:hover {
    background: var(--bg-tertiary);
  }

  .memory-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
  }

  .memory-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .memory-label {
    font-size: 11px;
    color: var(--text-tertiary);
    text-transform: uppercase;
  }

  .memory-value {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .memory-value.warning {
    color: var(--warning);
  }

  .memory-value.critical {
    color: var(--danger);
  }

  .memory-advice {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border-color);
  }

  .advice-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--success);
  }

  .advice-item.warning {
    color: var(--warning);
  }

  .advice-item.critical {
    color: var(--danger);
  }

  .backup-actions {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
  }

  .backup-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 20px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-primary);
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .backup-btn:hover:not(:disabled) {
    background: var(--bg-tertiary);
    border-color: var(--primary);
  }

  .backup-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .backup-btn.primary {
    background: var(--gradient-primary);
    color: white;
    border: none;
  }

  .backup-btn.primary:hover:not(:disabled) {
    opacity: 0.9;
  }

  .backup-message {
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 14px;
    margin-bottom: 16px;
  }

  .backup-message.success {
    background: var(--success-bg);
    color: #065f46;
  }

  .backup-message.error {
    background: var(--danger-100);
    color: #991b1b;
  }

  .backup-list {
    background: var(--bg-secondary);
    border-radius: 8px;
    padding: 16px;
    margin-top: 16px;
  }

  .backup-list h4 {
    margin: 0 0 12px 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .backup-empty {
    text-align: center;
    padding: 20px;
    color: var(--text-tertiary);
    font-size: 14px;
  }

  .backup-items {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .backup-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px;
    background: var(--bg-primary);
    border-radius: 6px;
    border: 1px solid var(--border-color);
  }

  .backup-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .backup-name {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .backup-meta {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .backup-actions-item {
    display: flex;
    gap: 8px;
  }

  .action-btn-small {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-primary);
    cursor: pointer;
    transition: all 0.2s;
  }

  .action-btn-small:hover {
    background: var(--bg-tertiary);
    border-color: var(--primary);
  }

  .action-btn-small.danger:hover {
    background: var(--danger-100);
    border-color: var(--danger);
    color: var(--danger);
  }

  .restore-confirm {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .confirm-content {
    background: var(--bg-primary);
    padding: 24px;
    border-radius: 12px;
    max-width: 400px;
    text-align: center;
  }

  .confirm-content p {
    margin: 0 0 8px 0;
    font-size: 16px;
    color: var(--text-primary);
  }

  .confirm-warning {
    color: var(--danger-hover) !important;
    font-size: 14px !important;
  }

  .confirm-actions {
    display: flex;
    gap: 12px;
    justify-content: center;
    margin-top: 20px;
  }

  .confirm-btn {
    padding: 10px 24px;
    border-radius: 8px;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .confirm-btn.cancel {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
  }

  .confirm-btn.cancel:hover {
    background: var(--bg-tertiary);
  }

  .confirm-btn.restore {
    background: var(--danger);
    border: 1px solid var(--danger);
    color: white;
  }

  .confirm-btn.restore:hover {
    background: var(--danger-hover);
  }

  /* Rate Limit Config Styles */
  .rate-limit-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border-color);
  }

  .rate-limit-status {
    font-size: 14px;
    font-weight: 600;
    color: var(--success);
  }

  .config-btn {
    padding: 8px 16px;
    background: var(--primary);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .config-btn:hover {
    background: #5a67d8;
  }

  .config-input-small {
    width: 80px;
    padding: 10px 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 14px;
  }

  .config-input-small:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  .rate-limit-stats {
    margin-top: 20px;
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
    border: 1px solid var(--border-color);
  }

  .stats-title {
    margin: 0 0 12px 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .stats-row {
    display: flex;
    gap: 24px;
  }

  .stat-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .stat-item .stat-label {
    font-size: 11px;
    color: var(--text-tertiary);
    text-transform: uppercase;
  }

  .stat-item .stat-value {
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .stat-item .stat-value.warning {
    color: var(--warning);
  }

  /* Fuse Status Styles */
  .fuse-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .fuse-item {
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
    border: 1px solid var(--border-color);
  }

  .fuse-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }

  .fuse-name {
    font-weight: 600;
    color: var(--text-primary);
    font-size: 15px;
  }

  .fuse-badge {
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
  }

  .fuse-badge.normal {
    background: var(--success-bg);
    color: #065f46;
  }

  .fuse-badge.warning {
    background: var(--warning-bg);
    color: #92400e;
  }

  .fuse-badge.critical {
    background: var(--danger-100);
    color: #991b1b;
  }

  .fuse-details {
    display: flex;
    gap: 24px;
  }

  .fuse-detail {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .detail-label {
    font-size: 11px;
    color: var(--text-tertiary);
    text-transform: uppercase;
  }

  .detail-value {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .fuse-empty {
    text-align: center;
    padding: 32px;
    color: var(--text-tertiary);
  }

  .fuse-empty p {
    margin: 0 0 12px 0;
  }

  .refresh-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-primary);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .refresh-btn:hover {
    background: var(--bg-tertiary);
    border-color: var(--primary);
    color: var(--primary);
  }
</style>
