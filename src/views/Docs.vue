<template>
  <div class="docs-page">
    <header class="docs-topbar">
      <router-link to="/" class="topbar-back">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
      </router-link>
      <div class="topbar-title">CodingMatrix</div>
      <div class="topbar-divider"></div>
      <div class="topbar-sub">文档中心</div>
      <div class="topbar-spacer"></div>
      <div class="topbar-search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input v-model="search" type="text" placeholder="搜索文档..." />
      </div>
    </header>

    <div class="docs-body">
      <aside class="docs-aside">
        <div class="aside-inner">
          <div v-for="group in nav" :key="group.label" class="aside-group">
            <div class="aside-label">{{ group.label }}</div>
            <a
              v-for="item in group.items"
              :key="item.id"
              :class="['aside-link', { active: active === item.id }]"
              :href="'#' + item.id"
              @click.prevent="go(item.id)"
            >
              <span class="aside-dot"></span>
              {{ item.name }}
            </a>
          </div>
        </div>
      </aside>

      <main ref="mainRef" class="docs-main">
        <!-- Hero -->
        <section id="overview" class="section">
          <div class="hero-card">
            <div class="hero-kicker">Platform Overview</div>
            <h1 class="hero-heading">CodingMatrix 智能代码生成平台</h1>
            <p class="hero-desc">基于多 Agent 协作的 AI 开发助手。集成 8+ AI 供应商，支持智能对话、项目生成、代码审查、工作流编排，覆盖 15+ 编程语言。</p>
            <div class="hero-stats">
              <div class="stat">
                <div class="stat-num">6</div>
                <div class="stat-text">核心模块</div>
              </div>
              <div class="stat">
                <div class="stat-num">8+</div>
                <div class="stat-text">AI 供应商</div>
              </div>
              <div class="stat">
                <div class="stat-num">20+</div>
                <div class="stat-text">API 端点</div>
              </div>
              <div class="stat">
                <div class="stat-num">15+</div>
                <div class="stat-text">生成语言</div>
              </div>
            </div>
          </div>
        </section>

        <!-- 核心功能 -->
        <section id="features" class="section">
          <div class="section-head">
            <h2>核心功能</h2>
          </div>
          <div class="card-list">
            <div v-for="f in features" :key="f.id" class="expand-card" :class="{ open: openId === f.id }">
              <button class="expand-trigger" @click="openId = openId === f.id ? null : f.id">
                <span class="expand-icon">{{ f.icon }}</span>
                <span class="expand-info">
                  <span class="expand-title">{{ f.title }}</span>
                  <span class="expand-brief">{{ f.brief }}</span>
                </span>
                <svg class="expand-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M6 9l6 6 6-6"/></svg>
              </button>
              <div v-if="openId === f.id" class="expand-body">
                <div v-for="(b, i) in f.blocks" :key="i" class="detail-block">
                  <h4>{{ b.title }}</h4>
                  <p v-if="b.text">{{ b.text }}</p>
                  <ul v-if="b.list">
                    <li v-for="(li, j) in b.list" :key="j">{{ li }}</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- AI 供应商 -->
        <section id="providers" class="section">
          <div class="section-head">
            <h2>支持的 AI 供应商</h2>
            <p class="section-sub">内置多个主流供应商适配器，支持自定义 base_url 接入任意兼容 OpenAI 接口的服务</p>
          </div>
          <div class="grid-2">
            <div v-for="p in providers" :key="p.name" class="provider-row">
              <div class="provider-left">
                <div class="provider-name">{{ p.name }}</div>
                <div class="provider-desc">{{ p.desc }}</div>
              </div>
              <div class="provider-tag">{{ p.models }}</div>
            </div>
          </div>
        </section>

        <!-- 快速开始 -->
        <section id="quickstart" class="section">
          <div class="section-head">
            <h2>快速开始</h2>
          </div>
          <div class="timeline">
            <div v-for="(s, i) in steps" :key="i" class="timeline-item">
              <div class="timeline-marker">{{ i + 1 }}</div>
              <div class="timeline-content">
                <h4>{{ s.title }}</h4>
                <p>{{ s.text }}</p>
                <pre v-if="s.code"><code>{{ s.code }}</code></pre>
              </div>
            </div>
          </div>
        </section>

        <!-- API Key -->
        <section id="apikey" class="section">
          <div class="section-head">
            <h2>API Key 管理</h2>
          </div>
          <div class="content-card">
            <p>平台使用 RSA 加密传输 API Key，服务端使用 Redis 内存存储，支持 TTL 自动过期。用户可同时配置多个供应商的 Key，系统根据任务类型自动路由到最优模型。</p>
            <div class="two-col">
              <div>
                <h4>安全机制</h4>
                <ul>
                  <li>RSA 公钥加密传输，防止中间人攻击</li>
                  <li>服务端仅在 Redis 中存储，TTL 自动过期</li>
                  <li>Token 用量统计可视化</li>
                  <li>支持 Key 轮换，旧 Key 自动失效</li>
                </ul>
              </div>
              <div>
                <h4>配置步骤</h4>
                <ol>
                  <li>进入「设置 → API Key 管理」</li>
                  <li>选择供应商类型</li>
                  <li>输入 API Key，系统自动加密上传</li>
                  <li>在「模型配置」中分配具体模型</li>
                </ol>
              </div>
            </div>
          </div>
        </section>

        <!-- Agent 协作 -->
        <section id="agent" class="section">
          <div class="section-head">
            <h2>Agent 协作架构</h2>
            <p class="section-sub">四个层级的 Agent 分工协作，交叉验证确保代码质量</p>
          </div>
          <div class="layer-stack">
            <div class="layer" style="--layer-color: #818cf8">
              <div class="layer-badge" style="background: rgba(129,140,248,0.12); color: #818cf8">决策层</div>
              <h4>Architect Agent</h4>
              <p>分析用户需求，拆解任务为可执行子任务列表，确定技术栈和项目结构。生成需求文档和技术设计方案。</p>
            </div>
            <div class="layer" style="--layer-color: #34d399">
              <div class="layer-badge" style="background: rgba(52,211,153,0.12); color: #34d399">执行层</div>
              <h4>Frontend / Backend Agent</h4>
              <p>根据设计方案分别生成前端和后端代码。前端负责 UI 组件、路由、状态管理；后端负责 API、数据库、业务逻辑。</p>
            </div>
            <div class="layer" style="--layer-color: #fbbf24">
              <div class="layer-badge" style="background: rgba(251,191,36,0.12); color: #fbbf24">审查层</div>
              <h4>Reviewer Agent</h4>
              <p>对生成的代码进行质量检查：代码规范、安全漏洞、性能问题、类型安全。输出审查报告和修复建议。</p>
            </div>
            <div class="layer" style="--layer-color: #f87171">
              <div class="layer-badge" style="background: rgba(248,113,113,0.12); color: #f87171">修复层</div>
              <h4>Fixer Agent</h4>
              <p>根据审查结果自动修复问题，支持多轮迭代直到所有检查通过。修复后的代码会重新提交审查。</p>
            </div>
          </div>
          <div class="content-card" style="margin-top: 16px">
            <h4>交叉验证机制</h4>
            <p>每个 Agent 完成任务后，结果会被其他 Agent 交叉验证。例如 Backend Agent 生成的 API 会被 Frontend Agent 验证接口兼容性，确保前后端联调无误。</p>
          </div>
        </section>

        <!-- 项目生成 -->
        <section id="project" class="section">
          <div class="section-head">
            <h2>项目生成与管理</h2>
          </div>
          <div class="content-card">
            <div class="two-col">
              <div>
                <h4>生成流程</h4>
                <ol>
                  <li>在 Agent 面板输入项目需求描述</li>
                  <li>Architect Agent 分析需求并生成任务计划</li>
                  <li>用户确认后多 Agent 并行执行</li>
                  <li>实时查看生成进度和中间产物</li>
                  <li>生成完成后在线预览、编辑或下载</li>
                </ol>
              </div>
              <div>
                <h4>支持的项目类型</h4>
                <ul>
                  <li><strong>Web 应用</strong> — Vue/React + Node.js/Python/Go</li>
                  <li><strong>API 服务</strong> — FastAPI / Express / Gin</li>
                  <li><strong>CLI 工具</strong> — Python Click / Go Cobra</li>
                  <li><strong>静态站点</strong> — HTML/CSS/JS + Tailwind</li>
                </ul>
                <h4>Git 集成</h4>
                <p>支持推送到 GitHub，自动创建仓库、初始化分支、提交代码。支持分支管理和 Merge Request。</p>
              </div>
            </div>
          </div>
        </section>

        <!-- 特色功能 -->
        <section id="special" class="section">
          <div class="section-head">
            <h2>特色功能</h2>
          </div>
          <div class="icon-grid">
            <div v-for="s in specials" :key="s.title" class="icon-card">
              <div class="icon-card-icon">{{ s.icon }}</div>
              <div class="icon-card-title">{{ s.title }}</div>
              <div class="icon-card-desc">{{ s.desc }}</div>
            </div>
          </div>
        </section>

        <!-- 技术架构 -->
        <section id="architecture" class="section">
          <div class="section-head">
            <h2>技术架构</h2>
          </div>
          <div class="stack-table">
            <div v-for="s in stack" :key="s.layer" class="stack-row">
              <div class="stack-layer">{{ s.layer }}</div>
              <div class="stack-tech">{{ s.tech }}</div>
              <div class="stack-note">{{ s.note }}</div>
            </div>
          </div>
        </section>

        <!-- 部署 -->
        <section id="deployment" class="section">
          <div class="section-head">
            <h2>部署指南</h2>
          </div>
          <div class="content-card">
            <div class="two-col">
              <div>
                <h4>环境要求</h4>
                <ul>
                  <li>Python 3.10+</li>
                  <li>Node.js 18+（前端构建）</li>
                  <li>Redis 6+（缓存和 Key 存储）</li>
                  <li>SQLite 3.35+（默认数据库）</li>
                </ul>
              </div>
              <div>
                <h4>本地开发</h4>
                <pre><code># 后端
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd src && npm install && npm run dev</code></pre>
              </div>
            </div>
            <h4>生产部署</h4>
            <pre><code># 构建前端
