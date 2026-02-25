<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { startAnalysis, getAnalysis, submitDecision, fixEligibility, cancelAnalysis, uploadVerificationDocuments, type CustomFixInput } from '@/api/analysis'
import { uploadAttachments, listAttachments, type TenderAttachment } from '@/api/tenders'
import type {
  Analysis, Step0Result, Step1Result, Step2Result, Step3Result,
  Step4Result, Step5Result, Step6Result, EligibilityCondition
} from '@/types/analysis'
import CopyableText from '@/components/analysis/CopyableText.vue'

const props = defineProps<{ id: string }>()
const router = useRouter()
const analysis = ref<Analysis | null>(null)
const loading = ref(true)
const error = ref('')
const sseConnected = ref(false)

// Progress tracking
const progressInfo = ref<{
  step: number
  label: string
  phase: string
  percent: number
  attachment_count: number
} | null>(null)

// Fix selections for eligibility
const fixSelections = ref<Record<number, string>>({})
const customTexts = ref<Record<number, string>>({})
const addToProfile = ref<Record<number, boolean>>({})
const addToPortfolio = ref<Record<number, boolean>>({})

// Attachment upload (ZIP support)
const attachmentFiles = ref<File[]>([])
const attachmentUploading = ref(false)
const attachmentDragOver = ref(false)
const attachmentUploadResult = ref<{ added: number; skipped: number } | null>(null)
const existingAttachments = ref<TenderAttachment[]>([])

// Verification files
const verificationFiles = ref<File[]>([])
const verificationUploading = ref(false)
const verificationDragOver = ref(false)

const tenderId = computed(() => Number(props.id))

const steps = [
  { num: 0, label: 'Warunki udziału' },
  { num: 1, label: 'Zakres i wymagania' },
  { num: 2, label: 'Rozwiązanie techniczne' },
  { num: 3, label: 'Wycena i koszty' },
  { num: 4, label: 'Analiza ryzyk' },
  { num: 5, label: 'Dokumenty ofertowe' },
  { num: 6, label: 'Weryfikacja' },
]

let eventSource: EventSource | null = null

function connectSSE() {
  if (eventSource) eventSource.close()
  eventSource = new EventSource(`/api/tenders/${props.id}/analysis/stream`)
  sseConnected.value = true

  eventSource.addEventListener('step_started', (e: any) => {
    try { const d = JSON.parse(e.data); activeTab.value = d.step } catch { /* ignore */ }
    refreshAnalysis()
  })
  eventSource.addEventListener('step_completed', (e: any) => {
    try { const d = JSON.parse(e.data); activeTab.value = d.step } catch { /* ignore */ }
    progressInfo.value = null
    refreshAnalysis()
  })
  eventSource.addEventListener('progress', (e: any) => {
    try { progressInfo.value = JSON.parse(e.data) } catch { /* ignore */ }
  })
  eventSource.addEventListener('error', (e: any) => {
    try {
      const data = JSON.parse(e.data)
      error.value = data.message || 'Błąd analizy'
    } catch { /* SSE connection error */ }
    progressInfo.value = null
    refreshAnalysis()
  })
  eventSource.onerror = () => { sseConnected.value = false }
}

async function refreshAnalysis() {
  try { analysis.value = await getAnalysis(tenderId.value) } catch { /* ignore */ }
}

async function loadAnalysis() {
  loading.value = true
  error.value = ''
  try {
    analysis.value = await getAnalysis(tenderId.value)
    if (analysis.value.status === 'running') { connectSSE(); startPolling() }
  } catch {
    try {
      analysis.value = await startAnalysis(tenderId.value)
      connectSSE(); startPolling()
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Nie udało się uruchomić analizy'
    }
  } finally { loading.value = false }
}

onMounted(() => { loadAnalysis(); loadExistingAttachments() })

onUnmounted(() => { if (eventSource) eventSource.close(); stopPolling() })

// Polling fallback
let pollInterval: ReturnType<typeof setInterval> | null = null
function startPolling() {
  if (pollInterval) return
  pollInterval = setInterval(async () => {
    await refreshAnalysis()
    if (analysis.value && analysis.value.status !== 'running') stopPolling()
  }, 3000)
}
function stopPolling() {
  if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
}

async function handleQuickReject() {
  try {
    await submitDecision(tenderId.value, 'no_go')
    router.push('/')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Błąd odrzucania przetargu'
  }
}

async function handleDecision(decision: 'go' | 'no_go') {
  error.value = ''
  try {
    analysis.value = await submitDecision(tenderId.value, decision)
    if (decision === 'go') { connectSSE(); startPolling() }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Błąd wysyłania decyzji'
    console.error('handleDecision error:', e)
  }
}

const cancelling = ref(false)

async function handleCancelAnalysis() {
  cancelling.value = true
  try {
    analysis.value = await cancelAnalysis(tenderId.value)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Błąd anulowania'
  } finally {
    cancelling.value = false
  }
}

const fixSaving = ref(false)

async function handleFixEligibility() {
  error.value = ''
  fixSaving.value = true
  const fixes = Object.entries(fixSelections.value).map(([condIdx, option]) => ({
    condition_index: Number(condIdx),
    chosen_fix: option,
  }))
  const customs: CustomFixInput[] = Object.entries(customTexts.value)
    .filter(([, text]) => text.trim())
    .map(([condIdx, text]) => ({
      condition_index: Number(condIdx),
      text,
      add_to_profile: addToProfile.value[Number(condIdx)] || false,
      add_to_portfolio: addToPortfolio.value[Number(condIdx)] || false,
    }))
  if (!fixes.length && !customs.length) { fixSaving.value = false; return }
  try {
    analysis.value = await fixEligibility(tenderId.value, fixes, customs)
    fixSelections.value = {}
    customTexts.value = {}
    addToProfile.value = {}
    addToPortfolio.value = {}
    connectSSE(); startPolling()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Błąd ponownego sprawdzenia'
    console.error('handleFixEligibility error:', e)
  } finally {
    fixSaving.value = false
  }
}

function stepStatus(stepNum: number): 'done' | 'active' | 'pending' {
  if (!analysis.value) return 'pending'
  const a = analysis.value
  if (a.status === 'running' && a.current_step === stepNum) return 'active'
  const stepKey = `step${stepNum}_result` as keyof Analysis
  if (a[stepKey]) return 'done'
  if (stepNum < a.current_step) return 'done'
  if (stepNum === a.current_step && a.status === 'running') return 'active'
  return 'pending'
}

const activeTab = ref(0)

function switchTab(num: number) {
  activeTab.value = num
}

const step0 = computed((): Step0Result | null => analysis.value?.step0_result as Step0Result | null)
const step1 = computed((): Step1Result | null => analysis.value?.step1_result as Step1Result | null)
const step2 = computed((): Step2Result | null => analysis.value?.step2_result as Step2Result | null)
const step3 = computed((): Step3Result | null => analysis.value?.step3_result as Step3Result | null)
const step4 = computed((): Step4Result | null => analysis.value?.step4_result as Step4Result | null)
const step5 = computed((): Step5Result | null => analysis.value?.step5_result as Step5Result | null)
const step6 = computed((): Step6Result | null => analysis.value?.step6_result as Step6Result | null)

const failedConditions = computed((): EligibilityCondition[] => {
  if (!step0.value?.conditions) return []
  return step0.value.conditions.filter(c => !c.met)
})

