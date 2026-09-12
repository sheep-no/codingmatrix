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
          <div v-for="group in filteredNav" :key="group.label" class="aside-group">
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
          <p v-if="search.trim() && !filteredNav.length" class="aside-empty">没有匹配的章节</p>
        </div>
      </aside>

      <main ref="mainRef" class="docs-main">
        <!-- Hero -->
        <section id="overview" class="section">
          <div class="hero-card">
            <div class="hero-kicker">Workbench Guide</div>
            <h1 class="hero-heading">CodingMatrix 智能工作台</h1>
            <p class="hero-desc">首页对话、按需联网、Agent 项目生成、PPT 成片、AI 绘画、虚拟姬和图表编辑都在同一套工作台里完成。</p>
            <div class="hero-stats">
              <div class="stat">
                <div class="stat-num">对话</div>
                <div class="stat-text">流式问答与联网</div>
              </div>
              <div class="stat">
                <div class="stat-num">Agent</div>
                <div class="stat-text">项目生成</div>
              </div>
              <div class="stat">
                <div class="stat-num">PPT</div>
                <div class="stat-text">大纲到成片</div>
              </div>
              <div class="stat">
                <div class="stat-num">工具</div>
                <div class="stat-text">绘画 / 虚拟姬 / 图表</div>
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
            <p class="section-sub">对话与生成默认走硅基流动；设置里可再接 OpenAI 兼容的自定义供应商</p>
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
            <p>对话、PPT、绘画和 Agent 都走你在设置里提交的硅基流动 Key。原始 Key 只在浏览器提交，经 RSA 加密后由服务端写入 Redis，不会写进仓库。</p>
            <div class="two-col">
              <div>
                <h4>安全机制</h4>
                <ul>
                  <li>RSA 公钥加密传输</li>
                  <li>服务端 Redis 存储，支持 TTL</li>
                  <li>前端只保留 token 与元数据，不回显原始 Key</li>
                  <li>聊天刷新续流时也不会把 Key 写入本地快照</li>
                </ul>
              </div>
              <div>
                <h4>配置步骤</h4>
                <ol>
                  <li>打开「设置 → API Key 管理」</li>
                  <li>提交硅基流动 Key，系统自动加密上传</li>
                  <li>需要兼容 OpenAI 接口时，再到「自定义供应商」填写 base_url</li>
                  <li>Agent 页面可在「Agent 模型配置」里指定会话模型</li>
                </ol>
              </div>
            </div>
          </div>
        </section>

        <section id="chat" class="section">
          <div class="section-head">
            <h2>首页对话与联网</h2>
            <p class="section-sub">从侧栏回到「会话」，或打开首页输入框即可提问</p>
          </div>
          <div class="content-card">
            <div class="two-col">
              <div>
                <h4>提问方式</h4>
                <ul>
                  <li>未登录会先引导登录；未配置 Key 会跳到设置页</li>
                  <li>支持深度推理、文件和图片附件</li>
                  <li>回答以 SSE 流式输出，搜索和生成阶段会显示进度</li>
                  <li>搜索中或回答中刷新页面，会恢复当前阶段并自动续请</li>
                </ul>
              </div>
              <div>
                <h4>联网检索</h4>
                <ul>
                  <li>按需联网：由快模型判断这条消息要不要搜</li>
                  <li>联网开启 / 关闭：强制搜索或只走模型</li>
                  <li>浅搜索一轮；多轮最多两轮，空结果会换词再搜</li>
                  <li>空消息和打招呼会跳过检索判断</li>
                </ul>
              </div>
            </div>
            <h4>侧栏历史</h4>
            <ul>
              <li>登录后侧栏列出最近对话，点击即可继续</li>
              <li>工具集「搜索历史」打开搜索框，按提示词关键词筛选当前用户会话</li>
              <li>清除关键词或关闭搜索框后，重新加载全部记录</li>
            </ul>
          </div>
        </section>

        <section id="ppt" class="section">
          <div class="section-head">
            <h2>PPT 生成</h2>
            <p class="section-sub">工具集 → PPT 生成，三步完成大纲到成片</p>
          </div>
          <div class="content-card">
            <div class="two-col">
              <div>
                <h4>三步流程</h4>
                <ol>
                  <li>填写主题，页数默认自动，也可选约 8 / 12 / 16 / 20 页</li>
                  <li>大纲流式起草：主区逐页出现卡片，刷新后会继续起草</li>
                  <li>审阅时可增删、重排和改稿，确认后导出成片</li>
                </ol>
              </div>
              <div>
                <h4>成片与历史</h4>
                <ul>
                  <li>导出进度走 WebSocket，刷新后按任务 ID 续看</li>
                  <li>成片主区显示进度条和页清单</li>
                  <li>删除前确认后立即清文件</li>
                  <li>生成物默认保留 30 天</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section id="project" class="section">
          <div class="section-head">
            <h2>项目生成与管理</h2>
          </div>
          <div class="content-card">
            <div class="two-col">
              <div>
                <h4>生成流程</h4>
                <ol>
                  <li>打开工具集「项目」，进入 Agent 工作台</li>
                  <li>输入需求并发送，云端以 SSE 流式返回思考和文件</li>
                  <li>需要本地执行时，Agent Host 会弹出审批</li>
                  <li>工作区展示进度、文件树、验证结果和待决策项</li>
                  <li>完成后可预览、下载或继续改需求</li>
                </ol>
              </div>
              <div>
                <h4>工作台能力</h4>
                <ul>
                  <li>会话历史、模型上下文和 Skills 同步</li>
                  <li>手机端单列布局，会话和文件从抽屉打开</li>
                  <li>VS Code 扩展可承接本地验证和 Host 动作</li>
                  <li>删除会话前会确认，确认后立即清记录</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section id="tools" class="section">
          <div class="section-head">
            <h2>工具集</h2>
            <p class="section-sub">侧栏「工具集」入口，菜单可滚动</p>
          </div>
          <div class="content-card">
            <div class="two-col">
              <div>
                <h4>工作台与创作</h4>
                <ul>
                  <li>项目 / 能力 / 文档 / 设置：进入对应页面</li>
                  <li>PPT 生成、AI 绘画、虚拟姬、图表编辑器</li>
                  <li>图表支持 XLSX / XLS / CSV / JSON，导出 PNG</li>
                </ul>
              </div>
              <div>
                <h4>工程与历史</h4>
                <ul>
                  <li>Docker 配置、临时工作流</li>
                  <li>搜索历史：按关键词筛选侧栏对话，请求 POST /api/v1/history</li>
                  <li>能力中心五个面板：视觉工具、知识库、代码沙箱、Skills、Agent Host</li>
                  <li>超级用户可从工具集打开管理员面板；admin 也可访问 /admin</li>
                  <li>管理后台：监控、日志、用户、Nginx、服务管理、资源配置；超级管理员另有模型管理与并发仪表板</li>
                  <li>外观支持白天、夜晚、随系统</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <!-- Agent 协作 -->
        <section id="agent" class="section">
          <div class="section-head">
            <h2>Agent 工作台</h2>
            <p class="section-sub">云端流式编排 + 本地 Host 执行，会话、文件和验证在同一页完成</p>
          </div>
          <div class="layer-stack">
            <div class="layer" style="--layer-color: #818cf8">
              <div class="layer-badge" style="background: rgba(129,140,248,0.12); color: #818cf8">云端</div>
              <h4>编排与流式输出</h4>
              <p>需求经 /api/v1/agent/orchestrate/stream 流式返回思考、步骤和生成文件。会话可暂停、恢复和取消。</p>
            </div>
            <div class="layer" style="--layer-color: #34d399">
              <div class="layer-badge" style="background: rgba(52,211,153,0.12); color: #34d399">本地</div>
              <h4>Agent Host</h4>
              <p>读写工作区、跑终端和本地验证前会先审批。断线后的验证结果会排队，恢复连接再回传。</p>
            </div>
            <div class="layer" style="--layer-color: #fbbf24">
              <div class="layer-badge" style="background: rgba(251,191,36,0.12); color: #fbbf24">技能</div>
              <h4>Skills</h4>
              <p>系统、用户和工作区 Skills 按命名空间隔离，可在能力中心管理并同步到工作台。</p>
            </div>
            <div class="layer" style="--layer-color: #f87171">
              <div class="layer-badge" style="background: rgba(248,113,113,0.12); color: #f87171">反馈</div>
              <h4>统一任务反馈</h4>
              <p>Agent、工作流、PPT 和绘画共用状态、进度、耗时和下一步操作，失败可重试，完成后可预览或下载。</p>
            </div>
          </div>
          <div class="content-card" style="margin-top: 16px">
            <h4>能力中心</h4>
            <p>工具集「能力」打开 /capabilities。视觉工具调用 /api/v1/vision；知识库走 /api/v1/aicloud/knowledge；代码沙箱执行 /api/v1/aicloud/execute；Skills 走 /api/v1/skills；Agent Host 列出 /api/v1/agent/host/sessions。</p>
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
cd src && npm install && npm run dev

