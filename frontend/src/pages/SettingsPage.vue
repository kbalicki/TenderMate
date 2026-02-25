<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSettings, updateSettings, type AppSettings } from '@/api/settings'

const settings = ref<AppSettings | null>(null)
const saving = ref(false)
const saved = ref(false)
const loading = ref(true)

onMounted(async () => {
  try {
    settings.value = await getSettings()
  } finally {
    loading.value = false
  }
})

async function save() {
  if (!settings.value) return
  saving.value = true
  try {
    settings.value = await updateSettings(settings.value)
    saved.value = true
    setTimeout(() => (saved.value = false), 2000)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="loading" class="text-center text-gray-400 py-8">Ladowanie...</div>
  <div v-else-if="settings">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Ustawienia</h1>
      <div class="flex items-center gap-3">
        <span v-if="saved" class="text-sm text-green-600">Zapisano!</span>
        <button
          @click="save"
          :disabled="saving"
          class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-50"
        >
          {{ saving ? 'Zapisywanie...' : 'Zapisz' }}
        </button>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow p-6 space-y-6">
      <div>
        <h2 class="text-sm font-semibold text-gray-900 mb-4">Przetwarzanie</h2>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Jednoczesne przetwarzanie przetargow
            </label>
            <p class="text-xs text-gray-500 mb-2">
              Maksymalna liczba przetargow scrapowanych i analizowanych rownoczesnie.
              Wyzsze wartosci przyspieszaja prace, ale zuzywaja wiecej zasobow API.
            </p>
            <div class="flex items-center gap-4">
              <input
                v-model.number="settings.max_concurrent_tasks"
                type="range"
                min="1"
                max="10"
                class="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
              />
              <span class="text-lg font-bold text-indigo-600 w-8 text-center">{{ settings.max_concurrent_tasks }}</span>
            </div>
            <div class="flex justify-between text-[10px] text-gray-400 mt-1 px-0.5">
              <span>1 (oszczedny)</span>
              <span>5 (zbalansowany)</span>
              <span>10 (max)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
