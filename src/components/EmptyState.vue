<template>
  <div class="empty-state">
    <div class="empty-state-bg">
      <div class="bg-circle bg-circle-1"></div>
      <div class="bg-circle bg-circle-2"></div>
      <div class="bg-circle bg-circle-3"></div>
      <div class="floating-particles">
        <span v-for="n in 12" :key="n" class="particle" :style="getParticleStyle(n)"></span>
      </div>
    </div>
    <div class="empty-state-content">
      <div class="hero-section">
        <div class="hero-icon">
          <div class="icon-ring icon-ring-1"></div>
          <div class="icon-ring icon-ring-2"></div>
          <div class="icon-ring icon-ring-3"></div>
          <div class="icon-core">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path
                d="M12 2a7 7 0 0 1 7 7v3h3a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h3V9a7 7 0 0 1 7-7z"
              />
              <path d="M9 21h6" />
              <path d="M12 17v4" />
            </svg>
          </div>
        </div>
        <h1 class="hero-title">{{ typingTitle }}</h1>
        <p v-if="showSubtitle" class="hero-subtitle">{{ typingSubtitle }}</p>
      </div>

      <div class="quick-actions">
        <div class="action-label">快速开始</div>
        <div class="action-chips">
          <button class="action-chip" @click="$emit('quick-prompt', '帮我写一个Python快速排序')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="16 18 22 12 16 6" />
              <polyline points="8 6 2 12 8 18" />
            </svg>
            <span>写代码</span>
          </button>
          <button class="action-chip" @click="$emit('quick-prompt', '解释一下什么是RESTful API')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <span>问问题</span>
          </button>
          <button class="action-chip" @click="$emit('quick-prompt', '帮我分析一下这段代码的问题')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path
                d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"
              />
            </svg>
            <span>调试代码</span>
          </button>
          <button class="action-chip" @click="$emit('quick-prompt', '帮我写一个项目readme文档')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <span>写文档</span>
          </button>
        </div>
      </div>

      <div class="prompt-carousel">
        <div class="carousel-label">灵感提示</div>
        <div class="carousel-track">
          <button
            v-for="(prompt, index) in carouselPrompts"
            :key="index"
            class="carousel-item"
            @click="$emit('quick-prompt', prompt.text)"
          >
            <span class="carousel-emoji">{{ prompt.emoji }}</span>
            <span class="carousel-text">{{ prompt.text }}</span>
          </button>
        </div>
      </div>

      <div class="features-section">
        <div class="section-label">功能亮点</div>
        <div class="features-grid">
          <div class="feature-card">
            <div class="feature-icon feature-icon-1">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path
                  d="M12 2a3 3 0 0 1 3 3v7h3a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3v-5a3 3 0 0 1 3-3h3V5a3 3 0 0 1 3-3z"
                />
                <path d="M9 12l2 2 4-4" />
              </svg>
            </div>
            <div class="feature-content">
              <h3>智能对话</h3>
              <p>自然流畅的对话体验</p>
            </div>
          </div>
          <div class="feature-card">
            <div class="feature-icon feature-icon-2">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
                <line x1="14" y1="4" x2="10" y2="20" />
              </svg>
            </div>
            <div class="feature-content">
              <h3>代码生成</h3>
              <p>快速生成高质量代码</p>
            </div>
          </div>
          <div class="feature-card">
            <div class="feature-icon feature-icon-3">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 6v6l4 2" />
              </svg>
            </div>
            <div class="feature-content">
              <h3>深度思考</h3>
              <p>复杂问题逐步分析</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, onMounted, onBeforeUnmount } from 'vue'

  defineEmits(['quick-prompt'])

  const FULL_TITLE = '欢迎使用 AI 助手'
  const FULL_SUBTITLE = '您的智能编程伙伴，让创意触手可及'

  const typingTitle = ref('')
  const typingSubtitle = ref('')
  const showSubtitle = ref(false)

  let titleTimer = null
  let subtitleTimer = null

  const startTypingAnimation = () => {
    typingTitle.value = ''
    showSubtitle.value = false

    let i = 0
    titleTimer = setInterval(() => {
      if (i < FULL_TITLE.length) {
        typingTitle.value += FULL_TITLE[i]
        i++
      } else {
        clearInterval(titleTimer)
        showSubtitle.value = true
        startSubtitleTyping()
      }
    }, 80)
  }

  const startSubtitleTyping = () => {
    typingSubtitle.value = ''

    let i = 0
    subtitleTimer = setInterval(() => {
      if (i < FULL_SUBTITLE.length) {
        typingSubtitle.value += FULL_SUBTITLE[i]
        i++
      } else {
        clearInterval(subtitleTimer)
      }
    }, 50)
  }

  const getParticleStyle = n => {
    const size = Math.random() * 6 + 4
    const left = Math.random() * 100
    const delay = Math.random() * 10
    const duration = Math.random() * 10 + 15
    return {
      width: `${size}px`,
      height: `${size}px`,
      left: `${left}%`,
      animationDelay: `${delay}s`,
      animationDuration: `${duration}s`
    }
  }

  const carouselPrompts = [
    { emoji: '🎮', text: '帮我写一个五子棋小游戏' },
    { emoji: '📊', text: '用 Python 分析 CSV 数据并生成图表' },
    { emoji: '🌐', text: '设计一个个人博客网站' },
    { emoji: '🔧', text: '写一个 Docker 部署配置' },
    { emoji: '📱', text: '做一个响应式登录页面' },
    { emoji: '🤖', text: '解释 Transformer 模型原理' },
    { emoji: '📝', text: '帮我润色这段英文邮件' },
    { emoji: '🎨', text: '用 CSS 做一个加载动画' },
    { emoji: '💡', text: '对比 React 和 Vue 的优缺点' },
    { emoji: '🚀', text: '优化这段 SQL 查询性能' }
  ]

  onMounted(() => {
    startTypingAnimation()
  })

  onBeforeUnmount(() => {
    if (titleTimer) clearInterval(titleTimer)
    if (subtitleTimer) clearInterval(subtitleTimer)
  })

  defineExpose({ startTypingAnimation })
