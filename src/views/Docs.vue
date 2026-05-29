<template>
  <div class="docs-standalone">
    <header class="docs-header">
      <div class="header-content">
        <router-link to="/" class="back-btn">
          <svg class="back-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          返回首页
        </router-link>
        <h1 class="header-title">文档中心</h1>
      </div>
    </header>

    <div class="docs-body">
      <aside class="docs-sidebar">
        <nav class="sidebar-nav">
          <div class="nav-section">
            <h3 class="nav-heading">功能介绍</h3>
            <ul>
              <li v-for="item in featureIntro" :key="item.id">
                <a :href="`#feature-${item.id}`" class="nav-link" @click.prevent="scrollTo(`feature-${item.id}`)">{{ item.title }}</a>
              </li>
            </ul>
          </div>
          <div class="nav-section">
            <h3 class="nav-heading">常见问题</h3>
            <ul>
              <li v-for="item in faqs" :key="item.id">
                <a :href="`#faq-${item.id}`" class="nav-link" @click.prevent="scrollTo(`faq-${item.id}`)">{{ item.title }}</a>
              </li>
            </ul>
          </div>
          <div class="nav-section">
            <h3 class="nav-heading">使用指南</h3>
            <ul>
              <li v-for="item in guides" :key="item.id">
                <a :href="`#guide-${item.id}`" class="nav-link" @click.prevent="scrollTo(`guide-${item.id}`)">{{ item.title }}</a>
              </li>
            </ul>
          </div>
          <div class="nav-section">
            <h3 class="nav-heading">技术说明</h3>
            <ul>
              <li v-for="item in techDocs" :key="item.id">
                <a :href="`#tech-${item.id}`" class="nav-link" @click.prevent="scrollTo(`tech-${item.id}`)">{{ item.title }}</a>
              </li>
            </ul>
          </div>
        </nav>
      </aside>

      <main class="docs-main">
        <section id="features" class="doc-section">
          <h2 class="section-title">项目功能介绍</h2>
          <div class="feature-hero">
            <div class="hero-text">
              <h3>CodingMatrix 智能代码生成平台</h3>
              <p>基于多 Agent 协作的 AI 开发助手，支持智能对话、项目生成、代码审查等功能。</p>
            </div>
          </div>
          <div class="doc-cards">
            <div v-for="feature in featureIntro" :id="`feature-${feature.id}`" :key="feature.id" class="doc-card">
              <div class="card-icon">{{ feature.icon }}</div>
              <h3 class="card-title">{{ feature.title }}</h3>
              <p class="card-desc">{{ feature.description }}</p>
              <router-link :to="feature.link" class="card-link">了解详细 →</router-link>
            </div>
          </div>
        </section>

        <section id="faq" class="doc-section">
          <h2 class="section-title">常见问题</h2>
          <div class="notice-card">
            <div class="notice-icon">⚠</div>
            <div class="notice-text">
              <h3>在线测试支持的语言</h3>
              <p>平台目前仅支持 <strong>Python</strong> 和 <strong>JavaScript</strong> 的在线编译和验证。</p>
              <p>其他语言生成的代码无法在服务器端测试，请在本地环境中验证。</p>
            </div>
          </div>
          <div class="doc-cards">
            <div v-for="faq in faqs" :id="`faq-${faq.id}`" :key="faq.id" class="doc-card">
              <h3 class="card-title">{{ faq.title }}</h3>
              <p class="card-desc">{{ faq.description }}</p>
              <router-link :to="faq.link" class="card-link">阅读更多 →</router-link>
            </div>
          </div>
        </section>

        <section id="guides" class="doc-section">
          <h2 class="section-title">使用指南</h2>
          <div class="doc-cards">
            <div v-for="guide in guides" :id="`guide-${guide.id}`" :key="guide.id" class="doc-card">
              <h3 class="card-title">{{ guide.title }}</h3>
              <p class="card-desc">{{ guide.description }}</p>
              <router-link :to="guide.link" class="card-link">阅读更多 →</router-link>
            </div>
          </div>
        </section>

        <section id="tech" class="doc-section">
          <h2 class="section-title">技术说明</h2>
          <div class="doc-cards">
            <div v-for="tech in techDocs" :id="`tech-${tech.id}`" :key="tech.id" class="doc-card">
              <h3 class="card-title">{{ tech.title }}</h3>
              <p class="card-desc">{{ tech.description }}</p>
              <router-link :to="tech.link" class="card-link">阅读更多 →</router-link>
            </div>
          </div>
        </section>
      </main>
    </div>

    <footer class="docs-footer">
      <p>&copy; 2024 AI 助手 &middot; 文档中心</p>
    </footer>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const featureIntro = ref([
  { id: 1, title: '智能对话与代码生成', description: '支持多轮对话，自动理解需求并生成代码。覆盖 Python、JavaScript、Go、Rust 等主流语言，支持在线测试验证。', icon: '💬', link: '/docs/features' },
  { id: 2, title: 'Agent 协作开发', description: '多 Agent 分工合作：决策层分析规划、执行层生成代码、审查层检查质量、修复层改进问题，交叉验证确保方案可行性。', icon: '🤖', link: '/docs/features' },
  { id: 3, title: '多供应商支持', description: '内置硅基流动、阿里百炼、智谱、DeepSeek、OpenAI、Anthropic 等供应商。支持自定义 base_url + 协议类型添加任意 API 服务，自动拉取模型列表。', icon: '☁️', link: '/docs/features' },
  { id: 4, title: '项目生成与管理', description: '输入需求一键生成完整项目结构，支持 Git 集成、GitHub 推送、分支管理。工作流可视化管理，支持审批和执行。', icon: '📂', link: '/docs/features' },
  { id: 5, title: 'API Key 管理', description: 'RSA 加密传输，Redis 内存存储，TTL 自动过期。支持多供应商 Key 同时配置，Token 使用统计可视化。', icon: '🔑', link: '/docs/apikey-guide' },
  { id: 6, title: '特色功能', description: 'PPT 自动生成、图像生成 (Kolors)、GirlAI 虚拟助手、知识库管理、文件预览、任务队列、系统监控等丰富功能。', icon: '✨', link: '/docs/features' }
])

