<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listTenders, deleteTender } from '@/api/tenders'
import type { Tender } from '@/types/tender'
import { statusLabels, getStatusLabel, getStatusColor } from '@/composables/useStatusLabels'

const tenders = ref<Tender[]>([])
const loading = ref(true)
const statusFilter = ref<string>('')

onMounted(load)

async function load() {
  loading.value = true
  try {
    tenders.value = await listTenders(statusFilter.value || undefined)
  } finally {
    loading.value = false
  }
}

async function handleDelete(id: number) {
  if (!confirm('Na pewno usunąć?')) return
  await deleteTender(id)
  tenders.value = tenders.value.filter(t => t.id !== id)
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Przetargi</h1>
      <RouterLink to="/tenders/new" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
        + Nowy przetarg
      </RouterLink>
    </div>

    <div class="mb-4">
      <select v-model="statusFilter" @change="load" class="border border-gray-300 rounded-lg px-3 py-2 text-sm">
        <option value="">Wszystkie statusy</option>
        <option v-for="(label, key) in statusLabels" :key="key" :value="key">{{ label }}</option>
      </select>
    </div>

    <div v-if="loading" class="text-center text-gray-400 py-8">Ładowanie...</div>
    <div v-else-if="tenders.length === 0" class="text-center text-gray-400 py-8">Brak przetargów</div>
    <div v-else class="bg-white rounded-lg shadow divide-y divide-gray-200">
      <div v-for="tender in tenders" :key="tender.id" class="flex items-center justify-between px-5 py-4">
        <RouterLink :to="`/tenders/${tender.id}`" class="flex-1 min-w-0">
          <p class="text-sm font-medium text-gray-900 truncate">{{ tender.title || 'Bez tytułu' }}</p>
          <p class="text-xs text-gray-500 mt-1">
            {{ tender.source_type === 'url' ? tender.portal_name || tender.source_url : 'Ręczny' }}
            · {{ new Date(tender.created_at).toLocaleDateString('pl-PL') }}
          </p>
        </RouterLink>
        <div class="flex items-center gap-3 ml-4">
          <span :class="['text-xs px-2 py-1 rounded-full whitespace-nowrap', getStatusColor(tender.status)]">
            {{ getStatusLabel(tender.status) }}
          </span>
          <RouterLink
            v-if="['scraped', 'analyzing', 'awaiting_decision', 'in_progress'].includes(tender.status)"
            :to="`/tenders/${tender.id}/analysis`"
            class="text-xs text-indigo-600 hover:text-indigo-800"
          >
            Analiza
          </RouterLink>
          <button @click="handleDelete(tender.id)" class="text-xs text-red-600 hover:text-red-800">Usuń</button>
        </div>
      </div>
    </div>
  </div>
</template>
