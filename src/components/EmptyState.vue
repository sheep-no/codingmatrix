<template>
  <div class="empty-state idle-stage" role="region" aria-label="对话待机画面">
    <div class="idle-atmosphere" aria-hidden="true">
      <div class="idle-grid"></div>
      <div class="idle-wash idle-wash-a"></div>
      <div class="idle-wash idle-wash-b"></div>
      <span class="idle-orbit"></span>
    </div>

    <div class="idle-board">
      <p class="idle-kicker">{{ greeting }} · CodingMatrix</p>
      <h1 class="idle-title">从一句需求开始</h1>
      <p class="idle-lead">
        把问题写进下方输入框。写代码、拆原理、改缺陷、起草文档，都可以从这里起手。
      </p>

      <div class="idle-prompts">
        <button
          v-for="item in prompts"
          :key="item.title"
          class="idle-card"
          type="button"
          :style="{ '--card-accent': item.accent }"
          @click="$emit('quick-prompt', item.prompt)"
        >
          <span class="idle-card-index">{{ item.index }}</span>
          <span class="idle-card-body">
            <span class="idle-card-title">{{ item.title }}</span>
            <span class="idle-card-copy">{{ item.copy }}</span>
          </span>
        </button>
      </div>

      <p class="idle-hint">Enter 发送 · Shift + Enter 换行</p>
    </div>
  </div>
</template>

<script setup>
  import { computed } from 'vue'

  defineEmits(['quick-prompt'])

  const greeting = computed(() => {
    const hour = new Date().getHours()
    if (hour < 5) return '夜深了'
    if (hour < 11) return '早上好'
    if (hour < 14) return '中午好'
    if (hour < 18) return '下午好'
    return '晚上好'
  })

  const prompts = [
    {
      index: '01',
      title: '写一段可运行的代码',
      copy: '带注释和测试，直接能跑。',
      prompt: '帮我写一个 Python 快速排序，带测试用例和简要注释',
      accent: '#c45c26'
    },
    {
      index: '02',
      title: '把概念讲清楚',
      copy: '用生活例子拆开技术名词。',
      prompt: '用一个生活中的例子解释什么是 RESTful API',
      accent: '#2a6f6a'
    },
    {
      index: '03',
      title: '定位代码问题',
      copy: '先找原因，再给修法。',
      prompt: '帮我分析这段代码可能的缺陷，并给出修改建议',
      accent: '#3d4a9c'
    },
    {
      index: '04',
      title: '起草一份说明',
      copy: '结构清楚，别人能接着写。',
      prompt: '帮我写一个项目 README 大纲，包含简介、安装、使用和贡献',
      accent: '#8a4a6a'
    }
  ]
</script>

<style scoped>
  .idle-stage {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 0;
    overflow: hidden;
    background:
      radial-gradient(1200px 520px at 12% -10%, color-mix(in srgb, var(--accent-primary) 16%, transparent), transparent 58%),
      var(--bg-primary);
  }

  .idle-atmosphere {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }

  .idle-grid {
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(to right, color-mix(in srgb, var(--control-border) 70%, transparent) 1px, transparent 1px),
      linear-gradient(to bottom, color-mix(in srgb, var(--control-border) 70%, transparent) 1px, transparent 1px);
    background-size: 48px 48px;
    mask-image: radial-gradient(ellipse at 50% 42%, #000 18%, transparent 72%);
    opacity: 0.45;
  }

  .idle-wash {
    position: absolute;
    border-radius: 50%;
    filter: blur(72px);
  }

  .idle-wash-a {
    width: min(42vw, 420px);
    height: min(42vw, 420px);
    right: -8%;
    top: -12%;
    background: color-mix(in srgb, var(--accent-primary) 28%, transparent);
  }

  .idle-wash-b {
    width: min(36vw, 340px);
    height: min(36vw, 340px);
    left: -6%;
    bottom: -16%;
    background: color-mix(in srgb, #c45c26 22%, transparent);
  }

  .idle-orbit {
    position: absolute;
    width: min(58vw, 640px);
    height: min(58vw, 640px);
    left: 50%;
    top: 46%;
    border: 1px solid color-mix(in srgb, var(--accent-primary) 28%, transparent);
    border-radius: 50%;
    transform: translate(-50%, -50%) rotate(12deg);
  }

  .idle-board {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    width: min(880px, calc(100% - 48px));
    padding: 28px 8px 16px;
  }

  .idle-kicker {
    margin: 0 0 14px;
    color: var(--accent-primary);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
  }

  .idle-title {
    margin: 0;
    max-width: 14ch;
    color: var(--text-primary);
    font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", "STSong", Georgia, serif;
    font-size: clamp(36px, 6vw, 64px);
    font-weight: 700;
    line-height: 1.08;
    letter-spacing: -0.04em;
  }

  .idle-lead {
    margin: 18px 0 32px;
    max-width: 36em;
    color: var(--text-secondary);
    font-size: clamp(15px, 1.7vw, 18px);
    line-height: 1.7;
  }

  .idle-prompts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }

  .idle-card {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 14px;
    min-height: var(--control-min-size);
    padding: 18px 18px 16px;
    border: 1px solid var(--control-border);
    border-left: 4px solid var(--card-accent);
    border-radius: 18px;
    background: color-mix(in srgb, var(--bg-secondary) 88%, transparent);
    color: inherit;
    text-align: left;
    cursor: pointer;
    backdrop-filter: blur(12px);
    transition:
      transform var(--motion-fast),
      border-color var(--motion-fast),
      background var(--motion-fast),
      box-shadow var(--motion-fast);
  }

  .idle-card:hover,
  .idle-card:focus-visible {
    transform: translateY(-3px);
    background: var(--bg-secondary);
    border-color: color-mix(in srgb, var(--card-accent) 55%, var(--control-border));
    box-shadow: 0 18px 40px color-mix(in srgb, var(--card-accent) 18%, transparent);
    outline: none;
  }

  .idle-card-index {
    color: var(--card-accent);
    font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.08em;
    padding-top: 4px;
  }

  .idle-card-body {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }

  .idle-card-title {
    color: var(--text-primary);
    font-size: 16px;
    font-weight: 700;
  }

  .idle-card-copy {
    color: var(--text-secondary);
    font-size: 13px;
    line-height: 1.5;
  }

  .idle-hint {
    margin: 22px 0 0;
    color: var(--text-tertiary);
    font-size: 12px;
    letter-spacing: 0.04em;
  }

  @media (max-width: 720px) {
    .idle-board {
      width: min(100% - 32px, 880px);
      padding: 12px 0 8px;
    }

    .idle-prompts {
      grid-template-columns: 1fr;
    }

    .idle-title {
      max-width: none;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .idle-card,
    .idle-card:hover,
    .idle-card:focus-visible {
      transition: none;
      transform: none;
    }
  }
</style>
