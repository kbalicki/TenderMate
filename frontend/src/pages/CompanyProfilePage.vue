<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  getProfile,
  updateProfile,
  addTeamMember,
  updateTeamMember,
  deleteTeamMember,
  addPortfolioProject,
  updatePortfolioProject,
  deletePortfolioProject,
} from '@/api/companyProfile'
import type { CompanyProfile, TeamMember, PortfolioProject } from '@/types/companyProfile'

const profile = ref<CompanyProfile | null>(null)
const activeTab = ref<'info' | 'team' | 'portfolio' | 'preferences'>('info')
const saving = ref(false)
const saved = ref(false)

// Team member form
const emptyMember = (): Omit<TeamMember, 'id'> => ({
  full_name: '',
  role: '',
  experience_years: null,
  qualifications: '',
  bio: '',
})
const memberForm = ref<Omit<TeamMember, 'id'>>(emptyMember())
const editingMemberId = ref<number | null>(null)
const showMemberForm = ref(false)

// Portfolio form
const emptyProject = (): Omit<PortfolioProject, 'id'> => ({
  project_name: '',
  client_name: '',
  description: '',
  contract_value_pln: null,
  year_started: null,
  year_completed: null,
  technologies_used: [],
})
const projectForm = ref<Omit<PortfolioProject, 'id'>>(emptyProject())
const editingProjectId = ref<number | null>(null)
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

// --- Team Members ---

function openAddMember() {
  editingMemberId.value = null
  memberForm.value = emptyMember()
  showMemberForm.value = true
}

function openEditMember(member: TeamMember) {
  editingMemberId.value = member.id
  memberForm.value = {
    full_name: member.full_name,
    role: member.role,
    experience_years: member.experience_years,
    qualifications: member.qualifications,
    bio: member.bio,
  }
  showMemberForm.value = true
}

function cancelMemberForm() {
  showMemberForm.value = false
  editingMemberId.value = null
  memberForm.value = emptyMember()
}

async function handleSaveMember() {
  if (!profile.value) return
  if (editingMemberId.value !== null) {
    const updated = await updateTeamMember(editingMemberId.value, memberForm.value)
    const idx = profile.value.team_members.findIndex(m => m.id === editingMemberId.value)
    if (idx !== -1) profile.value.team_members[idx] = updated
  } else {
    const created = await addTeamMember(memberForm.value)
    profile.value.team_members.push(created)
  }
  cancelMemberForm()
}

async function handleDeleteMember(id: number) {
  if (!confirm('Usunac tego czlonka zespolu?')) return
  await deleteTeamMember(id)
  if (profile.value) {
    profile.value.team_members = profile.value.team_members.filter(m => m.id !== id)
  }
}

// --- Portfolio Projects ---

function openAddProject() {
  editingProjectId.value = null
  projectForm.value = emptyProject()
  showProjectForm.value = true
}

function openEditProject(project: PortfolioProject) {
  editingProjectId.value = project.id
  projectForm.value = {
    project_name: project.project_name,
    client_name: project.client_name,
    description: project.description,
    contract_value_pln: project.contract_value_pln,
    year_started: project.year_started,
    year_completed: project.year_completed,
    technologies_used: [...(project.technologies_used || [])],
  }
  showProjectForm.value = true
}

function cancelProjectForm() {
  showProjectForm.value = false
  editingProjectId.value = null
  projectForm.value = emptyProject()
}

async function handleSaveProject() {
  if (!profile.value) return
  if (editingProjectId.value !== null) {
    const updated = await updatePortfolioProject(editingProjectId.value, projectForm.value)
    const idx = profile.value.portfolio_projects.findIndex(p => p.id === editingProjectId.value)
    if (idx !== -1) profile.value.portfolio_projects[idx] = updated
  } else {
    const created = await addPortfolioProject(projectForm.value)
    profile.value.portfolio_projects.push(created)
  }
  cancelProjectForm()
}

async function handleDeleteProject(id: number) {
  if (!confirm('Usunac ten projekt?')) return
  await deletePortfolioProject(id)
  if (profile.value) {
    profile.value.portfolio_projects = profile.value.portfolio_projects.filter(p => p.id !== id)
  }
}

