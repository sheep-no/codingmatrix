<template>
  <Modal :visible="visible" title="系统信息检测" size="lg" @close="$emit('close')">
    <div class="system-info">
      <!-- 平台信息 -->
      <section class="info-section">
        <h3 class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          平台信息
        </h3>

        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">操作系统</span>
            <span class="info-value">{{ systemInfo.os || '检测中...' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">浏览器</span>
            <span class="info-value">{{ systemInfo.browser || '检测中...' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">屏幕分辨率</span>
            <span class="info-value">{{ systemInfo.screen || '-' }}</span>
          </div>
        </div>
      </section>

      <!-- Java 环境 -->
      <section class="info-section">
        <h3 class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path
              d="M12 2a3 3 0 013 3v7h3a3 3 0 013 3v5a3 3 0 01-3 3H6a3 3 0 01-3-3v-5a3 3 0 013-3h3V5a3 3 0 013-3z"
            />
          </svg>
          Java 环境
        </h3>

        <div class="status-card" :class="javaStatus.status">
          <div class="status-indicator">
            <div class="status-dot" :class="javaStatus.status" />
            <span>{{ javaStatus.text }}</span>
          </div>
          <div v-if="javaStatus.version" class="version-info">
            {{ javaStatus.version }}
          </div>
        </div>
      </section>

      <!-- 部署建议 -->
      <section class="info-section">
        <h3 class="section-title">部署建议</h3>
        <div class="platform-grid">
          <button
            v-for="platform in platforms"
            :key="platform.id"
            class="platform-card"
            :class="{ active: selectedPlatform === platform.id }"
            @click="selectPlatform(platform.id)"
          >
            <div class="platform-icon" :class="platform.id">
              {{ platform.icon }}
            </div>
            <span class="platform-name">{{ platform.name }}</span>
            <span class="platform-desc">{{ platform.desc }}</span>
          </button>
        </div>
      </section>
    </div>

    <template #footer>
      <Button variant="ghost" @click="$emit('close')">关闭</Button>
      <Button variant="primary" @click="$emit('apply-platform', selectedPlatform)">
        应用此平台配置
      </Button>
    </template>
  </Modal>
</template>

<script setup>
  import { ref, computed, onMounted } from 'vue'
  import Modal from './ui/Modal.vue'
  import Button from './ui/Button.vue'

  defineProps({
    visible: { type: Boolean, default: false }
  })

  defineEmits(['close', 'apply-platform'])

  const systemInfo = ref({})
  const javaStatus = ref({ status: 'checking', text: '检测中...', version: '' })
  const selectedPlatform = ref('nginx')

  const platforms = [
    { id: 'nginx', name: 'Nginx', icon: '🌐', desc: '高性能 Web 服务器' },
    { id: 'docker', name: 'Docker', icon: '🐳', desc: '容器化部署' },
    { id: 'k8s', name: 'Kubernetes', icon: '☸️', desc: '容器编排平台' }
  ]

  const selectPlatform = id => {
    selectedPlatform.value = id
  }

  const detectSystem = async () => {
    // 操作系统
    const userAgent = navigator.userAgent
    if (userAgent.includes('Windows')) {
      systemInfo.value.os = 'Windows'
    } else if (userAgent.includes('Mac')) {
      systemInfo.value.os = 'macOS'
    } else if (userAgent.includes('Linux')) {
      systemInfo.value.os = 'Linux'
    } else {
      systemInfo.value.os = 'Unknown'
    }

    // 浏览器
    if (userAgent.includes('Chrome')) {
      systemInfo.value.browser = 'Chrome'
    } else if (userAgent.includes('Firefox')) {
      systemInfo.value.browser = 'Firefox'
    } else if (userAgent.includes('Safari')) {
      systemInfo.value.browser = 'Safari'
    } else {
      systemInfo.value.browser = 'Unknown'
    }

    // 屏幕
    systemInfo.value.screen = `${screen.width} × ${screen.height}`

    // Java 检测（模拟）
    setTimeout(() => {
      javaStatus.value = {
        status: 'success',
        text: '已安装',
        version: 'Java 17.0.1'
      }
    }, 1000)
  }

  onMounted(() => {
    detectSystem()
  })
</script>

<style scoped>
  .system-info {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-6);
  }

  .info-section {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-3);
  }

  .section-title {
    display: flex;
    align-items: center;
    gap: var(--spacing-2);
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
  }

  .section-title svg {
    width: 20px;
    height: 20px;
    color: var(--color-blue-600);
  }

  .info-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--spacing-3);
  }

  .info-item {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-1);
    padding: var(--spacing-3);
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
  }

  .info-label {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    font-weight: 500;
  }

  .info-value {
    font-size: var(--text-sm);
    color: var(--text-primary);
    font-weight: 600;
  }

  .status-card {
    padding: var(--spacing-4);
    border-radius: var(--radius-lg);
    border: 2px solid var(--border-color);
  }

  .status-card.success {
    border-color: var(--color-success-500);
    background: linear-gradient(135deg, var(--color-success-50) 0%, transparent 100%);
  }

  .status-card.checking {
    border-color: var(--color-warning-500);
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: var(--spacing-2);
    font-weight: 600;
  }

  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    animation: pulse 2s ease-in-out infinite;
  }

  .status-dot.success {
    background: var(--color-success-500);
  }

  .status-dot.checking {
    background: var(--color-warning-500);
  }

  .version-info {
    margin-top: var(--spacing-2);
    font-size: var(--text-sm);
    color: var(--text-secondary);
    font-family: monospace;
  }

  .platform-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--spacing-3);
  }

  .platform-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--spacing-2);
    padding: var(--spacing-4);
    background: var(--bg-primary);
    border: 2px solid var(--border-color);
    border-radius: var(--radius-lg);
    cursor: pointer;
    transition: all var(--transition-base);
  }

  .platform-card:hover {
    border-color: var(--color-blue-400);
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }

  .platform-card.active {
    border-color: var(--color-blue-600);
    background: linear-gradient(135deg, var(--color-blue-50) 0%, var(--color-blue-100) 100%);
  }

  .platform-icon {
    font-size: 32px;
    margin-bottom: var(--spacing-1);
  }

  .platform-name {
    font-size: var(--text-base);
    font-weight: 600;
    color: var(--text-primary);
  }

  .platform-desc {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    text-align: center;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }

  @media (max-width: 768px) {
    .info-grid,
    .platform-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
