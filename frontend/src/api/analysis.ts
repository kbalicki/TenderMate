import api from './client'
import type { Analysis, AnalysisDocument, VerificationFile } from '@/types/analysis'

export async function startAnalysis(tenderId: number): Promise<Analysis> {
  const { data } = await api.post(`/tenders/${tenderId}/analysis/start`)
  return data
}

export async function getAnalysis(tenderId: number): Promise<Analysis> {
  const { data } = await api.get(`/tenders/${tenderId}/analysis`)
  return data
}

export interface CustomFixInput {
  condition_index: number
  text: string
  add_to_profile: boolean
  add_to_portfolio: boolean
}

export async function fixEligibility(
  tenderId: number,
  fixActions: Record<string, unknown>[],
  customInputs: CustomFixInput[] = [],
): Promise<Analysis> {
  const { data } = await api.post(`/tenders/${tenderId}/analysis/fix-eligibility`, {
    fix_actions: fixActions,
    custom_inputs: customInputs,
  })
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

export async function uploadVerificationDocuments(tenderId: number, files: File[]): Promise<Analysis> {
  const formData = new FormData()
  files.forEach(f => formData.append('files', f))
  const { data } = await api.post(`/tenders/${tenderId}/analysis/verify`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function getVerificationFiles(tenderId: number): Promise<VerificationFile[]> {
  const { data } = await api.get(`/tenders/${tenderId}/analysis/verification-files`)
  return data
}
