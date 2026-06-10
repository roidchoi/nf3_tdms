<script setup lang="ts">
import { onMounted, computed, watch } from 'vue'
import { useExplorerStore } from '@/stores/explorerStore'

const store = useExplorerStore()

// 컴포넌트 마운트 시 테이블 메타데이터 로드 후 최초 데이터 조회
onMounted(async () => {
  await store.fetchMetadata()
  if (store.selectedTable) {
    await store.fetchPreviewData()
  }
})

// 동적으로 컬럼 헤더 추출 (시스템 생성 필드를 별도로 숨기지 않고 유연한 전체 노출)
const tableHeaders = computed<string[]>(() => {
  if (store.tableData.length === 0) return []
  return Object.keys(store.tableData[0])
})

// 시장 변경 감지 시 테이블 목록 스위칭 및 첫 데이터 조회
const handleMarketChange = async (market: 'kr' | 'us') => {
  store.setMarket(market)
  await store.fetchPreviewData()
}

// 테이블 변경 시 데이터 자동 조회
watch(() => store.selectedTable, async (newTable) => {
  if (newTable) {
    store.offset = 0 // 테이블 전환 시 페이지 초기화
    await store.fetchPreviewData()
  }
})

// 검색 필터 실행
const handleSearch = async () => {
  store.offset = 0
  await store.fetchPreviewData()
}

// 필터 리셋 및 재조회
const handleReset = async () => {
  store.resetFilters()
  await store.fetchPreviewData()
}

// 페이징: 이전 페이지
const handlePrevPage = async () => {
  if (store.offset > 0) {
    store.offset = Math.max(0, store.offset - store.limit)
    await store.fetchPreviewData()
  }
}

// 페이징: 다음 페이지 (다음 데이터 유무는 현재 데이터가 limit 수만큼 가득 찼는지로 판별)
const handleNextPage = async () => {
  if (store.tableData.length === store.limit) {
    store.offset += store.limit
    await store.fetchPreviewData()
  }
}

// 페이지 크기(Limit) 변경 시 재조회
const handleLimitChange = async () => {
  store.offset = 0
  await store.fetchPreviewData()
}
</script>

