export interface EligibilityCondition {
  name: string
  description: string
  met: boolean
  reason: string
  fixable: boolean
  fix_options: string[]
}

export interface Step0WadiumInfo {
  required: boolean
  amount: string
  currency: string
  forms: string[]
  deadline: string
  bank_account: string | null
  source_reference: string
}

export interface Step0EvaluationCriterion {
  name: string
  weight_pct: number
  scoring_method: string
  source_reference: string
}

export interface Step0Result {
  eligible: boolean
  conditions: EligibilityCondition[]
  summary: string
  scope_description: string
  estimated_budget: string
  wadium: Step0WadiumInfo | null
  evaluation_criteria: Step0EvaluationCriterion[] | null
}

// Step 1: Scope & Requirements
export interface FunctionalRequirement {
  id: string
  name: string
  description: string
  priority: 'must_have' | 'should_have' | 'nice_to_have'
  acceptance_criteria: string[]
  source_reference: string
}

export interface NonFunctionalRequirement {
  name: string
  description: string
  metric: string
  source_reference: string
}

export interface Deliverable {
  name: string
  description: string
  format: string
  deadline: string | null
}

export interface Step1Result {
  scope_summary: string
  functional_requirements: FunctionalRequirement[]
  non_functional_requirements: NonFunctionalRequirement[]
  deliverables: Deliverable[]
  out_of_scope: string[]
  assumptions: string[]
  open_questions: string[]
  summary: string
}

// Step 2: Technical Solution
export interface OpenSourceOption {
  name: string
  category: string
  fits: boolean
  coverage_pct: number
  pros: string[]
  cons: string[]
  customization_needed: string
  license: string
  license_compatible: boolean
}

export interface StackItem {
  layer: string
  technology: string
  version: string
  rationale: string
  license: string
  cost: string
}

export interface IntegrationPoint {
  name: string
  description: string
  technology: string
  complexity: 'low' | 'medium' | 'high'
}

export interface Step2Result {
  recommended_architecture: string
  open_source_analysis: OpenSourceOption[]
  proposed_stack: StackItem[]
  integration_points: IntegrationPoint[]
  hosting_recommendation: string
  summary: string
}

// Step 3: Effort & Cost
export interface WorkPackage {
  name: string
  description: string
  tasks: string[]
  hours: number
  cost_net_pln: number
}

export interface PricingItem {
  name: string
  description: string
  unit: string
  quantity: number | null
  unit_price_net: number | null
  total_net: number | null
  notes: string
}

export interface EvaluationCriterion {
  name: string
  weight_pct: number
  scoring_method: string
  how_to_maximize: string
  our_strategy: string
}

export interface Deadline {
  name: string
  date: string
  type: string
  notes: string
}

export interface RequiredPerson {
  role: string
  min_experience_years: number
  required_certifications: string[]
  min_count: number
  our_candidate: string
  notes: string
}

export interface AdditionalCost {
  name: string
  description: string
  cost_net_pln: number
  recurring: string
}

export interface Step3Result {
  work_packages: WorkPackage[]
  pricing_items: PricingItem[]
  evaluation_criteria: EvaluationCriterion[]
  deadlines: Deadline[]
  required_personnel: RequiredPerson[]
  subtotal_hours: number
  subtotal_net_pln: number
  qa_buffer_pct: number
  qa_buffer_pln: number
  risk_buffer_pct: number
  risk_buffer_pln: number
  additional_costs: AdditionalCost[]
  total_net_pln: number
  total_gross_pln: number
  suggested_offer_price_net: number
  price_justification: string
  summary: string
}

// Step 4: Risk Analysis
export interface Risk {
  name: string
  severity: 'high' | 'medium' | 'low'
  category: string
  probability: number
  impact: number
  risk_score: number
  description: string
  mitigation: string
  impact_description: string
  owner: string
}

export interface Step4Result {
  risks: Risk[]
  critical_warnings: string[]
  contract_red_flags: string[]
  go_no_go_recommendation: string
  recommendation_rationale: string
  summary: string
}

// Step 5: Document Preparation
export interface DocumentGuide {
  document_name: string
  document_type: string
  is_required: boolean
  requires_signature: boolean
  instruction: string
  suggested_text: string
  warnings: string
  deadline: string | null
}

export interface WadiumInfo {
  required: boolean
  amount: string
  forms: string[]
  deadline: string
  bank_account: string
  our_action: string
  notes: string
}

export interface Step5Result {
  document_guides: DocumentGuide[]
  wadium: WadiumInfo | null
  submission_checklist: string[]
  general_notes: string
}

// Step 6: Document Verification
export interface DocumentIssue {
  severity: 'error' | 'warning' | 'info'
  description: string
  location: string
  fix_suggestion: string
  risk: string
}

export interface CheckedDocument {
  filename: string
  document_type: string
  status: 'ok' | 'warning' | 'error'
  issues: DocumentIssue[]
  completeness_pct: number
  missing_elements: string[]
}

export interface CrossDocumentIssue {
  description: string
  documents_involved: string[]
  fix_suggestion: string
}

export interface Step6Result {
  overall_status: 'ok' | 'issues_found'
  documents_checked: CheckedDocument[]
  missing_documents: string[]
  cross_document_issues: CrossDocumentIssue[]
  summary: string
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
  step1_result: Step1Result | null
  step2_result: Step2Result | null
  step3_result: Step3Result | null
  step4_result: Step4Result | null
  step5_result: Step5Result | null
  step6_result: Step6Result | null
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

export interface VerificationFile {
  id: number
  original_filename: string
  file_size_bytes: number
  uploaded_at: string
}
