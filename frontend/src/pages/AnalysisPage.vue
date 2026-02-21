<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { startAnalysis, getAnalysis, submitDecision, fixEligibility } from '@/api/analysis'
import type { Analysis, Step0Result, EligibilityCondition } from '@/types/analysis'
import CopyableText from '@/components/analysis/CopyableText.vue'

const props = defineProps<{ id: string }>()
const analysis = ref<Analysis | null>(null)
const loading = ref(true)
const error = ref('')
const sseConnected = ref(false)

// Fix selections for eligibility
const fixSelections = ref<Record<number, string>>({})

const tenderId = computed(() => Number(props.id))

const steps = [
  { num: 0, label: 'Warunki udziału' },
  { num: 1, label: 'Wymagane dokumenty' },
  { num: 2, label: 'Wycena i kryteria' },
  { num: 3, label: 'Analiza ryzyk' },
  { num: 4, label: 'Estymacja kosztów' },
  { num: 5, label: 'Wytyczne dokumentów' },
]

let eventSource: EventSource | null = null

function connectSSE() {
  if (eventSource) eventSource.close()
  eventSource = new EventSource(`/api/tenders/${props.id}/analysis/stream`)
  sseConnected.value = true

  eventSource.addEventListener('step_started', () => {
    refreshAnalysis()
  })

  eventSource.addEventListener('step_completed', () => {
    refreshAnalysis()
  })

  eventSource.addEventListener('error', (e: any) => {
    try {
      const data = JSON.parse(e.data)
      error.value = data.message || 'Błąd analizy'
    } catch {
      // SSE connection error, try to reconnect
    }
    refreshAnalysis()
  })

  eventSource.onerror = () => {
    sseConnected.value = false
  }
}

async function refreshAnalysis() {
  try {
    analysis.value = await getAnalysis(tenderId.value)
  } catch { /* ignore */ }
}