const faqs = ref([
  { id: 10, title: '支持哪些编程语言？', description: '平台目前仅支持 Python 和 JavaScript 的在线编译和验证。其他语言生成的代码无法在服务器端测试，请在本地环境中验证。', link: '/docs/supported-languages' },
  { id: 11, title: '如何开始使用？', description: '了解如何使用平台生成项目的完整流程。', link: '/docs/getting-started' },
  { id: 12, title: '生成失败怎么办？', description: '了解错误处理和问题排查方法。', link: '/docs/troubleshooting' }
])

const guides = ref([
  { id: 20, title: '快速开始', description: '环境配置、依赖安装、启动服务、常见问题排查。', link: '/docs/getting-started' },
  { id: 21, title: 'API Key 使用指南', description: 'API Key 配置、管理和使用详细说明，包含多供应商和 Token 统计。', link: '/docs/apikey-guide' },
  { id: 22, title: '模型配置指南', description: '如何根据不同的任务需求选择合适的模型和供应商。', link: '/docs/model-config' },
  { id: 23, title: '项目结构说明', description: '了解生成项目的标准目录结构和开发约定。', link: '/docs/project-structure' }
])

const techDocs = ref([
  { id: 30, title: '架构设计', description: '了解系统整体架构和各组件职责划分。', link: '/docs/architecture' },
  { id: 31, title: '部署指南', description: '如何部署平台到生产环境。', link: '/docs/deployment' },
  { id: 32, title: '安全说明', description: '平台安全机制和用户数据保护措施。', link: '/docs/security' },
  { id: 33, title: 'API 文档', description: '完整的 API 端点文档和使用示例。', link: '/docs/api' }
])

