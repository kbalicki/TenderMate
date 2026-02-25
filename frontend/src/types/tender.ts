export interface TenderAttachment {
  id: number
  filename: string
  file_size_bytes: number | null
  mime_type: string | null
}

export interface Tender {
  id: number
  source_type: string
  source_url: string | null
  portal_name: string | null
  title: string | null
  contracting_authority: string | null
  authority_type: string | null
  reference_number: string | null
  submission_deadline: string | null
  status: string
  error_message: string | null
  ai_summary: string | null
  created_at: string
  updated_at: string
}

export interface TenderDetail extends Tender {
  tender_text: string | null
  attachments: TenderAttachment[]
}

export interface AnalysisSummary {
  eligible: boolean | null
  eligibility_summary: string | null
  go_no_go: string | null
  go_no_go_rationale: string | null
  total_net_pln: number | null
  scope_description: string | null
  analysis_status: string | null
  user_decision: string | null
  attachment_count: number
}

export interface TenderListItem extends Tender {
  analysis_summary: AnalysisSummary | null
  attachment_count: number
}

export interface PaginatedTenders {
  items: TenderListItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}