onMounted(async () => {
  try {
    // Try to get existing analysis
    analysis.value = await getAnalysis(tenderId.value)
    if (analysis.value.status === 'running') {
      connectSSE()
    }
  } catch {
    // No analysis yet, start one
    try {
      analysis.value = await startAnalysis(tenderId.value)
      connectSSE()
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Nie udało się uruchomić analizy'
    }
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  if (eventSource) eventSource.close()
})

// Polling fallback for when SSE is not connected
let pollInterval: ReturnType<typeof setInterval> | null = null

function startPolling() {
  if (pollInterval) return
  pollInterval = setInterval(async () => {
    await refreshAnalysis()
    if (analysis.value && analysis.value.status !== 'running') {
      stopPolling()
    }
  }, 3000)
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

async function handleDecision(decision: 'go' | 'no_go') {
  analysis.value = await submitDecision(tenderId.value, decision)
  if (decision === 'go') {
    connectSSE()
    startPolling()
  }
}

async function handleFixEligibility() {
  const fixes = Object.entries(fixSelections.value).map(([condIdx, option]) => ({
    condition_index: Number(condIdx),
    chosen_fix: option,
  }))
  if (!fixes.length) return
  analysis.value = await fixEligibility(tenderId.value, fixes)
  connectSSE()
  startPolling()
}

function stepStatus(stepNum: number): 'done' | 'active' | 'pending' {
  if (!analysis.value) return 'pending'
  const a = analysis.value
  if (a.status === 'running' && a.current_step === stepNum) return 'active'
  const stepKey = `step${stepNum}_result` as keyof Analysis
  if (a[stepKey]) return 'done'
  if (stepNum < a.current_step) return 'done'
  if (stepNum === a.current_step) return 'active'
  return 'pending'
}

const step0 = computed((): Step0Result | null => {
  if (!analysis.value?.step0_result) return null
  return analysis.value.step0_result as Step0Result
})

const failedConditions = computed((): EligibilityCondition[] => {
  if (!step0.value?.conditions) return []
  return step0.value.conditions.filter(c => !c.met)
})

const hasFixableConditions = computed((): boolean => {
  return failedConditions.value.some(c => c.fixable && c.fix_options?.length)
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Analiza przetargu #{{ id }}</h1>
      <RouterLink :to="`/tenders/${id}`" class="text-sm text-indigo-600 hover:text-indigo-800">
        Wróć do przetargu
      </RouterLink>
    </div>

    <div v-if="loading" class="text-center text-gray-400 py-12">
      <div class="animate-spin h-8 w-8 border-3 border-indigo-600 border-t-transparent rounded-full mx-auto mb-3"></div>
      <p>Uruchamiam analizę...</p>
    </div>

    <div v-else-if="error && !analysis" class="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
      <p class="text-red-800">{{ error }}</p>
    </div>

    <div v-else-if="analysis">
      <!-- Stepper -->
      <div class="flex items-center gap-1 mb-8 overflow-x-auto pb-2">
        <div
          v-for="step in steps"
          :key="step.num"
          :class="[
            'flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap',
            stepStatus(step.num) === 'done' ? 'bg-green-100 text-green-800' :
            stepStatus(step.num) === 'active' ? 'bg-indigo-100 text-indigo-800' :
            'bg-gray-100 text-gray-400'
          ]"
        >
          <span
            class="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
            :class="[
              stepStatus(step.num) === 'done' ? 'bg-green-600 text-white' :
              stepStatus(step.num) === 'active' ? 'bg-indigo-600 text-white' :
              'bg-gray-300 text-white'
            ]"
          >
            {{ stepStatus(step.num) === 'done' ? '✓' : step.num }}
          </span>
          {{ step.label }}
        </div>
      </div>

      <!-- Error message -->
      <div v-if="error" class="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
        <p class="text-sm text-red-800">{{ error }}</p>
      </div>

      <!-- Running indicator -->
      <div v-if="analysis.status === 'running'" class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6 flex items-center gap-3">
        <div class="animate-spin h-5 w-5 border-2 border-indigo-600 border-t-transparent rounded-full"></div>
        <span class="text-sm text-blue-800">
          Analiza w toku — krok {{ analysis.current_step }}:
          {{ steps[analysis.current_step]?.label }}...
          <span class="text-xs text-blue-600 ml-2">(Claude CLI pracuje, to może potrwać 30–60 sekund)</span>
        </span>
      </div>

      <!-- ===== STEP 0: Eligibility ===== -->
      <div v-if="step0" class="bg-white rounded-lg shadow p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Krok 0: Warunki udziału</h2>

        <!-- Conditions list -->
        <div v-if="step0.conditions?.length" class="space-y-3 mb-4">
          <div
            v-for="(cond, i) in step0.conditions"
            :key="i"
            :class="[
              'border rounded-lg p-4',
              cond.met ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
            ]"
          >
            <div class="flex items-start gap-3">
              <span :class="cond.met ? 'text-green-600' : 'text-red-600'" class="text-xl mt-0.5">
                {{ cond.met ? '✓' : '✗' }}
              </span>
              <div class="flex-1">
                <p class="font-medium text-sm text-gray-900">{{ cond.name }}</p>
                <p class="text-xs text-gray-600 mt-1">{{ cond.description }}</p>
                <p class="text-xs mt-1" :class="cond.met ? 'text-green-700' : 'text-red-700'">
                  {{ cond.reason }}
                </p>

                <!-- Fix options for failed conditions -->
                <div v-if="!cond.met && cond.fixable && cond.fix_options?.length" class="mt-3 bg-white rounded p-3 border border-yellow-200">
                  <p class="text-xs font-medium text-yellow-800 mb-2">Możliwe rozwiązania:</p>
                  <div class="space-y-1.5">
                    <label
                      v-for="(opt, j) in cond.fix_options"
                      :key="j"
                      class="flex items-start gap-2 text-xs text-gray-700 cursor-pointer hover:text-gray-900"
                    >
                      <input
                        type="radio"
                        :name="'fix-' + i"
                        :value="opt"
                        v-model="fixSelections[i]"
                        class="mt-0.5 text-indigo-600"
                      />
                      <span>{{ opt }}</span>
                    </label>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Summary -->
        <div v-if="step0.summary" class="bg-gray-50 rounded-lg p-4 mb-4">
          <CopyableText :text="step0.summary" />
        </div>

        <!-- Actions when NOT eligible -->
        <div v-if="step0.eligible === false && analysis.status === 'waiting_user'" class="border-t pt-4 space-y-3">
          <div v-if="hasFixableConditions" class="flex gap-3">
            <button
              @click="handleFixEligibility"
              :disabled="Object.keys(fixSelections).length === 0"
              class="px-4 py-2 bg-yellow-600 text-white rounded-lg text-sm hover:bg-yellow-700 disabled:opacity-50"
            >
              Ponów sprawdzenie z poprawkami
            </button>
            <button
              @click="handleDecision('no_go')"
              class="px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700"
            >
              Odrzuć przetarg
            </button>
          </div>
          <div v-else>
            <p class="text-sm text-red-700 mb-3">Nie spełniamy warunków i nie ma możliwości naprawy.</p>
            <button
              @click="handleDecision('no_go')"
              class="px-6 py-3 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700"
            >
              Odrzuć przetarg
            </button>
          </div>
        </div>

        <!-- GO / NO-GO Decision -->
        <div v-if="step0.eligible && analysis.status === 'waiting_user' && !analysis.user_decision" class="border-t pt-4">
          <div class="bg-indigo-50 rounded-lg p-4 mb-4">
            <h3 class="font-medium text-gray-900 mb-2">Zakres zamówienia</h3>
            <p class="text-sm text-gray-700">{{ step0.scope_description }}</p>
            <p class="text-sm text-gray-700 mt-2">
              <strong>Szacunkowy budżet:</strong> {{ step0.estimated_budget }}
            </p>
          </div>
          <div class="flex gap-3">
            <button
              @click="handleDecision('go')"
              class="flex-1 px-6 py-3 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 text-center"
            >
              GO — Kontynuuj analizę
            </button>
            <button
              @click="handleDecision('no_go')"
              class="flex-1 px-6 py-3 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 text-center"
            >
              NO-GO — Odpuść
            </button>
          </div>
        </div>

        <div v-if="analysis.user_decision === 'no_go'" class="border-t pt-4">
          <p class="text-red-600 font-medium">Przetarg odrzucony.</p>
        </div>
      </div>

      <!-- ===== STEP 1: Documents ===== -->
      <div v-if="analysis.step1_result" class="bg-white rounded-lg shadow p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Krok 1: Wymagane dokumenty</h2>

        <!-- Wadium -->
        <div v-if="analysis.step1_result.wadium?.required" class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
          <h3 class="font-medium text-yellow-800 mb-2">Wadium</h3>
          <dl class="text-sm space-y-1">
            <div><dt class="inline text-gray-600">Kwota:</dt> <dd class="inline font-medium">{{ analysis.step1_result.wadium.amount }}</dd></div>
            <div v-if="analysis.step1_result.wadium.deadline"><dt class="inline text-gray-600">Termin:</dt> <dd class="inline">{{ analysis.step1_result.wadium.deadline }}</dd></div>
            <div v-if="analysis.step1_result.wadium.forms?.length"><dt class="inline text-gray-600">Formy:</dt> <dd class="inline">{{ analysis.step1_result.wadium.forms.join(', ') }}</dd></div>
            <div v-if="analysis.step1_result.wadium.notes"><dt class="inline text-gray-600">Uwagi:</dt> <dd class="inline">{{ analysis.step1_result.wadium.notes }}</dd></div>
          </dl>
        </div>

        <!-- Documents list -->
        <div v-if="analysis.step1_result.documents?.length" class="space-y-2">
          <div v-for="(doc, i) in analysis.step1_result.documents" :key="i" class="border rounded-lg p-3">
            <div class="flex items-start justify-between">
              <div>
                <p class="text-sm font-medium text-gray-900">{{ doc.name }}</p>
                <p class="text-xs text-gray-600 mt-1">{{ doc.description }}</p>
                <div class="flex gap-2 mt-1">
                  <span v-if="doc.requires_signature" class="text-[10px] bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded">Podpis</span>
                  <span class="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">{{ doc.type }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="analysis.step1_result.summary" class="mt-4">
          <CopyableText :text="analysis.step1_result.summary" />
        </div>
      </div>

      <!-- ===== STEP 2: Pricing & Criteria ===== -->
      <div v-if="analysis.step2_result" class="bg-white rounded-lg shadow p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Krok 2: Wycena, kryteria, terminy</h2>

        <!-- Evaluation criteria -->
        <div v-if="analysis.step2_result.evaluation_criteria?.length" class="mb-4">
          <h3 class="text-sm font-semibold text-gray-700 mb-2">Kryteria oceny ofert</h3>
          <div class="space-y-2">
            <div v-for="(cr, i) in analysis.step2_result.evaluation_criteria" :key="i" class="bg-indigo-50 rounded-lg p-3">
              <div class="flex items-center justify-between mb-1">
                <span class="text-sm font-medium text-gray-900">{{ cr.name }}</span>
                <span class="text-sm font-bold text-indigo-700">{{ cr.weight_pct }}%</span>
              </div>
              <p class="text-xs text-gray-600">{{ cr.scoring_method }}</p>
              <p class="text-xs text-green-700 mt-1">Jak maksymalizować: {{ cr.how_to_maximize }}</p>
            </div>
          </div>
        </div>

        <!-- Pricing items -->
        <div v-if="analysis.step2_result.pricing_items?.length" class="mb-4">
          <h3 class="text-sm font-semibold text-gray-700 mb-2">Pozycje do wyceny</h3>
          <table class="w-full text-sm">
            <thead><tr class="text-left text-xs text-gray-500 border-b">
              <th class="pb-2">Pozycja</th><th class="pb-2">Jednostka</th><th class="pb-2">Ilość</th>
            </tr></thead>
            <tbody>
              <tr v-for="(item, i) in analysis.step2_result.pricing_items" :key="i" class="border-b border-gray-100">
                <td class="py-2"><p class="font-medium">{{ item.name }}</p><p class="text-xs text-gray-500">{{ item.description }}</p></td>
                <td class="py-2 text-gray-600">{{ item.unit }}</td>
                <td class="py-2 text-gray-600">{{ item.quantity || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Deadlines -->
        <div v-if="analysis.step2_result.deadlines?.length" class="mb-4">
          <h3 class="text-sm font-semibold text-gray-700 mb-2">Terminy</h3>
          <div class="space-y-1">
            <div v-for="(dl, i) in analysis.step2_result.deadlines" :key="i" class="flex justify-between text-sm py-1 border-b border-gray-100">
              <span class="text-gray-700">{{ dl.name }}</span>
              <span class="font-medium text-gray-900">{{ dl.date }}</span>
            </div>
          </div>
        </div>

        <!-- Required personnel -->
        <div v-if="analysis.step2_result.required_personnel?.length" class="mb-4">
          <h3 class="text-sm font-semibold text-gray-700 mb-2">Wymagany personel</h3>
          <div class="space-y-2">
            <div v-for="(person, i) in analysis.step2_result.required_personnel" :key="i" class="bg-gray-50 rounded-lg p-3">
              <p class="text-sm font-medium text-gray-900">{{ person.role }} <span class="text-xs text-gray-500">(min. {{ person.min_count || 1 }} os.)</span></p>
              <p v-if="person.min_experience_years" class="text-xs text-gray-600">Min. {{ person.min_experience_years }} lat doświadczenia</p>
              <p v-if="person.required_certifications?.length" class="text-xs text-gray-600">Certyfikaty: {{ person.required_certifications.join(', ') }}</p>
            </div>
          </div>
        </div>

        <div v-if="analysis.step2_result.summary" class="mt-4">
          <CopyableText :text="analysis.step2_result.summary" />
        </div>
      </div>

      <!-- ===== STEP 3: Risks ===== -->
      <div v-if="analysis.step3_result" class="bg-white rounded-lg shadow p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Krok 3: Analiza ryzyk</h2>

        <!-- Critical warnings -->
        <div v-if="analysis.step3_result.critical_warnings?.length" class="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
          <h3 class="font-medium text-red-800 mb-2">Ostrzeżenia krytyczne</h3>
          <ul class="list-disc list-inside text-sm text-red-700 space-y-1">
            <li v-for="(w, i) in analysis.step3_result.critical_warnings" :key="i">{{ w }}</li>
          </ul>
        </div>

        <!-- Risks -->
        <div v-if="analysis.step3_result.risks?.length" class="space-y-3">
          <div
            v-for="(risk, i) in analysis.step3_result.risks"
            :key="i"
            :class="[
              'border-l-4 rounded-lg p-4 bg-white border',
              risk.severity === 'high' ? 'border-l-red-500 border-red-100' :
              risk.severity === 'medium' ? 'border-l-yellow-500 border-yellow-100' :
              'border-l-green-500 border-green-100'
            ]"
          >
            <div class="flex items-center gap-2 mb-1">
              <span
                :class="[
                  'text-[10px] font-bold uppercase px-1.5 py-0.5 rounded',
                  risk.severity === 'high' ? 'bg-red-100 text-red-800' :
                  risk.severity === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                  'bg-green-100 text-green-800'
                ]"
              >
                {{ risk.severity === 'high' ? 'WYSOKIE' : risk.severity === 'medium' ? 'ŚREDNIE' : 'NISKIE' }}
              </span>
              <span class="text-xs text-gray-500">{{ risk.category }}</span>
            </div>
            <p class="text-sm font-medium text-gray-900">{{ risk.name }}</p>
            <p class="text-xs text-gray-600 mt-1">{{ risk.description }}</p>
            <p class="text-xs text-blue-700 mt-1"><strong>Mitygacja:</strong> {{ risk.mitigation }}</p>
          </div>
        </div>

        <div v-if="analysis.step3_result.summary" class="mt-4">
          <CopyableText :text="analysis.step3_result.summary" />
        </div>
      </div>

      <!-- ===== STEP 4: Cost Estimation ===== -->
      <div v-if="analysis.step4_result" class="bg-white rounded-lg shadow p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Krok 4: Estymacja kosztów</h2>

        <div v-if="analysis.step4_result.proposed_stack?.length" class="mb-4">
          <h3 class="text-sm font-semibold text-gray-700 mb-2">Proponowany stack</h3>
          <div class="flex flex-wrap gap-1">
            <span v-for="tech in analysis.step4_result.proposed_stack" :key="tech" class="bg-indigo-100 text-indigo-800 text-xs px-2 py-1 rounded">{{ tech }}</span>
          </div>
        </div>

        <div v-if="analysis.step4_result.work_packages?.length" class="mb-4">
          <table class="w-full text-sm">
            <thead><tr class="text-left text-xs text-gray-500 border-b">
              <th class="pb-2">Pakiet prac</th><th class="pb-2 text-right">Godziny</th><th class="pb-2 text-right">Koszt netto (PLN)</th>
            </tr></thead>
            <tbody>
              <tr v-for="(wp, i) in analysis.step4_result.work_packages" :key="i" class="border-b border-gray-100">
                <td class="py-2"><p class="font-medium">{{ wp.name }}</p><p class="text-xs text-gray-500">{{ wp.description }}</p></td>
                <td class="py-2 text-right text-gray-600">{{ wp.hours }}h</td>
                <td class="py-2 text-right font-medium">{{ wp.cost_net_pln?.toLocaleString() }}</td>
              </tr>
              <tr class="border-b border-gray-200 bg-gray-50">
                <td class="py-2 font-medium">Suma prac</td>
                <td class="py-2 text-right text-gray-600">{{ analysis.step4_result.subtotal_hours }}h</td>
                <td class="py-2 text-right font-bold">{{ analysis.step4_result.subtotal_net_pln?.toLocaleString() }}</td>
              </tr>
              <tr class="border-b border-gray-100">
                <td class="py-2 text-gray-600">+ QA/testy ({{ analysis.step4_result.qa_buffer_pct }}%)</td>
                <td></td>
                <td class="py-2 text-right text-gray-600">{{ analysis.step4_result.qa_buffer_pln?.toLocaleString() }}</td>
              </tr>
              <tr class="border-b border-gray-100">
                <td class="py-2 text-gray-600">+ Bufor ryzyka ({{ analysis.step4_result.risk_buffer_pct }}%)</td>
                <td></td>
                <td class="py-2 text-right text-gray-600">{{ analysis.step4_result.risk_buffer_pln?.toLocaleString() }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="bg-indigo-50 font-bold">
                <td class="py-3">RAZEM NETTO</td>
                <td></td>
                <td class="py-3 text-right text-indigo-700 text-lg">{{ analysis.step4_result.total_net_pln?.toLocaleString() }} PLN</td>
              </tr>
              <tr v-if="analysis.step4_result.total_gross_pln" class="bg-indigo-50">
                <td class="pb-3 text-sm text-gray-600">RAZEM BRUTTO</td>
                <td></td>
                <td class="pb-3 text-right text-sm text-gray-600">{{ analysis.step4_result.total_gross_pln?.toLocaleString() }} PLN</td>
              </tr>
            </tfoot>
          </table>
        </div>

        <!-- Additional costs -->
        <div v-if="analysis.step4_result.additional_costs?.length" class="mb-4">
          <h3 class="text-sm font-semibold text-gray-700 mb-2">Koszty dodatkowe</h3>
          <div class="space-y-1">
            <div v-for="(cost, i) in analysis.step4_result.additional_costs" :key="i" class="flex justify-between text-sm py-1 border-b border-gray-100">
              <span class="text-gray-700">{{ cost.name }} <span class="text-xs text-gray-400">({{ cost.recurring }})</span></span>
              <span class="font-medium">{{ cost.cost_net_pln?.toLocaleString() }} PLN</span>
            </div>
          </div>
        </div>

        <div v-if="analysis.step4_result.summary" class="mt-4">
          <CopyableText :text="analysis.step4_result.summary" />
        </div>
      </div>

      <!-- ===== STEP 5: Document Guidance ===== -->
      <div v-if="analysis.step5_result" class="bg-white rounded-lg shadow p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Krok 5: Wytyczne do dokumentów</h2>

        <div v-if="analysis.step5_result.document_guides?.length" class="space-y-4">
          <details v-for="(guide, i) in analysis.step5_result.document_guides" :key="i" class="border rounded-lg">
            <summary class="px-4 py-3 cursor-pointer hover:bg-gray-50 flex items-center justify-between">
              <span class="text-sm font-medium text-gray-900">{{ guide.document_name }}</span>
            </summary>
            <div class="px-4 pb-4 space-y-3">
              <div v-if="guide.instruction">
                <h4 class="text-xs font-semibold text-gray-500 uppercase mb-1">Instrukcja</h4>
                <p class="text-sm text-gray-700 whitespace-pre-wrap">{{ guide.instruction }}</p>
              </div>
              <div v-if="guide.suggested_text">
                <h4 class="text-xs font-semibold text-gray-500 uppercase mb-1">Tekst do skopiowania</h4>
                <CopyableText :text="guide.suggested_text" />
              </div>
              <div v-if="guide.warnings" class="bg-yellow-50 rounded p-2">
                <p class="text-xs text-yellow-800">{{ guide.warnings }}</p>
              </div>
            </div>
          </details>
        </div>

        <div v-if="analysis.step5_result.general_notes" class="mt-4 bg-blue-50 rounded-lg p-4">
          <h3 class="text-sm font-semibold text-blue-800 mb-1">Ogólne uwagi</h3>
          <CopyableText :text="analysis.step5_result.general_notes" />
        </div>
      </div>

      <!-- Completion -->
      <div v-if="analysis.status === 'completed' && analysis.user_decision === 'go'" class="bg-green-50 border border-green-200 rounded-lg p-6 text-center">
        <p class="text-green-800 font-medium text-lg mb-2">Analiza zakończona</p>
        <p class="text-sm text-green-700">Możesz teraz przygotować dokumenty ofertowe na podstawie wytycznych powyżej.</p>
      </div>
    </div>
  </div>
</template>
