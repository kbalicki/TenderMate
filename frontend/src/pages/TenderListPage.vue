<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { listTenders, deleteTender, type TenderListParams } from '@/api/tenders'
import { startAnalysis, restartAnalysis } from '@/api/analysis'
import type { TenderListItem, PaginatedTenders } from '@/types/tender'
import { statusLabels, getStatusLabel, getStatusColor, getDisplayStatus, isDeadlineExpired } from '@/composables/useStatusLabels'

const data = ref<PaginatedTenders | null>(null)
const loading = ref(true)

// Filters & pagination
const statusFilter = ref('')
const searchQuery = ref('')
const sortBy = ref('submission_deadline')
const sortDir = ref<'asc' | 'desc'>('asc')
const page = ref(1)
const pageSize = ref(25)

let searchTimeout: ReturnType<typeof setTimeout> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
const PROCESSING_STATUSES = ['new', 'scraping', 'analyzing', 'running']

const hasProcessingItems = computed(() => {
  if (!data.value) return false
  return data.value.items.some(t => PROCESSING_STATUSES.includes(t.status))
})

function isProcessing(status: string): boolean {
  return PROCESSING_STATUSES.includes(status)
}

onMounted(async () => {
  await load()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (hasProcessingItems.value) {
      try {
        const params: TenderListParams = {
          page: page.value,
          page_size: pageSize.value,
          sort_by: sortBy.value,
          sort_dir: sortDir.value,
        }
        if (statusFilter.value) params.status = statusFilter.value
        if (searchQuery.value.trim()) params.search = searchQuery.value.trim()
        data.value = await listTenders(params)
      } catch { /* ignore polling errors */ }
    }
  }, 5000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function load() {
  loading.value = true
  try {
    const params: TenderListParams = {
      page: page.value,
      page_size: pageSize.value,
      sort_by: sortBy.value,
      sort_dir: sortDir.value,
    }
    if (statusFilter.value) params.status = statusFilter.value
    if (searchQuery.value.trim()) params.search = searchQuery.value.trim()
    data.value = await listTenders(params)
  } finally {
    loading.value = false
  }
}

function onSearchInput() {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => { page.value = 1; load() }, 400)
}

function toggleSort(col: string) {
  if (sortBy.value === col) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = col
    sortDir.value = col === 'submission_deadline' ? 'asc' : 'desc'
  }
  page.value = 1
  load()
}

function sortIcon(col: string): string {
  if (sortBy.value !== col) return '↕'
  return sortDir.value === 'asc' ? '↑' : '↓'
}

function goToPage(p: number) {
  page.value = p
  load()
}

watch(statusFilter, () => { page.value = 1; load() })

async function handleDelete(id: number) {
  if (!confirm('Na pewno usunąć?')) return
  await deleteTender(id)
  selectedIds.value.delete(id)
  load()
}

// Selection & bulk actions
const selectedIds = ref<Set<number>>(new Set())
const bulkRunning = ref(false)

const allSelected = computed(() => {
  if (!data.value || data.value.items.length === 0) return false
  return data.value.items.every(t => selectedIds.value.has(t.id))
})

function toggleAll() {
  if (!data.value) return
  if (allSelected.value) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(data.value.items.map(t => t.id))
  }
}

