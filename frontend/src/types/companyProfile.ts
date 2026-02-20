export interface TeamMember {
  id: number
  full_name: string
  role: string | null
  experience_years: number | null
  qualifications: string | null
  bio: string | null
}

export interface PortfolioProject {
  id: number
  project_name: string
  client_name: string | null
  description: string | null
  contract_value_pln: number | null
  year_started: number | null
  year_completed: number | null
  technologies_used: string[]
}

export interface CompanyProfile {
  id: number
  company_name: string
  nip: string | null
  regon: string | null
  krs: string | null
  address_street: string | null
  address_city: string | null
  address_postal_code: string | null
  address_country: string
  phone: string | null
  email: string | null
  website: string | null
  description: string | null
  technologies: string[]
  certifications: string[]
  preferences_min_budget: number | null
  preferences_max_budget: number | null
  preferences_categories: string[]
  preferences_excluded_keywords: string[]
  hourly_rate_pln: number
  qa_buffer_pct: number
  risk_buffer_pct: number
  bank_account: string | null
  contact_person: string | null
  team_members: TeamMember[]
  portfolio_projects: PortfolioProject[]
}
