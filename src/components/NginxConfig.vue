<template>
  <div v-if="visible" class="nginx-config-overlay" @click.self="$emit('close')">
    <div class="nginx-config-modal">
      <div class="modal-header">
        <h2>Nginx 配置工具</h2>
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
        <!-- 平台选择 -->
        <div class="platform-selector">
          <h3>选择平台</h3>
          <div class="platform-radio-group">
            <label class="radio-label">
              <input v-model="currentPlatform" type="radio" value="linux" name="platform" />
              <span class="radio-custom"></span>
              <span>Linux</span>
            </label>
            <label class="radio-label">
              <input v-model="currentPlatform" type="radio" value="windows" name="platform" />
              <span class="radio-custom"></span>
              <span>Windows</span>
            </label>
          </div>
        </div>

        <!-- API 验证结果区域 -->
        <div v-if="apiValidationResult" class="api-validation-result">
          <div class="validation-header" :class="apiValidationStatus">
            <span class="status-icon">{{ apiValidationStatus === 'success' ? '✓' : '✗' }}</span>
            <span class="status-title">{{
              apiValidationStatus === 'success' ? '配置验证通过' : '配置验证失败'
            }}</span>
            <button class="close-validation-btn" @click="apiValidationResult = false">×</button>
          </div>
          <div class="validation-content">
            <div v-if="apiValidationOutput" class="validation-output">
              <pre>{{ apiValidationOutput }}</pre>
            </div>
            <div
              v-if="apiValidationSuggestions && apiValidationSuggestions.length > 0"
              class="validation-suggestions"
            >
              <h4>修复建议：</h4>
              <ul>
                <li v-for="(suggestion, index) in apiValidationSuggestions" :key="index">
                  {{ suggestion }}
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- 配置类型选择 -->
        <div class="config-type-selector">
          <h3>配置类型</h3>
          <div class="type-buttons">
            <button
              v-for="type in configTypes"
              :key="type.id"
              :class="{ active: currentType === type.id }"
              @click="selectConfigType(type.id)"
            >
              {{ type.name }}
            </button>
          </div>
        </div>

        <!-- Nginx 安装目录 -->
        <div class="nginx-path-selector">
          <h3>Nginx 安装目录</h3>
          <div class="path-input-group">
            <input
              v-model="nginxInstallPath"
              type="text"
              :placeholder="currentPlatform === 'windows' ? 'C:/nginx' : '/etc/nginx'"
              class="path-input"
            />
            <button class="path-hint-btn" @click="fillDefaultPath">
              <span class="icon">🔄</span>
              使用默认值
            </button>
          </div>
          <div class="path-description">
            <span class="icon">[INFO]</span>
            <span class="text">
              您的 Nginx 安装目录路径。配置文件（如 mime.types）将从此目录加载。
              <code v-if="currentPlatform === 'windows'">默认: C:/nginx</code>
              <code v-else>默认: /etc/nginx</code>
            </span>
          </div>
        </div>

        <!-- 配置折叠面板 -->
        <div class="accordion-section">
          <!-- 基本配置 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('basic')">
              <h3>基本配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.basic }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.basic }">
              <div class="config-form">
                <div class="form-group">
                  <label>服务器名称 (Server Name)</label>
                  <input
                    v-model="formData.serverName"
                    type="text"
                    placeholder="example.com www.example.com"
                  />
                  <small class="help-text">多个域名用空格分隔</small>
                </div>

                <div class="form-group">
                  <label>监听端口 (Port)</label>
                  <input v-model="formData.port" type="number" placeholder="80 / 443" />
                </div>

                <div v-if="currentType === 'https'" class="form-group">
                  <label>SSL 证书路径</label>
                  <input
                    v-model="formData.sslCert"
                    type="text"
                    placeholder="/etc/nginx/ssl/cert.pem"
                  />
                </div>

                <div v-if="currentType === 'https'" class="form-group">
                  <label>SSL 私钥路径</label>
                  <input
                    v-model="formData.sslKey"
                    type="text"
                    placeholder="/etc/nginx/ssl/key.pem"
                  />
                </div>

                <div class="form-group">
                  <label>代理目标 (Upstream)</label>
                  <input
                    v-model="formData.upstream"
                    type="text"
                    placeholder="http://localhost:3000"
                  />
                  <small class="help-text">负载均衡类型留空使用后端服务器列表</small>
                </div>

                <div v-if="currentType === 'loadbalancer'" class="form-group">
                  <label>后端服务器 (多个服务器用逗号分隔)</label>
                  <input
                    v-model="formData.servers"
                    type="text"
                    placeholder="localhost:3001,localhost:3002,localhost:3003"
                  />
                </div>
              </div>
            </div>
          </div>

          <!-- Worker 进程配置 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('worker')">
              <h3>Worker 进程配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.worker }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.worker }">
              <div class="config-form">
                <div class="form-group">
                  <label>Worker 进程数</label>
                  <select v-model="formData.workerProcesses">
                    <option value="auto">auto（自动）</option>
                    <option value="1">1</option>
                    <option value="2">2</option>
                    <option value="4">4</option>
                    <option value="8">8</option>
                  </select>
                  <small class="help-text">通常设置为 CPU 核心数</small>
                </div>

                <div class="form-group">
                  <label>Worker 连接数</label>
                  <input v-model="formData.workerConnections" type="number" placeholder="1024" />
                  <small class="help-text">每个 worker 进程的最大连接数</small>
                </div>

                <div class="form-group">
                  <label>Worker Rlimit 数量</label>
                  <input v-model="formData.workerRlimitNofile" type="number" placeholder="65535" />
                  <small class="help-text">最大文件描述符数量</small>
                </div>
              </div>
            </div>
          </div>

          <!-- 日志配置 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('logging')">
              <h3>日志配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.logging }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.logging }">
              <div class="config-form">
                <div class="form-group">
                  <label>访问日志路径</label>
                  <input
                    v-model="formData.accessLog"
                    type="text"
                    placeholder="/var/log/nginx/access.log"
                  />
                </div>

                <div class="form-group">
                  <label>访问日志格式</label>
                  <select v-model="formData.accessLogFormat">
                    <option value="combined">combined（标准格式）</option>
                    <option value="main">main（简化格式）</option>
                    <option value="json">json（JSON 格式）</option>
                    <option value="custom">custom（自定义格式）</option>
                  </select>
                </div>

                <div class="form-group">
                  <label>错误日志路径</label>
                  <input
                    v-model="formData.errorLog"
                    type="text"
                    placeholder="/var/log/nginx/error.log"
                  />
                </div>

                <div class="form-group">
                  <label>错误日志级别</label>
                  <select v-model="formData.errorLogLevel">
                    <option value="debug">debug（调试）</option>
                    <option value="info">info（信息）</option>
                    <option value="notice">notice（通知）</option>
                    <option value="warn">warn（警告）</option>
                    <option value="error">error（错误）</option>
                    <option value="crit">crit（严重）</option>
                    <option value="alert">alert（警报）</option>
                    <option value="emerg">emerg（紧急）</option>
                  </select>
                </div>

                <div class="checkbox-group">
                  <label>
                    <input v-model="formData.logNotFound" type="checkbox" />
                    记录未找到的请求 (log_not_found)
                  </label>
                </div>
              </div>
            </div>
          </div>

          <!-- 超时配置 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('timeout')">
              <h3>超时配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.timeout }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.timeout }">
              <div class="config-form">
                <div class="form-group">
                  <label>保持连接超时 (秒)</label>
                  <input v-model="formData.keepaliveTimeout" type="number" placeholder="65" />
                  <small class="help-text">保持连接的时间</small>
                </div>

                <div class="form-group">
                  <label>Client Body 超时 (秒)</label>
                  <input v-model="formData.clientBodyTimeout" type="number" placeholder="60" />
                  <small class="help-text">读取请求体超时时间</small>
                </div>

                <div class="form-group">
                  <label>Client Header 超时 (秒)</label>
                  <input v-model="formData.clientHeaderTimeout" type="number" placeholder="60" />
                  <small class="help-text">读取请求头超时时间</small>
                </div>

                <div class="form-group">
                  <label>发送超时 (秒)</label>
                  <input v-model="formData.sendTimeout" type="number" placeholder="60" />
                  <small class="help-text">响应发送超时时间</small>
                </div>

                <div class="form-group">
                  <label>Client Header Buffer 大小 (KB)</label>
                  <input v-model="formData.clientHeaderBufferSize" type="number" placeholder="1" />
                  <small class="help-text">请求头缓冲区大小</small>
                </div>

                <div class="form-group">
                  <label>大 Client Header Buffer 数</label>
                  <input
                    v-model="formData.largeClientHeaderBuffersNum"
                    type="number"
                    placeholder="4"
                  />
                </div>

                <div class="form-group">
                  <label>大 Client Header Buffer 大小 (KB)</label>
                  <input
                    v-model="formData.largeClientHeaderBuffersSize"
                    type="number"
                    placeholder="8"
                  />
                </div>
              </div>
            </div>
          </div>

          <!-- 性能优化 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('performance')">
              <h3>性能优化</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.performance }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.performance }">
              <div class="checkbox-group">
                <label>
                  <input v-model="formData.sendfile" type="checkbox" />
                  启用 Sendfile（零拷贝传输）
                </label>
                <label>
                  <input v-model="formData.tcpNopush" type="checkbox" />
                  启用 TCP_NOPUSH
                </label>
                <label>
                  <input v-model="formData.tcpNodelay" type="checkbox" />
                  启用 TCP_NODELAY
                </label>
                <label>
                  <input v-model="formData.resetTimedoutConnection" type="checkbox" />
                  超时后重置连接
                </label>
              </div>

              <div class="form-group" style="margin-top: 15px">
                <label>重试等待时间 (毫秒)</label>
                <input
                  v-model="formData.resetDelayedConnectionTimeout"
                  type="number"
                  placeholder="0"
                />
              </div>

              <div class="form-group">
                <label>Output Buffer 数量</label>
                <input v-model="formData.outputBuffersNum" type="number" placeholder="1" />
              </div>

              <div class="form-group">
                <label>Output Buffer 大小 (KB)</label>
                <input v-model="formData.outputBufferSize" type="number" placeholder="32" />
              </div>

              <div class="form-group">
                <label>多重读取次数</label>
                <input v-model="formData.multiAccept" type="number" placeholder="off" />
                <small class="help-text">设置为 on 或 off</small>
              </div>

              <div class="form-group">
                <label>使用 epoll（仅 Linux）</label>
                <select v-model="formData.useEpoll" :disabled="currentPlatform !== 'linux'">
                  <option value="off">off</option>
                  <option value="on">on</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Gzip 压缩配置 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('gzip')">
              <h3>Gzip 压缩配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.gzip }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.gzip }">
              <div class="checkbox-group">
                <label>
                  <input v-model="formData.gzipEnabled" type="checkbox" />
                  启用 Gzip 压缩
                </label>
                <label>
                  <input v-model="formData.gzipVary" type="checkbox" />
                  添加 Vary 响应头
                </label>
                <label>
                  <input v-model="formData.gzipDisableMsis6" type="checkbox" />
                  禁用 IE6 压缩
                </label>
              </div>

              <div class="form-group" style="margin-top: 15px">
                <label>Gzip 压缩级别 (1-9)</label>
                <input v-model="formData.gzipLevel" type="number" min="1" max="9" placeholder="6" />
                <small class="help-text">级别越高压缩率越高但消耗更多 CPU</small>
              </div>

              <div class="form-group">
                <label>最小压缩文件大小 (字节)</label>
                <input v-model="formData.gzipMinLength" type="number" placeholder="1024" />
                <small class="help-text">小于此值的文件不压缩</small>
              </div>

              <div class="form-group">
                <label>压缩缓冲区 (数量)</label>
                <input v-model="formData.gzipBuffersNum" type="number" placeholder="16" />
              </div>

              <div class="form-group">
                <label>压缩缓冲区 (大小 KB)</label>
                <input v-model="formData.gzipBuffersSize" type="number" placeholder="8" />
              </div>

              <div class="form-group">
                <label>压缩 HTTP 版本</label>
                <select v-model="formData.gzipHttpVersion">
                  <option value="1.0">HTTP/1.0</option>
                  <option value="1.1">HTTP/1.1</option>
                </select>
              </div>

              <div class="form-group">
                <label>压缩类型</label>
                <input
                  v-model="formData.gzipTypes"
                  type="text"
                  placeholder="text/plain text/css application/json"
                  class="wide-input"
                />
                <small class="help-text">用空格分隔多个 MIME 类型</small>
              </div>
            </div>
          </div>

          <!-- 代理配置 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('proxy')">
              <h3>代理配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.proxy }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.proxy }">
              <div class="form-group">
                <label>代理连接超时 (秒)</label>
                <input v-model="formData.proxyConnectTimeout" type="number" placeholder="60" />
              </div>

              <div class="form-group">
                <label>代理发送超时 (秒)</label>
                <input v-model="formData.proxySendTimeout" type="number" placeholder="60" />
              </div>

              <div class="form-group">
                <label>代理读取超时 (秒)</label>
                <input v-model="formData.proxyReadTimeout" type="number" placeholder="60" />
              </div>

              <div class="form-group">
                <label>代理缓冲大小 (KB)</label>
                <input v-model="formData.proxyBufferSize" type="number" placeholder="4" />
              </div>

              <div class="form-group">
                <label>代理缓冲数量</label>
                <input v-model="formData.proxyBuffersNum" type="number" placeholder="8" />
              </div>

              <div class="form-group">
                <label>代理缓冲每个大小 (KB)</label>
                <input v-model="formData.proxyBuffersSize" type="number" placeholder="4" />
              </div>

              <div class="checkbox-group" style="margin-top: 15px">
                <label>
                  <input v-model="formData.proxyRedirect" type="checkbox" />
                  自动重定向
                </label>
                <label>
                  <input v-model="formData.proxyInterceptErrors" type="checkbox" />
                  拦截错误
                </label>
              </div>

              <div class="form-group" style="margin-top: 15px">
                <label>代理最大临时文件大小 (MB)</label>
                <input v-model="formData.proxyMaxTempFileSize" type="number" placeholder="1024" />
              </div>
            </div>
          </div>

          <!-- SSL/TLS 配置 -->
          <div v-if="currentType === 'https'" class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('ssl')">
              <h3>SSL/TLS 配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.ssl }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.ssl }">
              <div class="form-group">
                <label>SSL 协议版本</label>
                <input
                  v-model="formData.sslProtocols"
                  type="text"
                  placeholder="TLSv1.2 TLSv1.3"
                  class="wide-input"
                />
                <small class="help-text">建议使用 TLSv1.2 和 TLSv1.3</small>
              </div>

              <div class="form-group">
                <label>SSL 加密套件</label>
                <input
                  v-model="formData.sslCiphers"
                  type="text"
                  placeholder="HIGH:!aNULL:!MD5"
                  class="wide-input"
                />
              </div>

              <div class="form-group">
                <label>SSL 会话缓存 (MB)</label>
                <input v-model="formData.sslSessionCacheSize" type="number" placeholder="10" />
              </div>

              <div class="form-group">
                <label>SSL 会话超时 (分钟)</label>
                <input v-model="formData.sslSessionTimeout" type="number" placeholder="10" />
              </div>

              <div class="checkbox-group" style="margin-top: 15px">
                <label>
                  <input v-model="formData.sslPreferServerCiphers" type="checkbox" />
                  优先使用服务器加密套件
                </label>
                <label>
                  <input v-model="formData.sslSessionTickets" type="checkbox" />
                  启用 Session Tickets
                </label>
              </div>

              <div class="form-group" style="margin-top: 15px">
                <label>OCSP Stapling URL</label>
                <input v-model="formData.sslStapling" type="text" placeholder="on" />
              </div>

              <div class="form-group">
                <label>HSTS 最大时间（天）</label>
                <input v-model="formData.hstsMaxAge" type="number" placeholder="31536000" />
                <small class="help-text">设置为 0 禁用 HSTS</small>
              </div>

              <div class="checkbox-group" style="margin-top: 15px">
                <label>
                  <input v-model="formData.hstsIncludeSubdomains" type="checkbox" />
                  HSTS 包含子域名
                </label>
                <label>
                  <input v-model="formData.hstsPreload" type="checkbox" />
                  HSTS 预加载
                </label>
              </div>
            </div>
          </div>

          <!-- 缓存配置 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('cache')">
              <h3>缓存配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.cache }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.cache }">
              <div class="checkbox-group">
                <label>
                  <input v-model="formData.cacheEnabled" type="checkbox" />
                  启用静态资源缓存
                </label>
                <label v-if="currentType !== 'static'">
                  <input v-model="formData.enableProxyCache" type="checkbox" />
                  启用代理缓存
                </label>
              </div>

              <div v-if="formData.cacheEnabled" style="margin-top: 15px">
                <div class="form-group">
                  <label>静态缓存时间（天）</label>
                  <input v-model="formData.staticCacheTime" type="number" placeholder="30" />
                </div>

                <div class="form-group">
                  <label>缓存的文件扩展名</label>
                  <input
                    v-model="formData.cacheExtensions"
                    type="text"
                    placeholder="jpg,jpeg,png,gif,ico,css,js,svg,woff,woff2,ttf,eot"
                    class="wide-input"
                  />
                  <small class="help-text">用逗号分隔</small>
                </div>
              </div>

              <div
                v-if="formData.enableProxyCache && currentType !== 'static'"
                style="margin-top: 15px"
              >
                <div class="form-group">
                  <label>代理缓存路径</label>
                  <input
                    v-model="formData.proxyCachePath"
                    type="text"
                    placeholder="/var/cache/nginx/proxy_cache"
                  />
                </div>

                <div class="form-group">
                  <label>代理缓存目录层级</label>
                  <input v-model="formData.proxyCacheLevels" type="text" placeholder="1:2" />
                </div>

                <div class="form-group">
                  <label>代理缓存名称</label>
                  <input
                    v-model="formData.proxyCacheZone"
                    type="text"
                    placeholder="proxy_cache_zone"
                  />
                </div>

                <div class="form-group">
                  <label>代理缓存大小 (MB)</label>
                  <input v-model="formData.proxyCacheSize" type="number" placeholder="100" />
                </div>

                <div class="form-group">
                  <label>代理缓存非活动时间（分钟）</label>
                  <input v-model="formData.proxyCacheInactive" type="number" placeholder="60" />
                </div>

                <div class="form-group">
                  <label>代理缓存使用情况最大占用 (%)</label>
                  <input v-model="formData.proxyCacheMaxSize" type="number" placeholder="80" />
                </div>
              </div>
            </div>
          </div>

          <!-- 限流配置 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('ratelimit')">
              <h3>限流配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.ratelimit }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.ratelimit }">
              <div v-if="currentPlatform === 'windows'" class="platform-warning">
                <span class="warning-icon">[WARN]</span>
                <span>Windows 版 Nginx 不支持限流功能</span>
              </div>

              <div v-else>
                <div class="checkbox-group">
                  <label>
                    <input v-model="formData.rateLimitEnabled" type="checkbox" />
                    启用请求限流
                  </label>
                </div>

                <div v-if="formData.rateLimitEnabled" style="margin-top: 15px">
                  <div class="form-group">
                    <label>限流区域名称</label>
                    <input v-model="formData.rateLimitZone" type="text" placeholder="one" />
                  </div>

                  <div class="form-group">
                    <label>限流速率 (请求数/秒)</label>
                    <input v-model="formData.rateLimitRate" type="number" placeholder="10" />
                  </div>

                  <div class="form-group">
                    <label>限流键</label>
                    <select v-model="formData.rateLimitKey">
                      <option value="$binary_remote_addr">客户端 IP 地址</option>
                      <option value="$remote_addr">客户端 IP 地址（文本）</option>
                      <option value="$server_name">服务器名称</option>
                      <option value="$request_uri">请求 URI</option>
                    </select>
                  </div>

                  <div class="form-group">
                    <label>突发大小</label>
                    <input v-model="formData.rateLimitBurst" type="number" placeholder="20" />
                    <small class="help-text">允许的突发请求数</small>
                  </div>

                  <div class="form-group">
                    <label>限流区域大小 (MB)</label>
                    <input v-model="formData.rateLimitZoneSize" type="number" placeholder="10" />
                  </div>
                </div>
              </div>

              <div class="checkbox-group" style="margin-top: 15px">
                <label>
                  <input v-model="formData.limitConnEnabled" type="checkbox" />
                  启用连接数限制
                </label>
              </div>

              <div v-if="formData.limitConnEnabled" style="margin-top: 15px">
                <div class="form-group">
                  <label>最大连接数</label>
                  <input v-model="formData.limitConnNum" type="number" placeholder="10" />
                </div>

                <div class="form-group">
                  <label>连接限流区域名称</label>
                  <input v-model="formData.limitConnZone" type="text" placeholder="addr" />
                </div>
              </div>
            </div>
          </div>

          <!-- CORS 配置 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('cors')">
              <h3>CORS 跨域配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.cors }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.cors }">
              <div class="checkbox-group">
                <label>
                  <input v-model="formData.corsEnabled" type="checkbox" />
                  启用 CORS 跨域支持
                </label>
              </div>

              <div v-if="formData.corsEnabled" style="margin-top: 15px">
                <div class="form-group">
                  <label>允许的源 (Access-Control-Allow-Origin)</label>
                  <input v-model="formData.corsOrigin" type="text" placeholder="*" />
                  <small class="help-text">使用 * 允许所有源，或指定多个源</small>
                </div>

                <div class="form-group">
                  <label>允许的方法 (Access-Control-Allow-Methods)</label>
                  <input
                    v-model="formData.corsMethods"
                    type="text"
                    placeholder="GET, POST, PUT, DELETE, OPTIONS"
                    class="wide-input"
                  />
                </div>

                <div class="form-group">
                  <label>允许的请求头 (Access-Control-Allow-Headers)</label>
                  <input
                    v-model="formData.corsHeaders"
                    type="text"
                    placeholder="DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization"
                    class="wide-input"
                  />
                </div>

                <div class="form-group">
                  <label>暴露的响应头 (Access-Control-Expose-Headers)</label>
                  <input
                    v-model="formData.corsExposeHeaders"
                    type="text"
                    placeholder="Content-Length,Content-Range"
                    class="wide-input"
                  />
                </div>

                <div class="form-group">
                  <label>预检请求缓存时间（秒）</label>
                  <input v-model="formData.corsMaxAge" type="number" placeholder="86400" />
                </div>

                <div class="checkbox-group">
                  <label>
                    <input v-model="formData.corsAllowCredentials" type="checkbox" />
                    允许凭证 (Allow-Credentials)
                  </label>
                </div>
              </div>
            </div>
          </div>

          <!-- 安全头配置 -->
          <div class="accordion-item">
            <div class="accordion-header" @click="toggleAccordion('security')">
              <h3>安全头配置</h3>
              <span class="accordion-icon" :class="{ expanded: accordions.security }">▼</span>
            </div>
            <div class="accordion-content" :class="{ expanded: accordions.security }">
              <div class="checkbox-group">
                <label>
                  <input v-model="formData.securityHeaders" type="checkbox" />
                  启用安全头
                </label>
              </div>

              <div v-if="formData.securityHeaders" style="margin-top: 15px">
                <div class="form-group">
                  <label>X-Frame-Options</label>
                  <select v-model="formData.xFrameOptions">
                    <option value="SAMEORIGIN">SAMEORIGIN</option>
                    <option value="DENY">DENY</option>
                    <option value="ALLOW-FROM">ALLOW-FROM</option>
                  </select>
                </div>

                <div v-if="formData.xFrameOptions === 'ALLOW-FROM'" class="form-group">
                  <label>X-Frame-Options 允许的源</label>
                  <input
                    v-model="formData.xFrameAllowFrom"
                    type="text"
                    placeholder="https://example.com"
                  />
                </div>

                <div class="form-group">
                  <label>X-Content-Type-Options</label>
                  <select v-model="formData.xContentTypeOptions">
                    <option value="nosniff">nosniff</option>
                    <option value="">禁用</option>
                  </select>
                </div>

                <div class="form-group">
                  <label>X-XSS-Protection</label>
                  <select v-model="formData.xXssProtection">
                    <option value="1; mode=block">1; mode=block</option>
                    <option value="1">1</option>
                    <option value="0">0（禁用）</option>
                  </select>
                </div>

                <div class="form-group">
                  <label>Content-Security-Policy</label>
                  <input
                    v-model="formData.contentSecurityPolicy"
                    type="text"
                    placeholder="default-src 'self'"
                    class="wide-input"
                  />
                </div>

                <div class="form-group">
                  <label>Referrer-Policy</label>
                  <select v-model="formData.referrerPolicy">
                    <option value="strict-origin-when-cross-origin">
                      strict-origin-when-cross-origin
                    </option>
                    <option value="no-referrer">no-referrer</option>
                    <option value="no-referrer-when-downgrade">no-referrer-when-downgrade</option>
                    <option value="origin">origin</option>
                    <option value="origin-when-cross-origin">origin-when-cross-origin</option>
                    <option value="same-origin">same-origin</option>
                    <option value="strict-origin">strict-origin</option>
                    <option value="unsafe-url">unsafe-url</option>
                  </select>
                </div>

                <div class="form-group">
                  <label>Permissions-Policy</label>
                  <input
                    v-model="formData.permissionsPolicy"
                    type="text"
                    placeholder="geolocation=(), microphone=(), camera=()"
                    class="wide-input"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 配置预览 -->
        <div class="config-preview">
          <div class="preview-header">
            <h3>配置预览</h3>
            <div class="preview-actions">
              <button class="action-btn" @click="copyConfig"><span>[LIST]</span> Copy</button>
              <button class="action-btn" @click="downloadConfig">
                <span>[SAVE]</span> Download
              </button>
              <button class="action-btn" @click="validateConfig"><span>✓</span> 本地验证</button>
              <button
                class="action-btn api-validate-btn"
                :disabled="isApiValidating"
                @click="validateWithApi"
              >
                <span>{{ isApiValidating ? '[LOADING]' : '[FIND]' }}</span>
                {{ isApiValidating ? 'API 验证中...' : 'API 验证' }}
              </button>
            </div>
          </div>
          <pre class="config-content">{{ generatedConfig }}</pre>
          <div v-if="validationMessage" :class="['validation-message', validationStatus]">
            {{ validationMessage }}
          </div>
        </div>
      </div>

      <!-- 配置模板 -->
      <div class="templates-section">
        <h3>常用模板</h3>
        <div class="template-category">
          <h4>前端应用</h4>
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
          <h4>后端应用</h4>
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
          <h4>CMS 系统</h4>
          <div class="template-buttons">
            <button
              v-for="template in cmsTemplates"
              :key="template.id"
              @click="applyTemplate(template)"
            >
              {{ template.name }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 隐藏的文件输入，用于导入配置 -->
    <input
      ref="fileInput"
      type="file"
      accept=".conf,.json"
      style="display: none"
      @change="handleFileImport"
    />
  </div>
</template>

<script setup>
  import { ref, computed, watch } from 'vue'
  import { api } from '@/utils/api/index'

  const API_BASE_URL = import.meta.env.VITE_API_BASE || '/api/v1'

  const props = defineProps({
    visible: {
      type: Boolean,
      default: false
    }
  })

  const emit = defineEmits(['close'])

  const currentType = ref('basic')
  const validationMessage = ref('')
  const validationStatus = ref('')
  const isApiValidating = ref(false)
  const apiValidationResult = ref(false)
  const apiValidationStatus = ref('')
  const apiValidationOutput = ref('')
  const apiValidationSuggestions = ref([])
  const fileInput = ref(null)

  // 折叠面板状态
  const accordions = ref({
    basic: true,
    worker: false,
    logging: false,
    timeout: false,
    performance: false,
    gzip: false,
    proxy: false,
    ssl: false,
    cache: false,
    ratelimit: false,
    cors: false,
    security: false
  })

  // 切换折叠面板
  const toggleAccordion = key => {
    accordions.value[key] = !accordions.value[key]
  }

  // 折叠所有面板
  const collapseAll = () => {
    Object.keys(accordions.value).forEach(key => {
      accordions.value[key] = false
    })
  }

  // 展开所有面板
  const expandAll = () => {
    Object.keys(accordions.value).forEach(key => {
      accordions.value[key] = true
    })
  }

  // 填充默认路径
  const fillDefaultPath = () => {
    if (currentPlatform.value === 'windows') {
      nginxInstallPath.value = 'C:/nginx'
    } else {
      nginxInstallPath.value = '/etc/nginx'
    }
  }

  // 设置平台
  const setPlatform = platform => {
    currentPlatform.value = platform
    nginxInstallPath.value = platform === 'windows' ? 'C:/nginx' : '/etc/nginx'

    if (platform === 'windows') {
      formData.value.accessLog = 'C:/nginx/logs/access.log'
      formData.value.errorLog = 'C:/nginx/logs/error.log'
      if (formData.value.sslCert && formData.value.sslCert.includes('/etc/')) {
        formData.value.sslCert = formData.value.sslCert.replace('/etc/nginx/ssl/', 'C:/nginx/ssl/')
        formData.value.sslKey = formData.value.sslKey.replace('/etc/nginx/ssl/', 'C:/nginx/ssl/')
      }
      if (formData.value.proxyCachePath && formData.value.proxyCachePath.includes('/var/')) {
        formData.value.proxyCachePath = formData.value.proxyCachePath.replace(
          '/var/cache/nginx/',
          'C:/nginx/cache/'
        )
      }
    } else {
      formData.value.accessLog = '/var/log/nginx/access.log'
      formData.value.errorLog = '/var/log/nginx/error.log'
      if (formData.value.sslCert && formData.value.sslCert.includes('C:/nginx/')) {
        formData.value.sslCert = formData.value.sslCert.replace('C:/nginx/ssl/', '/etc/nginx/ssl/')
        formData.value.sslKey = formData.value.sslKey.replace('C:/nginx/ssl/', '/etc/nginx/ssl/')
      }
      if (formData.value.proxyCachePath && formData.value.proxyCachePath.includes('C:/nginx/')) {
        formData.value.proxyCachePath = formData.value.proxyCachePath.replace(
          'C:/nginx/cache/',
          '/var/cache/nginx/'
        )
      }
    }
  }

  // 暴露方法给父组件
  defineExpose({
    setPlatform
  })

  const configTypes = [
    { id: 'basic', name: '基础反向代理' },
    { id: 'https', name: 'HTTPS 配置' },
    { id: 'loadbalancer', name: '负载均衡' },
    { id: 'static', name: '静态文件服务器' }
  ]

  // 前端应用模板
  const frontendTemplates = [
    {
      id: 'react',
      name: 'React/Vue 应用',
      type: 'static',
      data: { upstream: '', staticCacheTime: 30 }
    },
    {
      id: 'angular',
      name: 'Angular 应用',
      type: 'static',
      data: { upstream: '', staticCacheTime: 30 }
    }
  ]

  // 后端应用模板
  const backendTemplates = [
    {
      id: 'nodejs',
      name: 'Node.js 应用',
      type: 'basic',
      data: { port: 80, upstream: 'http://localhost:3000', gzipEnabled: true }
    },
    {
      id: 'django',
      name: 'Django 应用',
      type: 'basic',
      data: { port: 80, upstream: 'http://localhost:8080', gzipEnabled: true }
    },
    {
      id: 'flask',
      name: 'Flask 应用',
      type: 'basic',
      data: { port: 80, upstream: 'http://localhost:5000', gzipEnabled: true }
    },
    {
      id: 'fastapi',
      name: 'FastAPI 应用',
      type: 'basic',
      data: { port: 80, upstream: 'http://localhost:8080', gzipEnabled: true, cacheEnabled: true }
    },
    {
      id: 'golang',
      name: 'Go 应用',
      type: 'basic',
      data: { port: 80, upstream: 'http://localhost:8080', gzipEnabled: true }
    },
    {
      id: 'springboot',
      name: 'Spring Boot 应用',
      type: 'basic',
      data: { port: 80, upstream: 'http://localhost:8080', gzipEnabled: true }
    },
    {
      id: 'dotnetcore',
      name: 'ASP.NET Core 应用',
      type: 'basic',
      data: { port: 80, upstream: 'http://localhost:5000', gzipEnabled: true }
    }
  ]

  // CMS 系统模板
  const cmsTemplates = [
    {
      id: 'wordpress',
      name: 'WordPress',
      type: 'https',
      data: { port: 443, upstream: 'http://localhost:8080', gzipEnabled: true, cacheEnabled: true }
    },
    {
      id: 'joomla',
      name: 'Joomla',
      type: 'https',
      data: { port: 443, upstream: 'http://localhost:8080', gzipEnabled: true, cacheEnabled: true }
    },
    {
      id: 'drupal',
      name: 'Drupal',
      type: 'https',
      data: { port: 443, upstream: 'http://localhost:8080', gzipEnabled: true, cacheEnabled: true }
    }
  ]

  const formData = ref({
    // 基本配置
    serverName: '',
    port: 80,
    sslCert: '',
    sslKey: '',
    upstream: '',
    servers: '',

    // Worker 进程配置
    workerProcesses: 'auto',
    workerConnections: 1024,
    workerRlimitNofile: 65535,

    // 日志配置
    accessLog: '/var/log/nginx/access.log',
    accessLogFormat: 'combined',
    errorLog: '/var/log/nginx/error.log',
    errorLogLevel: 'warn',
    logNotFound: false,

    // 超时配置
    keepaliveTimeout: 65,
    clientBodyTimeout: 60,
    clientHeaderTimeout: 60,
    sendTimeout: 60,
    clientHeaderBufferSize: 1,
    largeClientHeaderBuffersNum: 4,
    largeClientHeaderBuffersSize: 8,

    // 性能优化
    sendfile: true,
    tcpNopush: true,
    tcpNodelay: true,
    resetTimedoutConnection: true,
    resetDelayedConnectionTimeout: 0,
    outputBuffersNum: 1,
    outputBufferSize: 32,
    multiAccept: 'off',
    useEpoll: 'on',

    // Gzip 配置
    gzipEnabled: true,
    gzipVary: true,
    gzipDisableMsis6: true,
    gzipLevel: 6,
    gzipMinLength: 1024,
    gzipBuffersNum: 16,
    gzipBuffersSize: 8,
    gzipHttpVersion: '1.1',
    gzipTypes:
      'text/plain text/css text/xml text/javascript application/x-javascript application/javascript application/json application/xml application/xml+rss application/rss+xml font/truetype font/opentype application/vnd.ms-fontobject image/svg+xml',

    // 代理配置
    proxyConnectTimeout: 60,
    proxySendTimeout: 60,
    proxyReadTimeout: 60,
    proxyBufferSize: 4,
    proxyBuffersNum: 8,
    proxyBuffersSize: 4,
    proxyRedirect: true,
    proxyInterceptErrors: false,
    proxyMaxTempFileSize: 1024,

    // SSL 配置
    sslProtocols: 'TLSv1.2 TLSv1.3',
    sslCiphers: 'HIGH:!aNULL:!MD5',
    sslSessionCacheSize: 10,
    sslSessionTimeout: 10,
    sslPreferServerCiphers: true,
    sslSessionTickets: true,
    sslStapling: 'on',
    hstsMaxAge: 31536000,
    hstsIncludeSubdomains: true,
    hstsPreload: false,

    // 缓存配置
    cacheEnabled: true,
    enableProxyCache: false,
    staticCacheTime: 30,
    cacheExtensions: 'jpg,jpeg,png,gif,ico,css,js,svg,woff,woff2,ttf,eot',
    proxyCachePath: '/var/cache/nginx/proxy_cache',
    proxyCacheLevels: '1:2',
    proxyCacheZone: 'proxy_cache_zone',
    proxyCacheSize: 100,
    proxyCacheInactive: 60,
    proxyCacheMaxSize: 80,

    // 限流配置
    rateLimitEnabled: false,
    rateLimitZone: 'one',
    rateLimitRate: 10,
    rateLimitKey: '$binary_remote_addr',
    rateLimitBurst: 20,
    rateLimitZoneSize: 10,
    limitConnEnabled: false,
    limitConnNum: 10,
    limitConnZone: 'addr',

    // CORS 配置
    corsEnabled: false,
    corsOrigin: '*',
    corsMethods: 'GET, POST, PUT, DELETE, OPTIONS, PATCH',
    corsHeaders:
      'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization',
    corsExposeHeaders: 'Content-Length,Content-Range',
    corsMaxAge: 86400,
    corsAllowCredentials: false,

    // 安全头配置
    securityHeaders: false,
    xFrameOptions: 'SAMEORIGIN',
    xFrameAllowFrom: '',
    xContentTypeOptions: 'nosniff',
    xXssProtection: '1; mode=block',
    contentSecurityPolicy: "default-src 'self'",
    referrerPolicy: 'strict-origin-when-cross-origin',
    permissionsPolicy: 'geolocation=(), microphone=(), camera=()'
  })

  const nginxInstallPath = ref('') // Nginx 安装目录
  const currentPlatform = ref('linux') // 'linux' or 'windows'

  const selectConfigType = type => {
    currentType.value = type
    // 根据类型设置默认值
    if (type === 'https') {
      formData.value.port = 443
    } else if (type === 'basic' || type === 'loadbalancer') {
      formData.value.port = 80
    }
  }

  // 生成完整配置
  const generatedConfig = computed(() => {
    let config = ''

    // 根据 nginx 安装路径生成对应的配置
    const nginxPath =
      nginxInstallPath.value || (currentPlatform.value === 'windows' ? 'C:/nginx' : '/etc/nginx')

    // 主配置 - worker_processes 和 pid 文件
    config += `user nginx;\n`
    config += `worker_processes ${formData.value.workerProcesses};\n`

    // 只有 Linux 支持 pid 文件
    if (currentPlatform.value === 'linux') {
      const pidPath = nginxInstallPath.value ? `${nginxPath}/logs/nginx.pid` : '/run/nginx.pid'
      config += `pid ${pidPath};\n`
    } else {
      config += `# pid file: ${nginxPath}/logs/nginx.pid (Windows 不支持 pid 指令）\n`
    }

    // Worker 文件限制
    if (formData.value.workerRlimitNofile) {
      config += `worker_rlimit_nofile ${formData.value.workerRlimitNofile};\n`
    }

    config += `\n`

    // events 块
    config += `events {\n`
    config += `    worker_connections ${formData.value.workerConnections};\n`
    config += `    ${formData.value.multiAccept === 'on' ? 'multi_accept on;' : ''}\n`
    if (currentPlatform.value === 'linux' && formData.value.useEpoll === 'on') {
      config += `    use epoll;\n`
    }
    config += `}\n\n`

    // http 块开始
    config += `http {\n`

    // include mime.types
    const mimeTypesPath = `${nginxPath}/conf/mime.types`
    config += `    include ${mimeTypesPath};\n`

    config += `    default_type application/octet-stream;\n\n`

    // 日志格式
    const logFormats = generateLogFormats()
    config += logFormats

    // 访问日志配置
    config += `    access_log ${formData.value.accessLog} ${formData.value.accessLogFormat};\n`
    config += `    error_log ${formData.value.errorLog} ${formData.value.errorLogLevel};\n`

    // 记录未找到的请求
    if (!formData.value.logNotFound) {
      config += `    log_not_found off;\n`
    }

    config += `\n`

    // 性能优化
    config += `    sendfile ${formData.value.sendfile ? 'on' : 'off'};\n`
    config += `    tcp_nopush ${formData.value.tcpNopush ? 'on' : 'off'};\n`
    config += `    tcp_nodelay ${formData.value.tcpNodelay ? 'on' : 'off'};\n`
    config += `    keepalive_timeout ${formData.value.keepaliveTimeout};\n`
    config += `    ${formData.value.resetTimedoutConnection ? 'reset_timedout_connection on;' : ''}\n`

    if (formData.value.resetDelayedConnectionTimeout > 0) {
      config += `    reset_delayed_connection_timeout ${formData.value.resetDelayedConnectionTimeout}ms;\n`
    }

    if (formData.value.outputBuffersNum && formData.value.outputBufferSize) {
      config += `    output_buffers ${formData.value.outputBuffersNum} ${formData.value.outputBufferSize}k;\n`
    }

    config += `    client_body_timeout ${formData.value.clientBodyTimeout}s;\n`
    config += `    client_header_timeout ${formData.value.clientHeaderTimeout}s;\n`
    config += `    send_timeout ${formData.value.sendTimeout}s;\n`
    config += `    client_header_buffer_size ${formData.value.clientHeaderBufferSize}k;\n`
    config += `    large_client_header_buffers ${formData.value.largeClientHeaderBuffersNum} ${formData.value.largeClientHeaderBuffersSize}k;\n`

    config += `\n`

    // 限流配置 - 必须在 http 块级别
    if (formData.value.rateLimitEnabled && currentPlatform.value !== 'windows') {
      config += `    # 请求限流\n`
      config += `    limit_req_zone ${formData.value.rateLimitKey} zone=${formData.value.rateLimitZone}:${formData.value.rateLimitZoneSize}m rate=${formData.value.rateLimitRate}r/s;\n\n`
    }

    // 连接数限制
    if (formData.value.limitConnEnabled) {
      config += `    # 连接数限制\n`
      config += `    limit_conn_zone $binary_remote_addr zone=${formData.value.limitConnZone}:10m;\n\n`
    }

    // 代理缓存配置
    if (formData.value.enableProxyCache && currentType.value !== 'static') {
      config += `    # 代理缓存配置\n`
      config += `    proxy_cache_path ${formData.value.proxyCachePath} levels=${formData.value.proxyCacheLevels} keys_zone=${formData.value.proxyCacheZone}:${formData.value.proxyCacheSize}m inactive=${formData.value.proxyCacheInactive}m max_size=${formData.value.proxyCacheMaxSize}%;\n\n`
    }

    // 基础 upstream 配置（负载均衡）
    if (currentType.value === 'loadbalancer' && formData.value.servers) {
      config += `    upstream backend {\n`
      const servers = formData.value.servers.split(',').filter(s => s.trim())
      servers.forEach(server => {
        config += `        server ${server.trim()};\n`
      })
      config += `    }\n\n`
    }

    // Gzip 配置 - 在 http 块级别
    if (formData.value.gzipEnabled) {
      config += `    # Gzip 压缩配置\n`
      config += `    gzip ${formData.value.gzipEnabled ? 'on' : 'off'};\n`
      config += `    gzip_vary ${formData.value.gzipVary ? 'on' : 'off'};\n`
      config += `    gzip_disable "msie6";\n`
      config += `    gzip_comp_level ${formData.value.gzipLevel};\n`
      config += `    gzip_min_length ${formData.value.gzipMinLength};\n`
      config += `    gzip_buffers ${formData.value.gzipBuffersNum} ${formData.value.gzipBuffersSize}k;\n`
      config += `    gzip_http_version ${formData.value.gzipHttpVersion};\n`
      config += `    gzip_types ${formData.value.gzipTypes};\n\n`
    }

    // HTTP 重定向 server 块（HTTPS 模式）
    if (currentType.value === 'https') {
      config += `    server {\n`
      config += `        listen 80;\n`
      config += `        server_name ${formData.value.serverName || 'example.com'};\n`
      config += `        return 301 https://$server_name$request_uri;\n`
      config += `    }\n\n`
    }

    // 主 server 块
    const upstreamTarget =
      currentType.value === 'loadbalancer'
        ? 'backend'
        : formData.value.upstream || 'http://localhost:3000'

    config += `    server {\n`
    config += `        listen ${formData.value.port}${currentType.value === 'https' ? ' ssl http2' : ''};\n`
    config += `        server_name ${formData.value.serverName || 'example.com'};\n\n`

    // SSL 配置
    if (currentType.value === 'https') {
      config += `        # SSL 配置\n`
      config += `        ssl_certificate ${formData.value.sslCert || '/etc/nginx/ssl/cert.pem'};\n`
      config += `        ssl_certificate_key ${formData.value.sslKey || '/etc/nginx/ssl/key.pem'};\n`
      config += `        ssl_protocols ${formData.value.sslProtocols};\n`
      config += `        ssl_ciphers ${formData.value.sslCiphers};\n`
      config += `        ssl_prefer_server_ciphers ${formData.value.sslPreferServerCiphers ? 'on' : 'off'};\n`
      config += `        ssl_session_cache shared:SSL:${formData.value.sslSessionCacheSize}m;\n`
      config += `        ssl_session_timeout ${formData.value.sslSessionTimeout}m;\n`
      config += `        ssl_session_tickets ${formData.value.sslSessionTickets ? 'on' : 'off'};\n`
      config += `        ssl_stapling ${formData.value.sslStapling};\n`
      config += `        ssl_stapling_verify on;\n\n`

      // HSTS 配置
      if (formData.value.hstsMaxAge > 0) {
        config += `        add_header Strict-Transport-Security "max-age=${formData.value.hstsMaxAge}${formData.value.hstsIncludeSubdomains ? '; includeSubDomains' : ''}${formData.value.hstsPreload ? '; preload' : ''}" always;\n`
      }
    }

    // 安全头配置
    if (formData.value.securityHeaders) {
      config += `        # 安全头配置\n`
      if (formData.value.xFrameOptions) {
        if (formData.value.xFrameOptions === 'ALLOW-FROM' && formData.value.xFrameAllowFrom) {
          config += `        add_header X-Frame-Options "ALLOW-FROM ${formData.value.xFrameAllowFrom}" always;\n`
        } else {
          config += `        add_header X-Frame-Options "${formData.value.xFrameOptions}" always;\n`
        }
      }
      if (formData.value.xContentTypeOptions) {
        config += `        add_header X-Content-Type-Options "${formData.value.xContentTypeOptions}" always;\n`
      }
      if (formData.value.xXssProtection) {
        config += `        add_header X-XSS-Protection "${formData.value.xXssProtection}" always;\n`
      }
      if (formData.value.contentSecurityPolicy) {
        config += `        add_header Content-Security-Policy "${formData.value.contentSecurityPolicy}" always;\n`
      }
      if (formData.value.referrerPolicy) {
        config += `        add_header Referrer-Policy "${formData.value.referrerPolicy}" always;\n`
      }
      if (formData.value.permissionsPolicy) {
        config += `        add_header Permissions-Policy "${formData.value.permissionsPolicy}" always;\n`
      }
      config += `\n`
    }

    // CORS 配置
    if (formData.value.corsEnabled) {
      config += `        # CORS 跨域配置\n`
      config += `        add_header 'Access-Control-Allow-Origin' '${formData.value.corsOrigin}' always;\n`
      config += `        add_header 'Access-Control-Allow-Methods' '${formData.value.corsMethods}' always;\n`
      config += `        add_header 'Access-Control-Allow-Headers' '${formData.value.corsHeaders}' always;\n`
      if (formData.value.corsExposeHeaders) {
        config += `        add_header 'Access-Control-Expose-Headers' '${formData.value.corsExposeHeaders}' always;\n`
      }
      if (formData.value.corsMaxAge > 0) {
        config += `        add_header 'Access-Control-Max-Age' '${formData.value.corsMaxAge}' always;\n`
      }
      if (formData.value.corsAllowCredentials) {
        config += `        add_header 'Access-Control-Allow-Credentials' 'true' always;\n`
      }
      config += `\n`

      // OPTIONS 请求处理
      config += `        if ($request_method = 'OPTIONS') {\n`
      config += `            return 204;\n`
      config += `        }\n\n`
    }

    // 代理超时配置
    config += `        # 代理超时配置\n`
    config += `        proxy_connect_timeout ${formData.value.proxyConnectTimeout}s;\n`
    config += `        proxy_send_timeout ${formData.value.proxySendTimeout}s;\n`
    config += `        proxy_read_timeout ${formData.value.proxyReadTimeout}s;\n`
    config += `        proxy_buffer_size ${formData.value.proxyBufferSize}k;\n`
    config += `        proxy_buffers ${formData.value.proxyBuffersNum} ${formData.value.proxyBuffersSize}k;\n`
    if (formData.value.proxyMaxTempFileSize) {
      config += `        proxy_max_temp_file_size ${formData.value.proxyMaxTempFileSize}m;\n`
    }
    if (formData.value.proxyRedirect) {
      config += `        proxy_redirect on;\n`
    }
    if (formData.value.proxyInterceptErrors) {
      config += `        proxy_intercept_errors on;\n`
    }
    config += `\n`

    // 静态资源缓存 location
    if (formData.value.cacheEnabled) {
      const extensions = formData.value.cacheExtensions
        .split(',')
        .map(e => e.trim())
        .filter(e => e)
        .join('|')
      if (extensions) {
        config += `        # 静态资源缓存\n`
        config += `        location ~* \\.(?:${extensions})$ {\n`
        config += `            expires ${formData.value.staticCacheTime}d;\n`
        config += `            add_header Cache-Control "public, immutable";\n`
        if (currentType.value !== 'static') {
          config += `            proxy_pass ${upstreamTarget};\n`
        }
        config += `        }\n\n`
      }
    }

    // 主 location
    config += `        location / {\n`

    // 限流
    if (formData.value.rateLimitEnabled && currentPlatform.value !== 'windows') {
      config += `            limit_req zone=${formData.value.rateLimitZone} burst=${formData.value.rateLimitBurst} nodelay;\n`
    }

    // 连接数限制
    if (formData.value.limitConnEnabled) {
      config += `            limit_conn ${formData.value.limitConnZone} ${formData.value.limitConnNum};\n`
    }

    if (currentType.value === 'static') {
      config += `            root /var/www/html;\n`
      config += `            index index.html index.htm;\n`
      config += `            try_files $uri $uri/ /index.html;\n`
    } else {
      config += `            proxy_pass ${upstreamTarget};\n`
      // 代理头设置
      config += `            proxy_http_version 1.1;\n`
      config += `            proxy_set_header Upgrade $http_upgrade;\n`
      config += `            proxy_set_header Connection 'upgrade';\n`
      config += `            proxy_set_header Host $host;\n`
      config += `            proxy_set_header X-Real-IP $remote_addr;\n`
      config += `            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n`
      config += `            proxy_set_header X-Forwarded-Proto $scheme;\n`
      config += `            proxy_cache_bypass $http_upgrade;\n`

      // 代理缓存
      if (formData.value.enableProxyCache) {
        config += `            proxy_cache ${formData.value.proxyCacheZone};\n`
        config += `            proxy_cache_valid 200 60m;\n`
        config += `            proxy_cache_valid 404 1m;\n`
        config += `            add_header X-Cache-Status $upstream_cache_status;\n`
      }
    }
    config += `        }\n`
    config += `    }\n`

    // http 块结束
    config += `}\n`

    return config
  })

  // 生成日志格式
  const generateLogFormats = () => {
    let formats = ''

    // combined 格式
    formats += `    log_format combined '$remote_addr - $remote_user [$time_local] "$request" '$st "$status $body_bytes_sent "$http_referer" "$http_user_agent"';\n`

    // main 格式
    formats += `    log_format main '$remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent';\n`

    // json 格式
    if (formData.value.accessLogFormat === 'json') {
      formats += `    log_format json escape=json '{\n`
      formats += `        "time_local": "$time_local",\n`
      formats += `        "remote_addr": "$remote_addr",\n`
      formats += `        "remote_user": "$remote_user",\n`
      formats += `        "request": "$request",\n`
      formats += `        "status": "$status",\n`
      formats += `        "body_bytes_sent": "$body_bytes_sent",\n`
      formats += `        "request_time": "$request_time",\n`
      formats += `        "http_referrer": "$http_referer",\n`
      formats += `        "http_user_agent": "$http_user_agent"\n`
      formats += `    }';\n`
    }

    return formats
  }

  const copyConfig = async () => {
    try {
      await navigator.clipboard.writeText(generatedConfig.value)
      validationMessage.value = '✓ 配置已复制到剪贴板'
      validationStatus.value = 'success'
      setTimeout(() => {
        validationMessage.value = ''
      }, 3000)
    } catch (err) {
      validationMessage.value = '✗ 复制失败: ' + err.message
      validationStatus.value = 'error'
    }
  }

  const downloadConfig = () => {
    const blob = new Blob([generatedConfig.value], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'nginx.conf'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    validationMessage.value = '✓ 配置文件已下载'
    validationStatus.value = 'success'
    setTimeout(() => {
      validationMessage.value = ''
    }, 3000)
  }

  const validateConfig = () => {
    const config = generatedConfig.value
    const errors = []

    if (!formData.value.serverName) {
      errors.push('服务器名称不能为空')
    }
    if (!formData.value.upstream && currentType.value !== 'static') {
      errors.push('代理目标不能为空')
    }
    if (currentType.value === 'https') {
      if (!formData.value.sslCert) errors.push('SSL证书路径不能为空')
      if (!formData.value.sslKey) errors.push('SSL私钥路径不能为空')
    }
    if (currentType.value === 'loadbalancer' && !formData.value.servers) {
      errors.push('后端服务器列表不能为空')
    }

    // 简单的语法检查
    if (!config.includes('server {') || !config.includes('}')) {
      errors.push('配置缺少 server 块的大括号')
    }

    if (!config.includes('http {') || !config.includes('}')) {
      errors.push('配置缺少 http 块的大括号')
    }

    if (errors.length > 0) {
      validationMessage.value = '✗ 验证失败: ' + errors.join('; ')
      validationStatus.value = 'error'
    } else {
      validationMessage.value = '✓ 配置验证通过'
      validationStatus.value = 'success'
    }

    setTimeout(() => {
      validationMessage.value = ''
    }, 5000)
  }

  // API 验证配置
  const validateWithApi = async () => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      alert('请先登录后再使用 API 验证功能')
      return
    }

    isApiValidating.value = true
    apiValidationResult.value = true
    apiValidationStatus.value = 'loading'
    apiValidationOutput.value = ''
    apiValidationSuggestions.value = []

    const config = generatedConfig.value

    // 将配置包装在 http 块中（如果需要）
    const wrappedConfig = config.includes('http {')
      ? config
      : `http {\n    ${config
          .split('\n')
          .map(line => line)
          .join('\n    ')}\n}`

    let fullOutput = ''
    let errorMessage = ''
    let hasErrors = false

    try {
      const apiEndpoint = '/api/v2/nginx/check'

      let apiUrl = apiEndpoint
      if (API_BASE_URL) {
        if (API_BASE_URL.startsWith('http')) {
          apiUrl = API_BASE_URL.replace('/api/v1', '') + apiEndpoint
        } else {
          apiUrl = API_BASE_URL.replace('/api/v1', '') + apiEndpoint
        }
      }

      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          config: wrappedConfig
        })
      })

      if (!response.ok) {
        if (response.status === 404) {
          apiValidationStatus.value = 'error'
          apiValidationOutput.value = 'API 端点不存在。请确认后端服务已启动或检查 API 路径配置。'
          apiValidationSuggestions.value = [
            '检查后端服务是否正在运行',
            '确认 API 基础 URL 配置是否正确',
            '联系管理员确认 API 端点是否已部署',
            `当前请求路径: ${apiUrl}`
          ]
          isApiValidating.value = false
          return
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const contentType = response.headers.get('content-type')

      if (
        contentType &&
        contentType.includes('application/json') &&
        !contentType.includes('event-stream')
      ) {
        const data = await response.json()
        if (data.status === 'ok') {
          apiValidationStatus.value = 'success'
          apiValidationOutput.value = data.message || '配置语法正确'
          apiValidationSuggestions.value = []
        } else {
          apiValidationStatus.value = 'error'
          apiValidationOutput.value = data.message || '配置验证失败'
          apiValidationSuggestions.value = ['请检查配置文件']
        }
        isApiValidating.value = false
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.trim() === '' || line.startsWith('data:')) {
            const dataStr = line.replace('data:', '').trim()
            if (dataStr === '[DONE]') continue

            try {
              const data = JSON.parse(dataStr)
              if (data.choices && data.choices[0]) {
                const delta = data.choices[0].delta
                if (delta && delta.content) {
                  fullOutput += delta.content
                  apiValidationOutput.value = fullOutput
                }
              }
            } catch (e) {
              console.warn('解析 SSE 数据失败:', e)
            }
          }
        }
      }

      if (fullOutput && fullOutput.length > 0) {
        hasErrors = true
        errorMessage = fullOutput
      }

      apiValidationStatus.value = hasErrors ? 'error' : 'success'
      if (hasErrors) {
        apiValidationSuggestions.value = [
          '配置验证失败，请参考上方错误信息和AI建议进行修复',
          '查看详细信息了解具体错误原因',
          '建议根据 AI 提供的建议修改配置后重新验证'
        ]
      } else {
        apiValidationSuggestions.value = []
      }
    } catch (error) {
      console.error('API 验证错误:', error)
      apiValidationStatus.value = 'error'
      apiValidationOutput.value = `验证请求失败: ${error.message}`
      apiValidationSuggestions.value = [
        '检查网络连接是否正常',
        '确认后端服务是否运行',
        '检查 API 基础 URL 配置是否正确',
        '确认 token 是否有效',
        `详细错误: ${error.stack || error.message}`
      ]
    } finally {
      isApiValidating.value = false
    }
  }

  const applyTemplate = template => {
    currentType.value = template.type
    Object.assign(formData.value, template.data)

    // 根据当前选择的平台设置默认路径
    if (currentPlatform.value === 'windows') {
      formData.value.accessLog = 'C:/nginx/logs/access.log'
      formData.value.errorLog = 'C:/nginx/logs/error.log'
      formData.value.proxyCachePath = 'C:/nginx/cache/proxy_cache'
      if (template.type === 'https') {
        formData.value.sslCert = 'C:/nginx/ssl/cert.pem'
        formData.value.sslKey = 'C:/nginx/ssl/key.pem'
      }
    } else {
      formData.value.accessLog = '/var/log/nginx/access.log'
      formData.value.errorLog = '/var/log/nginx/error.log'
      formData.value.proxyCachePath = '/var/cache/nginx/proxy_cache'
      if (template.type === 'https') {
        formData.value.sslCert = '/etc/nginx/ssl/cert.pem'
        formData.value.sslKey = '/etc/nginx/ssl/key.pem'
      }
    }

    validationMessage.value = `✓ 已应用"${template.name}"模板（${currentPlatform.value === 'windows' ? 'Windows' : 'Linux'}）`
    validationStatus.value = 'success'
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
        // 尝试解析为 JSON
        if (file.name.endsWith('.json')) {
          const importedData = JSON.parse(content)
          formData.value = { ...formData.value, ...importedData.formData }
          nginxInstallPath.value = importedData.nginxInstallPath || nginxInstallPath.value
          currentPlatform.value = importedData.currentPlatform || currentPlatform.value

          validationMessage.value = '✓ 配置导入成功'
          validationStatus.value = 'success'
        } else {
          // 对于 .conf 文件，只显示导入成功提示，但不解析
          validationMessage.value = '✓ 配置文件导入成功（仅支持 JSON 格式的配置导入）'
          validationStatus.value = 'success'
        }
      } catch (error) {
        validationMessage.value = '✗ 导入失败: ' + error.message
        validationStatus.value = 'error'
      }

      setTimeout(() => {
        validationMessage.value = ''
      }, 3000)

      // 清空文件输入
      fileInput.value.value = ''
    }

    reader.readAsText(file)
  }

  // 导出配置
  const exportConfig = () => {
    const exportData = {
      version: '1.0',
      timestamp: new Date().toISOString(),
      currentPlatform: currentPlatform.value,
      nginxInstallPath: nginxInstallPath.value,
      currentType: currentType.value,
      formData: formData.value,
      accordions: accordions.value
    }

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'nginx-config-export.json'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    validationMessage.value = '✓ 配置已导出为 JSON 文件'
    validationStatus.value = 'success'
    setTimeout(() => {
      validationMessage.value = ''
    }, 3000)
  }

  // 监听平台变化
  watch(currentPlatform, newPlatform => {
    setPlatform(newPlatform)
  })
