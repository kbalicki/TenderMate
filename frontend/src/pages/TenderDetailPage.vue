<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getTender } from '@/api/tenders'
import { startAnalysis } from '@/api/analysis'
import type { TenderDetail } from '@/types/tender'

const props = defineProps<{ id: string }>()
const router = useRouter()
const tender = ref<TenderDetail | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    tender.value = await getTender(Number(props.id))
  } finally {
    loading.value = false
  }
})

async function handleStartAnalysis() {
  await startAnalysis(Number(props.id))
  router.push(`/tenders/${props.id}/analysis`)
}
</script>

<template>
  <div v-if="loading" class="text-center text-gray-400 py-8">Ladowanie...</div>
  <div v-else-if="tender">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ tender.title || 'Przetarg #' + tender.id }}</h1>
        <p class="text-sm text-gray-500 mt-1">
          {{ tender.contracting_authority || '' }}
          <span v-if="tender.reference_number">· {{ tender.reference_number }}</span>
        </p>
      </div>
      <button
        v-if="['new', 'scraped'].includes(tender.status)"
        @click="handleStartAnalysis"
        class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700"
      >
        Rozpocznij analize
      </button>
      <RouterLink
        v-else-if="['analyzing', 'awaiting_decision', 'in_progress'].includes(tender.status)"
        :to="`/tenders/${tender.id}/analysis`"
        class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700"
      >
        Przejdz do analizy
      </RouterLink>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Tender text -->
      <div class="lg:col-span-2 bg-white rounded-lg shadow p-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-3">Tresc przetargu</h2>
        <div v-if="tender.tender_text" class="text-sm text-gray-700 whitespace-pre-wrap max-h-[600px] overflow-auto">
          {{ tender.tender_text }}
        </div>
        <p v-else class="text-sm text-gray-400">Brak tresci (oczekuje na scrapowanie)</p>
      </div>

      <!-- Sidebar -->
      <div class="space-y-4">
        <div class="bg-white rounded-lg shadow p-5">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">Informacje</h3>
          <dl class="space-y-2 text-sm">
            <div>
              <dt class="text-gray-500">Status</dt>
              <dd class="font-medium">{{ tender.status }}</dd>
            </div>
            <div>
              <dt class="text-gray-500">Zrodlo</dt>
              <dd>{{ tender.source_type === 'url' ? tender.source_url : 'Reczne' }}</dd>
            </div>
            <div v-if="tender.submission_deadline">
              <dt class="text-gray-500">Termin skladania</dt>
              <dd>{{ new Date(tender.submission_deadline).toLocaleString('pl-PL') }}</dd>
            </div>
          </dl>
        </div>

        <div class="bg-white rounded-lg shadow p-5">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">Zalaczniki ({{ tender.attachments.length }})</h3>
          <div v-if="tender.attachments.length === 0" class="text-sm text-gray-400">Brak zalacznikow</div>
          <div v-else class="space-y-2">
            <a
              v-for="att in tender.attachments"
              :key="att.id"
              :href="`/api/tenders/${tender.id}/attachments/${att.id}/download`"
              class="flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-800"
            >
              <span>{{ att.filename }}</span>
              <span v-if="att.file_size_bytes" class="text-xs text-gray-400">
                ({{ (att.file_size_bytes / 1024).toFixed(0) }} KB)
              </span>
            </a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
