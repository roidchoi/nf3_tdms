<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import http from '@/api/http'
import type {
  MethodListResponse,
  MethodInfo,
  MethodExecuteRequest,
  MethodExecuteResponse
} from '@/types/debug'

// State
const selectedTarget = ref<'kis' | 'kiwoom'>('kis')
const mockMode = ref(false)
const selectedMethod = ref('')
const methodParams = ref<Record<string, any>>({})
const methodList = ref<MethodListResponse>({ kis: [], kiwoom: [] })
const executionResult = ref<MethodExecuteResponse | null>(null)
const isLoading = ref(false)

// Computed
const currentMethodList = computed(() => methodList.value[selectedTarget.value])
const currentMethodInfo = computed(() => {
  return currentMethodList.value.find((m) => m.name === selectedMethod.value)
})

// Methods
async function loadMethods() {
  try {
    const response = await http.get<MethodListResponse>('/debug/methods')
    methodList.value = response.data
  } catch (error: any) {
    console.error('메소드 목록 로드 실패:', error)
    alert('메소드 목록을 불러오는 데 실패했습니다.')
  }
}

function resetParams() {
  if (currentMethodInfo.value) {
    // 기본값으로 파라미터 초기화
    methodParams.value = { ...currentMethodInfo.value.defaults }
  }
}

async function executeMethod() {
  if (!selectedMethod.value) {
    alert('메소드를 선택하세요.')
    return
  }

  isLoading.value = true
  executionResult.value = null

  try {
    const request: MethodExecuteRequest = {
      target: selectedTarget.value,
      method_name: selectedMethod.value,
      params: methodParams.value,
      mock_mode: mockMode.value
    }

    const response = await http.post<MethodExecuteResponse>('/debug/execute', request)
    executionResult.value = response.data
  } catch (error: any) {
    executionResult.value = {
      success: false,
      error: {
        type: 'NetworkError',
        message: error.message || '요청 실패'
      }
    }
  } finally {
    isLoading.value = false
  }
}

// Watchers
watch(selectedTarget, () => {
  selectedMethod.value = ''
  methodParams.value = {}
  executionResult.value = null
})

watch(selectedMethod, resetParams)

// Lifecycle
onMounted(loadMethods)
</script>