cd src && npm run build

# 启动（自动服务静态文件）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4</code></pre>
            <p>生产环境建议 Docker Compose 编排，包含 Redis、Nginx 反向代理、健康检查。</p>
          </div>
        </section>

        <!-- 安全 -->
        <section id="security" class="section">
          <div class="section-head">
            <h2>安全说明</h2>
          </div>
          <div class="grid-3">
            <div class="info-card">
              <h4>认证与授权</h4>
              <ul>
                <li>JWT 双 Token 机制</li>
                <li>角色权限：superadmin / admin / normal</li>
                <li>WebSocket Token 认证</li>
              </ul>
            </div>
            <div class="info-card">
              <h4>数据安全</h4>
              <ul>
                <li>RSA 加密传输 API Key</li>
                <li>bcrypt 密码哈希</li>
                <li>CSP 安全策略头</li>
                <li>敏感信息不出日志</li>
              </ul>
            </div>
            <div class="info-card">
              <h4>网络安全</h4>
              <ul>
                <li>CORS 跨域控制</li>
                <li>请求频率限制</li>
                <li>WebSocket 连接数限制</li>
              </ul>
            </div>
          </div>
        </section>

        <!-- 语言支持 -->
        <section id="languages" class="section">
          <div class="section-head">
            <h2>在线语言支持</h2>
          </div>
          <div class="notice-box">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <div>
              <strong>在线编译限制：</strong>仅支持 <strong>Python</strong> 和 <strong>JavaScript</strong> 在线运行。其他语言生成的代码需在本地验证。
            </div>
          </div>
          <div class="lang-chips">
            <span class="chip chip-ok">Python</span>
            <span class="chip chip-ok">JavaScript</span>
            <span v-for="l in langs" :key="l" class="chip">{{ l }}</span>
          </div>
        </section>

        <!-- FAQ -->
        <section id="faq" class="section">
          <div class="section-head">
            <h2>常见问题</h2>
          </div>
          <div class="card-list">
            <div v-for="f in faqs" :key="f.q" class="expand-card" :class="{ open: openFaq === f.q }">
              <button class="expand-trigger" @click="openFaq = openFaq === f.q ? null : f.q">
                <span class="expand-info">
                  <span class="expand-title">{{ f.q }}</span>
                </span>
                <svg class="expand-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M6 9l6 6 6-6"/></svg>
              </button>
              <div v-if="openFaq === f.q" class="expand-body">
                <p v-for="(p, i) in f.a" :key="i">{{ p }}</p>
              </div>
            </div>
          </div>
        </section>

        <footer class="docs-foot">
          <span>CodingMatrix &copy; 2024</span>
          <span class="foot-sep">&middot;</span>
          <span>智能代码生成平台</span>
        </footer>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'

