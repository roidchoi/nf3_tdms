<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useDataStore } from '@/stores/dataStore'
import type { DataPreviewParams } from '@/types/data'

const dataStore = useDataStore()

// 현재 날짜 기준으로 기본 분기 계산 (예: 2025Q4)
const getCurrentQuarter = () => {
  const now = new Date()
  const q = Math.ceil((now.getMonth() + 1) / 3)
  return `${now.getFullYear()}Q${q}`
}

const filters = ref({
  table: 'daily_ohlcv',
  stk_cd: '',
  quarter: getCurrentQuarter(), // [신규]
  startDate: new Date().toISOString().split('T')[0], // 기본값 오늘
  endDate: new Date().toISOString().split('T')[0],
  limit: 50,
  offset: 0
})

// [신규] 테이블 타입 감지
const isTargetHistory = computed(() => filters.value.table === 'minute_target_history')
const isFinancial = computed(() => filters.value.table.startsWith('financial_'))
const isGeneral = computed(() => !isTargetHistory.value && !isFinancial.value)

// 데이터 조회
const fetchData = () => {
  // API 파라미터 구성 (타입에 따라 다르게 보냄)
  const params: DataPreviewParams = {
    limit: filters.value.limit,
    offset: filters.value.offset
  }

  if (isTargetHistory.value) {
    params.quarter = filters.value.quarter
  } else if (isFinancial.value) {
    params.stk_cd = filters.value.stk_cd
  } else {
    // General
    if (filters.value.stk_cd) params.stk_cd = filters.value.stk_cd
    if (filters.value.startDate) params.start_date = filters.value.startDate
    if (filters.value.endDate) params.end_date = filters.value.endDate
  }

  dataStore.fetchPreview(filters.value.table, params)
}

// 테이블 변경 시 필터 초기화
watch(() => filters.value.table, () => {
  filters.value.offset = 0
  // 데이터 초기화 (선택 사항)
  // dataStore.previewData = [] 
})

// 동적 헤더
const headers = computed(() => {
  const firstRow = dataStore.previewData[0]
  if (firstRow) return Object.keys(firstRow)
  return []
})

// 페이지네이션
const prevPage = () => {
  if (filters.value.offset >= filters.value.limit) {
    filters.value.offset -= filters.value.limit
    fetchData()
  }
}
const nextPage = () => {
  if (dataStore.previewData.length === filters.value.limit) {
    filters.value.offset += filters.value.limit
    fetchData()
  }
}
</script>

<template>
  <div class="explorer-view">
    <div class="header">
      <h2>💾 DB 데이터 탐색기</h2>
    </div>

    <div class="control-panel">
      <div class="form-group">
        <label>테이블 선택</label>
        <select v-model="filters.table">
          <option v-for="tb in dataStore.tables" :key="tb" :value="tb">
            {{ tb }}
          </option>
        </select>
      </div>

      <div v-if="isTargetHistory" class="form-group">
        <label>분기 (Quarter)</label>
        <input type="text" v-model="filters.quarter" placeholder="YYYYQN (ex: 2025Q4)">
      </div>

      <div v-if="!isTargetHistory" class="form-group">
        <label>종목코드</label>
        <input type="text" v-model="filters.stk_cd" placeholder="예: 005930">
      </div>

      <div v-if="isGeneral" class="form-group">
        <label>기간</label>
        <div class="date-range">
          <input type="date" v-model="filters.startDate">
          <span>~</span>
          <input type="date" v-model="filters.endDate">
        </div>
      </div>

      <button @click="fetchData" class="search-btn" :disabled="dataStore.isLoading">
        {{ dataStore.isLoading ? '조회 중...' : '조회' }}
      </button>
    </div>

    <div v-if="dataStore.error" class="error-msg">
      ⚠️ {{ dataStore.error }}
    </div>

    <div class="table-wrapper">
      <table v-if="dataStore.previewData.length > 0">
        <thead>
          <tr>
            <th v-for="key in headers" :key="key">{{ key }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in dataStore.previewData" :key="idx">
            <td v-for="key in headers" :key="key">
              {{ row[key] }}
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="!dataStore.isLoading" class="empty-state">
        데이터가 없습니다. 조건을 확인하고 조회 버튼을 눌러주세요.
      </div>
    </div>

    <div class="pagination">
      <button @click="prevPage" :disabled="filters.offset === 0">이전</button>
      <span>Offset: {{ filters.offset }}</span>
      <button @click="nextPage" :disabled="dataStore.previewData.length < filters.limit">다음</button>
    </div>
  </div>
</template>

<style scoped>
/* 스타일은 기존 코드 그대로 유지 */
.explorer-view {
  max-width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 0;
}

.header h2 { margin: 0; color: #1e293b; font-size: 1.5rem; }

.control-panel {
  background: white;
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: flex-end;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

label { font-size: 0.85rem; color: #64748b; font-weight: 600; }

select, input {
  padding: 0.5rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 0.9rem;
}

.date-range { display: flex; align-items: center; gap: 0.5rem; }

.search-btn {
  padding: 0.6rem 1.5rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
}
.search-btn:disabled { background: #94a3b8; }

.error-msg {
  background: #fef2f2;
  color: #dc2626;
  padding: 1rem;
  border-radius: 6px;
  border: 1px solid #fecaca;
}

.table-wrapper {
  flex: 1;
  background: white;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  overflow: auto;
  min-height: 400px;
  max-width: 100%;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  white-space: nowrap;
}

th {
  background: #f8fafc;
  position: sticky;
  top: 0;
  padding: 0.8rem;
  text-align: left;
  border-bottom: 1px solid #e2e8f0;
  color: #475569;
}

td {
  padding: 0.6rem 0.8rem;
  border-bottom: 1px solid #f1f5f9;
  color: #334155;
}

.empty-state {
  padding: 3rem;
  text-align: center;
  color: #94a3b8;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
}

.pagination button {
  padding: 0.4rem 1rem;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  cursor: pointer;
}
.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>