<template>
  <div class="explorer-view-wrapper">
    <!-- 1. 헤더 영역 -->
    <div class="dashboard-toolbar">
      <div class="toolbar-title">
        <h2>🔍 DB Dynamic Data Explorer</h2>
        <span class="badge" :class="{ 'badge-offline': store.isOffline }">
          {{ store.isOffline ? 'Offline Mode' : 'Connected' }}
        </span>
      </div>
      <button class="action-btn" @click="handleReset" :disabled="store.loading">
        🔄 필터 초기화
      </button>
    </div>

    <!-- 2. 필터 및 컨트롤 패널 -->
    <div class="filter-box">
      <div class="filter-grid">
        <!-- 시장 선택 -->
        <div class="filter-item market-tabs-mini">
          <label>시장</label>
          <div class="tabs-wrapper">
            <button 
              type="button"
              class="tab-mini-btn"
              :class="{ active: store.selectedMarket === 'kr' }"
              @click="handleMarketChange('kr')"
            >
              🇰🇷 한국
            </button>
            <button 
              type="button"
              class="tab-mini-btn"
              :class="{ active: store.selectedMarket === 'us' }"
              @click="handleMarketChange('us')"
            >
              🇺🇸 미국
            </button>
          </div>
        </div>

        <!-- 테이블 드롭다운 -->
        <div class="filter-item select-field">
          <label for="table-select">대상 테이블</label>
          <select 
            id="table-select" 
            v-model="store.selectedTable"
            :disabled="store.loading"
          >
            <option 
              v-for="t in store.metadata[store.selectedMarket]" 
              :key="t.table" 
              :value="t.table"
            >
              {{ t.name }} ({{ t.table }})
            </option>
          </select>
        </div>

        <!-- 종목 코드 필터 -->
        <div class="filter-item text-field">
          <label for="stk-cd-input">종목코드/티커/CIK</label>
          <input 
            id="stk-cd-input" 
            type="text" 
            v-model="store.stkCd" 
            placeholder="예: 005930 또는 AAPL"
            @keyup.enter="handleSearch"
            :disabled="store.loading"
          />
        </div>

        <!-- 날짜 필터 -->
        <div class="filter-item date-field">
          <label>날짜 범위</label>
          <div class="date-range-inputs">
            <input 
              type="date" 
              v-model="store.startDate"
              :disabled="store.loading"
            />
            <span>~</span>
            <input 
              type="date" 
              v-model="store.endDate"
              :disabled="store.loading"
            />
          </div>
        </div>

        <!-- 조회 버튼 -->
        <div class="filter-item button-field">
          <button 
            class="search-btn" 
            @click="handleSearch"
            :disabled="store.loading"
          >
            <span v-if="store.loading" class="spinner-mini"></span>
            조회하기
          </button>
        </div>
      </div>
    </div>

    <!-- 3. 백엔드 오프라인 경고 배너 -->
    <div v-if="store.isOffline" class="error-state">
      <div class="error-header">
        ⚠️ {{ store.selectedMarket.toUpperCase() }} 백엔드 통신 실패 (장애 격리 모드)
      </div>
      <div class="error-body">
        하위 백엔드가 오프라인 상태이거나 통신 장애가 발생하였습니다. 시스템은 정상 작동 중이며, 백엔드가 기동되면 데이터 조회가 자동으로 복구됩니다.
        <div v-if="store.errorMessage" class="error-detail">{{ store.errorMessage }}</div>
      </div>
    </div>

    <!-- 4. 데이터 그리드 영역 -->
    <div class="grid-card">
      <div class="card-header">
        <div class="table-info">
          <h4>📊 데이터 테이블 미리보기</h4>
          <span class="count-badge" v-if="!store.isOffline && store.tableData.length > 0">
            총 {{ store.totalCount }}건 중 {{ store.offset + 1 }} ~ {{ store.offset + store.tableData.length }} 표시
          </span>
        </div>
        
        <!-- 페이지 크기(Limit) 설정 -->
        <div class="limit-selector" v-if="!store.isOffline">
          <label for="limit-select">표시 개수:</label>
          <select 
            id="limit-select" 
            v-model="store.limit" 
            @change="handleLimitChange"
            :disabled="store.loading"
          >
            <option :value="50">50개씩</option>
            <option :value="100">100개씩</option>
            <option :value="200">200개씩</option>
            <option :value="500">500개씩</option>
          </select>
        </div>
      </div>

      <!-- 로딩 상태 (스켈레톤 렌더링) -->
      <div v-if="store.loading" class="loading-container">
        <div class="skeleton-wrapper">
          <div class="skeleton-row header-skeleton"></div>
          <div v-for="i in 5" :key="i" class="skeleton-row body-skeleton"></div>
        </div>
      </div>

      <!-- 데이터 렌더링 테이블 -->
      <div v-else-if="store.tableData.length > 0 && !store.isOffline" class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th v-for="header in tableHeaders" :key="header">
                {{ header }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, rIdx) in store.tableData" :key="rIdx">
              <td v-for="header in tableHeaders" :key="header" class="data-cell">
                <span class="cell-value" :title="String(row[header] ?? '')">
                  {{ row[header] !== null && row[header] !== undefined ? row[header] : '-' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 비어있는 데이터 안내 -->
      <div v-else-if="!store.loading && !store.isOffline" class="no-data-container">
        <p class="no-data-text">🔍 조건에 부합하는 조회 데이터가 존재하지 않습니다.</p>
        <span class="no-data-desc">종목 코드나 날짜 필터를 수정하여 다시 검색해 보세요.</span>
      </div>
      
      <!-- 오프라인 모드 데이터 미표시 안내 -->
      <div v-else class="no-data-container offline-data-container">
        <p class="no-data-text">⚠️ 백엔드 오프라인 상태로 데이터를 표시할 수 없습니다.</p>
      </div>

      <!-- 5. 페이지네이션 바 -->
      <div class="pagination-bar" v-if="!store.isOffline && (store.offset > 0 || store.tableData.length === store.limit)">
        <button 
          class="page-btn" 
          @click="handlePrevPage" 
          :disabled="store.offset === 0 || store.loading"
        >
          ◀ 이전 페이지
        </button>
        <span class="page-indicator">Offset: {{ store.offset }}</span>
        <button 
          class="page-btn" 
          @click="handleNextPage" 
          :disabled="store.tableData.length < store.limit || store.loading"
        >
          다음 페이지 ▶
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.explorer-view-wrapper {
  color: #f8fafc;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.dashboard-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 16px;
}

.toolbar-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-title h2 {
  margin: 0;
  font-size: 1.4rem;
  font-weight: 600;
  background: linear-gradient(to right, #fff, #a5b4fc);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.badge {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
  color: var(--color-emerald, #10b981);
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 9999px;
  font-weight: 500;
}

.badge-offline {
  background: rgba(244, 63, 94, 0.1);
  border-color: rgba(244, 63, 94, 0.2);
  color: var(--color-rose, #f43f5e);
}

.action-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #f1f5f9;
  font-size: 0.85rem;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
}

/* 2. 필터 박스 */
.filter-box {
  background: rgba(30, 41, 59, 0.45);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 20px;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  align-items: flex-end;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-item label {
  font-size: 0.8rem;
  color: #94a3b8;
  font-weight: 500;
}

/* 시장 탭 버튼식 미니 레이아웃 */
.tabs-wrapper {
  display: flex;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  padding: 2px;
  height: 36px;
}

.tab-mini-btn {
  flex: 1;
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 0.85rem;
  font-weight: 500;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab-mini-btn.active {
  background: rgba(99, 102, 241, 0.2);
  color: #a5b4fc;
  border: 1px solid rgba(99, 102, 241, 0.3);
}

/* 셀렉트 및 입력 필드 */
select, input[type="text"], input[type="date"] {
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  padding: 8px 12px;
  color: #fff;
  font-size: 0.85rem;
  height: 36px;
  box-sizing: border-box;
}

select:focus, input[type="text"]:focus, input[type="date"]:focus {
  outline: none;
  border-color: var(--color-indigo);
}

.date-range-inputs {
  display: flex;
  align-items: center;
  gap: 8px;
}

.date-range-inputs input {
  flex: 1;
  width: 100%;
}

.search-btn {
  background: var(--color-indigo);
  border: none;
  color: #fff;
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;
  height: 36px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.search-btn:hover:not(:disabled) {
  filter: brightness(1.1);
}

.search-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 3. 에러 / 오프라인 배너 */
.error-state {
  background: rgba(244, 63, 94, 0.1);
  border: 1px solid rgba(244, 63, 94, 0.2);
  color: #fda4af;
  border-radius: 12px;
  padding: 16px;
  font-size: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.error-header {
  font-weight: 700;
  font-size: 0.95rem;
}

.error-body {
  line-height: 1.5;
  color: #f1f5f9;
}

.error-detail {
  margin-top: 6px;
  font-family: monospace;
  background: rgba(0, 0, 0, 0.2);
  padding: 6px 12px;
  border-radius: 6px;
  color: #fda4af;
}

/* 4. 데이터 그리드 카드 */
.grid-card {
  background: rgba(30, 41, 59, 0.45);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.grid-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-info h4 {
  margin: 0;
  font-size: 1.1rem;
  color: #fff;
}

.count-badge {
  display: inline-block;
  font-size: 0.78rem;
  color: #94a3b8;
  margin-top: 4px;
}

.limit-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

.limit-selector label {
  font-size: 0.8rem;
  color: #94a3b8;
}

.limit-selector select {
  height: 30px;
  padding: 4px 8px;
}

/* 테이블 뷰 포트 */
.table-wrapper {
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  max-height: 600px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.85rem;
}

.data-table th, .data-table td {
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  white-space: nowrap;
}

.data-table th {
  background: rgba(15, 23, 42, 0.4);
  color: #94a3b8;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 10;
}

.data-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.02);
}

.data-cell {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cell-value {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 데이터 없음 & 오프라인 플레이스홀더 */
.no-data-container {
  text-align: center;
  padding: 60px 20px;
  background: rgba(15, 23, 42, 0.15);
  border-radius: 8px;
  border: 1px dashed rgba(255, 255, 255, 0.08);
}

.no-data-text {
  font-size: 1rem;
  color: #cbd5e1;
  margin: 0 0 6px 0;
  font-weight: 500;
}

.no-data-desc {
  font-size: 0.82rem;
  color: #64748b;
}

.offline-data-container {
  border-color: rgba(244, 63, 94, 0.15);
}

/* 5. 스켈레톤 로더 */
.loading-container {
  padding: 10px 0;
}

.skeleton-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-row {
  height: 36px;
  border-radius: 6px;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.03) 25%, rgba(255, 255, 255, 0.06) 50%, rgba(255, 255, 255, 0.03) 75%);
  background-size: 200% 100%;
  animation: loading-pulse 1.5s infinite linear;
}

.header-skeleton {
  height: 40px;
  background: rgba(255, 255, 255, 0.05);
}

@keyframes loading-pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* 6. 페이지네이션 바 */
.pagination-bar {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  margin-top: 10px;
}

.page-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #f1f5f9;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.page-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-indicator {
  font-size: 0.82rem;
  color: #94a3b8;
  font-family: monospace;
}

/* 스피너 미니 */
.spinner-mini {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.2);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