<template>
  <div class="api-debugger">
    <h1 class="page-title">🔍 Advanced API Inspector</h1>
    <p class="page-description">
      외부 증권사 API의 실제 응답을 테스트하고 구조 변경을 감지합니다.
    </p>

    <div class="debugger-container">
      <!-- 1. Collector 선택 -->
      <section class="section">
        <h2 class="section-title">1️⃣ Collector 선택</h2>
        <div class="collector-select">
          <label>
            <input type="radio" v-model="selectedTarget" value="kis" />
            KIS REST (한국투자증권)
          </label>
          <label>
            <input type="radio" v-model="selectedTarget" value="kiwoom" />
            Kiwoom REST (키움증권)
          </label>
          <label class="mock-toggle">
            <input type="checkbox" v-model="mockMode" />
            Mock Mode (모의투자)
          </label>
        </div>
      </section>

      <!-- 2. Method 선택 -->
      <section class="section">
        <h2 class="section-title">2️⃣ Method 선택</h2>
        <select v-model="selectedMethod" class="method-select">
          <option value="">-- 메소드를 선택하세요 --</option>
          <option v-for="method in currentMethodList" :key="method.name" :value="method.name">
            {{ method.name }}
          </option>
        </select>
        <p v-if="currentMethodInfo" class="method-description">
          {{ currentMethodInfo.description }}
        </p>
      </section>

      <!-- 3. Parameters -->
      <section v-if="currentMethodInfo" class="section">
        <h2 class="section-title">3️⃣ Parameters</h2>
        <div class="params-form">
          <div v-for="param in currentMethodInfo.params" :key="param" class="param-row">
            <label>{{ param }}:</label>
            <input v-model="methodParams[param]" :placeholder="String(currentMethodInfo.defaults[param] || '')" />
          </div>
        </div>
        <button @click="executeMethod" :disabled="isLoading" class="execute-btn">
          {{ isLoading ? '실행 중...' : 'Execute Method' }}
        </button>
      </section>

      <!-- 4. Result Viewer -->
      <section v-if="executionResult" class="section">
        <h2 class="section-title">4️⃣ Result Viewer</h2>

        <!-- 성공 -->
        <div v-if="executionResult.success" class="result-success">
          <h3 class="result-header">
            ✅ Success
            <span v-if="executionResult.metadata" class="metadata">
              ({{ executionResult.metadata.execution_time }}s, {{ executionResult.metadata.result_type }}, {{ executionResult.metadata.result_length }} items)
            </span>
          </h3>

          <!-- 구조 검증 결과 -->
          <div v-if="executionResult.validation_result" class="validation-result" :class="executionResult.validation_result.status">
            <h4>📋 응답 구조 검증 (DATA_MAPPER)</h4>
            <p>{{ executionResult.validation_result.message }}</p>
            <details v-if="executionResult.validation_result.missing_keys && executionResult.validation_result.missing_keys.length > 0">
              <summary>누락된 키 ({{ executionResult.validation_result.missing_keys.length }}개)</summary>
              <pre>{{ JSON.stringify(executionResult.validation_result.missing_keys, null, 2) }}</pre>
            </details>
            <details v-if="executionResult.validation_result.extra_keys && executionResult.validation_result.extra_keys.length > 0">
              <summary>추가 키 ({{ executionResult.validation_result.extra_keys.length }}개)</summary>
              <pre>{{ JSON.stringify(executionResult.validation_result.extra_keys, null, 2) }}</pre>
            </details>
          </div>

          <!-- 결과 데이터 -->
          <details open>
            <summary>응답 데이터</summary>
            <pre class="result-data">{{ JSON.stringify(executionResult.result, null, 2) }}</pre>
          </details>
        </div>

        <!-- 실패 -->
        <div v-else class="result-error">
          <h3 class="result-header">❌ Error: {{ executionResult.error?.type }}</h3>
          <p class="error-message">{{ executionResult.error?.message }}</p>
          <p v-if="executionResult.error?.hint" class="error-hint">💡 {{ executionResult.error.hint }}</p>
          <p v-if="executionResult.error?.error_code" class="error-code">Error Code: {{ executionResult.error.error_code }}</p>
          <details v-if="executionResult.error?.traceback">
            <summary>Traceback</summary>
            <pre class="traceback">{{ executionResult.error.traceback }}</pre>
          </details>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.api-debugger {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.page-title {
  font-size: 2rem;
  font-weight: bold;
  margin-bottom: 0.5rem;
  color: #1e293b;
}

.page-description {
  color: #64748b;
  margin-bottom: 2rem;
}

.debugger-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.section {
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.section-title {
  font-size: 1.2rem;
  font-weight: 600;
  margin-bottom: 1rem;
  color: #334155;
}

.collector-select {
  display: flex;
  gap: 2rem;
  align-items: center;
}

.collector-select label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.mock-toggle {
  margin-left: auto;
  color: #f59e0b;
  font-weight: 600;
}

.method-select {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 1rem;
}

.method-description {
  margin-top: 0.5rem;
  color: #64748b;
  font-size: 0.9rem;
}

.params-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.param-row {
  display: grid;
  grid-template-columns: 150px 1fr;
  align-items: center;
  gap: 1rem;
}

.param-row label {
  font-weight: 600;
  color: #475569;
}

.param-row input {
  padding: 0.5rem;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  font-size: 0.95rem;
}

.execute-btn {
  padding: 0.75rem 2rem;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.execute-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.execute-btn:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.result-success,
.result-error {
  padding: 1rem;
  border-radius: 6px;
}

.result-success {
  background: #f0fdf4;
  border: 2px solid #22c55e;
}

.result-error {
  background: #fef2f2;
  border: 2px solid #ef4444;
}

.result-header {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 1rem;
}

.metadata {
  font-size: 0.9rem;
  color: #64748b;
  font-weight: normal;
}

.validation-result {
  background: white;
  padding: 1rem;
  border-radius: 4px;
  margin-bottom: 1rem;
}

.validation-result.success {
  border-left: 4px solid #22c55e;
}

.validation-result.error {
  border-left: 4px solid #ef4444;
}

.validation-result.warning {
  border-left: 4px solid #f59e0b;
}

.validation-result h4 {
  margin-bottom: 0.5rem;
  font-size: 1rem;
}

.error-message {
  font-weight: 600;
  color: #dc2626;
  margin-bottom: 0.5rem;
}

.error-hint {
  background: #fef3c7;
  padding: 0.75rem;
  border-radius: 4px;
  margin-top: 0.5rem;
  color: #92400e;
}

.error-code {
  font-family: monospace;
  background: #f1f5f9;
  padding: 0.5rem;
  border-radius: 4px;
  margin-top: 0.5rem;
}

.result-data,
.traceback {
  background: #1e293b;
  color: #e2e8f0;
  padding: 1rem;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 0.85rem;
  line-height: 1.5;
  max-height: 500px;
  overflow-y: auto;
}

details {
  margin-top: 1rem;
}

details summary {
  cursor: pointer;
  font-weight: 600;
  padding: 0.5rem;
  background: #f8fafc;
  border-radius: 4px;
}

details summary:hover {
  background: #f1f5f9;
}
</style>
