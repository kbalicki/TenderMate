<script setup lang="ts">
import AppSidebar from './AppSidebar.vue'
</script>

<template>
  <div class="flex h-screen bg-gray-50">
    <AppSidebar />
    <main class="flex-1 overflow-auto p-6">
      <RouterView />
    </main>
  </div>
</template>
