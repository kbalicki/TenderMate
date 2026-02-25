import api from './client'

export interface AppSettings {
  max_concurrent_tasks: number
}

export async function getSettings(): Promise<AppSettings> {
  const { data } = await api.get('/settings')
  return data
}

export async function updateSettings(settings: Partial<AppSettings>): Promise<AppSettings> {
  const { data } = await api.put('/settings', settings)
  return data
}
