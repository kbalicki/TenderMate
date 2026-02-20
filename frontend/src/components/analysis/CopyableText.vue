<script setup lang="ts">
import { ref } from 'vue'
import { useClipboard } from '@vueuse/core'

const props = defineProps<{ text: string }>()

const { copy } = useClipboard()
const copied = ref(false)

async function handleCopy() {
  await copy(props.text)
  copied.value = true
  setTimeout(() => (copied.value = false), 2000)
}
</script>

<template>
  <div class="relative group">
    <pre class="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-lg p-3 pr-16">{{ text }}</pre>
    <button
      @click="handleCopy"
      class="absolute top-2 right-2 px-2 py-1 text-xs rounded bg-gray-200 hover:bg-gray-300 text-gray-700 transition-colors"
    >
      {{ copied ? 'Skopiowano!' : 'Kopiuj' }}
    </button>
  </div>
</template>
