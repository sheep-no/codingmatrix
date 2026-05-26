import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../stores/user.js'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../components/index.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/project-generate',
      redirect: '/agent'
    },
    {
      path: '/workflow',
      name: 'workflow',
      component: () => import('../views/Workflow.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/ppt-generate',
      name: 'ppt-generate',
      component: () => import('../views/PPTGenerate.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/ppt-preview/:id',
      name: 'ppt-preview',
      component: () => import('../views/PPTPreview.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/image-generate',
      name: 'image-generate',
      component: () => import('../views/ImageGenerate.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/agent',
      name: 'agent-dashboard',
      component: () => import('../views/AgentDashboard.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/kolors',
      name: 'kolors',
      component: () => import('../views/ImageGenerate.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/aicloud',
      name: 'aicloud',
      component: () => import('../components/Aicloud.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/github-config',
      name: 'github-config',
      component: () => import('../components/GithubConfigPanel.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/Settings.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../components/AdminPanel.vue'),
      meta: { requiresAuth: true, requiresSuper: true }
    },
    {
      path: '/admin/dashboard',
      name: 'admin-dashboard',
      component: () => import('../views/AdminDashboard.vue'),
      meta: { requiresAuth: true, requiresSuper: true }
    },
    {
      path: '/docs',
      name: 'docs',
      component: () => import('../views/Docs.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      redirect: '/'
    }
  ]
})

// 路由守卫：认证 + 权限验证 (v5.0.2 修复：从 Pinia store 读取 token)
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  const token = userStore.getAccessToken() || localStorage.getItem('access_token')
  const permissionLevel = userStore.permissionLevel || localStorage.getItem('permission_level')

  if (to.meta.requiresAuth) {
    if (!token) {
      // 未登录，直接访问首页（首页会自动弹出登录框）
      next()
      return
    }
  }

  if (to.meta.requiresSuper) {
    if (!['admin', 'superadmin'].includes(permissionLevel)) {
      next('/')
      return
    }
  }

  next()
})

export default router