const hasFixableConditions = computed((): boolean => {
  return failedConditions.value.some(c => c.fixable && c.fix_options?.length)
})

const priorityBadge = (p: string) => {
  if (p === 'must_have') return 'bg-red-100 text-red-800'
  if (p === 'should_have') return 'bg-yellow-100 text-yellow-800'
  return 'bg-green-100 text-green-800'
}
const priorityLabel = (p: string) => {
  if (p === 'must_have') return 'WYMAGANE'
  if (p === 'should_have') return 'POŻĄDANE'
  return 'OPCJONALNE'
}

// Verification file handling
function handleVerificationDrop(e: DragEvent) {
  verificationDragOver.value = false
  const files = e.dataTransfer?.files
  if (files) addVerificationFiles(files)
}
function handleVerificationSelect(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (files) addVerificationFiles(files)
}
function addVerificationFiles(fileList: FileList) {
  for (const f of fileList) verificationFiles.value.push(f)
}
function removeVerificationFile(index: number) {
  verificationFiles.value.splice(index, 1)
}
async function submitVerification() {
  if (!verificationFiles.value.length) return
  verificationUploading.value = true
  error.value = ''
  try {
    analysis.value = await uploadVerificationDocuments(tenderId.value, verificationFiles.value)
    verificationFiles.value = []
    connectSSE(); startPolling()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Błąd wysyłania dokumentów'
  } finally { verificationUploading.value = false }
}

// Attachment upload handling
function handleAttachmentDrop(e: DragEvent) {
  attachmentDragOver.value = false
  const files = e.dataTransfer?.files
  if (files) addAttachmentFiles(files)
}
function handleAttachmentSelect(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (files) addAttachmentFiles(files)
}
function addAttachmentFiles(fileList: FileList) {
  for (const f of fileList) {
    // Skip duplicates already in queue
    if (!attachmentFiles.value.some(af => af.name === f.name && af.size === f.size)) {
      attachmentFiles.value.push(f)
    }
  }
}
function removeAttachmentFile(index: number) {
  attachmentFiles.value.splice(index, 1)
}
async function submitAttachments() {
  if (!attachmentFiles.value.length) return
  attachmentUploading.value = true
  attachmentUploadResult.value = null
  error.value = ''
  try {
    const result = await uploadAttachments(tenderId.value, attachmentFiles.value)
    attachmentUploadResult.value = { added: result.length, skipped: attachmentFiles.value.length - result.length }
    attachmentFiles.value = []
    // Refresh attachments list
    existingAttachments.value = await listAttachments(tenderId.value)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Błąd wgrywania plików'
  } finally { attachmentUploading.value = false }
}

