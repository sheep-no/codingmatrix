"""
Frontend Component Tests
使用 Vitest + @vue/test-utils 测试关键 Vue 组件
"""

# 由于前端测试需要 Vitest 环境，这里提供测试配置和示例
# 实际测试文件应放在 src/tests/ 目录下

import os
import json

# 测试配置
VITEST_CONFIG = """
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
 plugins: [vue()],
 resolve: {
 alias: {
 '@': fileURLToPath(new URL('.', import.meta.url))
 }
 },
 test: {
 environment: 'jsdom',
 globals: true,
 setupFiles: ['./src/test/setup.js'],
 coverage: {
 provider: 'v8',
 reporter: ['text', 'html'],
 exclude: ['node_modules/', 'src/test/', '**/*.spec.js']
 }
 },
 server: {
 port: 3000,
 host: true,
 allowedHosts: ['.monkeycode-ai.online'],
 proxy: {
 '/api': {
 target: 'http://localhost:8080',
 changeOrigin: true,
 ws: true,
 secure: false,
 cookieDomainRewrite: '127.0.0.1',
 cookiePathRewrite: '/'
 }
 }
 },
 build: {
 outDir: '../dist',
 assetsDir: 'static',
 sourcemap: true,
 chunkSizeWarningLimit: 500,
 rollupOptions: {
 output: {
 manualChunks(id) {
 if (id.includes('node_modules')) {
 if (id.includes('echarts')) {
 return 'echarts'
 }
 if (id.includes('highlight.js')) {
 return 'highlight'
 }
 if (id.includes('xlsx')) {
 return 'xlsx'
 }
 if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) {
 return 'vue-vendor'
 }
 return 'vendor'
 }
 }
 }
 }
 },
 publicDir: 'public'
})
"""

# 测试 setup 文件
TEST_SETUP = """
import { config } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// 全局配置
config.global.stubs = {
 RouterLink: true,
 RouterView: true,
}

// 每个测试前初始化 Pinia
beforeEach(() => {
 setActivePinia(createPinia())
})
"""

# Login 组件测试
LOGIN_TEST = """
import { describe, it, expect, vi } from 'vitest'
import { mount, shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Login from '@/views/Login.vue'

// Mock API
vi.mock('@/api/user', () => ({
 login: vi.fn(() => Promise.resolve({ code: 200, data: { token: 'mock-token' } })),
 getCaptcha: vi.fn(() => Promise.resolve({ code: 200, data: { captchaId: 'test-id', img: 'data:image/png;base64,test' } })),
 logout: vi.fn(() => Promise.resolve({ code: 200 })),
}))

describe('Login.vue', () => {
 beforeEach(() => {
 setActivePinia(createPinia())
 })

 it('renders login form', () => {
 const wrapper = shallowMount(Login)
 expect(wrapper.find('.login-form').exists()).toBe(true)
 expect(wrapper.find('input[type="text"]').exists()).toBe(true)
 expect(wrapper.find('input[type="password"]').exists()).toBe(true)
 })

 it('validates required fields', async () => {
 const wrapper = mount(Login)
 const submitBtn = wrapper.find('button[type="submit"]')
 
 await submitBtn.trigger('click')
 expect(wrapper.text()).toContain('请输入用户名')
 expect(wrapper.text()).toContain('请输入密码')
 })

 it('calls login API with valid credentials', async () => {
 const { login } = await import('@/api/user')
 const wrapper = mount(Login)
 
 await wrapper.find('input[type="text"]').setValue('admin')
 await wrapper.find('input[type="password"]').setValue('password123')
 await wrapper.find('button[type="submit"]').trigger('click')
 
 expect(login).toHaveBeenCalledWith({
 username: 'admin',
 password: 'password123',
 captchaId: expect.any(String),
 captcha: expect.any(String),
 })
 })

 it('shows error message on login failure', async () => {
 const { login } = await import('@/api/user')
 login.mockRejectedValueOnce(new Error('Invalid credentials'))
 
 const wrapper = mount(Login)
 await wrapper.find('input[type="text"]').setValue('admin')
 await wrapper.find('input[type="password"]').setValue('wrong')
 await wrapper.find('button[type="submit"]').trigger('click')
 
 expect(wrapper.text()).toContain('登录失败')
 })

 it('navigates to dashboard on successful login', async () => {
 const { login } = await import('@/api/user')
 const wrapper = mount(Login, {
 global: {
 mocks: {
 $router: { push: vi.fn() },
 $route: { query: {} },
 },
 },
 })
 
 await wrapper.find('input[type="text"]').setValue('admin')
 await wrapper.find('input[type="password"]').setValue('password123')
 await wrapper.find('button[type="submit"]').trigger('click')
 
 await wrapper.vm.$nextTick()
 expect(wrapper.global.mocks.$router.push).toHaveBeenCalledWith('/')
 })

 it('displays captcha image', async () => {
 const wrapper = mount(Login)
 await wrapper.vm.$nextTick()
 
 const captchaImg = wrapper.find('.captcha-image')
 expect(captchaImg.exists()).toBe(true)
 })
})
"""