const search = ref('')
const active = ref('overview')
const mainRef = ref(null)
const openId = ref(null)
const openFaq = ref(null)

const go = (id) => {
  const el = document.getElementById(id)
  if (!el || !mainRef.value) return
  mainRef.value.scrollTo({ top: el.offsetTop - mainRef.value.offsetTop + 4, behavior: 'smooth' })
}

let obs = null
onMounted(() => {
  nextTick(() => {
    if (!mainRef.value) return
    const secs = mainRef.value.querySelectorAll('.section[id]')
    obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) active.value = e.target.id
        }
      },
      { root: mainRef.value, rootMargin: '-60px 0px -65% 0px', threshold: 0 }
    )
    secs.forEach(s => obs.observe(s))
  })
})
onBeforeUnmount(() => { if (obs) obs.disconnect() })

const nav = [
  { label: '介绍', items: [
    { id: 'overview', name: '平台概览' },
    { id: 'features', name: '核心功能' },
    { id: 'providers', name: 'AI 供应商' },
  ]},
  { label: '使用指南', items: [
    { id: 'quickstart', name: '快速开始' },
    { id: 'apikey', name: 'API Key 管理' },
    { id: 'project', name: '项目生成' },
  ]},
  { label: '架构与技术', items: [
    { id: 'agent', name: 'Agent 协作' },
    { id: 'special', name: '特色功能' },
    { id: 'architecture', name: '技术架构' },
    { id: 'deployment', name: '部署指南' },
    { id: 'security', name: '安全说明' },
  ]},
  { label: '参考', items: [
    { id: 'languages', name: '语言支持' },
    { id: 'faq', name: '常见问题' },
  ]},
]