function addTech() {
  if (techInput.value.trim()) {
    projectForm.value.technologies_used.push(techInput.value.trim())
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
        <button @click="showMemberForm ? cancelMemberForm() : openAddMember()" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
          {{ showMemberForm ? 'Anuluj' : '+ Dodaj czlonka zespolu' }}
        </button>
      </div>

      <!-- Member form (add/edit) -->
      <div v-if="showMemberForm" class="bg-white rounded-lg shadow p-6 space-y-4">
        <h3 class="text-sm font-semibold text-gray-900">
          {{ editingMemberId !== null ? 'Edytuj czlonka zespolu' : 'Nowy czlonek zespolu' }}
        </h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-xs text-gray-500 mb-1">Imie i nazwisko</label>
            <input v-model="memberForm.full_name" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-500 mb-1">Rola</label>
            <input v-model="memberForm.role" placeholder="np. Senior Developer" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-500 mb-1">Lata doswiadczenia</label>
            <input v-model.number="memberForm.experience_years" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-500 mb-1">Kwalifikacje / certyfikaty</label>
            <input v-model="memberForm.qualifications" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">Bio</label>
          <textarea v-model="memberForm.bio" rows="2" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"></textarea>
        </div>
        <div class="flex gap-2">
          <button @click="handleSaveMember" class="px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700">
            {{ editingMemberId !== null ? 'Zapisz zmiany' : 'Dodaj' }}
          </button>
          <button @click="cancelMemberForm" class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm hover:bg-gray-300">Anuluj</button>
        </div>
      </div>

      <!-- Members list -->
      <div v-for="member in profile.team_members" :key="member.id" class="bg-white rounded-lg shadow p-4">
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <p class="font-medium text-gray-900">{{ member.full_name }}</p>
            <p class="text-sm text-indigo-600">{{ member.role }}</p>
            <p class="text-xs text-gray-500 mt-1">{{ member.experience_years }} lat doswiadczenia</p>
            <p v-if="member.qualifications" class="text-xs text-gray-600 mt-1">{{ member.qualifications }}</p>
            <p v-if="member.bio" class="text-xs text-gray-500 mt-1 italic">{{ member.bio }}</p>
          </div>
          <div class="flex gap-2 ml-4">
            <button @click="openEditMember(member)" class="text-indigo-600 hover:text-indigo-800 text-sm">Edytuj</button>
            <button @click="handleDeleteMember(member.id)" class="text-red-600 hover:text-red-800 text-sm">Usun</button>
          </div>
        </div>
      </div>
      <div v-if="profile.team_members.length === 0" class="text-center text-gray-400 py-8">Brak czlonkow zespolu</div>
    </div>

    <!-- Portfolio Tab -->
    <div v-if="activeTab === 'portfolio'" class="space-y-4">
      <div class="flex justify-end">
        <button @click="showProjectForm ? cancelProjectForm() : openAddProject()" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
          {{ showProjectForm ? 'Anuluj' : '+ Dodaj projekt' }}
        </button>
      </div>

      <!-- Project form (add/edit) -->
      <div v-if="showProjectForm" class="bg-white rounded-lg shadow p-6 space-y-4">
        <h3 class="text-sm font-semibold text-gray-900">
          {{ editingProjectId !== null ? 'Edytuj projekt' : 'Nowy projekt' }}
        </h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-xs text-gray-500 mb-1">Nazwa projektu</label>
            <input v-model="projectForm.project_name" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-500 mb-1">Klient</label>
            <input v-model="projectForm.client_name" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-500 mb-1">Wartosc kontraktu (PLN netto)</label>
            <input v-model.number="projectForm.contract_value_pln" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div class="flex gap-2">
            <div class="flex-1">
              <label class="block text-xs text-gray-500 mb-1">Rok start</label>
              <input v-model.number="projectForm.year_started" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div class="flex-1">
              <label class="block text-xs text-gray-500 mb-1">Rok koniec</label>
              <input v-model.number="projectForm.year_completed" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">Opis projektu</label>
          <textarea v-model="projectForm.description" rows="2" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"></textarea>
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">Technologie</label>
          <div class="flex gap-2 mb-2">
            <input v-model="techInput" @keyup.enter="addTech" placeholder="Dodaj technologie i nacisnij Enter" class="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            <button @click="addTech" class="px-3 py-2 bg-gray-200 rounded-lg text-sm hover:bg-gray-300">+</button>
          </div>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="(tech, i) in projectForm.technologies_used"
              :key="i"
              class="bg-indigo-100 text-indigo-800 text-xs px-2 py-1 rounded-full flex items-center gap-1"
            >
              {{ tech }}
              <button @click="projectForm.technologies_used.splice(i, 1)" class="hover:text-red-600">&times;</button>
            </span>
          </div>
        </div>
        <div class="flex gap-2">
          <button @click="handleSaveProject" class="px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700">
            {{ editingProjectId !== null ? 'Zapisz zmiany' : 'Dodaj' }}
          </button>
          <button @click="cancelProjectForm" class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm hover:bg-gray-300">Anuluj</button>
        </div>
      </div>

      <!-- Projects list -->
      <div v-for="project in profile.portfolio_projects" :key="project.id" class="bg-white rounded-lg shadow p-4">
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <p class="font-medium text-gray-900">{{ project.project_name }}</p>
            <p class="text-sm text-gray-500">{{ project.client_name }} · {{ project.contract_value_pln?.toLocaleString() }} PLN · {{ project.year_started }}-{{ project.year_completed }}</p>
            <p class="text-sm text-gray-600 mt-1">{{ project.description }}</p>
            <div class="flex flex-wrap gap-1 mt-2">
              <span v-for="tech in project.technologies_used" :key="tech" class="bg-gray-100 text-gray-700 text-xs px-2 py-0.5 rounded">{{ tech }}</span>
            </div>
          </div>
          <div class="flex gap-2 ml-4">
            <button @click="openEditProject(project)" class="text-indigo-600 hover:text-indigo-800 text-sm">Edytuj</button>
            <button @click="handleDeleteProject(project.id)" class="text-red-600 hover:text-red-800 text-sm">Usun</button>
          </div>
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
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Roczny obrót netto (PLN)</label>
        <input v-model.number="profile.annual_revenue_pln" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="np. 1000000" />
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Min. budzet (PLN)</label>
          <input v-model.number="profile.preferences_min_budget" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Max. budzet (PLN)</label>
          <input v-model.number="profile.preferences_max_budget" type="number" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
      </div>
    </div>
  </div>
  <div v-else class="text-center text-gray-400 py-8">Ladowanie profilu...</div>
</template>
