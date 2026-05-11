<script setup>
import { createApp, ref, h } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia } from 'pinia'
import { useAuthStore } from '@/stores/userLogin'
import { useGameStore } from '@/stores/gameStore'
// App Components
import GameLayout from '@/components/GameLayout.vue'
import SuccessModal from '@/components/GameModal/Suspense.vue'
import HistoryTable from '@/components/Page/HistoryTable.vue'

// Mocking router logic for App entry
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'Root',
      redirect: '/login'
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/pages/LoginPage.vue')
    },
    {
      path: '/games',
      name: 'Games',
      component: () => import('@/pages/GamePage.vue'),
      children: [
        { path: 'board', component: () => import('@/pages/boardGame.vue') }
      ]
    },
    {
      path: '/history',
      name: 'History',
      component: () => import('../pages/HistoryPage.vue')
    }
  ]
})

const pinia = createPinia()
const gameStore = useGameStore()
const authStore = useAuthStore()
</script>

<template>
  <div class="min-h-screen bg-gray-100 text-gray-900 flex flex-col">
    <header class="bg-indigo-700 p-4 shadow-lg">
      <div class="container mx-auto flex justify-between items-center">
        <h1 class="text-2xl font-bold text-white tracking-wider">五子棋大师 CLI</h1>
        <div class="space-x-4">
          <button @click="router.push('/games')" class="hover:bg-white hover:bg-opacity-20 px-4 py-2 rounded">
            对弈
          </button>
          <button @click="router.push('/history')" class="hover:bg-white hover:bg-opacity-20 px-4 py-2 rounded">
            历史记录
          </button>
          <button class="bg-yellow-500 text-white px-4 py-2 rounded">
            退出
          </button>
        </div>
      </div>
    </header>

    <main class="flex-grow container mx-auto p-6">
      <GameLayout v-bind:style="gameStore.style" />
    </main>

    <footer class="bg-gray-800 text-white p-4 text-center">
      <p>Copyright 2026 Sight The Orchestrate Project</p>
      <p class="text-xs text-gray-400">Vue3 + Tailwind + WebSocket</p>
    </footer>
  </div>
</template>

<style scoped>
.main {
  background: #f3f4f6;
}
.header {
  background-color: #4c51bf;
}
</style>