const features = [
  { id: 'chat', icon: '💬', title: '智能对话与代码生成', brief: '支持多轮对话，自动理解需求并生成代码',
    blocks: [
      { title: '对话能力', text: '基于大语言模型的多轮对话引擎，支持上下文记忆、意图识别、代码补全。用户用自然语言描述需求，系统自动生成可运行代码。' },
      { title: '支持语言', list: ['Python — Flask / FastAPI / Django', 'JavaScript / TypeScript — React / Vue / Next.js / Express', 'Go — Gin / Echo', 'Rust — Actix / Axum', 'Java — Spring Boot', 'PHP — Laravel'] },
      { title: '在线测试', text: 'Python 和 JavaScript 支持服务端在线编译运行。其他语言生成代码后需在本地测试。' },
    ]},
  { id: 'collab', icon: '🤖', title: '多 Agent 协作', brief: '决策、执行、审查、修复四层分工',
    blocks: [
      { title: '工作流程', text: 'Architect 分析需求拆解任务 → Frontend/Backend 并行生成代码 → Reviewer 质量审查 → Fixer 自动修复。支持实时进度查看。' },
      { title: '交叉验证', text: '每个 Agent 的输出会被其他 Agent 交叉验证。后端生成的 API 会被前端验证接口兼容性。' },
      { title: '质量保障', text: 'Reviewer 检查代码规范、安全漏洞、性能问题。Fixer 根据报告自动修复，支持多轮迭代。' },
    ]},
  { id: 'provider', icon: '☁️', title: '多供应商支持', brief: '内置 8+ 供应商，支持自定义接入',
    blocks: [
      { title: '内置供应商', text: '硅基流动、阿里百炼、智谱 AI、DeepSeek、OpenAI、Anthropic、Google Gemini、Moonshot。' },
      { title: '自定义接入', text: '通过自定义 base_url + 协议类型接入任意兼容 OpenAI 接口的服务，包括 Ollama、vLLM 等。' },
      { title: '智能路由', text: '根据任务类型自动选择最优模型，支持手动覆盖。' },
    ]},
  { id: 'projgen', icon: '📂', title: '项目生成与管理', brief: '输入需求一键生成完整项目',
    blocks: [
      { title: '生成流程', text: '输入需求 → Architect 生成计划 → 用户确认 → 多 Agent 并行执行 → 在线预览/编辑/下载。' },
      { title: 'Git 集成', text: '支持推送到 GitHub，自动创建仓库、分支管理、Merge Request。' },
    ]},
  { id: 'keym', icon: '🔑', title: 'API Key 管理', brief: 'RSA 加密传输，Redis 内存存储',
    blocks: [
      { title: '安全机制', text: 'RSA 公钥加密传输，Redis TTL 自动过期，敏感信息不出日志。' },
      { title: '多供应商', text: '同时配置多个供应商 Key，系统自动路由。Token 用量可视化。' },
    ]},
  { id: 'more', icon: '✨', title: '更多功能', brief: 'PPT 生成、图像生成、知识库等',
    blocks: [
      { title: '功能列表', list: ['PPT 自动生成 — 模板、图片搜索、PDF 导出', '图像生成 — Kolors 模型，文生图/图生图', 'GirlAI 虚拟助手', '知识库管理与 RAG 检索', 'Docker / Nginx 可视化管理', '系统监控与日志'] },
    ]},
]

