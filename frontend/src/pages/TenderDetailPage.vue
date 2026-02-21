<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getTender, rescrapeTender } from '@/api/tenders'
import { startAnalysis, getAnalysis } from '@/api/analysis'
import type { TenderDetail } from '@/types/tender'
import { getStatusLabel, getStatusColor } from '@/composables/useStatusLabels'

const props = defineProps<{ id: string }>()
const router = useRouter()
const tender = ref<TenderDetail | null>(null)
const loading = ref(true)
const analysisLoading = ref(false)
const analysisError = ref('')
const analysisStatus = ref<string | null>(null)
const rescrapeLoading = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null

const isScraping = computed(() => tender.value?.status === 'scraping' || tender.value?.status === 'new')
const isScrapeFailed = computed(() => tender.value?.status === 'scrape_failed')

async function fetchTender() {
  tender.value = await getTender(Number(props.id))
  try {
    const analysis = await getAnalysis(Number(props.id))
    analysisStatus.value = analysis.status
  } catch {
    // No analysis yet
  }
}

onMounted(async () => {
  try {
    await fetchTender()
  } finally {
    loading.value = false
  }
  if (isScraping.value) {
    startPolling()
  }
})

onUnmounted(() => {
  stopPolling()
})

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      await fetchTender()
      if (!isScraping.value) {
        stopPolling()
      }
    } catch {
      // ignore
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const canStartAnalysis = () => {
  if (!tender.value) return false
  if (analysisStatus.value === 'failed') return true
  return tender.value.status === 'scraped'
}

const canGoToAnalysis = () => {
  if (!tender.value) return false
  if (analysisStatus.value && !['failed'].includes(analysisStatus.value)) {
    return ['waiting_user', 'running', 'completed'].includes(analysisStatus.value)
  }
  return ['awaiting_decision', 'in_progress', 'completed'].includes(tender.value.status)
}

async function handleStartAnalysis() {
  analysisLoading.value = true
  analysisError.value = ''
  try {
    await startAnalysis(Number(props.id))
    router.push(`/tenders/${props.id}/analysis`)
  } catch (e: any) {
    analysisError.value = e?.response?.data?.detail || e?.message || 'Nie udało się uruchomić analizy'
  } finally {
    analysisLoading.value = false
  }
}

async function handleRescrape() {
  rescrapeLoading.value = true
  try {
    await rescrapeTender(Number(props.id))
    await fetchTender()
    startPolling()
  } catch (e: any) {
    analysisError.value = e?.response?.data?.detail || e?.message || 'Nie udało się ponowić scrapingu'
  } finally {
    rescrapeLoading.value = false
  }
}
</script>

<template>
  <div v-if="loading" class="text-center text-gray-400 py-8">Ładowanie...</div>
  <div v-else-if="tender">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ tender.title || 'Przetarg #' + tender.id }}</h1>
        <p class="text-sm text-gray-500 mt-1">
          {{ tender.contracting_authority || '' }}
          <span v-if="tender.reference_number">· {{ tender.reference_number }}</span>
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button
          v-if="isScrapeFailed"
          @click="handleRescrape"
          :disabled="rescrapeLoading"
          class="px-4 py-2 bg-orange-600 text-white rounded-lg text-sm hover:bg-orange-700 disabled:opacity-50"
        >
          {{ rescrapeLoading ? 'Pobieram...' : 'Ponów pobieranie' }}
        </button>
        <button
          v-if="canStartAnalysis()"
          @click="handleStartAnalysis"
          :disabled="analysisLoading"
          class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-50"
        >
          {{ analysisLoading ? 'Uruchamiam...' : analysisStatus === 'failed' ? 'Ponów analizę' : 'Rozpocznij analizę' }}
        </button>
        <RouterLink
          v-if="canGoToAnalysis()"
          :to="`/tenders/${tender.id}/analysis`"
          class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700"
        >
          Przejdź do analizy
        </RouterLink>
      </div>
    </div>

    <!-- Scraping in progress -->
    <div v-if="isScraping" class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6 flex items-center gap-3">
      <svg class="animate-spin h-5 w-5 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      <p class="text-sm text-blue-800">Pobieranie danych z portalu przetargowego... To może potrwać do 2 minut.</p>
    </div>

    <!-- Scrape failed -->
    <div v-if="isScrapeFailed" class="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
      <p class="text-sm text-red-800">Nie udało się pobrać danych z portalu. Kliknij "Ponów pobieranie" aby spróbować ponownie.</p>
    </div>

    <!-- Analysis error -->
    <div v-if="analysisError" class="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
      <p class="text-sm text-red-800">{{ analysisError }}</p>
    </div>

    <!-- Failed analysis -->
    <div v-if="analysisStatus === 'failed'" class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
      <p class="text-sm text-yellow-800">Poprzednia analiza nie powiodła się. Kliknij "Ponów analizę" aby spróbować ponownie.</p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="lg:col-span-2 bg-white rounded-lg shadow p-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-3">Treść przetargu</h2>
        <div v-if="tender.tender_text" class="text-sm text-gray-700 whitespace-pre-wrap max-h-[600px] overflow-auto">
          {{ tender.tender_text }}
        </div>
        <p v-else class="text-sm text-gray-400 italic">
          <span v-if="isScraping">Trwa pobieranie treści z portalu...</span>
          <span v-else-if="isScrapeFailed">Nie udało się pobrać treści. Spróbuj ponownie.</span>
          <span v-else-if="tender.source_type === 'url'">Scraper jeszcze nie pobrał danych z portalu.</span>
          <span v-else>Brak treści. Wróć do edycji i wklej treść przetargu.</span>
        </p>
      </div>

      <div class="space-y-4">
        <div class="bg-white rounded-lg shadow p-5">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">Informacje</h3>
          <dl class="space-y-2 text-sm">
            <div>
              <dt class="text-gray-500">Status</dt>
              <dd>
                <span :class="['text-xs px-2 py-1 rounded-full', getStatusColor(tender.status)]">
                  {{ getStatusLabel(tender.status) }}
                </span>
              </dd>
            </div>
            <div v-if="tender.portal_name">
              <dt class="text-gray-500">Portal</dt>
              <dd>{{ tender.portal_name }}</dd>
            </div>
            <div>
              <dt class="text-gray-500">Źródło</dt>
              <dd v-if="tender.source_type === 'url'" class="break-all text-xs">
                <a :href="tender.source_url!" target="_blank" class="text-indigo-600 hover:underline">
                  {{ tender.source_url }}
                </a>
              </dd>
              <dd v-else>Ręczne wprowadzenie</dd>
            </div>
            <div v-if="tender.submission_deadline">
              <dt class="text-gray-500">Termin składania</dt>
              <dd>{{ new Date(tender.submission_deadline).toLocaleString('pl-PL') }}</dd>
            </div>
            <div>
              <dt class="text-gray-500">Utworzono</dt>
              <dd>{{ new Date(tender.created_at).toLocaleString('pl-PL') }}</dd>
            </div>
          </dl>
        </div>

        <div class="bg-white rounded-lg shadow p-5">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">Załączniki ({{ tender.attachments.length }})</h3>
          <div v-if="isScraping && tender.attachments.length === 0" class="text-sm text-gray-400">Pobieranie załączników...</div>
          <div v-else-if="tender.attachments.length === 0" class="text-sm text-gray-400">Brak załączników</div>
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
