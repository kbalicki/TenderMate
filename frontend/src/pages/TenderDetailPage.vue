<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getTender, rescrapeTender } from '@/api/tenders'
import { startAnalysis, getAnalysis } from '@/api/analysis'
import type { TenderDetail } from '@/types/tender'
import type { Analysis } from '@/types/analysis'
import { getStatusLabel, getStatusColor } from '@/composables/useStatusLabels'
import PdfViewer from '@/components/PdfViewer.vue'

const props = defineProps<{ id: string }>()
const router = useRouter()
const tender = ref<TenderDetail | null>(null)
const loading = ref(true)
const analysisLoading = ref(false)
const analysisError = ref('')
const analysisStatus = ref<string | null>(null)
const analysisData = ref<Analysis | null>(null)
const rescrapeLoading = ref(false)

// PDF preview
const pdfPreviewUrl = ref<string | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null

const isScraping = computed(() => tender.value?.status === 'scraping' || tender.value?.status === 'new')
const isScrapeFailed = computed(() => tender.value?.status === 'scrape_failed')

const isPdf = (filename: string) => filename.toLowerCase().endsWith('.pdf')

function openPdfPreview(tenderId: number, attachmentId: number) {
  pdfPreviewUrl.value = `/api/tenders/${tenderId}/attachments/${attachmentId}/download`
}

async function fetchTender() {
  tender.value = await getTender(Number(props.id))
  try {
    const analysis = await getAnalysis(Number(props.id))
    analysisStatus.value = analysis.status
    analysisData.value = analysis
  } catch {
    // No analysis yet
  }
}