const providers = [
  { name: '硅基流动', desc: '国产高性能推理平台', models: 'Qwen / DeepSeek / GLM' },
  { name: '阿里百炼', desc: '阿里云 AI 服务', models: 'Qwen-Turbo / Plus / Max' },
  { name: '智谱 AI', desc: '清华系大模型', models: 'GLM-4 / CogView' },
  { name: 'DeepSeek', desc: '深度求索', models: 'DeepSeek-V2 / Coder' },
  { name: 'OpenAI', desc: '全球领先 AI 公司', models: 'GPT-4o / o1' },
  { name: 'Anthropic', desc: 'AI 安全研究', models: 'Claude 3.5 Sonnet' },
  { name: 'Google', desc: '谷歌 AI', models: 'Gemini Pro / Flash' },
  { name: 'Moonshot', desc: '月之暗面', models: 'Moonshot-v1 系列' },
]

const steps = [
  { title: '配置 API Key', text: '进入「设置 → API Key 管理」，添加至少一个供应商的 Key。推荐硅基流动或 DeepSeek。' },
  { title: '选择模型', text: '在「设置 → 模型配置」中为不同任务分配模型。系统会推荐可用模型。' },
  { title: '开始对话', text: '进入 Agent 面板，输入项目需求。Architect 会分析需求并生成任务计划。' },
  { title: '确认执行', text: '查看计划后点击「开始执行」，多 Agent 并行工作，实时查看进度。' },
  { title: '预览下载', text: '生成完成后在线预览、编辑，或打包下载、推送到 GitHub。' },
]

const specials = [
  { icon: '📊', title: 'PPT 自动生成', desc: '输入主题生成演示文稿，支持模板和 PDF 导出' },
  { icon: '🎨', title: '图像生成', desc: 'Kolors 模型，文生图、图生图、风格迁移' },
  { icon: '💬', title: 'GirlAI 助手', desc: '虚拟 AI 助手，个性化对话和知识问答' },
  { icon: '📚', title: '知识库', desc: '上传文档构建知识库，RAG 检索增强生成' },
  { icon: '🐳', title: 'Docker 管理', desc: '容器管理、镜像构建、资源监控' },
  { icon: '🌐', title: 'Nginx 配置', desc: '可视化配置，反向代理、SSL、负载均衡' },
  { icon: '📈', title: '系统监控', desc: 'CPU/内存/磁盘/网络实时监控' },
  { icon: '🔄', title: '工作流编排', desc: '可视化管理，审批、执行、重试' },
]

const stack = [
  { layer: '前端', tech: 'Vue 3 + Vite + Element Plus + Pinia', note: '单页应用，组件化，响应式状态' },
  { layer: '后端', tech: 'FastAPI + SQLAlchemy + SQLite + Redis', note: '异步 API，ORM，内存缓存，任务队列' },
  { layer: 'AI 层', tech: '多供应商适配器 + 模型路由器 + Agent 引擎', note: '统一封装，智能路由，任务编排' },
  { layer: '基础设施', tech: 'Docker + Nginx + WebSocket + SSE', note: '容器化，反向代理，实时通信' },
]