async function loadExistingAttachments() {
  try {
    existingAttachments.value = await listAttachments(tenderId.value)
  } catch { /* ignore */ }
}
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-3">
      <h1 class="text-lg font-bold text-gray-900">Analiza #{{ id }}</h1>
      <RouterLink :to="`/tenders/${id}`" class="text-xs text-indigo-600 hover:text-indigo-800">
        ← Wróć do przetargu
      </RouterLink>
    </div>

    <div v-if="loading" class="text-center text-gray-400 py-12">
      <div class="animate-spin h-8 w-8 border-3 border-indigo-600 border-t-transparent rounded-full mx-auto mb-3"></div>
      <p>Uruchamiam analizę...</p>
      <button @click="loadAnalysis" class="mt-4 text-xs text-indigo-600 hover:text-indigo-800 underline">
        Odśwież
      </button>
    </div>

    <div v-else-if="error && !analysis" class="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
      <p class="text-red-800 text-sm">{{ error }}</p>
    </div>

    <div v-else-if="analysis">
      <!-- Sticky Stepper -->
      <div class="sticky top-0 z-20 bg-white/95 backdrop-blur border-b border-gray-200 -mx-4 px-4 py-2 mb-4">
        <div class="flex items-center gap-1 overflow-x-auto">
          <button
            v-for="step in steps"
            :key="step.num"
            @click="switchTab(step.num)"
            :class="[
              'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors cursor-pointer',
              stepStatus(step.num) === 'done' ? 'bg-green-100 text-green-800 hover:bg-green-200' :
              stepStatus(step.num) === 'active' ? 'bg-indigo-100 text-indigo-800 hover:bg-indigo-200' :
              'bg-gray-100 text-gray-400 hover:bg-gray-200'
            ]"
          >
            <span
              class="w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold"
              :class="[
                stepStatus(step.num) === 'done' ? 'bg-green-600 text-white' :
                stepStatus(step.num) === 'active' ? 'bg-indigo-600 text-white' :
                'bg-gray-300 text-white'
              ]"
            >
              {{ stepStatus(step.num) === 'done' ? '✓' : step.num }}
            </span>
            {{ step.label }}
          </button>
        </div>
      </div>

      <!-- Error message -->
      <div v-if="error" class="bg-red-50 border border-red-200 rounded p-3 mb-3">
        <p class="text-xs text-red-800">{{ error }}</p>
      </div>

      <!-- Running indicator with progress -->
      <div v-if="analysis.status === 'running'" class="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
        <div class="flex items-center gap-2 mb-2">
          <div class="animate-spin h-4 w-4 border-2 border-indigo-600 border-t-transparent rounded-full"></div>
          <span class="text-xs font-medium text-blue-900">
            Krok {{ analysis.current_step }}/{{ steps.length - 1 }}: {{ progressInfo?.label || steps[analysis.current_step]?.label }}
          </span>
          <span v-if="progressInfo?.percent != null" class="text-[10px] text-blue-600 font-mono">
            {{ progressInfo.percent }}%
          </span>
        </div>
        <!-- Progress bar -->
        <div class="w-full bg-blue-200 rounded-full h-1.5 mb-1.5">
          <div
            class="bg-indigo-600 h-1.5 rounded-full transition-all duration-500"
            :style="{ width: (progressInfo?.percent ?? 10) + '%' }"
          ></div>
        </div>
        <!-- Phase description -->
        <div class="flex items-center justify-between">
          <p class="text-[11px] text-blue-700 italic">
            {{ progressInfo?.phase || 'Przetwarzam...' }}
          </p>
          <span v-if="progressInfo?.attachment_count" class="text-[10px] text-blue-500">
            {{ progressInfo.attachment_count }} załączników
          </span>
        </div>
      </div>

      <!-- ===== STEP 0: Eligibility ===== -->
      <div v-if="activeTab === 0 && step0" class="bg-white rounded-lg shadow p-4 mb-4">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-gray-900">Krok 0: Warunki udziału</h2>
          <button
            v-if="analysis.status === 'running' && analysis.current_step === 0"
            @click="handleCancelAnalysis"
            :disabled="cancelling"
            class="px-2.5 py-1 bg-gray-600 text-white rounded text-[10px] font-medium hover:bg-gray-700 disabled:opacity-50 flex items-center gap-1"
          >
            <svg v-if="cancelling" class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            {{ cancelling ? 'Anuluję...' : 'Przerwij sprawdzanie' }}
          </button>
        </div>

        <div v-if="step0.conditions?.length" class="space-y-2 mb-3">
          <div
            v-for="(cond, i) in step0.conditions"
            :key="i"
            :class="['border rounded p-3', cond.met ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50']"
          >
            <div class="flex items-start gap-2">
              <span :class="cond.met ? 'text-green-600' : 'text-red-600'" class="text-base mt-0.5">
                {{ cond.met ? '✓' : '✗' }}
              </span>
              <div class="flex-1 min-w-0">
                <div class="flex items-start justify-between gap-2">
                  <p class="font-medium text-xs text-gray-900">{{ cond.name }}</p>
                  <button
                    v-if="!cond.met && analysis?.status === 'waiting_user'"
                    @click="handleQuickReject"
                    class="shrink-0 px-2 py-1 bg-red-100 text-red-700 rounded text-[10px] font-medium hover:bg-red-200 transition-colors whitespace-nowrap"
                  >
                    Nie spełnimy
                  </button>
                </div>
                <p class="text-[11px] text-gray-600 mt-0.5">{{ cond.description }}</p>
                <p class="text-[11px] mt-0.5" :class="cond.met ? 'text-green-700' : 'text-red-700'">
                  {{ cond.reason }}
                </p>
                <div v-if="!cond.met && cond.fixable && cond.fix_options?.length" class="mt-2 bg-white rounded p-2 border border-yellow-200">
                  <p class="text-[10px] font-medium text-yellow-800 mb-1">Możliwe rozwiązania:</p>
                  <div class="space-y-1">
                    <label v-for="(opt, j) in cond.fix_options" :key="j"
                      class="flex items-start gap-1.5 text-[11px] text-gray-700 cursor-pointer hover:text-gray-900">
                      <input type="radio" :name="'fix-' + i" :value="opt" v-model="fixSelections[i]" class="mt-0.5 text-indigo-600" />
                      <span>{{ opt }}</span>
                    </label>
                  </div>
                </div>
                <!-- Custom text input for failed conditions -->
                <div v-if="!cond.met && analysis.status === 'waiting_user'" class="mt-2 bg-white rounded p-2 border border-blue-200">
                  <p class="text-[10px] font-medium text-blue-800 mb-1">Opisz dlaczego spełniasz ten warunek:</p>
                  <textarea
                    v-model="customTexts[i]"
                    rows="2"
                    class="w-full border border-gray-300 rounded px-2 py-1 text-[11px]"
                    placeholder="Np. Mamy projekt X dla klienta Y o wartości Z, technologie: A, B..."
                  ></textarea>
                  <div class="flex items-center gap-4 mt-1">
                    <label class="flex items-center gap-1 text-[10px] text-gray-600 cursor-pointer">
                      <input type="checkbox" v-model="addToProfile[i]" class="rounded text-indigo-600" />
                      Zapisz w profilu firmy (zespół, technologie, certyfikaty)
                    </label>
                    <label class="flex items-center gap-1 text-[10px] text-gray-600 cursor-pointer">
                      <input type="checkbox" v-model="addToPortfolio[i]" class="rounded text-indigo-600" />
                      Aktualizuj / dodaj projekty w portfolio
                    </label>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="step0.summary" class="bg-gray-50 rounded p-3 mb-3">
          <CopyableText :text="step0.summary" />
        </div>

        <!-- Attachment upload section -->
        <div v-if="analysis.status === 'waiting_user'" class="border-t pt-3 mb-3">
          <div class="bg-blue-50 border border-blue-200 rounded-lg p-3">
            <h3 class="text-xs font-semibold text-blue-900 mb-2 flex items-center gap-1.5">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              Dodaj brakujące dokumenty (ZIP, PDF, DOCX, XLSX)
            </h3>

            <!-- Existing attachments -->
            <div v-if="existingAttachments.length" class="mb-2">
              <p class="text-[10px] text-gray-500 mb-1">Obecne załączniki ({{ existingAttachments.length }}):</p>
              <div class="flex flex-wrap gap-1">
                <span v-for="att in existingAttachments" :key="att.id"
                  class="inline-flex items-center px-1.5 py-0.5 rounded bg-gray-100 text-[10px] text-gray-600">
                  {{ att.filename }}
                  <span v-if="att.file_size_bytes" class="text-gray-400 ml-1">({{ Math.round(att.file_size_bytes / 1024) }} KB)</span>
                </span>
              </div>
            </div>

            <!-- Drop zone -->
            <div
              @dragover.prevent="attachmentDragOver = true"
              @dragleave.prevent="attachmentDragOver = false"
              @drop.prevent="handleAttachmentDrop"
              :class="['border-2 border-dashed rounded-lg p-3 text-center cursor-pointer transition-colors',
                attachmentDragOver ? 'border-blue-400 bg-blue-100' : 'border-gray-300 hover:border-blue-400 bg-white']"
              @click="($refs.attachmentInput as HTMLInputElement)?.click()"
            >
              <p class="text-[11px] text-gray-500">Przeciągnij pliki lub kliknij aby wybrać</p>
              <p class="text-[10px] text-gray-400">ZIP-y zostaną automatycznie rozpakowane, duplikaty pominięte</p>
              <input ref="attachmentInput" type="file" multiple class="hidden" @change="handleAttachmentSelect"
                accept=".pdf,.docx,.doc,.xlsx,.xls,.zip,.rar,.7z,.csv,.txt,.pptx" />
            </div>

            <!-- Queued files -->
            <div v-if="attachmentFiles.length" class="mt-2 space-y-1">
              <div v-for="(file, i) in attachmentFiles" :key="i"
                class="flex items-center justify-between bg-white rounded px-2 py-1 border text-[11px]">
                <div class="flex items-center gap-1.5">
                  <span class="text-gray-400">{{ file.name.endsWith('.zip') ? '📦' : '📄' }}</span>
                  <span class="text-gray-700">{{ file.name }}</span>
                  <span class="text-gray-400">({{ Math.round(file.size / 1024) }} KB)</span>
                </div>
                <button @click="removeAttachmentFile(i)" class="text-red-400 hover:text-red-600 text-xs">✕</button>
              </div>
              <button @click="submitAttachments" :disabled="attachmentUploading"
                class="w-full px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-1.5">
                <svg v-if="attachmentUploading" class="animate-spin h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                {{ attachmentUploading ? 'Wgrywam i rozpakowuję...' : `Wgraj ${attachmentFiles.length} plik(ów)` }}
              </button>
            </div>

            <!-- Upload result -->
            <div v-if="attachmentUploadResult" class="mt-2 text-[11px]">
              <p class="text-green-700" v-if="attachmentUploadResult.added">
                Dodano {{ attachmentUploadResult.added }} nowych plików.
              </p>
              <p class="text-yellow-700" v-if="attachmentUploadResult.skipped">
                Pominięto {{ attachmentUploadResult.skipped }} duplikatów.
              </p>
            </div>
          </div>
        </div>

        <!-- NOT eligible -->
        <div v-if="step0.eligible === false && analysis.status === 'waiting_user'" class="border-t pt-3 space-y-2">
          <div class="flex gap-2">
            <button @click="handleFixEligibility"
              :disabled="fixSaving || (Object.keys(fixSelections).length === 0 && !Object.values(customTexts).some(t => t?.trim()))"
              class="px-3 py-1.5 bg-yellow-600 text-white rounded text-xs hover:bg-yellow-700 disabled:opacity-50 flex items-center gap-1.5">
              <svg v-if="fixSaving" class="animate-spin h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              {{ fixSaving ? 'Zapisuję i sprawdzam...' : 'Zapisz dane i ponów sprawdzanie' }}
            </button>
            <button @click="handleDecision('no_go')" class="px-3 py-1.5 bg-red-600 text-white rounded text-xs hover:bg-red-700">
              Odrzuć przetarg
            </button>
          </div>
        </div>

        <!-- GO / NO-GO -->
        <div v-if="step0.eligible && analysis.status === 'waiting_user' && !analysis.user_decision" class="border-t pt-3">
          <div class="bg-indigo-50 rounded p-3 mb-3 space-y-2">
            <p class="text-xs text-gray-700">{{ step0.scope_description }}</p>
            <p class="text-xs text-gray-700"><strong>Szacunkowy budżet:</strong> {{ step0.estimated_budget }}</p>

            <!-- Wadium -->
            <div v-if="step0.wadium" class="border-t border-indigo-200 pt-2">
              <p class="text-xs font-semibold text-gray-800 mb-1">Wadium</p>
              <div v-if="step0.wadium.required" class="space-y-0.5">
                <p class="text-xs text-gray-700"><strong>Kwota:</strong> {{ step0.wadium.amount }}</p>
                <p v-if="step0.wadium.forms?.length" class="text-xs text-gray-700"><strong>Formy:</strong> {{ step0.wadium.forms.join(', ') }}</p>
                <p v-if="step0.wadium.deadline" class="text-xs text-gray-700"><strong>Termin:</strong> {{ step0.wadium.deadline }}</p>
                <p v-if="step0.wadium.bank_account" class="text-xs text-gray-700"><strong>Konto:</strong> {{ step0.wadium.bank_account }}</p>
                <p v-if="step0.wadium.source_reference" class="text-[10px] text-gray-400">{{ step0.wadium.source_reference }}</p>
              </div>
              <p v-else class="text-xs text-green-700">Wadium nie jest wymagane</p>
            </div>

            <!-- Kryteria oceny ofert -->
            <div v-if="step0.evaluation_criteria?.length" class="border-t border-indigo-200 pt-2">
              <p class="text-xs font-semibold text-gray-800 mb-1">Kryteria oceny ofert</p>
              <div class="space-y-1.5">
                <div v-for="(crit, i) in step0.evaluation_criteria" :key="i" class="bg-white rounded border border-indigo-200 p-2">
                  <div class="flex items-center justify-between">
                    <span class="text-xs font-bold text-gray-900">{{ crit.name }}</span>
                    <span class="text-xs font-black text-indigo-700 bg-indigo-100 px-1.5 py-0.5 rounded">{{ crit.weight_pct }}%</span>
                  </div>
                  <p v-if="crit.scoring_method" class="text-[11px] text-gray-600 mt-0.5">{{ crit.scoring_method }}</p>
                </div>
              </div>
              <p class="text-[10px] text-gray-400 mt-1">Szczegółowa strategia punktowa pojawi się w kroku 3 (wycena)</p>
            </div>
          </div>
          <div class="flex gap-2">
            <button @click="handleDecision('go')" class="flex-1 px-4 py-2 bg-green-600 text-white rounded font-medium text-sm hover:bg-green-700 text-center">
              GO — Kontynuuj
            </button>
            <button @click="handleDecision('no_go')" class="flex-1 px-4 py-2 bg-red-600 text-white rounded font-medium text-sm hover:bg-red-700 text-center">
              NO-GO — Odpuść
            </button>
          </div>
        </div>

        <div v-if="analysis.user_decision === 'no_go'" class="border-t pt-3">
          <p class="text-red-600 font-medium text-sm">Przetarg odrzucony.</p>
        </div>
      </div>

      <!-- ===== STEP 1: Scope & Requirements ===== -->
      <div v-if="activeTab === 1 && step1" class="bg-white rounded-lg shadow p-4 mb-4">
        <h2 class="text-sm font-semibold text-gray-900 mb-3">Krok 1: Zakres i wymagania</h2>

        <div v-if="step1.scope_summary" class="bg-indigo-50 rounded p-3 mb-3">
          <p class="text-xs text-gray-700">{{ step1.scope_summary }}</p>
        </div>

        <!-- Functional requirements -->
        <div v-if="step1.functional_requirements?.length" class="mb-3">
          <h3 class="text-xs font-semibold text-gray-700 mb-1">Wymagania funkcjonalne ({{ step1.functional_requirements.length }})</h3>
          <div class="space-y-1">
            <details v-for="req in step1.functional_requirements" :key="req.id" class="border rounded">
              <summary class="px-3 py-2 cursor-pointer hover:bg-gray-50 flex items-center justify-between text-xs">
                <div class="flex items-center gap-1.5">
                  <span class="font-mono text-gray-400 text-[10px]">{{ req.id }}</span>
                  <span class="font-medium text-gray-900">{{ req.name }}</span>
                </div>
                <span :class="['text-[9px] font-bold uppercase px-1 py-0.5 rounded', priorityBadge(req.priority)]">
                  {{ priorityLabel(req.priority) }}
                </span>
              </summary>
              <div class="px-3 pb-2 space-y-1 text-[11px]">
                <p class="text-gray-700">{{ req.description }}</p>
                <div v-if="req.acceptance_criteria?.length">
                  <ul class="list-disc list-inside text-gray-600 space-y-0.5">
                    <li v-for="(ac, i) in req.acceptance_criteria" :key="i">{{ ac }}</li>
                  </ul>
                </div>
                <p v-if="req.source_reference" class="text-gray-400">Źródło: {{ req.source_reference }}</p>
              </div>
            </details>
          </div>
        </div>

        <!-- Non-functional requirements -->
        <div v-if="step1.non_functional_requirements?.length" class="mb-3">
          <h3 class="text-xs font-semibold text-gray-700 mb-1">Wymagania niefunkcjonalne</h3>
          <div class="space-y-1">
            <div v-for="(nfr, i) in step1.non_functional_requirements" :key="i" class="bg-gray-50 rounded p-2">
              <p class="text-xs font-medium text-gray-900">{{ nfr.name }}</p>
              <p class="text-[11px] text-gray-600">{{ nfr.description }}</p>
              <p v-if="nfr.metric" class="text-[11px] text-indigo-700">Metryka: {{ nfr.metric }}</p>
            </div>
          </div>
        </div>

        <!-- Deliverables -->
        <div v-if="step1.deliverables?.length" class="mb-3">
          <h3 class="text-xs font-semibold text-gray-700 mb-1">Produkty do dostarczenia</h3>
          <div class="space-y-0.5">
            <div v-for="(d, i) in step1.deliverables" :key="i" class="flex justify-between text-xs py-1.5 border-b border-gray-100">
              <div>
                <span class="font-medium text-gray-900">{{ d.name }}</span>
                <span class="text-[10px] text-gray-500 ml-1">({{ d.format }})</span>
              </div>
              <span v-if="d.deadline" class="text-[10px] text-gray-500 whitespace-nowrap">{{ d.deadline }}</span>
            </div>
          </div>
        </div>

        <!-- Open questions -->
        <div v-if="step1.open_questions?.length" class="bg-yellow-50 border border-yellow-200 rounded p-3 mb-3">
          <h3 class="font-medium text-yellow-800 text-xs mb-1">Pytania do zamawiającego</h3>
          <ul class="list-disc list-inside text-[11px] text-yellow-700 space-y-0.5">
            <li v-for="(q, i) in step1.open_questions" :key="i">{{ q }}</li>
          </ul>
        </div>

        <!-- Assumptions & Out of scope -->
        <div class="grid grid-cols-2 gap-3 mb-3">
          <div v-if="step1.assumptions?.length" class="bg-blue-50 rounded p-2">
            <h3 class="text-[10px] font-semibold text-blue-700 uppercase mb-1">Założenia</h3>
            <ul class="list-disc list-inside text-[11px] text-blue-800 space-y-0.5">
              <li v-for="(a, i) in step1.assumptions" :key="i">{{ a }}</li>
            </ul>
          </div>
          <div v-if="step1.out_of_scope?.length" class="bg-gray-50 rounded p-2">
            <h3 class="text-[10px] font-semibold text-gray-500 uppercase mb-1">Poza zakresem</h3>
            <ul class="list-disc list-inside text-[11px] text-gray-600 space-y-0.5">
              <li v-for="(o, i) in step1.out_of_scope" :key="i">{{ o }}</li>
            </ul>
          </div>
        </div>

        <div v-if="step1.summary"><CopyableText :text="step1.summary" /></div>
      </div>

      <!-- ===== STEP 2: Technical Solution ===== -->
      <div v-if="activeTab === 2 && step2" class="bg-white rounded-lg shadow p-4 mb-4">
        <h2 class="text-sm font-semibold text-gray-900 mb-3">Krok 2: Rozwiązanie techniczne</h2>

        <div v-if="step2.recommended_architecture" class="bg-indigo-50 rounded p-3 mb-3">
          <p class="text-xs text-gray-700 whitespace-pre-wrap">{{ step2.recommended_architecture }}</p>
        </div>

        <!-- Open source analysis -->
        <div v-if="step2.open_source_analysis?.length" class="mb-3">
          <h3 class="text-xs font-semibold text-gray-700 mb-1">Analiza open source</h3>
          <div class="space-y-2">
            <div v-for="(oss, i) in step2.open_source_analysis" :key="i"
              :class="['border rounded p-3', oss.fits ? 'border-green-200' : 'border-gray-200']">
              <div class="flex items-center justify-between mb-1">
                <div class="flex items-center gap-1.5">
                  <span :class="oss.fits ? 'text-green-600' : 'text-red-600'">{{ oss.fits ? '✓' : '✗' }}</span>
                  <span class="font-medium text-xs text-gray-900">{{ oss.name }}</span>
                  <span class="text-[9px] bg-gray-100 text-gray-600 px-1 py-0.5 rounded">{{ oss.category }}</span>
                </div>
                <span class="text-xs font-bold" :class="oss.coverage_pct >= 70 ? 'text-green-700' : oss.coverage_pct >= 40 ? 'text-yellow-700' : 'text-red-700'">
                  {{ oss.coverage_pct }}%
                </span>
              </div>
              <div class="w-full bg-gray-200 rounded-full h-1.5 mb-2">
                <div class="h-1.5 rounded-full" :class="oss.coverage_pct >= 70 ? 'bg-green-500' : oss.coverage_pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'"
                  :style="{ width: oss.coverage_pct + '%' }"></div>
              </div>
              <div class="grid grid-cols-2 gap-2 text-[11px]">
                <div v-if="oss.pros?.length">
                  <p class="font-semibold text-green-700 mb-0.5">Zalety</p>
                  <ul class="list-disc list-inside text-gray-600 space-y-0.5">
                    <li v-for="(p, j) in oss.pros" :key="j">{{ p }}</li>
                  </ul>
                </div>
                <div v-if="oss.cons?.length">
                  <p class="font-semibold text-red-700 mb-0.5">Wady</p>
                  <ul class="list-disc list-inside text-gray-600 space-y-0.5">
                    <li v-for="(c, j) in oss.cons" :key="j">{{ c }}</li>
                  </ul>
                </div>
              </div>
              <p v-if="oss.customization_needed" class="text-[11px] text-gray-600 mt-1"><span class="font-semibold">Do dostosowania:</span> {{ oss.customization_needed }}</p>
              <p class="text-[10px] text-gray-400 mt-0.5">
                Licencja: {{ oss.license }}
                <span v-if="oss.license_compatible" class="text-green-600">(OK)</span>
                <span v-else class="text-red-600">(UWAGA)</span>
              </p>
            </div>
          </div>
        </div>

        <!-- Proposed stack -->
        <div v-if="step2.proposed_stack?.length" class="mb-3">
          <h3 class="text-xs font-semibold text-gray-700 mb-1">Stack technologiczny</h3>
          <table class="w-full text-[11px]">
            <thead><tr class="text-left text-[10px] text-gray-500 border-b">
              <th class="pb-1">Warstwa</th><th class="pb-1">Technologia</th><th class="pb-1">Uzasadnienie</th><th class="pb-1">Licencja</th>
            </tr></thead>
            <tbody>
              <tr v-for="(s, i) in step2.proposed_stack" :key="i" class="border-b border-gray-100">
                <td class="py-1 text-gray-500 uppercase text-[10px]">{{ s.layer }}</td>
                <td class="py-1 font-medium">{{ s.technology }}</td>
                <td class="py-1 text-gray-600">{{ s.rationale }}</td>
                <td class="py-1 text-gray-500">{{ s.license }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Integration points -->
        <div v-if="step2.integration_points?.length" class="mb-3">
          <h3 class="text-xs font-semibold text-gray-700 mb-1">Punkty integracji</h3>
          <div class="space-y-1">
            <div v-for="(ip, i) in step2.integration_points" :key="i" class="bg-gray-50 rounded p-2 flex justify-between items-start">
              <div>
                <p class="text-xs font-medium text-gray-900">{{ ip.name }}</p>
                <p class="text-[11px] text-gray-600">{{ ip.description }} ({{ ip.technology }})</p>
              </div>
              <span :class="[
                'text-[9px] font-bold uppercase px-1 py-0.5 rounded',
                ip.complexity === 'high' ? 'bg-red-100 text-red-800' :
                ip.complexity === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                'bg-green-100 text-green-800'
              ]">{{ ip.complexity }}</span>
            </div>
          </div>
        </div>

        <div v-if="step2.hosting_recommendation" class="bg-blue-50 rounded p-2 mb-3">
          <p class="text-xs text-gray-700"><strong class="text-blue-700">Hosting:</strong> {{ step2.hosting_recommendation }}</p>
        </div>

        <div v-if="step2.summary"><CopyableText :text="step2.summary" /></div>
      </div>

      <!-- ===== STEP 3: Effort & Cost ===== -->
      <div v-if="activeTab === 3 && step3" class="bg-white rounded-lg shadow p-4 mb-4">
        <h2 class="text-sm font-semibold text-gray-900 mb-3">Krok 3: Wycena i koszty</h2>

        <!-- Evaluation criteria — prominent strategy section -->
        <div v-if="step3.evaluation_criteria?.length" class="mb-4 border-2 border-indigo-300 rounded-lg overflow-hidden">
          <div class="bg-indigo-600 px-3 py-2">
            <h3 class="text-sm font-bold text-white">Kryteria oceny ofert — strategia punktowa</h3>
            <p class="text-[11px] text-indigo-200">Zapoznaj się z każdym kryterium i zdecyduj, co oferujesz</p>
          </div>
          <div class="divide-y divide-indigo-100">
            <div v-for="(cr, i) in step3.evaluation_criteria" :key="i" class="p-3">
              <div class="flex items-center justify-between mb-1">
                <span class="text-sm font-bold text-gray-900">{{ cr.name }}</span>
                <span class="text-sm font-black text-indigo-700 bg-indigo-100 px-2 py-0.5 rounded">{{ cr.weight_pct }}%</span>
              </div>
              <p class="text-xs text-gray-600 mb-1">{{ cr.scoring_method }}</p>
              <div class="bg-green-50 border border-green-200 rounded p-2 mt-1">
                <p class="text-xs text-green-800"><strong>Jak zdobyć MAX punktów:</strong> {{ cr.how_to_maximize }}</p>
              </div>
              <div v-if="cr.our_strategy" class="bg-blue-50 border border-blue-200 rounded p-2 mt-1">
                <p class="text-xs text-blue-800"><strong>Nasza propozycja:</strong> {{ cr.our_strategy }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Work packages -->
        <div v-if="step3.work_packages?.length" class="mb-3">
          <h3 class="text-xs font-semibold text-gray-700 mb-1">Pakiety prac</h3>
          <table class="w-full text-[11px]">
            <thead><tr class="text-left text-[10px] text-gray-500 border-b">
              <th class="pb-1">Pakiet</th><th class="pb-1 text-right">Godziny</th><th class="pb-1 text-right">Netto</th>
            </tr></thead>
            <tbody>
              <tr v-for="(wp, i) in step3.work_packages" :key="i" class="border-b border-gray-100">
                <td class="py-1">
                  <p class="font-medium">{{ wp.name }}</p>
                  <p class="text-gray-500 text-[10px]">{{ wp.description }}</p>
                </td>
                <td class="py-1 text-right text-gray-600">{{ wp.hours }}h</td>
                <td class="py-1 text-right font-medium">{{ wp.cost_net_pln?.toLocaleString() }} PLN</td>
              </tr>
              <tr class="bg-gray-50 border-b">
                <td class="py-1 font-medium">Suma prac</td>
                <td class="py-1 text-right text-gray-600">{{ step3.subtotal_hours }}h</td>
                <td class="py-1 text-right font-bold">{{ step3.subtotal_net_pln?.toLocaleString() }} PLN</td>
              </tr>
              <tr class="border-b border-gray-100">
                <td class="py-1 text-gray-600">+ QA ({{ step3.qa_buffer_pct }}%)</td><td></td>
                <td class="py-1 text-right text-gray-600">{{ step3.qa_buffer_pln?.toLocaleString() }} PLN</td>
              </tr>
              <tr class="border-b border-gray-100">
                <td class="py-1 text-gray-600">+ Ryzyko ({{ step3.risk_buffer_pct }}%)</td><td></td>
                <td class="py-1 text-right text-gray-600">{{ step3.risk_buffer_pln?.toLocaleString() }} PLN</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="bg-indigo-50 font-bold">
                <td class="py-2">RAZEM NETTO</td><td></td>
                <td class="py-2 text-right text-indigo-700 text-sm">{{ step3.total_net_pln?.toLocaleString() }} PLN</td>
              </tr>
              <tr v-if="step3.total_gross_pln" class="bg-indigo-50">
                <td class="pb-2 text-[11px] text-gray-600">RAZEM BRUTTO</td><td></td>
                <td class="pb-2 text-right text-[11px] text-gray-600">{{ step3.total_gross_pln?.toLocaleString() }} PLN</td>
              </tr>
            </tfoot>
          </table>
        </div>

        <!-- Suggested offer price -->
        <div v-if="step3.suggested_offer_price_net" class="bg-green-50 border border-green-200 rounded p-3 mb-3">
          <p class="text-xs text-green-800">
            <strong>Cena ofertowa netto:</strong> {{ step3.suggested_offer_price_net?.toLocaleString() }} PLN
          </p>
          <p v-if="step3.price_justification" class="text-[11px] text-green-700 mt-0.5">{{ step3.price_justification }}</p>
        </div>

        <!-- Pricing items -->
        <div v-if="step3.pricing_items?.length" class="mb-3">
          <h3 class="text-xs font-semibold text-gray-700 mb-1">Formularz ofertowy</h3>
          <table class="w-full text-[11px]">
            <thead><tr class="text-left text-[10px] text-gray-500 border-b">
              <th class="pb-1">Pozycja</th><th class="pb-1">Jedn.</th><th class="pb-1 text-right">Cena</th><th class="pb-1 text-right">Ilość</th><th class="pb-1 text-right">Suma</th>
            </tr></thead>
            <tbody>
              <tr v-for="(item, i) in step3.pricing_items" :key="i" class="border-b border-gray-100">
                <td class="py-1 font-medium">{{ item.name }}</td>
                <td class="py-1 text-gray-600">{{ item.unit }}</td>
                <td class="py-1 text-right text-gray-600">{{ item.unit_price_net?.toLocaleString() || '-' }}</td>
                <td class="py-1 text-right text-gray-600">{{ item.quantity || '-' }}</td>
                <td class="py-1 text-right font-medium">{{ item.total_net?.toLocaleString() || '-' }} PLN</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Deadlines -->
        <div v-if="step3.deadlines?.length" class="mb-3">
          <h3 class="text-xs font-semibold text-gray-700 mb-1">Terminy</h3>
          <div class="space-y-0.5">
            <div v-for="(dl, i) in step3.deadlines" :key="i" class="flex justify-between text-[11px] py-1 border-b border-gray-100">
              <span class="text-gray-700">{{ dl.name }}</span>
              <span class="font-medium text-gray-900">{{ dl.date }}</span>
            </div>
          </div>
        </div>

        <!-- Required personnel -->
        <div v-if="step3.required_personnel?.length" class="mb-3">
          <h3 class="text-xs font-semibold text-gray-700 mb-1">Personel</h3>
          <div class="space-y-1">
            <div v-for="(person, i) in step3.required_personnel" :key="i" class="bg-gray-50 rounded p-2">
              <p class="text-xs font-medium text-gray-900">{{ person.role }}</p>
              <p v-if="person.min_experience_years" class="text-[11px] text-gray-600">Min. {{ person.min_experience_years }} lat doświadczenia</p>
              <p v-if="person.our_candidate" class="text-[11px] mt-0.5" :class="person.our_candidate.includes('brak') ? 'text-red-600 font-medium' : 'text-green-700'">
                Kandydat: {{ person.our_candidate }}
              </p>
            </div>
          </div>
        </div>

        <div v-if="step3.summary"><CopyableText :text="step3.summary" /></div>
      </div>

      <!-- ===== STEP 4: Risk Analysis ===== -->
      <div v-if="activeTab === 4 && step4" class="bg-white rounded-lg shadow p-4 mb-4">
        <h2 class="text-sm font-semibold text-gray-900 mb-3">Krok 4: Analiza ryzyk</h2>

        <!-- GO/NO-GO recommendation -->
        <div v-if="step4.go_no_go_recommendation" class="mb-3 p-3 rounded-lg border-2"
          :class="step4.go_no_go_recommendation === 'GO' ? 'bg-green-50 border-green-300' :
            step4.go_no_go_recommendation === 'NO-GO' ? 'bg-red-50 border-red-300' :
            'bg-yellow-50 border-yellow-300'">
          <p class="font-bold text-sm" :class="step4.go_no_go_recommendation === 'GO' ? 'text-green-800' :
            step4.go_no_go_recommendation === 'NO-GO' ? 'text-red-800' : 'text-yellow-800'">
            Rekomendacja: {{ step4.go_no_go_recommendation }}
          </p>
          <p v-if="step4.recommendation_rationale" class="text-xs mt-0.5" :class="step4.go_no_go_recommendation === 'GO' ? 'text-green-700' :
            step4.go_no_go_recommendation === 'NO-GO' ? 'text-red-700' : 'text-yellow-700'">
            {{ step4.recommendation_rationale }}
          </p>
        </div>

        <!-- Critical warnings -->
        <div v-if="step4.critical_warnings?.length" class="bg-red-50 border border-red-200 rounded p-3 mb-3">
          <h3 class="font-medium text-red-800 text-xs mb-1">Ostrzeżenia krytyczne</h3>
          <ul class="list-disc list-inside text-[11px] text-red-700 space-y-0.5">
            <li v-for="(w, i) in step4.critical_warnings" :key="i">{{ w }}</li>
          </ul>
        </div>

        <!-- Contract red flags -->
        <div v-if="step4.contract_red_flags?.length" class="bg-orange-50 border border-orange-200 rounded p-3 mb-3">
          <h3 class="font-medium text-orange-800 text-xs mb-1">Red flagi w umowie</h3>
          <ul class="list-disc list-inside text-[11px] text-orange-700 space-y-0.5">
            <li v-for="(rf, i) in step4.contract_red_flags" :key="i">{{ rf }}</li>
          </ul>
        </div>

        <!-- Risks -->
        <div v-if="step4.risks?.length" class="space-y-2">
          <div v-for="(risk, i) in step4.risks" :key="i"
            :class="[
              'border-l-4 rounded p-3 bg-white border',
              risk.severity === 'high' ? 'border-l-red-500 border-red-100' :
              risk.severity === 'medium' ? 'border-l-yellow-500 border-yellow-100' :
              'border-l-green-500 border-green-100'
            ]">
            <div class="flex items-center justify-between mb-0.5">
              <div class="flex items-center gap-1.5">
                <span :class="[
                  'text-[9px] font-bold uppercase px-1 py-0.5 rounded',
                  risk.severity === 'high' ? 'bg-red-100 text-red-800' :
                  risk.severity === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                  'bg-green-100 text-green-800'
                ]">
                  {{ risk.severity === 'high' ? 'WYS' : risk.severity === 'medium' ? 'ŚR' : 'NISK' }}
                </span>
                <span class="text-[10px] text-gray-500">{{ risk.category }}</span>
              </div>
              <span class="text-[10px] font-bold" :class="risk.risk_score >= 12 ? 'text-red-700' : risk.risk_score >= 6 ? 'text-yellow-700' : 'text-green-700'">
                P:{{ risk.probability }} I:{{ risk.impact }} = {{ risk.risk_score }}
              </span>
            </div>
            <p class="text-xs font-medium text-gray-900">{{ risk.name }}</p>
            <p class="text-[11px] text-gray-600">{{ risk.description }}</p>
            <p class="text-[11px] text-blue-700 mt-0.5"><strong>Mitygacja:</strong> {{ risk.mitigation }}</p>
          </div>
        </div>

        <div v-if="step4.summary" class="mt-3"><CopyableText :text="step4.summary" /></div>
      </div>

      <!-- ===== STEP 5: Document Preparation ===== -->
      <div v-if="activeTab === 5 && step5" class="bg-white rounded-lg shadow p-4 mb-4">
        <h2 class="text-sm font-semibold text-gray-900 mb-3">Krok 5: Dokumenty ofertowe</h2>

        <!-- Wadium -->
        <div v-if="step5.wadium?.required" class="bg-yellow-50 border border-yellow-200 rounded p-3 mb-3">
          <h3 class="font-medium text-yellow-800 text-xs mb-1">Wadium</h3>
          <div class="text-[11px] space-y-0.5">
            <p><span class="text-gray-600">Kwota:</span> <strong>{{ step5.wadium.amount }}</strong></p>
            <p v-if="step5.wadium.deadline"><span class="text-gray-600">Termin:</span> {{ step5.wadium.deadline }}</p>
            <p v-if="step5.wadium.forms?.length"><span class="text-gray-600">Formy:</span> {{ step5.wadium.forms.join(', ') }}</p>
            <p v-if="step5.wadium.bank_account"><span class="text-gray-600">Konto:</span> <span class="font-mono text-[10px]">{{ step5.wadium.bank_account }}</span></p>
            <p v-if="step5.wadium.our_action" class="text-yellow-800 mt-1"><strong>Do zrobienia:</strong> {{ step5.wadium.our_action }}</p>
          </div>
        </div>

        <!-- Document guides -->
        <div v-if="step5.document_guides?.length" class="space-y-2 mb-3">
          <details v-for="(guide, i) in step5.document_guides" :key="i" class="border rounded">
            <summary class="px-3 py-2 cursor-pointer hover:bg-gray-50 flex items-center justify-between text-xs">
              <div class="flex items-center gap-1.5">
                <span class="font-medium text-gray-900">{{ guide.document_name }}</span>
                <span v-if="guide.requires_signature" class="text-[9px] bg-blue-100 text-blue-800 px-1 py-0.5 rounded">Podpis</span>
              </div>
              <span v-if="guide.is_required" class="text-[9px] text-red-600 font-bold">WYMAGANY</span>
            </summary>
            <div class="px-3 pb-2 space-y-2">
              <div v-if="guide.instruction">
                <p class="text-[11px] text-gray-700 whitespace-pre-wrap">{{ guide.instruction }}</p>
              </div>
              <div v-if="guide.suggested_text">
                <p class="text-[10px] font-semibold text-gray-500 uppercase mb-0.5">Tekst do skopiowania</p>
                <CopyableText :text="guide.suggested_text" />
              </div>
              <p v-if="guide.warnings" class="text-[11px] text-yellow-800 bg-yellow-50 rounded p-1.5"><strong>Uwaga:</strong> {{ guide.warnings }}</p>
            </div>
          </details>
        </div>

        <!-- Submission checklist -->
        <div v-if="step5.submission_checklist?.length" class="bg-gray-50 border border-gray-200 rounded p-3 mb-3">
          <h3 class="font-medium text-gray-800 text-xs mb-1">Checklist</h3>
          <div class="space-y-0.5">
            <label v-for="(item, i) in step5.submission_checklist" :key="i" class="flex items-start gap-1.5 text-[11px] text-gray-700 cursor-pointer">
              <input type="checkbox" class="mt-0.5 text-indigo-600 rounded" />
              <span>{{ item }}</span>
            </label>
          </div>
        </div>

        <div v-if="step5.general_notes" class="bg-blue-50 rounded p-3">
          <CopyableText :text="step5.general_notes" />
        </div>
      </div>

      <!-- ===== STEP 6: Document Verification ===== -->
      <div v-if="activeTab === 6 && (analysis.status === 'completed' || step6 || (analysis.status === 'running' && analysis.current_step === 6))"
        class="bg-white rounded-lg shadow p-4 mb-4">
        <h2 class="text-sm font-semibold text-gray-900 mb-3">Krok 6: Weryfikacja dokumentów</h2>

        <div v-if="analysis.status === 'running' && analysis.current_step === 6" class="flex items-center gap-2 text-xs text-blue-800 mb-3">
          <div class="animate-spin h-4 w-4 border-2 border-indigo-600 border-t-transparent rounded-full"></div>
          Weryfikuję dokumenty...
        </div>

        <!-- Upload area -->
        <div v-if="!step6 && analysis.status === 'completed' && analysis.step5_result"
          class="border-2 border-dashed rounded-lg p-6 text-center transition-colors"
          :class="verificationDragOver ? 'border-indigo-400 bg-indigo-50' : 'border-gray-300'"
          @dragover.prevent="verificationDragOver = true"
          @dragleave="verificationDragOver = false"
          @drop.prevent="handleVerificationDrop">
          <p class="text-xs text-gray-600 mb-1">Przeciągnij przygotowane dokumenty ofertowe</p>
          <p class="text-[10px] text-gray-400 mb-3">DOCX, PDF, XLSX, XLS, DOC</p>
          <label class="inline-block px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-xs cursor-pointer hover:bg-gray-200">
            Wybierz pliki
            <input type="file" multiple accept=".docx,.pdf,.xlsx,.xls,.doc" class="hidden" @change="handleVerificationSelect" />
          </label>
          <div v-if="verificationFiles.length" class="mt-3 text-left space-y-1">
            <div v-for="(f, i) in verificationFiles" :key="i" class="flex items-center justify-between bg-gray-50 rounded px-2 py-1 text-xs">
              <span>{{ f.name }} <span class="text-gray-400">({{ (f.size / 1024).toFixed(0) }} KB)</span></span>
              <button @click="removeVerificationFile(i)" class="text-red-500 text-[10px]">Usuń</button>
            </div>
          </div>
          <button v-if="verificationFiles.length" @click="submitVerification" :disabled="verificationUploading"
            class="mt-3 px-4 py-2 bg-indigo-600 text-white rounded text-xs font-medium hover:bg-indigo-700 disabled:opacity-50">
            {{ verificationUploading ? 'Wysyłam...' : 'Wyślij do weryfikacji' }}
          </button>
        </div>

        <!-- Verification results -->
        <div v-if="step6">
          <div class="mb-3 p-3 rounded-lg border-2"
            :class="step6.overall_status === 'ok' ? 'bg-green-50 border-green-300' : 'bg-red-50 border-red-300'">
            <p class="font-bold text-sm" :class="step6.overall_status === 'ok' ? 'text-green-800' : 'text-red-800'">
              {{ step6.overall_status === 'ok' ? 'Dokumenty poprawne' : 'Znaleziono problemy' }}
            </p>
            <p v-if="step6.summary" class="text-xs mt-0.5" :class="step6.overall_status === 'ok' ? 'text-green-700' : 'text-red-700'">
              {{ step6.summary }}
            </p>
          </div>

          <div v-if="step6.missing_documents?.length" class="bg-red-50 border border-red-200 rounded p-3 mb-3">
            <h3 class="font-medium text-red-800 text-xs mb-1">Brakujące dokumenty</h3>
            <ul class="list-disc list-inside text-[11px] text-red-700 space-y-0.5">
              <li v-for="(md, i) in step6.missing_documents" :key="i">{{ md }}</li>
            </ul>
          </div>

          <div v-if="step6.cross_document_issues?.length" class="bg-orange-50 border border-orange-200 rounded p-3 mb-3">
            <h3 class="font-medium text-orange-800 text-xs mb-1">Niespójności</h3>
            <div v-for="(ci, i) in step6.cross_document_issues" :key="i" class="text-[11px] text-orange-700 mb-1.5">
              <p>{{ ci.description }}</p>
              <p class="text-[10px] text-orange-600">{{ ci.documents_involved.join(', ') }}</p>
              <p class="text-[10px] text-blue-700"><strong>Fix:</strong> {{ ci.fix_suggestion }}</p>
            </div>
          </div>

          <div v-if="step6.documents_checked?.length" class="space-y-2 mb-3">
            <details v-for="(doc, i) in step6.documents_checked" :key="i" class="border rounded"
              :class="doc.status === 'ok' ? 'border-green-200' : doc.status === 'warning' ? 'border-yellow-200' : 'border-red-200'">
              <summary class="px-3 py-2 cursor-pointer hover:bg-gray-50 flex items-center justify-between text-xs">
                <div class="flex items-center gap-1.5">
                  <span :class="doc.status === 'ok' ? 'text-green-600' : doc.status === 'warning' ? 'text-yellow-600' : 'text-red-600'">
                    {{ doc.status === 'ok' ? '✓' : doc.status === 'warning' ? '⚠' : '✗' }}
                  </span>
                  <span class="font-medium text-gray-900">{{ doc.filename }}</span>
                </div>
                <div class="flex items-center gap-1.5">
                  <span class="text-[10px] text-gray-500">{{ doc.completeness_pct }}%</span>
                  <span v-if="doc.issues?.length" class="text-[10px] text-red-600 font-medium">{{ doc.issues.length }} uwag</span>
                </div>
              </summary>
              <div class="px-3 pb-2">
                <div v-if="doc.issues?.length" class="space-y-1">
                  <div v-for="(issue, j) in doc.issues" :key="j"
                    :class="[
                      'border-l-4 rounded p-2',
                      issue.severity === 'error' ? 'border-l-red-500 bg-red-50' :
                      issue.severity === 'warning' ? 'border-l-yellow-500 bg-yellow-50' :
                      'border-l-blue-500 bg-blue-50'
                    ]">
                    <p class="text-[11px] text-gray-800">{{ issue.description }}</p>
                    <p v-if="issue.fix_suggestion" class="text-[10px] text-blue-700 mt-0.5"><strong>Fix:</strong> {{ issue.fix_suggestion }}</p>
                  </div>
                </div>
                <p v-if="!doc.issues?.length && !doc.missing_elements?.length" class="text-[11px] text-green-700">OK</p>
              </div>
            </details>
          </div>

          <!-- Re-verify -->
          <div class="border-t pt-3">
            <p class="text-[11px] text-gray-600 mb-2">Poprawiłeś dokumenty? Prześlij ponownie.</p>
            <div class="border-2 border-dashed rounded p-4 text-center"
              :class="verificationDragOver ? 'border-indigo-400 bg-indigo-50' : 'border-gray-300'"
              @dragover.prevent="verificationDragOver = true"
              @dragleave="verificationDragOver = false"
              @drop.prevent="handleVerificationDrop">
              <label class="inline-block px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-xs cursor-pointer hover:bg-gray-200">
                Wybierz pliki
                <input type="file" multiple accept=".docx,.pdf,.xlsx,.xls,.doc" class="hidden" @change="handleVerificationSelect" />
              </label>
              <div v-if="verificationFiles.length" class="mt-2 text-left space-y-1">
                <div v-for="(f, i) in verificationFiles" :key="i" class="flex items-center justify-between bg-gray-50 rounded px-2 py-1 text-xs">
                  <span>{{ f.name }}</span>
                  <button @click="removeVerificationFile(i)" class="text-red-500 text-[10px]">Usuń</button>
                </div>
              </div>
              <button v-if="verificationFiles.length" @click="submitVerification" :disabled="verificationUploading"
                class="mt-2 px-4 py-1.5 bg-indigo-600 text-white rounded text-xs hover:bg-indigo-700 disabled:opacity-50">
                {{ verificationUploading ? 'Wysyłam...' : 'Ponowna weryfikacja' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Completion -->
      <div v-if="activeTab === 6 && analysis.status === 'completed' && analysis.user_decision === 'go' && !step6" class="bg-green-50 border border-green-200 rounded p-4 text-center">
        <p class="text-green-800 font-medium text-sm">Analiza zakończona</p>
        <p class="text-xs text-green-700 mt-1">Przygotuj dokumenty na podstawie wytycznych powyżej, a następnie prześlij je do weryfikacji w kroku 6.</p>
      </div>
    </div>
  </div>
</template>
