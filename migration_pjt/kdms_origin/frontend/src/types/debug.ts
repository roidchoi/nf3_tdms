/**
 * API 진단 도구 타입 정의
 */

export interface MethodInfo {
  name: string
  params: string[]
  defaults: Record<string, any>
  description: string
}

export interface MethodExecuteRequest {
  target: 'kis' | 'kiwoom'
  method_name: string
  params: Record<string, any>
  mock_mode: boolean
}

export interface ExecutionMetadata {
  execution_time: number
  result_type: string
  result_length?: number
}

export interface ErrorDetail {
  type: string
  message: string
  traceback?: string
  error_code?: string
  hint?: string
}

export interface ValidationResult {
  status: 'success' | 'error' | 'warning' | 'skip'
  message: string
  required_keys?: string[]
  missing_keys?: string[]
  present_keys?: string[]
  extra_keys?: string[]
}

export interface MethodExecuteResponse {
  success: boolean
  result?: any
  metadata?: ExecutionMetadata
  error?: ErrorDetail
  validation_result?: ValidationResult
}

export interface MethodListResponse {
  kis: MethodInfo[]
  kiwoom: MethodInfo[]
}