const langs = ['Go', 'Rust', 'Java', 'C/C++', 'PHP', 'Ruby', 'Swift', 'Kotlin', 'C#', 'TypeScript', 'Shell', 'SQL', 'HTML/CSS']

const faqs = [
  { q: '支持哪些编程语言？', a: ['在线编译仅支持 Python 和 JavaScript。代码生成支持 15+ 种语言，包括 Go、Rust、Java、C/C++、PHP、Ruby、Swift、Kotlin 等。', '其他语言需在本地测试运行。'] },
  { q: 'API Key 如何保证安全？', a: ['RSA 公钥加密传输，服务端仅 Redis 内存存储，TTL 自动过期。', '密钥不出现在日志、前端响应或数据库中。'] },
  { q: '生成失败怎么办？', a: ['检查 Key 有效性和余额。查看系统日志了解错误原因。', '尝试更换模型或供应商。复杂项目可简化需求后重试。'] },
  { q: '如何选择合适的模型？', a: ['架构设计推荐 GPT-4o 或 Claude 3.5 Sonnet。代码生成推荐 DeepSeek-Coder 或 Qwen-Plus。', '系统支持自动路由，也可手动指定。'] },
  { q: '可以同时运行多个项目吗？', a: ['每用户最多 2 个并发会话。超时 10 分钟自动清理。'] },
  { q: '如何推送到 GitHub？', a: ['生成完成后点击「推送到 GitHub」，首次需授权。系统自动创建仓库并提交代码。'] },
  { q: '支持私有部署吗？', a: ['支持。需要 Python 3.10+、Node.js 18+、Redis 6+。参考「部署指南」章节。'] },
]
</script>

<style scoped>
.docs-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg-secondary, #f8fafc);
  color: var(--text-primary, #1e293b);
  overflow: hidden;
}

