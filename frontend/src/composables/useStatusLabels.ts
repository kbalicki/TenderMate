export const statusLabels: Record<string, string> = {
  new: 'Nowy',
  scraping: 'Pobieranie',
  scraped: 'Pobrany',
  scrape_failed: 'Błąd pobierania',
  analyzing: 'Analiza',
  eligibility_failed: 'Nie spełnia warunków',
  awaiting_decision: 'Oczekuje decyzji',
  rejected: 'Odrzucony',
  in_progress: 'W trakcie',
  completed: 'Zakończony',
  running: 'W trakcie',
  waiting_user: 'Oczekuje na Ciebie',
  failed: 'Błąd',
  pending: 'Oczekuje',
  archived: 'Archiwalne',
}

export function isDeadlineExpired(deadline: string | null): boolean {
  if (!deadline) return false
  return new Date(deadline) < new Date()
}

export function getDisplayStatus(status: string, deadline: string | null): string {
  if (isDeadlineExpired(deadline) && !['completed', 'rejected'].includes(status)) {
    return 'archived'
  }
  return status
}

export function getStatusLabel(status: string): string {
  return statusLabels[status] || status
}

export function getStatusColor(status: string): string {
  switch (status) {
    case 'completed': return 'bg-green-100 text-green-800'
    case 'rejected': case 'failed': case 'scrape_failed': case 'eligibility_failed': return 'bg-red-100 text-red-800'
    case 'analyzing': case 'running': case 'in_progress': return 'bg-blue-100 text-blue-800'
    case 'awaiting_decision': case 'waiting_user': return 'bg-yellow-100 text-yellow-800'
    case 'archived': return 'bg-orange-100 text-orange-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}
