import api from './client'
import type { Tender, TenderDetail, PaginatedTenders } from '@/types/tender'

export interface TenderListParams {
  status?: string
  search?: string
  sort_by?: string
  sort_dir?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export async function listTenders(params: TenderListParams = {}): Promise<PaginatedTenders> {
  const { data } = await api.get('/tenders', { params })
  return data
}

export async function createFromUrl(urls: string[]): Promise<Tender> {
  const { data } = await api.post('/tenders/from-url', { urls })
  return data
}

export async function createManual(title: string, tenderText: string, files: File[]): Promise<Tender> {
  const formData = new FormData()
  if (title) formData.append('title', title)
  if (tenderText) formData.append('tender_text', tenderText)
  for (const file of files) {
    formData.append('files', file)
  }
  const { data } = await api.post('/tenders/manual', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function getTender(id: number): Promise<TenderDetail> {
  const { data } = await api.get(`/tenders/${id}`)
  return data
}

export async function deleteTender(id: number): Promise<void> {
  await api.delete(`/tenders/${id}`)
}

export async function rescrapeTender(id: number): Promise<Tender> {
  const { data } = await api.post(`/tenders/${id}/rescrape`)
  return data
}