/* ── Topbar ── */
.docs-topbar {
  height: 52px;
  background: var(--bg-primary, #fff);
  border-bottom: 1px solid var(--border-color, #e2e8f0);
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 12px;
  flex-shrink: 0;
  z-index: 10;
}
.topbar-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  color: var(--text-secondary, #64748b);
  transition: all 0.15s;
}
.topbar-back:hover {
  background: var(--bg-tertiary, #f1f5f9);
  color: var(--text-primary);
}
.topbar-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.topbar-divider {
  width: 1px;
  height: 20px;
  background: var(--border-color, #e2e8f0);
}
.topbar-sub {
  font-size: 13px;
  color: var(--text-tertiary, #94a3b8);
}
.topbar-spacer { flex: 1; }
.topbar-search {
  position: relative;
  width: 220px;
}
.topbar-search svg {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary, #94a3b8);
  pointer-events: none;
}
.topbar-search input {
  width: 100%;
  padding: 6px 10px 6px 30px;
  background: var(--bg-secondary, #f8fafc);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.topbar-search input::placeholder { color: var(--text-tertiary, #94a3b8); }
.topbar-search input:focus { border-color: var(--primary, #14b8a6); }

/* ── Body ── */
.docs-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ── Aside ── */
.docs-aside {
  width: 200px;
  background: var(--bg-primary, #fff);
  border-right: 1px solid var(--border-color, #e2e8f0);
  overflow-y: auto;
  flex-shrink: 0;
}
.docs-aside::-webkit-scrollbar { width: 3px; }
.docs-aside::-webkit-scrollbar-thumb { background: var(--border-color, #e2e8f0); border-radius: 2px; }
.aside-inner { padding: 16px 0; }
.aside-group { margin-bottom: 20px; }
.aside-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 0 16px;
  margin-bottom: 4px;
}
.aside-link {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px 6px 20px;
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  text-decoration: none;
  cursor: pointer;
  transition: all 0.12s;
  border-left: 2px solid transparent;
}
.aside-link:hover {
  color: var(--text-primary);
  background: var(--bg-secondary, #f8fafc);
}
.aside-link.active {
  color: var(--primary, #14b8a6);
  border-left-color: var(--primary, #14b8a6);
  background: var(--bg-secondary, #f8fafc);
  font-weight: 500;
}
.aside-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--border-color, #e2e8f0);
  flex-shrink: 0;
  transition: background 0.12s;
}
.aside-link.active .aside-dot { background: var(--primary, #14b8a6); }

/* ── Main ── */
.docs-main {
  flex: 1;
  overflow-y: auto;
  padding: 28px 36px 60px;
  scroll-behavior: smooth;
}
.docs-main::-webkit-scrollbar { width: 5px; }
.docs-main::-webkit-scrollbar-thumb { background: var(--border-color, #e2e8f0); border-radius: 3px; }

.section {
  margin-bottom: 48px;
  scroll-margin-top: 12px;
}

/* ── Hero ── */
.hero-card {
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 12px;
  padding: 32px;
  position: relative;
  overflow: hidden;
}
.hero-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--gradient-primary, linear-gradient(90deg, #14b8a6, #0d9488));
}
.hero-kicker {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--primary, #14b8a6);
  margin-bottom: 8px;
}
.hero-heading {
  font-size: 26px;
  font-weight: 800;
  color: var(--text-primary);
  margin: 0 0 10px 0;
  line-height: 1.3;
}
.hero-desc {
  font-size: 14px;
  color: var(--text-secondary, #64748b);
  line-height: 1.7;
  margin: 0 0 24px 0;
  max-width: 560px;
}
.hero-stats {
  display: flex;
  gap: 32px;
}
.stat { text-align: center; }
.stat-num {
  font-size: 28px;
  font-weight: 800;
  color: var(--primary, #14b8a6);
  line-height: 1;
}
.stat-text {
  font-size: 12px;
  color: var(--text-tertiary, #94a3b8);
  margin-top: 4px;
}

/* ── Section Head ── */
.section-head {
  margin-bottom: 20px;
}
.section-head h2 {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.section-sub {
  font-size: 13px;
  color: var(--text-tertiary, #94a3b8);
  margin: 6px 0 0 0;
}

/* ── Expand Card ── */
.card-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.expand-card {
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.15s;
}
.expand-card.open { border-color: var(--primary, #14b8a6); }
.expand-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  color: inherit;
}
.expand-icon { font-size: 24px; flex-shrink: 0; }
.expand-info { flex: 1; min-width: 0; }
.expand-title {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.expand-brief {
  display: block;
  font-size: 12px;
  color: var(--text-tertiary, #94a3b8);
  margin-top: 2px;
}
.expand-arrow {
  color: var(--text-tertiary, #94a3b8);
  flex-shrink: 0;
  transition: transform 0.2s;
}
.expand-card.open .expand-arrow { transform: rotate(180deg); }
.expand-body {
  padding: 0 18px 18px 56px;
  border-top: 1px solid var(--border-color, #e2e8f0);
}
.detail-block { margin-top: 14px; }
.detail-block h4 {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary, #14b8a6);
  margin: 0 0 4px 0;
}
.detail-block p {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  line-height: 1.7;
  margin: 0 0 6px 0;
}
.detail-block ul, .detail-block ol {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  line-height: 1.7;
  margin: 0;
  padding-left: 18px;
}
.detail-block li { margin-bottom: 3px; }

/* ── Content Card ── */
.content-card {
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  padding: 20px 24px;
}
.content-card > p {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  line-height: 1.7;
  margin: 0 0 14px 0;
}
.content-card h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 16px 0 8px 0;
}
.content-card h4:first-child { margin-top: 0; }
.content-card ul, .content-card ol {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  line-height: 1.7;
  margin: 0;
  padding-left: 18px;
}
.content-card li { margin-bottom: 3px; }
.content-card pre {
  background: var(--bg-secondary, #f8fafc);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  padding: 12px 16px;
  margin: 10px 0;
  overflow-x: auto;
}
.content-card code {
  font-size: 12px;
  color: var(--primary, #14b8a6);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

/* ── Provider Grid ── */
.grid-2 {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.provider-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 18px;
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  transition: border-color 0.12s;
}
.provider-row:hover { border-color: var(--primary, #14b8a6); }
.provider-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.provider-desc {
  font-size: 12px;
  color: var(--text-tertiary, #94a3b8);
}
.provider-tag {
  font-size: 11px;
  color: var(--primary, #14b8a6);
  background: var(--bg-secondary, #f0fdfa);
  padding: 3px 10px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}

/* ── Timeline ── */
.timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  position: relative;
  padding-left: 28px;
}
.timeline::before {
  content: '';
  position: absolute;
  left: 13px;
  top: 20px;
  bottom: 20px;
  width: 2px;
  background: var(--border-color, #e2e8f0);
}
.timeline-item {
  display: flex;
  gap: 16px;
  position: relative;
  padding: 12px 0;
}
.timeline-marker {
  position: absolute;
  left: -28px;
  width: 28px;
  height: 28px;
  background: var(--primary, #14b8a6);
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  z-index: 1;
}
.timeline-content {
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  padding: 16px 20px;
  flex: 1;
}
.timeline-content h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}
.timeline-content p {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  line-height: 1.6;
  margin: 0;
}

/* ── Layer Stack ── */
.layer-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.layer {
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-left: 3px solid var(--layer-color, #94a3b8);
  border-radius: 8px;
  padding: 16px 20px;
}
.layer-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 2px 8px;
  border-radius: 3px;
  margin-bottom: 6px;
}
.layer h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}
.layer p {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  line-height: 1.6;
  margin: 0;
}

/* ── Icon Grid ── */
.icon-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.icon-card {
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  padding: 18px;
  text-align: center;
  transition: all 0.15s;
}
.icon-card:hover {
  border-color: var(--primary, #14b8a6);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px var(--shadow-color, rgba(0,0,0,0.06));
}
.icon-card-icon { font-size: 24px; margin-bottom: 8px; }
.icon-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}
.icon-card-desc {
  font-size: 11px;
  color: var(--text-tertiary, #94a3b8);
  line-height: 1.5;
}

/* ── Stack Table ── */
.stack-table {
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  overflow: hidden;
}
.stack-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
}
.stack-row:not(:last-child) { border-bottom: 1px solid var(--border-color, #e2e8f0); }
.stack-layer {
  font-size: 11px;
  font-weight: 700;
  color: var(--primary, #14b8a6);
  background: var(--bg-secondary, #f0fdfa);
  padding: 3px 10px;
  border-radius: 4px;
  width: 56px;
  text-align: center;
  flex-shrink: 0;
}
.stack-tech {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 260px;
}
.stack-note {
  font-size: 12px;
  color: var(--text-tertiary, #94a3b8);
}

/* ── Grid 3 ── */
.grid-3 {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}
.info-card {
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  padding: 18px 20px;
}
.info-card h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 10px 0;
}
.info-card ul {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  line-height: 1.7;
  margin: 0;
  padding-left: 16px;
}
.info-card li { margin-bottom: 4px; }

/* ── Notice ── */
.notice-box {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 18px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 10px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #92400e;
  line-height: 1.6;
}
.notice-box svg { color: #f59e0b; flex-shrink: 0; margin-top: 1px; }
.notice-box strong { color: #92400e; }

/* ── Lang Chips ── */
.lang-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  font-size: 12px;
  padding: 5px 12px;
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
  color: var(--text-secondary, #64748b);
}
.chip-ok {
  border-color: #86efac;
  background: #f0fdf4;
  color: #166534;
  font-weight: 500;
}

/* ── Footer ── */
.docs-foot {
  padding: 24px 0;
  text-align: center;
  font-size: 12px;
  color: var(--text-tertiary, #94a3b8);
  border-top: 1px solid var(--border-color, #e2e8f0);
  margin-top: 24px;
}
.foot-sep { margin: 0 6px; }

/* ── Responsive ── */
@media (max-width: 768px) {
  .docs-aside { display: none; }
  .docs-main { padding: 20px 16px 40px; }
  .topbar-search { display: none; }
  .two-col { grid-template-columns: 1fr; }
  .hero-stats { flex-wrap: wrap; gap: 20px; }
  .icon-grid { grid-template-columns: repeat(2, 1fr); }
  .grid-3 { grid-template-columns: 1fr; }
}
</style>
