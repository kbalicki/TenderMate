<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  getProfile,
  updateProfile,
  addTeamMember,
  deleteTeamMember,
  addPortfolioProject,
  deletePortfolioProject,
} from '@/api/companyProfile'
import type { CompanyProfile, TeamMember, PortfolioProject } from '@/types/companyProfile'

const profile = ref<CompanyProfile | null>(null)
const activeTab = ref<'info' | 'team' | 'portfolio' | 'preferences'>('info')
const saving = ref(false)
const saved = ref(false)

// Team member form
const newMember = ref<Omit<TeamMember, 'id'>>({
  full_name: '',
  role: '',
  experience_years: null,
  qualifications: '',
  bio: '',
})
const showMemberForm = ref(false)

// Portfolio form
const newProject = ref<Omit<PortfolioProject, 'id'>>({
  project_name: '',
  client_name: '',
  description: '',
  contract_value_pln: null,
  year_started: null,
  year_completed: null,
  technologies_used: [],
})
const showProjectForm = ref(false)
const techInput = ref('')

onMounted(async () => {
  profile.value = await getProfile()
})

async function saveProfile() {
  if (!profile.value) return
  saving.value = true
  try {
    profile.value = await updateProfile(profile.value)
    saved.value = true
    setTimeout(() => (saved.value = false), 2000)
  } finally {
    saving.value = false
  }
}

async function handleAddMember() {
  const member = await addTeamMember(newMember.value)
  profile.value?.team_members.push(member)
  showMemberForm.value = false
  newMember.value = { full_name: '', role: '', experience_years: null, qualifications: '', bio: '' }
}

async function handleDeleteMember(id: number) {
  await deleteTeamMember(id)
  if (profile.value) {
    profile.value.team_members = profile.value.team_members.filter(m => m.id !== id)
  }
}

async function handleAddProject() {
  const project = await addPortfolioProject(newProject.value)
  profile.value?.portfolio_projects.push(project)
  showProjectForm.value = false
  newProject.value = {
    project_name: '', client_name: '', description: '',
    contract_value_pln: null, year_started: null, year_completed: null, technologies_used: [],
  }
}

async function handleDeleteProject(id: number) {
  await deletePortfolioProject(id)
  if (profile.value) {
    profile.value.portfolio_projects = profile.value.portfolio_projects.filter(p => p.id !== id)
  }
}

function addTech() {
  if (techInput.value.trim()) {
    newProject.value.technologies_used.push(techInput.value.trim())
    techInput.value = ''
  }
}
</script>