# AgentChat 组件测试
AGENT_CHAT_TEST = """
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AgentChat from '@/views/AgentChat.vue'

// Mock API
vi.mock('@/api/agent', () => ({
 sendMessage: vi.fn(() => Promise.resolve({ code: 200, data: { message: 'Response', sessionId: 'session-1' } })),
 getHistory: vi.fn(() => Promise.resolve({ code: 200, data: { messages: [] } })),
 uploadFile: vi.fn(() => Promise.resolve({ code: 200, data: { fileId: 'file-1' } })),
 generateCode: vi.fn(() => Promise.resolve({ code: 200, data: { code: 'print("hello")' } })),
 getProjects: vi.fn(() => Promise.resolve({ code: 200, data: { projects: [] } })),
 saveProject: vi.fn(() => Promise.resolve({ code: 200 })),
}))

describe('AgentChat.vue', () => {
 beforeEach(() => {
 setActivePinia(createPinia())
 vi.clearAllMocks()
 })

 it('renders chat interface', () => {
 const wrapper = shallowMount(AgentChat)
 expect(wrapper.find('.chat-container').exists()).toBe(true)
 expect(wrapper.find('.message-input').exists()).toBe(true)
 expect(wrapper.find('.send-button').exists()).toBe(true)
 })

 it('sends message on button click', async () => {
 const { sendMessage } = await import('@/api/agent')
 const wrapper = mount(AgentChat)
 
 await wrapper.find('.message-input').setValue('Hello')
 await wrapper.find('.send-button').trigger('click')
 
 expect(sendMessage).toHaveBeenCalledWith({
 message: 'Hello',
 sessionId: expect.any(String),
 })
 })

 it('displays user message in chat', async () => {
 const wrapper = mount(AgentChat)
 
 await wrapper.find('.message-input').setValue('Test message')
 await wrapper.find('.send-button').trigger('click')
 await wrapper.vm.$nextTick()
 
 expect(wrapper.text()).toContain('Test message')
 })

 it('handles file upload', async () => {
 const { uploadFile } = await import('@/api/agent')
 const wrapper = mount(AgentChat)
 
 const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
 await wrapper.vm.handleFileUpload({ target: { files: [file] } })
 
 expect(uploadFile).toHaveBeenCalledWith(expect.any(FormData))
 })

 it('shows loading state during API call', async () => {
 const { sendMessage } = await import('@/api/agent')
 sendMessage.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))
 
 const wrapper = mount(AgentChat)
 await wrapper.find('.message-input').setValue('Loading test')
 await wrapper.find('.send-button').trigger('click')
 
 expect(wrapper.find('.loading-indicator').exists()).toBe(true)
 })

 it('displays error message on API failure', async () => {
 const { sendMessage } = await import('@/api/agent')
 sendMessage.mockRejectedValueOnce(new Error('Network error'))
 
 const wrapper = mount(AgentChat)
 await wrapper.find('.message-input').setValue('Error test')
 await wrapper.find('.send-button').trigger('click')
 await wrapper.vm.$nextTick()
 
 expect(wrapper.text()).toContain('发送失败')
 })

 it('supports markdown rendering', async () => {
 const wrapper = mount(AgentChat)
 
 // Mock API response with markdown
 const { sendMessage } = await import('@/api/agent')
 sendMessage.mockResolvedValueOnce({
 code: 200,
 data: { message: '**Bold** and *italic*', sessionId: 'session-1' },
 })
 
 await wrapper.find('.message-input').setValue('Markdown test')
 await wrapper.find('.send-button').trigger('click')
 await wrapper.vm.$nextTick()
 
 expect(wrapper.find('.markdown-content').exists()).toBe(true)
 })

 it('clears input after sending', async () => {
 const wrapper = mount(AgentChat)
 const input = wrapper.find('.message-input')
 
 await input.setValue('Test message')
 await wrapper.find('.send-button').trigger('click')
 await wrapper.vm.$nextTick()
 
 expect(input.element.value).toBe('')
 })
})
"""

