<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getAnalysis, submitDecision, continueAnalysis } from '@/api/analysis'
import type { Analysis } from '@/types/analysis'
import CopyableText from '@/components/analysis/CopyableText.vue'

const props = defineProps<{ id: string }>()
const analysis = ref<Analysis | null>(null)
const loading = ref(true)
const error = ref('')

const steps = [
  { num: 0, label: 'Warunki udzialu' },
  { num: 1, label: 'Wymagane dokumenty' },
  { num: 2, label: 'Wycena i kryteria' },
  { num: 3, label: 'Analiza ryzyk' },
  { num: 4, label: 'Estymacja kosztow' },
  { num: 5, label: 'Wytyczne dokumentow' },
]

const tenderId = computed(() => Number(props.id))

onMounted(async () => {
  try {
    analysis.value = await getAnalysis(tenderId.value)
  } catch {
    error.value = 'Analiza nie zostala jeszcze uruchomiona.'
  } finally {
    loading.value = false
  }
})

async function handleDecision(decision: 'go' | 'no_go') {
  analysis.value = await submitDecision(tenderId.value, decision)
}

async function handleContinue() {
  analysis.value = await continueAnalysis(tenderId.value)
  // Poll for completion
  pollAnalysis()
}

async function pollAnalysis() {
  const poll = setInterval(async () => {
    try {
      analysis.value = await getAnalysis(tenderId.value)
      if (analysis.value.status !== 'running') {
        clearInterval(poll)
      }
    } catch {
      clearInterval(poll)
    }
  }, 3000)
}

function stepStatus(stepNum: number): 'done' | 'active' | 'pending' {
  if (!analysis.value) return 'pending'
  if (stepNum < analysis.value.current_step) return 'done'
  if (stepNum === analysis.value.current_step) return 'active'
  return 'pending'
}
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-gray-900 mb-6">Analiza przetargu #{{ id }}</h1>

    <div v-if="loading" class="text-center text-gray-400 py-8">Ladowanie...</div>
    <div v-else-if="error" class="text-center text-red-600 py-8">{{ error }}</div>
    <div v-else-if="analysis">
      <!-- Stepper -->
      <div class="flex items-center gap-1 mb-8 overflow-x-auto">
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
          <span class="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
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

      <!-- Running indicator -->
      <div v-if="analysis.status === 'running'" class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6 flex items-center gap-3">
        <div class="animate-spin h-5 w-5 border-2 border-indigo-600 border-t-transparent rounded-full"></div>
        <span class="text-sm text-blue-800">Analiza w toku — krok {{ analysis.current_step }}...</span>
      </div>

      <!-- Step 0: Eligibility -->
      <div v-if="analysis.step0_result" class="bg-white rounded-lg shadow p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Krok 0: Warunki udzialu</h2>

        <div v-if="analysis.step0_result.conditions" class="space-y-3 mb-4">
          <div
            v-for="(cond, i) in analysis.step0_result.conditions"
            :key="i"
            :class="[
              'border rounded-lg p-3',
              cond.met ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
            ]"
          >
            <div class="flex items-start gap-2">
              <span :class="cond.met ? 'text-green-600' : 'text-red-600'" class="text-lg">
                {{ cond.met ? '✓' : '✗' }}
              </span>
              <div>
                <p class="font-medium text-sm text-gray-900">{{ cond.name }}</p>
                <p class="text-xs text-gray-600 mt-1">{{ cond.description }}</p>
                <p class="text-xs mt-1" :class="cond.met ? 'text-green-700' : 'text-red-700'">
                  {{ cond.reason }}
                </p>
                <div v-if="!cond.met && cond.fixable && cond.fix_options?.length" class="mt-2">
                  <p class="text-xs font-medium text-gray-700">Mozliwe rozwiazania:</p>
                  <div class="mt-1 space-y-1">
                    <label v-for="(opt, j) in cond.fix_options" :key="j" class="flex items-center gap-2 text-xs text-gray-600">
                      <input type="radio" :name="'fix-' + i" :value="opt" class="text-indigo-600" />
                      {{ opt }}
                    </label>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="analysis.step0_result.summary" class="bg-gray-50 rounded-lg p-3 mb-4">
          <CopyableText :text="analysis.step0_result.summary" />
        </div>

        <!-- Go/No-Go Decision -->
        <div v-if="analysis.step0_eligible && !analysis.user_decision" class="border-t pt-4">
          <div class="bg-indigo-50 rounded-lg p-4 mb-4">
            <h3 class="font-medium text-gray-900 mb-2">Zakres zamowienia</h3>
            <p class="text-sm text-gray-700">{{ analysis.step0_result.scope_description }}</p>
            <p class="text-sm text-gray-700 mt-2">
              <strong>Szacunkowy budzet:</strong> {{ analysis.step0_result.estimated_budget }}
            </p>
          </div>
          <div class="flex gap-3">
            <button
              @click="handleDecision('go')"
              class="flex-1 px-6 py-3 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700"
            >
              GO — Kontynuuj analize
            </button>
            <button
              @click="handleDecision('no_go')"
              class="flex-1 px-6 py-3 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700"
            >
              NO-GO — Odpusc
            </button>
          </div>
        </div>

        <div v-if="analysis.user_decision === 'no_go'" class="border-t pt-4">
          <p class="text-red-600 font-medium">Przetarg odrzucony.</p>
        </div>
      </div>

      <!-- Steps 1-5: Show results when available -->
      <div v-for="step in [
        { num: 1, key: 'step1_result', label: 'Wymagane dokumenty' },
        { num: 2, key: 'step2_result', label: 'Wycena, kryteria, terminy' },
        { num: 3, key: 'step3_result', label: 'Analiza ryzyk' },
        { num: 4, key: 'step4_result', label: 'Estymacja kosztow' },
        { num: 5, key: 'step5_result', label: 'Wytyczne do dokumentow' },
      ]" :key="step.num">
        <div
          v-if="(analysis as any)[step.key]"
          class="bg-white rounded-lg shadow p-6 mb-6"
        >
          <h2 class="text-lg font-semibold text-gray-900 mb-4">
            Krok {{ step.num }}: {{ step.label }}
          </h2>
          <CopyableText :text="JSON.stringify((analysis as any)[step.key], null, 2)" />
        </div>
      </div>

      <!-- Continue button -->
      <div
        v-if="analysis.status === 'waiting_user' && analysis.user_decision === 'go' && analysis.current_step < 5"
        class="text-center"
      >
        <button
          @click="handleContinue"
          class="px-6 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700"
        >
          Kontynuuj do kroku {{ analysis.current_step + 1 }}
        </button>
      </div>
    </div>
  </div>
</template>