<template>
  <div v-if="profile">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Profil firmy</h1>
      <div class="flex items-center gap-3">
        <span v-if="saved" class="text-sm text-green-600">Zapisano!</span>
        <button
          @click="saveProfile"
          :disabled="saving"
          class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-50"
        >
          {{ saving ? 'Zapisywanie...' : 'Zapisz' }}
        </button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="flex gap-6">
        <button
          v-for="tab in [
            { key: 'info', label: 'Dane firmy' },
            { key: 'team', label: 'Zespol' },
            { key: 'portfolio', label: 'Portfolio' },
            { key: 'preferences', label: 'Preferencje' },
          ]"
          :key="tab.key"
          @click="activeTab = tab.key as typeof activeTab"
          :class="[
            'pb-3 text-sm font-medium border-b-2 transition-colors',
            activeTab === tab.key
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          ]"
        >
          {{ tab.label }}
        </button>
      </nav>
    </div>

    <!-- Info Tab -->
    <div v-if="activeTab === 'info'" class="bg-white rounded-lg shadow p-6 space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Nazwa firmy</label>
          <input v-model="profile.company_name" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Osoba kontaktowa</label>
          <input v-model="profile.contact_person" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">NIP</label>
          <input v-model="profile.nip" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">REGON</label>
          <input v-model="profile.regon" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">KRS</label>
          <input v-model="profile.krs" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Telefon</label>
          <input v-model="profile.phone" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <input v-model="profile.email" type="email" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Strona www</label>
          <input v-model="profile.website" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Nr konta (wadium)</label>
          <input v-model="profile.bank_account" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Adres</label>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <input v-model="profile.address_street" placeholder="Ulica" class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <input v-model="profile.address_postal_code" placeholder="Kod pocztowy" class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <input v-model="profile.address_city" placeholder="Miasto" class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Opis firmy</label>
        <textarea v-model="profile.description" rows="4" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"></textarea>
      </div>
    </div>

    <!-- Team Tab -->
    <div v-if="activeTab === 'team'" class="space-y-4">
      <div class="flex justify-end">
        <button @click="showMemberForm = !showMemberForm" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
          {{ showMemberForm ? 'Anuluj' : '+ Dodaj czlonka zespolu' }}
        </button>
      </div>

      <div v-if="showMemberForm" class="bg-white rounded-lg shadow p-6 space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <input v-model="newMember.full_name" placeholder="Imie i nazwisko" class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <input v-model="newMember.role" placeholder="Rola (np. Senior Developer)" class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <input v-model.number="newMember.experience_years" type="number" placeholder="Lata doswiadczenia" class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <input v-model="newMember.qualifications" placeholder="Kwalifikacje/certyfikaty" class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <textarea v-model="newMember.bio" placeholder="Krotkie bio" rows="2" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"></textarea>
        <button @click="handleAddMember" class="px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700">Dodaj</button>
      </div>

      <div v-for="member in profile.team_members" :key="member.id" class="bg-white rounded-lg shadow p-4 flex items-center justify-between">
        <div>
          <p class="font-medium text-gray-900">{{ member.full_name }}</p>
          <p class="text-sm text-gray-500">{{ member.role }} · {{ member.experience_years }} lat doswiadczenia</p>
        </div>
        <button @click="handleDeleteMember(member.id)" class="text-red-600 hover:text-red-800 text-sm">Usun</button>
      </div>
      <div v-if="profile.team_members.length === 0" class="text-center text-gray-400 py-8">Brak czlonkow zespolu</div>
    </div>

    <!-- Portfolio Tab -->
    <div v-if="activeTab === 'portfolio'" class="space-y-4">
      <div class="flex justify-end">
        <button @click="showProjectForm = !showProjectForm" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
          {{ showProjectForm ? 'Anuluj' : '+ Dodaj projekt' }}
        </button>
      </div>

      <div v-if="showProjectForm" class="bg-white rounded-lg shadow p-6 space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <input v-model="newProject.project_name" placeholder="Nazwa projektu" class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <input v-model="newProject.client_name" placeholder="Klient" class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <input v-model.number="newProject.contract_value_pln" type="number" placeholder="Wartosc kontraktu (PLN)" class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <div class="flex gap-2">
            <input v-model.number="newProject.year_started" type="number" placeholder="Rok start" class="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            <input v-model.number="newProject.year_completed" type="number" placeholder="Rok koniec" class="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>
        <textarea v-model="newProject.description" placeholder="Opis projektu" rows="2" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"></textarea>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Technologie</label>
          <div class="flex gap-2 mb-2">
            <input v-model="techInput" @keyup.enter="addTech" placeholder="Dodaj technologie" class="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            <button @click="addTech" class="px-3 py-2 bg-gray-200 rounded-lg text-sm hover:bg-gray-300">+</button>
          </div>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="(tech, i) in newProject.technologies_used"
              :key="i"
              class="bg-indigo-100 text-indigo-800 text-xs px-2 py-1 rounded-full flex items-center gap-1"
            >
              {{ tech }}
              <button @click="newProject.technologies_used.splice(i, 1)" class="hover:text-red-600">&times;</button>
            </span>
          </div>
        </div>
        <button @click="handleAddProject" class="px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700">Dodaj</button>
      </div>

      <div v-for="project in profile.portfolio_projects" :key="project.id" class="bg-white rounded-lg shadow p-4">
        <div class="flex items-start justify-between">
          <div>
            <p class="font-medium text-gray-900">{{ project.project_name }}</p>
            <p class="text-sm text-gray-500">{{ project.client_name }} · {{ project.contract_value_pln?.toLocaleString() }} PLN · {{ project.year_started }}-{{ project.year_completed }}</p>
            <p class="text-sm text-gray-600 mt-1">{{ project.description }}</p>
            <div class="flex flex-wrap gap-1 mt-2">
              <span v-for="tech in project.technologies_used" :key="tech" class="bg-gray-100 text-gray-700 text-xs px-2 py-0.5 rounded">{{ tech }}</span>
            </div>
          </div>
          <button @click="handleDeleteProject(project.id)" class="text-red-600 hover:text-red-800 text-sm">Usun</button>
        </div>
      </div>
      <div v-if="profile.portfolio_projects.length === 0" class="text-center text-gray-400 py-8">Brak projektow w portfolio</div>
    </div>

    <!-- Preferences Tab -->
    <div v-if="activeTab === 'preferences'" class="bg-white rounded-lg shadow p-6 space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Stawka godzinowa (PLN netto)</label>
          <input v-model.number="profile.hourly_rate_pln" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Bufor QA (%)</label>
          <input v-model.number="profile.qa_buffer_pct" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Bufor ryzyka (%)</label>
          <input v-model.number="profile.risk_buffer_pct" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Min. budżet (PLN)</label>
          <input v-model.number="profile.preferences_min_budget" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Max. budżet (PLN)</label>
          <input v-model.number="profile.preferences_max_budget" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
      </div>
    </div>
  </div>
  <div v-else class="text-center text-gray-400 py-8">Ladowanie profilu...</div>
</template>