# ProjectGenerate 组件测试
PROJECT_GENERATE_TEST = """
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ProjectGenerate from '@/views/ProjectGenerate.vue'

// Mock API
vi.mock('@/api/project', () => ({
 generate: vi.fn(() => Promise.resolve({ code: 200, data: { projectId: 'proj-1' } })),
 getStatus: vi.fn(() => Promise.resolve({ code: 200, data: { status: 'completed', progress: 100 } })),
 download: vi.fn(() => Promise.resolve({ code: 200, data: { url: '/download/test.zip' } })),
 getTemplates: vi.fn(() => Promise.resolve({ code: 200, data: { templates: [] } })),
 analyzeComplexity: vi.fn(() => Promise.resolve({ code: 200, data: { complexity: 'medium' } })),
}))

describe('ProjectGenerate.vue', () => {
 beforeEach(() => {
 setActivePinia(createPinia())
 vi.clearAllMocks()
 })

 it('renders project generation form', () => {
 const wrapper = shallowMount(ProjectGenerate)
 expect(wrapper.find('.project-form').exists()).toBe(true)
 expect(wrapper.find('select[name="template"]').exists()).toBe(true)
 expect(wrapper.find('textarea[name="description"]').exists()).toBe(true)
 })

 it('validates required fields', async () => {
 const wrapper = mount(ProjectGenerate)
 await wrapper.find('button[type="submit"]').trigger('click')
 
 expect(wrapper.text()).toContain('请输入项目描述')
 })

 it('calls generate API with form data', async () => {
 const { generate } = await import('@/api/project')
 const wrapper = mount(ProjectGenerate)
 
 await wrapper.find('textarea[name="description"]').setValue('Test project')
 await wrapper.find('select[name="template"]').setValue('vue-template')
 await wrapper.find('button[type="submit"]').trigger('click')
 
 expect(generate).toHaveBeenCalledWith({
 description: 'Test project',
 template: 'vue-template',
 })
 })

 it('shows progress during generation', async () => {
 const { generate, getStatus } = await import('@/api/project')
 generate.mockResolvedValue({ code: 200, data: { projectId: 'proj-1' } })
 getStatus.mockResolvedValue({ code: 200, data: { status: 'running', progress: 50 } })
 
 const wrapper = mount(ProjectGenerate)
 await wrapper.find('textarea[name="description"]').setValue('Test')
 await wrapper.find('button[type="submit"]').trigger('click')
 await wrapper.vm.$nextTick()
 
 expect(wrapper.find('.progress-bar').exists()).toBe(true)
 })

 it('displays download link on completion', async () => {
 const { generate, getStatus, download } = await import('@/api/project')
 generate.mockResolvedValue({ code: 200, data: { projectId: 'proj-1' } })
 getStatus.mockResolvedValue({ code: 200, data: { status: 'completed', progress: 100 } })
 download.mockResolvedValue({ code: 200, data: { url: '/download/proj-1.zip' } })
 
 const wrapper = mount(ProjectGenerate)
 await wrapper.find('textarea[name="description"]').setValue('Test')
 await wrapper.find('button[type="submit"]').trigger('click')
 
 // Wait for polling to complete
 await new Promise(resolve => setTimeout(resolve, 200))
 await wrapper.vm.$nextTick()
 
 expect(wrapper.find('.download-link').exists()).toBe(true)
 })

 it('handles generation error', async () => {
 const { generate } = await import('@/api/project')
 generate.mockRejectedValueOnce(new Error('Generation failed'))
 
 const wrapper = mount(ProjectGenerate)
 await wrapper.find('textarea[name="description"]').setValue('Test')
 await wrapper.find('button[type="submit"]').trigger('click')
 await wrapper.vm.$nextTick()
 
 expect(wrapper.text()).toContain('生成失败')
 })

 it('loads templates on mount', async () => {
 const { getTemplates } = await import('@/api/project')
 mount(ProjectGenerate)
 
 expect(getTemplates).toHaveBeenCalled()
 })

 it('analyzes complexity before generation', async () => {
 const { analyzeComplexity, generate } = await import('@/api/project')
 analyzeComplexity.mockResolvedValue({ code: 200, data: { complexity: 'low' } })
 
 const wrapper = mount(ProjectGenerate)
 await wrapper.find('textarea[name="description"]').setValue('Simple project')
 await wrapper.find('button.analyze-btn').trigger('click')
 await wrapper.vm.$nextTick()
 
 expect(analyzeComplexity).toHaveBeenCalledWith({ description: 'Simple project' })
 })
})
"""

# 创建测试目录结构
def create_test_files():
 """创建前端测试文件"""
 test_dir = '/workspace/src/test'
 os.makedirs(test_dir, exist_ok=True)
 
 # 写入 setup 文件
 with open(os.path.join(test_dir, 'setup.js'), 'w') as f:
 f.write(TEST_SETUP)
 
 # 创建组件测试目录
 components_test_dir = os.path.join(test_dir, 'components')
 os.makedirs(components_test_dir, exist_ok=True)
 
 # 写入测试文件
 test_files = {
 'Login.spec.js': LOGIN_TEST,
 'AgentChat.spec.js': AGENT_CHAT_TEST,
 'ProjectGenerate.spec.js': PROJECT_GENERATE_TEST,
 }
 
 for filename, content in test_files.items():
 filepath = os.path.join(components_test_dir, filename)
 with open(filepath, 'w') as f:
 f.write(content)
 
 print(f"Created frontend test files in {test_dir}")


if __name__ == '__main__':
 create_test_files()
