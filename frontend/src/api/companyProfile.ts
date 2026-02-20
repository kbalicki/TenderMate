import api from './client'
import type { CompanyProfile, TeamMember, PortfolioProject } from '@/types/companyProfile'

export async function getProfile(): Promise<CompanyProfile> {
  const { data } = await api.get('/company-profile')
  return data
}

export async function updateProfile(profile: Partial<CompanyProfile>): Promise<CompanyProfile> {
  const { data } = await api.put('/company-profile', profile)
  return data
}

export async function addTeamMember(member: Omit<TeamMember, 'id'>): Promise<TeamMember> {
  const { data } = await api.post('/company-profile/team', member)
  return data
}

export async function updateTeamMember(id: number, member: Omit<TeamMember, 'id'>): Promise<TeamMember> {
  const { data } = await api.put(`/company-profile/team/${id}`, member)
  return data
}

export async function deleteTeamMember(id: number): Promise<void> {
  await api.delete(`/company-profile/team/${id}`)
}

export async function addPortfolioProject(project: Omit<PortfolioProject, 'id'>): Promise<PortfolioProject> {
  const { data } = await api.post('/company-profile/portfolio', project)
  return data
}

export async function updatePortfolioProject(id: number, project: Omit<PortfolioProject, 'id'>): Promise<PortfolioProject> {
  const { data } = await api.put(`/company-profile/portfolio/${id}`, project)
  return data
}

export async function deletePortfolioProject(id: number): Promise<void> {
  await api.delete(`/company-profile/portfolio/${id}`)
}
