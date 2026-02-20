export interface EligibilityCondition {
  name: string
  description: string
  met: boolean
  reason: string
  fixable: boolean
  fix_options: string[]
}

export interface Step0Result {
  eligible: boolean
  conditions: EligibilityCondition[]
  summary: string
  scope_description: string
  estimated_budget: string
}

export interface Analysis {
  id: number
  tender_id: number
  current_step: number
  status: string
  step0_result: Step0Result | null
  step0_eligible: boolean | null
  step0_fix_actions: unknown[] | null
  user_decision: string | null
  step1_result: Record<string, unknown> | null
  step2_result: Record<string, unknown> | null
  step3_result: Record<string, unknown> | null
  step4_result: Record<string, unknown> | null
  step5_result: Record<string, unknown> | null
  error_message: string | null
}

export interface AnalysisDocument {
  id: number
  document_name: string
  instruction: string | null
  suggested_text: string | null
  is_completed: boolean
  order_index: number
}
