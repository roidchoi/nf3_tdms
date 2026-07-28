<script setup lang="ts">
import { onMounted, computed, watch } from 'vue'
import { useExplorerStore } from '@/stores/explorerStore'

const store = useExplorerStore()

// 컴포넌트 마운트 시 테이블 메타데이터 로드 후 최초 데이터 조회
onMounted(async () => {
  await store.fetchMetadata()
  if (store.selectedTable) {
    store.applyDefaultFiltersForTable(store.selectedTable)
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
    store.applyDefaultFiltersForTable(newTable)
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

// 필터 동적 노출 여부 및 레이블 조건 설정
const showStkCdFilter = computed(() => {
  return !['system_milestones', 'trading_calendar'].includes(store.selectedTable)
})

const stkCdLabel = computed(() => {
  if (store.selectedMarket === 'us') {
    return ['us_ticker_master', 'us_daily_price'].includes(store.selectedTable) ? '티커' : 'CIK'
  }
  return '종목코드'
})

const stkCdPlaceholder = computed(() => {
  if (store.selectedMarket === 'us') {
    return ['us_ticker_master', 'us_daily_price'].includes(store.selectedTable) ? '예: AAPL' : '예: 0000320193'
  }
  return '예: 005930'
})

const showDateFilter = computed(() => {
  return [
    'daily_ohlcv', 'daily_ohlcv_adjusted', 'daily_market_cap', 'minute_ohlcv',
    'system_milestones', 'trading_calendar', 'price_adjustment_factors',
    'us_daily_price', 'us_daily_valuation', 'us_price_adjustment_factors',
    'us_ticker_history', 'us_collection_blacklist',
    'daily_investor_trade'
  ].includes(store.selectedTable)
})

const showQuarterFilter = computed(() => {
  return ['minute_target_history', 'financial_statements', 'financial_ratios'].includes(store.selectedTable)
})

const quarterLabel = computed(() => {
  return store.selectedTable === 'minute_target_history' ? '분기(Quarter)' : '결산년월(stac_yymm)'
})

const quarterPlaceholder = computed(() => {
  return store.selectedTable === 'minute_target_history' ? '예: 2026Q1' : '예: 202512'
})

const showMarketFilter = computed(() => {
  return ['minute_target_history', 'stock_info', 'us_ticker_master'].includes(store.selectedTable)
})

const marketFilterLabel = computed(() => {
  return store.selectedMarket === 'us' ? '거래소' : '시장 구분'
})

const isMarketSelect = computed(() => {
  return store.selectedTable === 'minute_target_history'
})

// 종목 코드 헬퍼 상태 및 메소드 정의
import { ref } from 'vue'
import http from '@/api/http'

const helperSearchKeyword = ref<string>('')
const helperMatchType = ref<'contains' | 'exact'>('contains')
const helperSearchField = ref<'all' | 'code' | 'name'>('all')
const helperLoading = ref<boolean>(false)
const helperResults = ref<any[]>([])
const hasSearchedHelper = ref<boolean>(false)

const searchHelperCodes = async () => {
  const kw = helperSearchKeyword.value.trim()
  if (!kw) return
  
  helperLoading.value = true
  hasSearchedHelper.value = true
  helperResults.value = []
  
  try {
    const market = store.selectedMarket
    const table = market === 'kr' ? 'stock_info' : 'us_ticker_master'
    const resp = await http.get<any>(`/preview/${market}/${table}`, {
      params: {
        limit: 15,
        keyword: kw,
        match_type: helperMatchType.value,
        search_field: helperSearchField.value
      }
    })
    if (resp.data && resp.data.data) {
      helperResults.value = resp.data.data
    }
  } catch (err) {
    console.error('Helper search failed:', err)
  } finally {
    helperLoading.value = false
  }
}

const applyHelperCode = (row: any) => {
  if (store.selectedMarket === 'kr') {
    store.stkCd = row.stk_cd
  } else {
    const cikTables = [
      'us_ticker_history', 'us_collection_blacklist', 'us_financial_facts',
      'us_standard_financials', 'us_share_history', 'us_price_adjustment_factors',
      'us_daily_valuation', 'us_financial_metrics'
    ]
    if (cikTables.includes(store.selectedTable)) {
      store.stkCd = row.cik
    } else {
      store.stkCd = row.latest_ticker || row.ticker || ''
    }
  }
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

        <!-- 종목 코드 필터 (동적) -->
        <div v-if="showStkCdFilter" class="filter-item text-field">
          <label for="stk-cd-input">{{ stkCdLabel }}</label>
          <input 
            id="stk-cd-input" 
            type="text" 
            v-model="store.stkCd" 
            :placeholder="stkCdPlaceholder"
            @keyup.enter="handleSearch"
            :disabled="store.loading"
          />
        </div>

        <!-- 날짜 필터 (동적) -->
        <div v-if="showDateFilter" class="filter-item date-field">
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

        <!-- 분기 필터 (동적) -->
        <div v-if="showQuarterFilter" class="filter-item text-field">
          <label for="quarter-input">{{ quarterLabel }}</label>
          <input 
            id="quarter-input" 
            type="text" 
            v-model="store.quarter" 
            :placeholder="quarterPlaceholder"
            @keyup.enter="handleSearch"
            :disabled="store.loading"
          />
        </div>

        <!-- 시장 상세 구분 필터 (동적) -->
        <div v-if="showMarketFilter" class="filter-item select-field">
          <label for="market-filter-input">{{ marketFilterLabel }}</label>
          <select 
            v-if="isMarketSelect"
            id="market-filter-input" 
            v-model="store.marketFilter"
            :disabled="store.loading"
            @change="handleSearch"
          >
            <option value="KOSPI">KOSPI</option>
            <option value="KOSDAQ">KOSDAQ</option>
          </select>
          <input 
            v-else
            id="market-filter-input" 
            type="text" 
            v-model="store.marketFilter" 
            :placeholder="store.selectedMarket === 'us' ? '예: NASDAQ, NYSE' : '예: KOSPI, KOSDAQ'"
            @keyup.enter="handleSearch"
            :disabled="store.loading"
          />
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

    <!-- 2.5 종목 코드 헬퍼창 -->
    <div class="code-helper-box">
      <div class="helper-header">
        <span class="helper-title">🔑 종목 코드 검색기 ({{ store.selectedMarket === 'kr' ? 'KR: 코드-종목명' : 'US: CIK-티커-회사명' }})</span>
      </div>
      <div class="helper-layout">
        <!-- 왼쪽: 결과 출력 (70%) -->
        <div class="helper-left-pane">
          <div v-if="helperResults.length > 0" class="helper-results-scroll">
            <table class="helper-results-table">
              <thead>
                <tr v-if="store.selectedMarket === 'kr'">
                  <th>종목코드</th>
                  <th>종목명</th>
                  <th>시장</th>
                  <th>작업</th>
                </tr>
                <tr v-else>
                  <th>CIK</th>
                  <th>티커</th>
                  <th>회사명</th>
                  <th>거래소</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in helperResults" :key="item.stk_cd || item.cik">
                  <template v-if="store.selectedMarket === 'kr'">
                    <td><code>{{ item.stk_cd }}</code></td>
                    <td>{{ item.stk_nm }}</td>
                    <td>{{ item.market_type }}</td>
                  </template>
                  <template v-else>
                    <td><code>{{ item.cik }}</code></td>
                    <td><code>{{ item.latest_ticker }}</code></td>
                    <td>{{ item.latest_name || item.name || '-' }}</td>
                    <td>{{ item.exchange }}</td>
                  </template>
                  <td>
                    <button class="apply-badge-btn" @click="applyHelperCode(item)">
                      ⚡ 필터 적용
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else-if="hasSearchedHelper && !helperLoading" class="helper-no-results">
            검색 결과가 없습니다.
          </div>
          <div v-else class="helper-placeholder">
            우측 검색란에 티커 또는 종목명을 입력하여 검색해 주세요.
          </div>
        </div>

        <!-- 오른쪽: 입력 검색 (30%) -->
        <div class="helper-right-pane">
          <div class="helper-search-group">
            <label>검색어</label>
            <div class="helper-search-input-wrapper">
              <input 
                type="text" 
                v-model="helperSearchKeyword" 
                :placeholder="store.selectedMarket === 'kr' ? '예: 삼성전자, 005930' : '예: Apple, AAPL, 0000320193'" 
                @keyup.enter="searchHelperCodes"
                :disabled="helperLoading"
              />
              <button class="helper-btn search-trigger-btn" @click="searchHelperCodes" :disabled="helperLoading">
                <span v-if="helperLoading" class="spinner-mini"></span>
                검색
              </button>
            </div>
          </div>
          
          <div class="helper-filter-options">
            <div class="option-group match-type-group">
              <label>일치 방식</label>
              <div class="radio-options">
                <label>
                  <input type="radio" v-model="helperMatchType" value="contains" />
                  부분
                </label>
                <label>
                  <input type="radio" v-model="helperMatchType" value="exact" />
                  정확
                </label>
              </div>
            </div>
            
            <div class="option-group search-field-group">
              <label>검색 범위</label>
              <div class="radio-options">
                <label>
                  <input type="radio" v-model="helperSearchField" value="all" />
                  전체
                </label>
                <label>
                  <input type="radio" v-model="helperSearchField" value="code" />
                  코드
                </label>
                <label>
                  <input type="radio" v-model="helperSearchField" value="name" />
                  명칭
                </label>
              </div>
            </div>
          </div>
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
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)) 120px;
  gap: 16px;
  align-items: flex-end;
}

@media (max-width: 1024px) {
  .filter-grid {
    grid-template-columns: 1fr;
  }
  .filter-item.date-field {
    grid-column: span 1 !important;
    min-width: auto !important;
  }
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-item.date-field {
  grid-column: span 2;
  min-width: 320px;
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
  width: 100%;
  padding: 8px 12px;
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
  overflow: auto;
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
  background: #0f172a; /* 스크롤 시 뒤 데이터가 비쳐 겹쳐 보이지 않도록 불투명 어두운 배경 적용 */
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

/* 코드 헬퍼 스타일 추가 */
.code-helper-box {
  background: rgba(30, 41, 59, 0.25);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 12px 16px;
  margin-top: 14px;
  margin-bottom: 14px;
  font-size: 0.85rem;
}

.helper-header {
  margin-bottom: 8px;
}

.helper-title {
  font-weight: 600;
  color: #94a3b8;
  font-size: 0.82rem;
  letter-spacing: 0.5px;
}

.helper-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 코드 헬퍼 스타일 개편 */
.helper-layout {
  display: flex;
  gap: 16px;
  margin-top: 8px;
}

@media (max-width: 768px) {
  .helper-layout {
    flex-direction: column-reverse;
  }
}

.helper-left-pane {
  flex: 7;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.helper-right-pane {
  flex: 3;
  background: rgba(15, 23, 42, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 240px;
}

.helper-search-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.helper-search-group label {
  font-size: 0.78rem;
  color: #94a3b8;
  font-weight: 500;
}

.helper-search-input-wrapper {
  display: flex;
  width: 100%;
  gap: 6px;
}

.helper-search-input-wrapper input {
  flex: 1;
  min-width: 0;
  height: 32px !important;
  font-size: 0.8rem;
}

.helper-filter-options {
  display: flex;
  gap: 12px;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.match-type-group {
  flex: 2;
}

.search-field-group {
  flex: 3;
}

.option-group label {
  font-size: 0.78rem;
  color: #94a3b8;
  font-weight: 500;
}

.radio-options {
  display: flex;
  flex-direction: row;
  gap: 8px;
  flex-wrap: wrap;
}

.radio-options label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.78rem;
  color: #e2e8f0;
  cursor: pointer;
  font-weight: normal;
}

.radio-options input[type="radio"] {
  cursor: pointer;
  margin: 0;
  width: auto;
  height: auto;
}

.search-trigger-btn {
  width: 60px;
  flex-shrink: 0;
  justify-content: center;
  height: 32px !important;
  font-weight: 600;
  font-size: 0.8rem;
  padding: 0 8px;
}

.helper-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 150px;
  background: rgba(15, 23, 42, 0.15);
  border: 1px dashed rgba(255, 255, 255, 0.05);
  border-radius: 6px;
  color: #64748b;
  font-size: 0.8rem;
  font-style: italic;
}

.helper-results-scroll {
  max-height: 250px;
  overflow-y: auto;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.3);
}

.helper-results-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.8rem;
}

.helper-results-table th, 
.helper-results-table td {
  padding: 6px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.helper-results-table th {
  background: rgba(255, 255, 255, 0.04);
  color: #94a3b8;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 1;
}

.helper-results-table code {
  font-family: monospace;
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 4px;
  border-radius: 4px;
  color: #a5b4fc;
}

.apply-badge-btn {
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  border: 1px solid rgba(99, 102, 241, 0.3);
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.72rem;
  font-weight: 500;
  transition: all 0.2s;
}

.apply-badge-btn:hover {
  background: #4f46e5;
  color: #fff;
  border-color: #4f46e5;
}

.helper-no-results {
  color: #64748b;
  text-align: center;
  padding: 8px;
  font-style: italic;
}
</style>
