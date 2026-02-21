<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  { path: '/', label: 'Panel główny', icon: '📊' },
  { path: '/tenders', label: 'Przetargi', icon: '📋' },
  { path: '/tenders/new', label: 'Nowy przetarg', icon: '➕' },
  { path: '/company', label: 'Profil firmy', icon: '🏢' },
]

function isActive(path: string): boolean {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <aside class="w-64 bg-gray-900 text-white flex flex-col">
    <div class="p-4 border-b border-gray-700">
      <h1 class="text-xl font-bold">TenderMate</h1>
      <p class="text-xs text-gray-400 mt-1">Analiza przetargów</p>
    </div>
    <nav class="flex-1 p-3 space-y-1">
      <RouterLink
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        :class="[
          'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
          isActive(item.path)
            ? 'bg-indigo-600 text-white'
            : 'text-gray-300 hover:bg-gray-800 hover:text-white'
        ]"
      >
        <span>{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>
  </aside>
</template>
