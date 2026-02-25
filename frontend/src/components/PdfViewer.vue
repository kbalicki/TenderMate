<script setup lang="ts">
import { ref, onMounted, watch, onUnmounted } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'

// Use the bundled worker
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.mjs',
  import.meta.url,
).toString()

const props = defineProps<{
  url: string
}>()

const emit = defineEmits<{
  close: []
}>()

const container = ref<HTMLDivElement | null>(null)
const currentPage = ref(1)
const totalPages = ref(0)
const scale = ref(1.2)
const loading = ref(true)
const errorMsg = ref('')

let pdfDoc: pdfjsLib.PDFDocumentProxy | null = null

async function loadPdf(url: string) {
  loading.value = true
  errorMsg.value = ''
  try {
    pdfDoc = await pdfjsLib.getDocument(url).promise
    totalPages.value = pdfDoc.numPages
    currentPage.value = 1
    await renderPage(1)
  } catch (e: any) {
    errorMsg.value = 'Nie udało się załadować PDF: ' + (e?.message || e)
  } finally {
    loading.value = false
  }
}

async function renderPage(num: number) {
  if (!pdfDoc || !container.value) return
  const page = await pdfDoc.getPage(num)
  const viewport = page.getViewport({ scale: scale.value })

  // Clear previous content
  container.value.innerHTML = ''

  const canvas = document.createElement('canvas')
  canvas.width = viewport.width
  canvas.height = viewport.height
  canvas.style.display = 'block'
  canvas.style.margin = '0 auto'
  container.value.appendChild(canvas)

  const ctx = canvas.getContext('2d')!
  await page.render({ canvasContext: ctx, viewport }).promise
}

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--
    renderPage(currentPage.value)
  }
}

function nextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value++
    renderPage(currentPage.value)
  }
}

function zoomIn() {
  scale.value = Math.min(scale.value + 0.3, 3)
  renderPage(currentPage.value)
}

function zoomOut() {
  scale.value = Math.max(scale.value - 0.3, 0.5)
  renderPage(currentPage.value)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
  if (e.key === 'ArrowLeft') prevPage()
  if (e.key === 'ArrowRight') nextPage()
}

onMounted(() => {
  loadPdf(props.url)
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  if (pdfDoc) pdfDoc.destroy()
})

watch(() => props.url, (newUrl) => {
  loadPdf(newUrl)
})
</script>

<template>
  <div class="fixed inset-0 z-50 bg-black/70 flex flex-col" @click.self="emit('close')">
    <!-- Toolbar -->
    <div class="bg-white border-b flex items-center justify-between px-4 py-2 shrink-0">
      <div class="flex items-center gap-3">
        <button @click="emit('close')" class="text-gray-500 hover:text-gray-800 text-lg font-bold px-2" title="Zamknij (Esc)">&times;</button>
        <span class="text-sm text-gray-600">
          Strona {{ currentPage }} / {{ totalPages }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <button @click="zoomOut" class="px-2 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200" title="Pomniejsz">-</button>
        <span class="text-xs text-gray-500 w-12 text-center">{{ Math.round(scale * 100) }}%</span>
        <button @click="zoomIn" class="px-2 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200" title="Powiększ">+</button>
        <button @click="prevPage" :disabled="currentPage <= 1" class="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-40">Poprzednia</button>
        <button @click="nextPage" :disabled="currentPage >= totalPages" class="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-40">Następna</button>
        <a :href="url" download class="px-3 py-1 text-sm bg-indigo-100 text-indigo-700 rounded hover:bg-indigo-200">Pobierz</a>
      </div>
    </div>

    <!-- PDF content -->
    <div class="flex-1 overflow-auto bg-gray-800 p-4">
      <div v-if="loading" class="text-center text-white py-12">
        <div class="animate-spin h-8 w-8 border-3 border-white border-t-transparent rounded-full mx-auto mb-3"></div>
        Ładowanie PDF...
      </div>
      <div v-else-if="errorMsg" class="text-center text-red-300 py-12">{{ errorMsg }}</div>
      <div ref="container"></div>
    </div>
  </div>
</template>