</script>

<style scoped>
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    position: relative;
    overflow: hidden;
    background: var(--bg-primary) !important;
  }

  .empty-state-bg {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
  }

  .bg-circle {
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    opacity: 0.6;
    animation: floatBg 20s ease-in-out infinite;
  }

  .bg-circle-1 {
    width: 600px;
    height: 600px;
    background: linear-gradient(135deg, var(--color-primary-500) 0%, var(--color-primary-600) 100%);
    top: -200px;
    right: -100px;
    animation-delay: 0s;
    opacity: 0.15;
  }

  .bg-circle-2 {
    width: 500px;
    height: 500px;
    background: linear-gradient(135deg, var(--color-blue-500) 0%, var(--color-blue-600) 100%);
    bottom: -150px;
    left: -100px;
    animation-delay: -7s;
    opacity: 0.12;
  }

  .bg-circle-3 {
    width: 400px;
    height: 400px;
    background: linear-gradient(135deg, var(--color-success-500) 0%, var(--color-success-600) 100%);
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    animation-delay: -14s;
    opacity: 0.1;
  }

  @keyframes floatBg {
    0%,
    100% {
      transform: translate(0, 0) scale(1);
    }
    33% {
      transform: translate(30px, -30px) scale(1.05);
    }
    66% {
      transform: translate(-20px, 20px) scale(0.95);
    }
  }

  .empty-state-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    max-width: 700px;
    padding: 40px;
    z-index: 1;
  }

  .hero-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 32px;
  }

  .hero-icon {
    position: relative;
    width: 120px;
    height: 120px;
    margin-bottom: 28px;
  }

  .icon-ring {
    position: absolute;
    border-radius: 50%;
    border: 2px solid var(--color-primary-400);
    opacity: 0.4;
    animation: pulseRing 3s ease-out infinite;
  }

  .icon-ring-1 {
    inset: 0;
    animation-delay: 0s;
  }

  .icon-ring-2 {
    inset: -15px;
    border-color: var(--color-primary-300);
    animation-delay: 0.5s;
  }

  .icon-ring-3 {
    inset: -30px;
    border-color: var(--color-primary-200);
    animation-delay: 1s;
  }

  @keyframes pulseRing {
    0% {
      transform: scale(1);
      opacity: 0.4;
    }
    100% {
      transform: scale(1.5);
      opacity: 0;
    }
  }

  .icon-core {
    position: absolute;
    inset: 15px;
    background: var(--gradient-primary);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow:
      var(--shadow-xl),
      0 0 40px var(--color-primary-500);
  }

  .icon-core svg {
    width: 40px;
    height: 40px;
    color: white;
  }

  .hero-title {
    font-size: 42px;
    font-weight: 800;
    color: var(--text-primary);
    margin-bottom: 12px;
    letter-spacing: -0.03em;
    text-align: center;
    text-shadow: 0 2px 20px rgba(0, 0, 0, 0.1);
    min-height: 52px;
  }

  .hero-title::after {
    content: '|';
    animation: blink-cursor 1s step-end infinite;
    color: var(--color-primary-500);
    margin-left: 2px;
  }

  @keyframes blink-cursor {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0;
    }
  }

  .hero-subtitle {
    font-size: 18px;
    color: var(--text-secondary);
    text-align: center;
    font-weight: 500;
    min-height: 27px;
  }

  .quick-actions {
    margin-bottom: 32px;
    text-align: center;
  }

  .action-label {
    font-size: 13px;
    color: var(--text-tertiary);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 16px;
  }

  .action-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    justify-content: center;
  }

  .action-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 20px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 100px;
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
    cursor: pointer;
    transition: all 0.25s ease;
    box-shadow: var(--shadow-sm);
  }

  .action-chip:hover {
    background: var(--gradient-primary);
    color: white;
    border-color: transparent;
    transform: translateY(-3px);
    box-shadow:
      var(--shadow-lg),
      0 10px 30px rgba(20, 184, 166, 0.3);
  }

  .action-chip svg {
    width: 18px;
    height: 18px;
  }

  .features-section {
    text-align: center;
    width: 100%;
  }

  .section-label {
    font-size: 13px;
    color: var(--text-tertiary);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 20px;
  }

  .features-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
  }

  .feature-card {
    background: var(--bg-secondary);
    padding: 24px 20px;
    border-radius: 16px;
    text-align: center;
    box-shadow: var(--shadow-md);
    transition: all 0.3s ease;
    border: 1px solid var(--border-color);
  }

  .feature-card:hover {
    transform: translateY(-8px);
    box-shadow: var(--shadow-xl);
    border-color: var(--color-primary-300);
    background: var(--bg-primary);
  }

  .feature-icon {
    width: 56px;
    height: 56px;
    margin: 0 auto 16px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: var(--shadow-md);
  }

  .feature-icon svg {
    width: 28px;
    height: 28px;
    color: white;
  }

  .feature-icon-1 {
    background: linear-gradient(135deg, var(--color-primary-500) 0%, var(--color-primary-600) 100%);
  }

  .feature-icon-2 {
    background: linear-gradient(135deg, var(--color-blue-500) 0%, var(--color-blue-600) 100%);
  }

  .feature-icon-3 {
    background: linear-gradient(135deg, var(--color-warning-500) 0%, var(--color-warning-600) 100%);
  }

  .feature-content h3 {
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 6px;
  }

  .feature-content p {
    font-size: 13px;
    color: var(--text-secondary);
  }

  .floating-particles {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
  }

  .particle {
    position: absolute;
    bottom: -10px;
    background: var(--color-primary-400);
    border-radius: 50%;
    opacity: 0.15;
    animation: float-up linear infinite;
  }

  @keyframes float-up {
    0% {
      transform: translateY(0) rotate(0deg);
      opacity: 0;
    }
    10% {
      opacity: 0.15;
    }
    90% {
      opacity: 0.15;
    }
    100% {
      transform: translateY(-100vh) rotate(720deg);
      opacity: 0;
    }
  }

  .prompt-carousel {
    margin-bottom: 36px;
    width: 100%;
  }

  .carousel-label {
    font-size: 13px;
    color: var(--text-tertiary);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 14px;
    text-align: center;
  }

  .carousel-track {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    justify-content: center;
    animation: fadeInUp 0.6s ease 1.5s both;
  }

  @keyframes fadeInUp {
    from {
      opacity: 0;
      transform: translateY(16px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .carousel-item {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-xl, 16px);
    font-size: 13px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition-base, 200ms);
    box-shadow: var(--shadow-xs);
    max-width: 260px;
  }

  .carousel-item:hover {
    background: var(--gradient-primary);
    color: #ffffff;
    border-color: transparent;
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }

  .carousel-item:active {
    transform: translateY(0);
  }

  .carousel-emoji {
    font-size: 18px;
    flex-shrink: 0;
  }

  .carousel-text {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