</script>

<style scoped>
  .api-validation-result {
    background: var(--bg-secondary);
    border: 2px solid #cbd5e1;
    border-radius: 8px;
    margin-bottom: 20px;
    overflow: hidden;
  }

  .validation-header {
    padding: 15px 20px;
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 600;
    justify-content: space-between;
  }

  .validation-header.success {
    background: #dcfce7;
    color: #166534;
    border-color: #22c55e;
  }

  .validation-header.error {
    background: #fee2e2;
    color: #991b1b;
    border-color: #ef4444;
  }

  .validation-header.loading {
    background: #dbeafe;
    color: #1e40af;
    border-color: #3b82f6;
  }

  .status-icon {
    font-size: 20px;
  }

  .close-validation-btn {
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: inherit;
    padding: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .close-validation-btn:hover {
    opacity: 0.7;
  }

  .validation-content {
    padding: 15px 20px;
    background: var(--bg-primary);
  }

  .validation-output {
    background: var(--bg-primary);
    color: #e2e8f0;
    padding: 15px;
    border-radius: 6px;
    margin-bottom: 15px;
  }

  .validation-output pre {
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
  }

  .validation-suggestions {
    background: #fef9c3;
    border-left: 4px solid #eab308;
    padding: 15px;
    border-radius: 4px;
  }

  .validation-suggestions h4 {
    margin: 0 0 10px 0;
    color: #854d0e;
    font-size: 14px;
  }

  .validation-suggestions ul {
    margin: 0;
    padding-left: 20px;
  }

  .validation-suggestions li {
    color: #854d0e;
    font-size: 14px;
    margin-bottom: 8px;
    line-height: 1.5;
  }

  .platform-selector {
    background: var(--bg-secondary);
    padding: 20px;
    border-radius: 8px;
    margin-bottom: 20px;
  }

  .platform-selector h3 {
    margin: 0 0 15px 0;
    color: var(--text-primary);
    font-size: 18px;
  }

  .platform-radio-group {
    display: flex;
    gap: 20px;
  }

  .radio-label {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    font-size: 14px;
    color: var(--text-primary);
    transition: all 0.3s;
  }

  .radio-label:hover {
    color: var(--color-primary);
  }

  .radio-label input[type='radio'] {
    display: none;
  }

  .radio-custom {
    width: 20px;
    height: 20px;
    border: 2px solid var(--border-color);
    border-radius: 50%;
    position: relative;
    transition: all 0.3s;
  }

  .radio-label input[type='radio']:checked + .radio-custom {
    border-color: var(--color-primary);
    background: linear-gradient(135deg, var(--color-primary) 0%, var(--teal-400) 100%);
  }

  .radio-label input[type='radio']:checked + .radio-custom::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 8px;
    height: 8px;
    background: white;
    border-radius: 50%;
  }

  .nginx-path-selector {
    background: var(--bg-secondary);
    padding: 20px;
    border-radius: 8px;
    margin-bottom: 20px;
    border: 1px solid var(--border-color);
  }

  .nginx-path-selector h3 {
    margin: 0 0 15px 0;
    color: var(--text-primary);
    font-size: 18px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .nginx-path-selector h3::before {
    content: '';
    display: none;
  }

  .path-input-group {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .path-input {
    flex: 1;
    padding: 12px 16px;
    border: 2px solid #d1d5db;
    border-radius: 6px;
    font-size: 14px;
    font-family: 'Courier New', monospace;
    transition: all 0.3s;
  }

  .path-input:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  .path-input::placeholder {
    color: var(--text-tertiary);
  }

  .path-hint-btn {
    padding: 8px 16px;
    background: var(--bg-primary);
    border: 2px solid var(--color-primary);
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    color: var(--color-primary);
    transition: all 0.3s;
    display: flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
  }

  .path-hint-btn:hover {
    background: var(--color-primary);
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  }

  .path-description {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px;
    background: var(--bg-secondary);
    border-radius: 6px;
    margin-top: 12px;
  }

  .path-description .icon {
    font-size: 16px;
  }

  .path-description .text {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.6;
  }

  .path-description code {
    background: #f3f4f6;
    color: #e11d48;
    padding: 2px 8px;
    border-radius: 4px;
    font-family: 'Courier New', monospace;
    font-size: 12px;
  }

  .api-validate-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .accordion-section {
    margin-bottom: 20px;
  }

  .accordion-item {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    margin-bottom: 10px;
    overflow: hidden;
  }

  .accordion-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15px 20px;
    cursor: pointer;
    background: #f9fafb;
    transition: all 0.3s;
    user-select: none;
  }

  .accordion-header:hover {
    background: #f3f4f6;
  }

  .accordion-header h3 {
    margin: 0;
    font-size: 16px;
    color: #374151;
    font-weight: 600;
  }

  .accordion-icon {
    transition: transform 0.3s;
    font-size: 12px;
    color: #6b7280;
  }

  .accordion-icon.expanded {
    transform: rotate(180deg);
  }

  .accordion-content {
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.3s ease-out;
    background: white;
  }

  .accordion-content.expanded {
    max-height: 5000px;
    overflow: visible;
  }

  .accordion-content .config-form {
    padding: 20px;
    background: white;
    border-top: none;
    border-radius: 0;
  }

  .platform-warning {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 15px;
    background: #fef3c7;
    border: 1px solid #fcd34d;
    border-radius: 6px;
    color: #92400e;
    font-size: 14px;
  }

  .warning-icon {
    font-size: 18px;
  }

  .wide-input {
    width: 100%;
    padding: 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 14px;
    transition: border-color 0.3s;
    font-family: 'Courier New', monospace;
  }

  .wide-input:focus {
    outline: none;
    border-color: #0d9488;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  .help-text {
    display: block;
    margin-top: 5px;
    font-size: 12px;
    color: #6b7280;
  }

  .nginx-config-overlay {
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

  .nginx-config-modal {
    background: white;
    border-radius: 12px;
    width: 90%;
    max-width: 1200px;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 30px;
    border-bottom: 1px solid #e5e7eb;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
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

  .config-type-selector h3 {
    margin-top: 0;
    color: #374151;
    font-size: 18px;
  }

  .type-buttons {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }

  .type-buttons button {
    padding: 10px 20px;
    border: 2px solid #d1d5db;
    background: white;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.3s;
  }

  .type-buttons button:hover {
    border-color: #0d9488;
    color: #0d9488;
  }

  .type-buttons button.active {
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    border-color: #0d9488;
    color: white;
  }

  .config-form {
    padding: 20px;
    border-radius: 8px;
  }

  .form-group {
    margin-bottom: 15px;
  }

  .form-group label {
    display: block;
    margin-bottom: 5px;
    color: #374151;
    font-weight: 500;
  }

  .form-group input,
  .form-group select {
    width: 100%;
    padding: 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 14px;
    transition: border-color 0.3s;
  }

  .form-group input:focus,
  .form-group select:focus {
    outline: none;
    border-color: #0d9488;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  .advanced-options {
    margin-top: 20px;
    padding-top: 20px;
  }

  .advanced-options h4 {
    margin: 0 0 15px 0;
    color: #374151;
    font-size: 16px;
  }

  .checkbox-group {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 10px;
  }

  .checkbox-group label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
  }

  .checkbox-group input[type='checkbox'] {
    width: 18px;
    height: 18px;
    cursor: pointer;
  }

  .config-preview {
    margin-bottom: 20px;
  }

  .preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    flex-wrap: wrap;
    gap: 10px;
  }

  .preview-header h3 {
    margin: 0;
    color: #374151;
    font-size: 18px;
    flex-shrink: 0;
  }

  .preview-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }

  .action-btn {
    padding: 8px 16px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    transition: all 0.3s;
    white-space: nowrap;
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
    color: #e2e8f0;
    padding: 20px;
    border-radius: 8px;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
    max-height: 400px;
    overflow-y: auto;
    white-space: pre-wrap;
  }

  .validation-message {
    padding: 10px 15px;
    border-radius: 6px;
    margin-top: 10px;
    font-size: 14px;
  }

  .validation-message.success {
    background: #d1fae5;
    color: #065f46;
  }

  .validation-message.error {
    background: #fee2e2;
    color: #991b1b;
  }

  .templates-section {
    padding: 20px 30px;
    border-top: 1px solid #e5e7eb;
    background: #f9fafb;
  }

  .templates-section h3 {
    margin: 0 0 15px 0;
    color: #374151;
    font-size: 18px;
  }

  .template-category {
    margin-bottom: 20px;
  }

  .template-category:last-child {
    margin-bottom: 0;
  }

  .template-category h4 {
    margin: 0 0 10px 0;
    color: #6b7280;
    font-size: 14px;
    font-weight: 600;
  }

  .template-buttons {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }

  .template-buttons button {
    padding: 8px 16px;
    background: white;
    border: 2px solid #0d9488;
    color: #0d9488;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    transition: all 0.3s;
  }

  .template-buttons button:hover {
    background: #0d9488;
    color: white;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  }

  /* 滚动条样式 */
  .modal-body::-webkit-scrollbar,
  .config-content::-webkit-scrollbar {
    width: 8px;
  }

  .modal-body::-webkit-scrollbar-track,
  .config-content::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 4px;
  }

  .modal-body::-webkit-scrollbar-thumb,
  .config-content::-webkit-scrollbar-thumb {
    background: #888;
    border-radius: 4px;
  }

  .modal-body::-webkit-scrollbar-thumb:hover,
  .config-content::-webkit-scrollbar-thumb:hover {
    background: #555;
  }

  /* 响应式设计 */
  @media (max-width: 768px) {
    .nginx-config-modal {
      width: 95%;
      max-height: 95vh;
    }

    .modal-header {
      padding: 15px 20px;
    }

    .modal-header h2 {
      font-size: 20px;
    }

    .modal-body {
      padding: 20px;
    }

    .accordion-header h3 {
      font-size: 14px;
    }

    .checkbox-group {
      grid-template-columns: 1fr;
    }

    .type-buttons button,
    .template-buttons button {
      flex: 1;
      min-width: 100px;
    }

    .preview-actions {
      flex-wrap: wrap;
    }

    .platform-radio-group {
      flex-direction: column;
      gap: 10px;
    }
  }
</style>
