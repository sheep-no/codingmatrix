import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../components/index.vue')
    },
    {
      path: '/project-generate',
      name: 'project-generate',
      component: () => import('../views/ProjectGenerate.vue')
    },
    {
      path: '/workflow',
      name: 'workflow',
      component: () => import('../views/Workflow.vue')
    },
    {
      path: '/ppt-generate',
      name: 'ppt-generate',
      component: () => import('../views/PPTGenerate.vue')
    },
    {
      path: '/image-generate',
      name: 'image-generate',
      component: () => import('../views/ImageGenerate.vue')
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../components/AdminPanel.vue'),
      meta: { requiresSuper: true }
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      redirect: '/'
    }
  ]
})

// 路由守卫：权限验证
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  const permissionLevel = localStorage.getItem('permission_level')

  // 检查是否需要管理员权限（admin 或 superadmin）
  if (to.meta.requiresSuper) {
    if (!token) {
      next('/')
      return
    }

    if (!['admin', 'superadmin'].includes(permissionLevel)) {
      alert('访问被拒绝：需要管理员权限')
      next('/')
      return
    }
  }

  next()
})

export default router
