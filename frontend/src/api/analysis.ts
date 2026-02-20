import api from './client'
import type { Analysis, AnalysisDocument } from '@/types/analysis'

export async function startAnalysis(tenderId: number): Promise<Analysis> {
  const { data } = await api.post(`/tenders/${tenderId}/analysis/start`)
  return data
}

export async function getAnalysis(tenderId: number): Promise<Analysis> {
  const { data } = await api.get(`/tenders/${tenderId}/analysis`)
  return data
}

export async function fixEligibility(tenderId: number, fixActions: Record<string, unknown>[]): Promise<Analysis> {
  const { data } = await api.post(`/tenders/${tenderId}/analysis/fix-eligibility`, { fix_actions: fixActions })
  return data
}

export async function submitDecision(tenderId: number, decision: 'go' | 'no_go'): Promise<Analysis> {
  const { data } = await api.post(`/tenders/${tenderId}/analysis/decision`, { decision })
  return data
}

export async function continueAnalysis(tenderId: number): Promise<Analysis> {
  const { data } = await api.post(`/tenders/${tenderId}/analysis/continue`)
  return data
}

export async function getDocuments(tenderId: number): Promise<AnalysisDocument[]> {
  const { data } = await api.get(`/tenders/${tenderId}/analysis/documents`)
  return data
}

export async function toggleDocument(tenderId: number, docId: number): Promise<AnalysisDocument> {
  const { data } = await api.put(`/tenders/${tenderId}/analysis/documents/${docId}`)
  return data
}