const scrollTo = (id) => {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<style scoped>
.docs-standalone {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #0f172a;
  color: #e2e8f0;
}

.docs-header {
  height: 64px;
  background: rgba(15, 23, 42, 0.95);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
  padding: 0 32px;
  max-width: 1400px;
  margin: 0 auto;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #94a3b8;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: color 0.2s;
}

.back-btn:hover { color: #ffffff; }

.back-icon { width: 18px; height: 18px; }

.header-title {
  font-size: 18px;
  font-weight: 700;
  color: #ffffff;
  margin: 0;
}

.docs-body {
  display: flex;
  flex: 1;
}

.docs-sidebar {
  width: 240px;
  background: rgba(15, 23, 42, 0.5);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  overflow-y: auto;
  flex-shrink: 0;
  padding: 24px 0;
}

.sidebar-nav { padding: 0 16px; }

.nav-section { margin-bottom: 28px; }

.nav-heading {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin: 0 0 10px 8px;
}

.nav-section ul { list-style: none; padding: 0; margin: 0; }

.nav-section li { margin-bottom: 2px; }

.nav-link {
  display: block;
  padding: 8px 12px;
  color: #94a3b8;
  text-decoration: none;
  font-size: 13px;
  border-radius: 6px;
  transition: all 0.2s;
}

.nav-link:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #e2e8f0;
}

.docs-main {
  flex: 1;
  overflow-y: auto;
  padding: 40px;
}

.doc-section { margin-bottom: 56px; }

.section-title {
  font-size: 26px;
  font-weight: 700;
  color: #ffffff;
  margin: 0 0 24px 0;
  padding-bottom: 12px;
  border-bottom: 2px solid rgba(99, 102, 241, 0.4);
}

.feature-hero {
  padding: 28px 32px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.15));
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 16px;
  margin-bottom: 24px;
}

.hero-text h3 {
  font-size: 22px;
  font-weight: 700;
  color: #ffffff;
  margin: 0 0 8px 0;
}

.hero-text p {
  font-size: 15px;
  color: #cbd5e1;
  line-height: 1.7;
  margin: 0;
}

.card-icon {
  font-size: 28px;
  margin-bottom: 12px;
}

.notice-card {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 24px;
  background: rgba(250, 204, 21, 0.08);
  border: 1px solid rgba(250, 204, 21, 0.3);
  border-radius: 12px;
  margin-bottom: 24px;
}

.notice-icon {
  font-size: 24px;
  line-height: 1;
  flex-shrink: 0;
}

.notice-text h3 {
  font-size: 16px;
  font-weight: 600;
  color: #fbbf24;
  margin: 0 0 8px 0;
}

.notice-text p {
  font-size: 14px;
  color: #d4d4d8;
  line-height: 1.6;
  margin: 0;
}

.notice-text strong {
  color: #fbbf24;
}

.doc-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.doc-card {
  padding: 24px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  transition: all 0.3s;
}

.doc-card:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(99, 102, 241, 0.3);
  transform: translateY(-2px);
}

.card-title {
  font-size: 17px;
  font-weight: 600;
  color: #ffffff;
  margin: 0 0 8px 0;
}

.card-desc {
  font-size: 14px;
  color: #94a3b8;
  line-height: 1.6;
  margin: 0 0 16px 0;
}

.card-link {
  font-size: 13px;
  color: #818cf8;
  text-decoration: none;
  font-weight: 500;
  transition: color 0.2s;
}

.card-link:hover {
  color: #a5b4fc;
  text-decoration: underline;
}

.docs-footer {
  padding: 20px;
  text-align: center;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  color: #475569;
  font-size: 13px;
}

@media (max-width: 768px) {
  .docs-sidebar { display: none; }
  .docs-main { padding: 24px 16px; }
  .doc-cards { grid-template-columns: 1fr; }
  .header-content { padding: 0 16px; }
}
</style>