// Analysis summary for quick overview
const analysisSummary = computed(() => {
  const a = analysisData.value
  if (!a || !a.step0_result) return null
  const s0 = a.step0_result as any
  const s1 = a.step1_result as any
  const s3 = a.step3_result as any
  const s4 = a.step4_result as any
  return {
    eligible: s0?.eligible,
    scopeSummary: s1?.scope_summary,
    totalNet: s3?.total_net_pln,
    suggestedPrice: s3?.suggested_offer_price_net,
    goNoGo: s4?.go_no_go_recommendation,
    goNoGoRationale: s4?.recommendation_rationale,
  }
})

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
          <span v-if="tender.authority_type === 'public'" title="Instytucja publiczna">&#127963; </span>
          <span v-else-if="tender.authority_type === 'private'" title="Firma prywatna">&#127970; </span>
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
        <a
          v-if="tender.source_url && analysisData?.user_decision === 'go'"
          :href="tender.source_url"
          target="_blank"
          class="px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 flex items-center gap-1.5"
        >
          Złóż ofertę
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
        </a>
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

    <!-- Podsumowanie -->
    <div v-if="tender.ai_summary" class="bg-indigo-50 border border-indigo-200 rounded-lg p-4 mb-6">
      <h3 class="text-xs font-semibold text-indigo-700 uppercase mb-1">Podsumowanie</h3>
      <p class="text-sm text-gray-800">{{ tender.ai_summary }}</p>
    </div>

    <!-- Error message from scraping -->
    <div v-if="tender.error_message && !isScrapeFailed" class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-6">
      <p class="text-xs text-yellow-800">⚠ {{ tender.error_message }}</p>
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
          <h3 class="text-sm font-semibold text-gray-900 mb-4">Informacje</h3>
          <dl class="text-sm divide-y divide-gray-100">
            <div class="flex justify-between items-center py-2.5">
              <dt class="text-gray-500 font-medium">Status</dt>
              <dd>
                <span :class="['text-xs px-2 py-1 rounded-full font-medium', getStatusColor(tender.status)]">
                  {{ getStatusLabel(tender.status) }}
                </span>
              </dd>
            </div>
            <div v-if="tender.contracting_authority" class="py-2.5">
              <dt class="text-gray-500 font-medium text-xs uppercase tracking-wide mb-0.5">Zamawiający</dt>
              <dd class="text-gray-900">
                <span v-if="tender.authority_type === 'public'" class="text-xs mr-1" title="Instytucja publiczna">&#127963;</span>
                <span v-else-if="tender.authority_type === 'private'" class="text-xs mr-1" title="Firma prywatna">&#127970;</span>
                {{ tender.contracting_authority }}
              </dd>
            </div>
            <div v-if="tender.reference_number" class="flex justify-between items-center py-2.5">
              <dt class="text-gray-500 font-medium">Nr ref.</dt>
              <dd class="text-gray-900 text-xs font-mono">{{ tender.reference_number }}</dd>
            </div>
            <div v-if="tender.submission_deadline" class="flex justify-between items-center py-2.5">
              <dt class="text-gray-500 font-medium">Termin składania</dt>
              <dd :class="['font-medium', new Date(tender.submission_deadline) < new Date() ? 'text-red-600' : 'text-gray-900']">
                {{ new Date(tender.submission_deadline).toLocaleString('pl-PL') }}
              </dd>
            </div>
            <div v-if="tender.portal_name" class="flex justify-between items-center py-2.5">
              <dt class="text-gray-500 font-medium">Portal</dt>
              <dd class="text-gray-900">{{ tender.portal_name }}</dd>
            </div>
            <div class="py-2.5">
              <dt class="text-gray-500 font-medium text-xs uppercase tracking-wide mb-0.5">Źródło</dt>
              <dd v-if="tender.source_type === 'url'" class="break-all text-xs">
                <a :href="tender.source_url!" target="_blank" class="text-indigo-600 hover:underline">
                  {{ tender.source_url }}
                </a>
              </dd>
              <dd v-else class="text-gray-900">Ręczne wprowadzenie</dd>
            </div>
            <div class="flex justify-between items-center py-2.5">
              <dt class="text-gray-500 font-medium">Utworzono</dt>
              <dd class="text-gray-600 text-xs">{{ new Date(tender.created_at).toLocaleString('pl-PL') }}</dd>
            </div>
          </dl>
        </div>

        <div class="bg-white rounded-lg shadow p-5">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-gray-900">Załączniki ({{ tender.attachments.length }})</h3>
            <a
              v-if="tender.attachments.length > 1"
              :href="`/api/tenders/${tender.id}/attachments/download-all`"
              class="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
              Pobierz wszystkie (ZIP)
            </a>
          </div>
          <div v-if="isScraping && tender.attachments.length === 0" class="text-sm text-gray-400">Pobieranie załączników...</div>
          <div v-else-if="tender.attachments.length === 0" class="text-sm text-gray-400">Brak załączników</div>
          <div v-else class="space-y-2">
            <div
              v-for="att in tender.attachments"
              :key="att.id"
              class="flex items-center justify-between"
            >
              <a
                :href="`/api/tenders/${tender.id}/attachments/${att.id}/download`"
                class="flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-800 min-w-0"
              >
                <span class="truncate">{{ att.filename }}</span>
                <span v-if="att.file_size_bytes" class="text-xs text-gray-400 shrink-0">
                  ({{ (att.file_size_bytes / 1024).toFixed(0) }} KB)
                </span>
              </a>
              <button
                v-if="isPdf(att.filename)"
                @click="openPdfPreview(tender.id, att.id)"
                class="text-xs text-gray-500 hover:text-indigo-600 shrink-0 ml-2"
                title="Podgląd PDF"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Analysis summary card -->
    <div v-if="analysisSummary && analysisStatus !== 'failed'" class="mt-6 bg-white rounded-lg shadow p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-3">Podsumowanie analizy</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <!-- Eligibility -->
        <div class="rounded-lg p-4" :class="analysisSummary.eligible ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'">
          <p class="text-xs font-semibold uppercase" :class="analysisSummary.eligible ? 'text-green-600' : 'text-red-600'">Warunki udziału</p>
          <p class="text-lg font-bold mt-1" :class="analysisSummary.eligible ? 'text-green-800' : 'text-red-800'">
            {{ analysisSummary.eligible ? 'SPEŁNIAMY' : 'NIE SPEŁNIAMY' }}
          </p>
        </div>

        <!-- Cost estimate -->
        <div v-if="analysisSummary.totalNet" class="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p class="text-xs font-semibold uppercase text-blue-600">Szacowany koszt netto</p>
          <p class="text-lg font-bold text-blue-800 mt-1">{{ analysisSummary.totalNet?.toLocaleString() }} PLN</p>
          <p v-if="analysisSummary.suggestedPrice" class="text-xs text-blue-600 mt-1">
            Proponowana cena: {{ analysisSummary.suggestedPrice?.toLocaleString() }} PLN
          </p>
        </div>

        <!-- GO/NO-GO -->
        <div v-if="analysisSummary.goNoGo" class="rounded-lg p-4 border"
          :class="analysisSummary.goNoGo === 'GO' ? 'bg-green-50 border-green-200' : analysisSummary.goNoGo === 'NO-GO' ? 'bg-red-50 border-red-200' : 'bg-yellow-50 border-yellow-200'">
          <p class="text-xs font-semibold uppercase"
            :class="analysisSummary.goNoGo === 'GO' ? 'text-green-600' : analysisSummary.goNoGo === 'NO-GO' ? 'text-red-600' : 'text-yellow-600'">
            Rekomendacja
          </p>
          <p class="text-lg font-bold mt-1"
            :class="analysisSummary.goNoGo === 'GO' ? 'text-green-800' : analysisSummary.goNoGo === 'NO-GO' ? 'text-red-800' : 'text-yellow-800'">
            {{ analysisSummary.goNoGo }}
          </p>
          <p v-if="analysisSummary.goNoGoRationale" class="text-xs mt-1"
            :class="analysisSummary.goNoGo === 'GO' ? 'text-green-700' : analysisSummary.goNoGo === 'NO-GO' ? 'text-red-700' : 'text-yellow-700'">
            {{ analysisSummary.goNoGoRationale }}
          </p>
        </div>
      </div>

      <!-- Scope summary -->
      <div v-if="analysisSummary.scopeSummary" class="mt-4 bg-gray-50 rounded-lg p-4">
        <p class="text-xs font-semibold uppercase text-gray-500 mb-1">Zakres zamówienia</p>
        <p class="text-sm text-gray-700">{{ analysisSummary.scopeSummary }}</p>
      </div>
    </div>

    <!-- PDF Viewer modal -->
    <PdfViewer v-if="pdfPreviewUrl" :url="pdfPreviewUrl" @close="pdfPreviewUrl = null" />
  </div>
</template>