# PPT 成片（可选）
celery -A app.celery_app worker --loglevel=info</code></pre>
              </div>
            </div>
            <h4>生产部署</h4>
            <pre><code># 构建前端
cd src && npm run build

# 启动（自动服务静态文件）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4</code></pre>
            <p>生产环境可用 Docker Compose 编排 Redis、Celery、Nginx 反向代理和健康检查。PPT 在 PPT_USE_CELERY=true 时由 Celery worker 导出成片。</p>
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
              <strong>代码沙箱：</strong>能力中心可在线运行 <strong>Python</strong>、<strong>JavaScript</strong> 和 <strong>Go</strong>。Agent 生成的其他语言由 Host 在本地验证。
            </div>
          </div>
          <div class="lang-chips">
            <span class="chip chip-ok">Python</span>
            <span class="chip chip-ok">JavaScript</span>
            <span class="chip chip-ok">Go</span>
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
          <span>CodingMatrix &copy; 2026</span>
          <span class="foot-sep">&middot;</span>
          <span>智能工作台</span>
        </footer>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'

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
    { id: 'chat', name: '首页对话' },
    { id: 'ppt', name: 'PPT 生成' },
    { id: 'project', name: '项目生成' },
    { id: 'tools', name: '工具集' },
  ]},
  { label: '架构与技术', items: [
    { id: 'agent', name: 'Agent 工作台' },
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

const filteredNav = computed(() => {
  const query = search.value.trim().toLowerCase()
  if (!query) return nav
  return nav
    .map(group => ({
      ...group,
      items: group.items.filter(item => item.name.toLowerCase().includes(query))
    }))
    .filter(group => group.items.length)
})

const features = [
  { id: 'chat', icon: '💬', title: '首页对话与联网', brief: '流式问答，按需检索，刷新后续上搜索或回答',
    blocks: [
      { title: '怎么用', text: '在首页输入问题。可开关联网、选择浅搜索或两轮搜索，并附带文件或图片。' },
      { title: '联网', list: ['按需联网由快模型判断', '强制开启或关闭联网', '空结果会换词再搜', '搜索中或回答中刷新会自动续请'] },
    ]},
  { id: 'collab', icon: '🤖', title: 'Agent 项目生成', brief: '云端流式编排，本地 Host 审批执行',
    blocks: [
      { title: '工作流程', text: '在工具集打开「项目」，发送需求后查看思考、文件和验证结果。本地动作需审批。' },
      { title: '同步', text: 'Skills 可在能力中心管理。VS Code 扩展可承接本地验证。' },
    ]},
  { id: 'provider', icon: '☁️', title: '模型接入', brief: '硅基流动内置，自定义供应商可补 OpenAI 兼容接口',
    blocks: [
      { title: '内置', text: '硅基流动提供对话、推理、代码、绘画和 OCR 等模型，例如 DeepSeek R1、Qwen、GLM、Kolors。' },
      { title: '自定义', text: '设置 → 自定义供应商，填写兼容 OpenAI 的 base_url。' },
    ]},
  { id: 'projgen', icon: '📂', title: 'PPT 与成片', brief: '流式大纲、审阅改稿、WebSocket 导出',
    blocks: [
      { title: '流程', text: '主题 → 流式大纲 → 增删重排 → 导出。页数默认自动。' },
      { title: '进度', text: '起草和导出刷新后都能续上。历史删除立即清文件，产物默认保留 30 天。' },
    ]},
  { id: 'keym', icon: '🔑', title: 'API Key 管理', brief: 'RSA 加密提交，Redis 存储 token',
    blocks: [
      { title: '安全机制', text: '浏览器提交原始 Key，服务端只存加密结果和 token。刷新续流不会把 Key 写入本地。' },
      { title: '入口', text: '设置 → API Key 管理。未配置 Key 时对话会引导到设置页。' },
    ]},
  { id: 'more', icon: '✨', title: '工具与能力', brief: '绘画、虚拟姬、图表、知识库和沙箱',
    blocks: [
      { title: '工具集', list: ['AI 绘画 — Kolors 文生图', '虚拟姬 — 回合式陪伴对话', '图表编辑器 — 表格导入与 PNG 导出', '能力中心 — 视觉、知识库、沙箱、Skills、Host', '搜索历史 — 按关键词筛选侧栏对话', '管理员面板 — 监控、日志、用户与系统配置'] },
    ]},
]

const providers = [
  { name: '硅基流动', desc: '默认对话、推理、代码、绘画入口', models: 'DeepSeek R1 / Qwen / GLM / Kolors' },
  { name: '自定义供应商', desc: '设置里填写 OpenAI 兼容 base_url', models: '按你接入的服务而定' },
]

const steps = [
  { title: '登录工作台', text: '打开首页，用已有账号登录。未登录时发送消息会弹出登录。' },
  { title: '配置硅基流动 Key', text: '进入「设置 → API Key 管理」，提交 Key。系统用 RSA 加密上传。' },
  { title: '先在首页提问', text: '需要查资料时打开联网。按需模式由模型判断；搜索或回答中刷新会自动续上。' },
  { title: '按任务打开工具', text: 'PPT、绘画、虚拟姬、图表、项目都在侧栏工具集。能力页管理视觉、知识库、沙箱、Skills 和 Host。搜索历史用来筛选侧栏对话。超级用户可从工具集打开管理员面板，admin 也可访问 /admin。' },
  { title: '查看结果', text: '对话在首页继续；PPT 和绘画可看历史；Agent 在工作台预览文件。删除都是永久删除。' },
]

const specials = [
  { icon: '📊', title: 'PPT 生成', desc: '流式大纲、审阅改稿、导出成片，刷新不丢进度' },
  { icon: '🎨', title: 'AI 绘画', desc: 'Kolors 文生图，历史可删，产物默认保留 30 天' },
  { icon: '💬', title: '虚拟姬', desc: '回合式陪伴对话，使用当前用户的 API Key' },
  { icon: '📚', title: '知识库', desc: '在能力中心上传文档，供检索增强' },
  { icon: '🐳', title: 'Docker 配置', desc: '工具集里打开容器相关配置' },
  { icon: '📈', title: '图表编辑器', desc: '导入表格数据，六类图表，导出 PNG' },
  { icon: '🛠️', title: '能力中心', desc: '视觉、知识库、沙箱、Skills 与 Host' },
  { icon: '🔍', title: '搜索历史', desc: '按提示词关键词筛选侧栏对话，清除后恢复全部记录' },
  { icon: '🔧', title: '管理员面板', desc: '监控、日志、用户、Nginx、服务与资源配置；超级管理员另有模型管理与并发仪表板' },
  { icon: '🔄', title: '临时工作流', desc: '短任务编排，状态与重试跟 Agent 同一套反馈' },
]

const stack = [
  { layer: '前端', tech: 'Vue 3 + Vite + Pinia + Element Plus', note: '工作台路由、SSE 消费、主题切换' },
  { layer: '后端', tech: 'FastAPI + SQLAlchemy + SQLite + Redis + Celery', note: '对话、PPT 队列、Key 与会话' },
  { layer: 'AI 层', tech: '硅基流动模型目录 + 自定义 OpenAI 兼容供应商', note: '对话检索规划、Agent 编排、Kolors 绘画' },
  { layer: '实时通道', tech: 'SSE + WebSocket', note: '聊天/Agent 走 SSE，PPT 导出走 WebSocket' },
]

const langs = ['Rust', 'Java', 'C/C++', 'PHP', 'Ruby', 'Swift', 'Kotlin', 'C#', 'TypeScript', 'Shell', 'SQL', 'HTML/CSS']

const faqs = [
  { q: '为什么一提问就让我去设置？', a: ['对话、PPT 和绘画都要先有硅基流动 Key。', '打开「设置 → API Key 管理」提交后即可。'] },
  { q: '按需联网会不会每句都搜？', a: ['按需模式由快模型判断。空消息和打招呼会跳过。', '需要稳定检索时把联网改成开启；只要模型时改成关闭。'] },
  { q: '搜索或回答到一半刷新会丢吗？', a: ['不会。首页会恢复当前阶段并自动再请求。', 'PPT 大纲起草和成片导出同样会按本地会话续上。'] },
  { q: 'PPT 一定要指定页数吗？', a: ['默认自动。需要大致篇幅时再选约 8 / 12 / 16 / 20 页。'] },
  { q: '删掉的对话或 PPT 还能找回吗？', a: ['不能。删除前会确认，确认后立即清记录和文件。'] },
  { q: '怎么找以前的对话？', a: ['登录后侧栏列出最近会话，点击即可继续。', '工具集「搜索历史」按提示词关键词筛选；清除关键词后恢复全部列表。'] },
  { q: 'API Key 存在哪？', a: ['浏览器用 RSA 加密提交，服务端放 Redis。', '前端本地只留 token 和元数据，原始 Key 不入库、不进仓库。'] },
  { q: '支持私有部署吗？', a: ['支持。需要 Python 3.10+、Node.js 18+、Redis 6+。参考「部署指南」。'] },
]
</script>

<style scoped>
.docs-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
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
.aside-empty {
  margin: 8px 16px 0;
  font-size: 12px;
  color: var(--text-tertiary, #94a3b8);
}
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
  background: var(--warning-bg);
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
  background: var(--success-bg);
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