function toggleOne(id: number) {
  const s = new Set(selectedIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selectedIds.value = s
}

const analyzableSelected = computed(() => {
  if (!data.value) return []
  return data.value.items.filter(t => selectedIds.value.has(t.id) && t.status === 'scraped')
})

const reanalyzableSelected = computed(() => {
  if (!data.value) return []
  return data.value.items.filter(t => selectedIds.value.has(t.id) && ['completed', 'rejected', 'waiting_user', 'analyzing'].includes(t.status))
})

const deletableSelected = computed(() => {
  if (!data.value) return []
  return data.value.items.filter(t => selectedIds.value.has(t.id))
})

async function bulkStartAnalysis() {
  const items = analyzableSelected.value
  if (items.length === 0) return
  if (!confirm(`Uruchomić analizę dla ${items.length} przetargów?`)) return
  bulkRunning.value = true
  try {
    for (const t of items) {
      try { await startAnalysis(t.id) } catch { /* continue */ }
    }
    selectedIds.value = new Set()
    await load()
  } finally {
    bulkRunning.value = false
  }
}

async function bulkRestartAnalysis() {
  const items = reanalyzableSelected.value
  if (items.length === 0) return
  if (!confirm(`Ponowić analizę dla ${items.length} przetargów?`)) return
  bulkRunning.value = true
  try {
    for (const t of items) {
      try { await restartAnalysis(t.id) } catch { /* continue */ }
    }
    selectedIds.value = new Set()
    await load()
  } finally {
    bulkRunning.value = false
  }
}

async function bulkDelete() {
  const items = deletableSelected.value
  if (items.length === 0) return
  if (!confirm(`Na pewno usunąć ${items.length} przetargów?`)) return
  bulkRunning.value = true
  try {
    for (const t of items) {
      try { await deleteTender(t.id) } catch { /* continue */ }
    }
    selectedIds.value = new Set()
    await load()
  } finally {
    bulkRunning.value = false
  }
}

function eligibilityBadge(t: TenderListItem): { text: string; class: string; tooltip?: string } | null {
  const s = t.analysis_summary
  if (!s) return null
  if (s.eligible === true) return { text: 'SPEŁNIA', class: 'bg-green-100 text-green-800' }
  if (s.eligible === false) return {
    text: 'NIE SPEŁNIA',
    class: 'bg-red-100 text-red-800',
    tooltip: s.eligibility_summary || undefined,
  }
  if (s.analysis_status === 'running') return { text: '...', class: 'bg-blue-100 text-blue-800' }
  return null
}

function formatDeadline(d: string | null): { date: string; time: string } | null {
  if (!d) return null
  const dt = new Date(d)
  return {
    date: dt.toLocaleDateString('pl-PL'),
    time: dt.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' }),
  }
}

// Stats
const stats = computed(() => {
  if (!data.value) return { total: 0, analyzing: 0, completed: 0, rejected: 0, archived: 0, errors: 0 }
  const items = data.value.items
  return {
    total: data.value.total,
    analyzing: items.filter(t => ['analyzing', 'running', 'waiting_user'].includes(t.status)).length,
    completed: items.filter(t => t.status === 'completed').length,
    rejected: items.filter(t => t.status === 'rejected').length,
    archived: items.filter(t => isDeadlineExpired(t.submission_deadline) && !['completed', 'rejected'].includes(t.status)).length,
    errors: items.filter(t => ['scrape_failed', 'failed'].includes(t.status) || t.error_message).length,
  }
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-bold text-gray-900">TenderMate</h1>
      <RouterLink to="/tenders/new" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
        + Nowy przetarg
      </RouterLink>
    </div>

    <!-- Stats -->
    <div v-if="data" class="grid grid-cols-3 md:grid-cols-6 gap-3 mb-4">
      <button @click="statusFilter = ''; page = 1; load()"
        :class="['rounded-lg p-3 text-left transition-colors', !statusFilter ? 'bg-indigo-50 ring-2 ring-indigo-300' : 'bg-white shadow hover:bg-gray-50']">
        <p class="text-[10px] text-gray-500 uppercase tracking-wide">Wszystkie</p>
        <p class="text-xl font-bold text-gray-900">{{ stats.total }}</p>
      </button>
      <button @click="statusFilter = 'analyzing'; page = 1; load()"
        :class="['rounded-lg p-3 text-left transition-colors', statusFilter === 'analyzing' ? 'bg-blue-50 ring-2 ring-blue-300' : 'bg-white shadow hover:bg-gray-50']">
        <p class="text-[10px] text-blue-600 uppercase tracking-wide">W analizie</p>
        <p class="text-xl font-bold text-blue-600">{{ stats.analyzing }}</p>
      </button>
      <button @click="statusFilter = 'completed'; page = 1; load()"
        :class="['rounded-lg p-3 text-left transition-colors', statusFilter === 'completed' ? 'bg-green-50 ring-2 ring-green-300' : 'bg-white shadow hover:bg-gray-50']">
        <p class="text-[10px] text-green-600 uppercase tracking-wide">Zakończone</p>
        <p class="text-xl font-bold text-green-600">{{ stats.completed }}</p>
      </button>
      <button @click="statusFilter = 'rejected'; page = 1; load()"
        :class="['rounded-lg p-3 text-left transition-colors', statusFilter === 'rejected' ? 'bg-red-50 ring-2 ring-red-300' : 'bg-white shadow hover:bg-gray-50']">
        <p class="text-[10px] text-red-600 uppercase tracking-wide">Odrzucone</p>
        <p class="text-xl font-bold text-red-600">{{ stats.rejected }}</p>
      </button>
      <button @click="statusFilter = 'failed'; page = 1; load()"
        :class="['rounded-lg p-3 text-left transition-colors', statusFilter === 'failed' ? 'bg-red-50 ring-2 ring-red-300' : 'bg-white shadow hover:bg-gray-50']">
        <p class="text-[10px] text-red-600 uppercase tracking-wide">Błędy</p>
        <p class="text-xl font-bold text-red-600">{{ stats.errors }}</p>
      </button>
      <button @click="statusFilter = 'archived'; page = 1; load()"
        :class="['rounded-lg p-3 text-left transition-colors', statusFilter === 'archived' ? 'bg-orange-50 ring-2 ring-orange-300' : 'bg-white shadow hover:bg-gray-50']">
        <p class="text-[10px] text-orange-600 uppercase tracking-wide">Archiwalne</p>
        <p class="text-xl font-bold text-orange-600">{{ stats.archived }}</p>
      </button>
    </div>

    <!-- Filters -->
    <div class="flex items-center gap-3 mb-4">
      <select v-model="statusFilter" @change="page = 1; load()" class="border border-gray-300 rounded-lg px-3 py-1.5 text-sm">
        <option value="">Wszystkie statusy</option>
        <option v-for="(label, key) in statusLabels" :key="key" :value="key">{{ label }}</option>
      </select>
      <input
        v-model="searchQuery"
        @input="onSearchInput"
        type="text"
        placeholder="Szukaj (tytuł, zamawiający, nr ref.)..."
        class="border border-gray-300 rounded-lg px-3 py-1.5 text-sm flex-1 max-w-md"
      />
      <span v-if="data" class="text-xs text-gray-400">{{ data.total }} przetargów</span>
    </div>

    <!-- Bulk action bar -->
    <div v-if="selectedIds.size > 0" class="flex items-center gap-3 mb-3 px-3 py-2 bg-indigo-50 border border-indigo-200 rounded-lg text-sm">
      <span class="text-indigo-700 font-medium">Zaznaczono: {{ selectedIds.size }}</span>
      <button
        v-if="analyzableSelected.length > 0"
        @click="bulkStartAnalysis"
        :disabled="bulkRunning"
        class="px-3 py-1 bg-indigo-600 text-white rounded text-xs hover:bg-indigo-700 disabled:opacity-50"
      >
        Uruchom analizę ({{ analyzableSelected.length }})
      </button>
      <button
        v-if="reanalyzableSelected.length > 0"
        @click="bulkRestartAnalysis"
        :disabled="bulkRunning"
        class="px-3 py-1 bg-amber-600 text-white rounded text-xs hover:bg-amber-700 disabled:opacity-50"
      >
        Ponów analizę ({{ reanalyzableSelected.length }})
      </button>
      <button
        @click="bulkDelete"
        :disabled="bulkRunning"
        class="px-3 py-1 bg-red-600 text-white rounded text-xs hover:bg-red-700 disabled:opacity-50"
      >
        Usuń ({{ deletableSelected.length }})
      </button>
      <button @click="selectedIds = new Set()" class="text-xs text-gray-500 hover:text-gray-700 ml-auto">
        Odznacz wszystko
      </button>
    </div>

    <div v-if="loading && !data" class="text-center text-gray-400 py-8">Ładowanie...</div>
    <div v-else-if="data && data.items.length === 0" class="text-center text-gray-400 py-8">Brak przetargów</div>

    <!-- Table -->
    <div v-else-if="data" class="bg-white rounded-lg shadow overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-xs text-gray-500 border-b bg-gray-50">
            <th class="px-2 py-2 w-8">
              <input type="checkbox" :checked="allSelected" @change="toggleAll" class="rounded border-gray-300" />
            </th>
            <th class="px-3 py-2 cursor-pointer select-none" @click="toggleSort('title')">
              Tytuł <span class="text-gray-300">{{ sortIcon('title') }}</span>
            </th>
            <th class="px-3 py-2 cursor-pointer select-none" @click="toggleSort('contracting_authority')">
              Zamawiający <span class="text-gray-300">{{ sortIcon('contracting_authority') }}</span>
            </th>
            <th class="px-3 py-2 whitespace-nowrap">Portal</th>
            <th class="px-3 py-2 cursor-pointer select-none whitespace-nowrap" @click="toggleSort('submission_deadline')">
              Termin <span class="text-gray-300">{{ sortIcon('submission_deadline') }}</span>
            </th>
            <th class="px-3 py-2 cursor-pointer select-none" @click="toggleSort('status')">
              Status <span class="text-gray-300">{{ sortIcon('status') }}</span>
            </th>
            <th class="px-3 py-2">Warunki</th>
            <th class="px-3 py-2 text-center">Wadium</th>
            <th class="px-3 py-2 text-center">Zał.</th>
            <th class="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="t in data.items"
            :key="t.id"
            class="border-b border-gray-100 hover:bg-gray-50 group"
          >
            <!-- Checkbox -->
            <td class="px-2 py-2 w-8">
              <input type="checkbox" :checked="selectedIds.has(t.id)" @change="toggleOne(t.id)" class="rounded border-gray-300" />
            </td>

            <!-- Title + AI summary tooltip -->
            <td class="px-3 py-2 max-w-xs">
              <RouterLink :to="`/tenders/${t.id}`" class="font-medium text-gray-900 hover:text-indigo-600 block truncate" :title="t.ai_summary || t.title || ''">
                {{ t.title || 'Bez tytułu' }}
              </RouterLink>
              <p v-if="t.ai_summary" class="text-[10px] text-gray-500 line-clamp-2 mt-0.5">{{ t.ai_summary }}</p>
              <p v-if="t.reference_number && !t.ai_summary" class="text-[10px] text-gray-400 truncate">{{ t.reference_number }}</p>
            </td>

            <!-- Authority -->
            <td class="px-3 py-2 text-gray-600 max-w-[200px]" :title="t.contracting_authority || ''">
              <div class="flex items-center gap-1">
                <span v-if="t.authority_type === 'public'" class="text-[10px] shrink-0" title="Instytucja publiczna">&#127963;</span>
                <span v-else-if="t.authority_type === 'private'" class="text-[10px] shrink-0" title="Firma prywatna">&#127970;</span>
                <span class="truncate">{{ t.contracting_authority || '—' }}</span>
              </div>
            </td>

            <!-- Portal -->
            <td class="px-3 py-2 text-[10px] text-gray-500 whitespace-nowrap">
              {{ t.portal_name || '—' }}
            </td>

            <!-- Deadline -->
            <td class="px-3 py-2 whitespace-nowrap" :class="t.submission_deadline && new Date(t.submission_deadline) < new Date() ? 'text-red-500' : 'text-gray-600'">
              <template v-if="formatDeadline(t.submission_deadline)">
                <span>{{ formatDeadline(t.submission_deadline)!.date }}</span>
                <span class="block text-[10px] opacity-60">{{ formatDeadline(t.submission_deadline)!.time }}</span>
              </template>
              <span v-else>—</span>
            </td>

            <!-- Status -->
            <td class="px-3 py-2">
              <span class="inline-flex items-center gap-1">
                <svg v-if="isProcessing(t.status)" class="animate-spin h-3 w-3 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span :class="['text-[10px] px-1.5 py-0.5 rounded-full whitespace-nowrap font-medium', getStatusColor(getDisplayStatus(t.status, t.submission_deadline))]">
                  {{ getStatusLabel(getDisplayStatus(t.status, t.submission_deadline)) }}
                </span>
              </span>
              <!-- Error tooltip -->
              <div v-if="t.error_message" class="relative group/err inline-block ml-1 align-middle">
                <span class="text-red-500 cursor-help text-xs font-bold" title="">&#9888;</span>
                <div class="hidden group-hover/err:block absolute z-50 bottom-full left-0 mb-1 w-64 p-2 bg-red-50 border border-red-200 rounded shadow-lg text-[11px] text-red-700 whitespace-normal">
                  {{ t.error_message }}
                </div>
              </div>
            </td>

            <!-- Eligibility -->
            <td class="px-3 py-2">
              <span
                v-if="eligibilityBadge(t)"
                :class="['text-[10px] px-1.5 py-0.5 rounded font-bold cursor-default', eligibilityBadge(t)!.class]"
                :title="eligibilityBadge(t)!.tooltip"
              >
                {{ eligibilityBadge(t)!.text }}
              </span>
            </td>

            <!-- Wadium -->
            <td class="px-3 py-2 text-center">
              <span v-if="t.analysis_summary?.wadium_required === true" class="text-[10px] text-orange-700 font-medium whitespace-nowrap">
                {{ t.analysis_summary.wadium_amount || 'TAK' }}
              </span>
              <span v-else-if="t.analysis_summary?.wadium_required === false" class="text-[10px] text-gray-400">—</span>
            </td>

            <!-- Attachment count -->
            <td class="px-3 py-2 text-center text-gray-400">
              <span v-if="t.attachment_count">{{ t.attachment_count }}</span>
            </td>

            <!-- Actions -->
            <td class="px-3 py-2 text-right whitespace-nowrap">
              <RouterLink
                v-if="['scraped', 'analyzing', 'awaiting_decision', 'in_progress', 'running', 'waiting_user', 'completed', 'rejected', 'eligibility_failed'].includes(t.status)"
                :to="`/tenders/${t.id}/analysis`"
                class="text-[11px] text-indigo-600 hover:text-indigo-800 mr-2"
              >
                Analiza
              </RouterLink>
              <button @click="handleDelete(t.id)" class="text-[11px] text-red-500 hover:text-red-700 opacity-0 group-hover:opacity-100 transition-opacity">
                Usuń
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div v-if="data.total_pages > 1" class="flex items-center justify-between px-4 py-3 border-t bg-gray-50 text-sm">
        <span class="text-xs text-gray-500">
          Strona {{ data.page }} z {{ data.total_pages }} ({{ data.total }} wyników)
        </span>
        <div class="flex items-center gap-1">
          <button
            @click="goToPage(data!.page - 1)"
            :disabled="data.page <= 1"
            class="px-2 py-1 rounded text-xs border border-gray-300 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ← Poprzednia
          </button>
          <template v-for="p in data.total_pages" :key="p">
            <button
              v-if="p === 1 || p === data.total_pages || Math.abs(p - data.page) <= 2"
              @click="goToPage(p)"
              :class="[
                'px-2 py-1 rounded text-xs border',
                p === data.page ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-300 hover:bg-gray-100'
              ]"
            >
              {{ p }}
            </button>
            <span v-else-if="p === 2 || p === data.total_pages - 1" class="text-gray-400">…</span>
          </template>
          <button
            @click="goToPage(data!.page + 1)"
            :disabled="data.page >= data.total_pages"
            class="px-2 py-1 rounded text-xs border border-gray-300 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Następna →
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
