<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { createFromUrl, createManual } from '@/api/tenders'

const router = useRouter()
const mode = ref<'url' | 'manual'>('url')
const loading = ref(false)
const errorMsg = ref('')

// URL mode
const urlText = ref('')

// Manual mode
const title = ref('')
const tenderText = ref('')
const files = ref<File[]>([])
const isDragging = ref(false)

async function submitUrl() {
  const urls = urlText.value.split('\n').map(u => u.trim()).filter(Boolean)
  if (!urls.length) return
  loading.value = true
  errorMsg.value = ''
  try {
    const tender = await createFromUrl(urls)
    router.push(`/tenders/${tender.id}`)
  } catch (err: any) {
    errorMsg.value = err?.response?.data?.detail || err?.message || 'Nie udało się utworzyć przetargu. Sprawdź czy backend działa.'
  } finally {
    loading.value = false
  }
}

async function submitManual() {
  if (!tenderText.value.trim() && !files.value.length) return
  loading.value = true
  errorMsg.value = ''
  try {
    const tender = await createManual(title.value, tenderText.value, files.value)
    router.push(`/tenders/${tender.id}`)
  } catch (err: any) {
    errorMsg.value = err?.response?.data?.detail || err?.message || 'Nie udało się utworzyć przetargu. Sprawdź czy backend działa.'
  } finally {
    loading.value = false
  }
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  if (e.dataTransfer?.files) {
    files.value.push(...Array.from(e.dataTransfer.files))
  }
}

function handleFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) {
    files.value.push(...Array.from(input.files))
  }
}

function removeFile(index: number) {
  files.value.splice(index, 1)
}
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-gray-900 mb-6">Nowy przetarg</h1>

    <!-- Mode tabs -->
    <div class="flex gap-2 mb-6">
      <button
        @click="mode = 'url'"
        :class="[
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          mode === 'url' ? 'bg-indigo-600 text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
        ]"
      >
        Z adresu URL
      </button>
      <button
        @click="mode = 'manual'"
        :class="[
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          mode === 'manual' ? 'bg-indigo-600 text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
        ]"
      >
        Ręczne wprowadzenie
      </button>
    </div>

    <!-- Error message -->
    <div v-if="errorMsg" class="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
      {{ errorMsg }}
    </div>

    <!-- URL mode -->
    <div v-if="mode === 'url'" class="bg-white rounded-lg shadow p-6 space-y-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">
          Adresy URL przetargów (jeden na linię)
        </label>
        <textarea
          v-model="urlText"
          rows="5"
          placeholder="https://ezamowienia.gov.pl/..."
          class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono"
        ></textarea>
      </div>
      <button
        @click="submitUrl"
        :disabled="loading || !urlText.trim()"
        class="px-6 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-50"
      >
        {{ loading ? 'Przetwarzanie...' : 'Pobierz i analizuj' }}
      </button>
    </div>

    <!-- Manual mode -->
    <div v-if="mode === 'manual'" class="bg-white rounded-lg shadow p-6 space-y-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Tytuł przetargu</label>
        <input v-model="title" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="Opcjonalnie" />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Treść przetargu</label>
        <textarea
          v-model="tenderText"
          rows="10"
          placeholder="Wklej treść SWZ / OPZ / ogłoszenia..."
          class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
        ></textarea>
      </div>

      <!-- Dropzone -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Załączniki</label>
        <div
          @dragover.prevent="isDragging = true"
          @dragleave="isDragging = false"
          @drop.prevent="handleDrop"
          :class="[
            'border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer',
            isDragging ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-gray-400'
          ]"
          @click="($refs.fileInput as HTMLInputElement)?.click()"
        >
          <p class="text-sm text-gray-500">Przeciągnij pliki tutaj lub kliknij, aby wybrać</p>
          <p class="text-xs text-gray-400 mt-1">PDF, DOC, DOCX, XLS, XLSX, ZIP</p>
          <input ref="fileInput" type="file" multiple class="hidden" @change="handleFileInput" />
        </div>

        <div v-if="files.length" class="mt-3 space-y-2">
          <div v-for="(file, i) in files" :key="i" class="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
            <span class="text-sm text-gray-700">{{ file.name }} ({{ (file.size / 1024).toFixed(0) }} KB)</span>
            <button @click="removeFile(i)" class="text-red-600 hover:text-red-800 text-sm">&times;</button>
          </div>
        </div>
      </div>

      <button
        @click="submitManual"
        :disabled="loading || (!tenderText.trim() && !files.length)"
        class="px-6 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-50"
      >
        {{ loading ? 'Tworzenie...' : 'Utwórz przetarg' }}
      </button>
    </div>
  </div>
</template>
