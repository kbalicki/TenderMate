<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listTenders } from '@/api/tenders'
import type { Tender } from '@/types/tender'

const recentTenders = ref<Tender[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    recentTenders.value = await listTenders()
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-gray-900 mb-6">Dashboard</h1>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
      <div class="bg-white rounded-lg shadow p-5">
        <p class="text-sm text-gray-500">Wszystkie przetargi</p>
        <p class="text-3xl font-bold text-gray-900 mt-1">{{ recentTenders.length }}</p>
      </div>
      <div class="bg-white rounded-lg shadow p-5">
        <p class="text-sm text-gray-500">W analizie</p>
        <p class="text-3xl font-bold text-indigo-600 mt-1">
          {{ recentTenders.filter(t => ['analyzing', 'awaiting_decision', 'in_progress'].includes(t.status)).length }}
        </p>
      </div>
      <div class="bg-white rounded-lg shadow p-5">
        <p class="text-sm text-gray-500">Odrzucone</p>
        <p class="text-3xl font-bold text-red-600 mt-1">
          {{ recentTenders.filter(t => t.status === 'rejected').length }}
        </p>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow">
      <div class="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-gray-900">Ostatnie przetargi</h2>
        <RouterLink to="/tenders/new" class="text-sm text-indigo-600 hover:text-indigo-800">
          + Nowy przetarg
        </RouterLink>
      </div>
      <div v-if="loading" class="p-8 text-center text-gray-400">Ladowanie...</div>
      <div v-else-if="recentTenders.length === 0" class="p-8 text-center text-gray-400">
        Brak przetargow. Dodaj pierwszy przetarg.
      </div>
      <div v-else class="divide-y divide-gray-200">
        <RouterLink
          v-for="tender in recentTenders.slice(0, 10)"
          :key="tender.id"
          :to="`/tenders/${tender.id}`"
          class="flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors"
        >
          <div>
            <p class="text-sm font-medium text-gray-900">{{ tender.title || 'Bez tytulu' }}</p>
            <p class="text-xs text-gray-500">{{ tender.source_type === 'url' ? tender.source_url : 'Reczny' }}</p>
          </div>
          <span
            :class="[
              'text-xs px-2 py-1 rounded-full',
              tender.status === 'completed' ? 'bg-green-100 text-green-800' :
              tender.status === 'rejected' ? 'bg-red-100 text-red-800' :
              tender.status === 'analyzing' ? 'bg-blue-100 text-blue-800' :
              'bg-gray-100 text-gray-800'
            ]"
          >
            {{ tender.status }}
          </span>
        </RouterLink>
      </div>
    </div>
  </div>
</template>
