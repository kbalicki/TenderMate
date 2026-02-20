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
  reference_number: string | null
  submission_deadline: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface TenderDetail extends Tender {
  tender_text: string | null
  attachments: TenderAttachment[]
}
