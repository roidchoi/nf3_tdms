import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/api/http'

export interface TableMeta {
  table: string
  name: string
}

export interface PreviewMetadata {
  kr: TableMeta[]
  us: TableMeta[]
}

export interface PreviewResponse {
  offline: boolean
  table: string
  count: number
  data: any[]
  message?: string
  applied_quarter?: string
}

export const useExplorerStore = defineStore('explorer', () => {
  const metadata = ref<PreviewMetadata>({ kr: [], us: [] })
  const selectedMarket = ref<'kr' | 'us'>('kr')
  const selectedTable = ref<string>('')
  
  const stkCd = ref<string>('')
  const startDate = ref<string>('')
  const endDate = ref<string>('')
  const quarter = ref<string>('')
  const marketFilter = ref<string>('')
  const limit = ref<number>(50)
  const offset = ref<number>(0)
  
  const loading = ref<boolean>(false)
  const isOffline = ref<boolean>(false)
  const tableData = ref<any[]>([])
  const totalCount = ref<number>(0)
  const errorMessage = ref<string>('')

  // 1. 테이블 메타데이터 로드
  const fetchMetadata = async () => {
    try {
      const resp = await http.get<PreviewMetadata>('/preview/meta')
      metadata.value = resp.data
      
      // 기본 테이블 설정 (selectedTable이 비어있을 경우)
      if (!selectedTable.value && resp.data[selectedMarket.value]?.length > 0) {
        selectedTable.value = resp.data[selectedMarket.value][0].table
      }
    } catch (err: any) {
      errorMessage.value = err.message || '메타데이터 로드 실패'
    }
  }

  // 2. 미리보기 데이터 조회
  const fetchPreviewData = async () => {
    if (!selectedTable.value) return
    
    loading.value = true
    isOffline.value = false
    errorMessage.value = ''
    
    try {
      const params: Record<string, any> = {
        limit: limit.value,
        offset: offset.value
      }
      if (stkCd.value.trim()) {
        params.stk_cd = stkCd.value.trim()
      }
      if (startDate.value) {
        params.start_date = startDate.value
      }
      if (endDate.value) {
        params.end_date = endDate.value
      }
      if (quarter.value.trim()) {
        params.quarter = quarter.value.trim()
      }
      if (marketFilter.value.trim()) {
        params.market_filter = marketFilter.value.trim()
      }

      const resp = await http.get<PreviewResponse>(
        `/preview/${selectedMarket.value}/${selectedTable.value}`,
        { params }
      )
      
      const resData = resp.data
      if (resData.offline) {
        isOffline.value = true
        tableData.value = []
        totalCount.value = 0
        errorMessage.value = resData.message || '하위 백엔드가 오프라인 상태입니다.'
      } else {
        tableData.value = resData.data || []
        totalCount.value = resData.count || 0
        if (resData.applied_quarter) {
          if (selectedTable.value === 'minute_target_history' && stkCd.value.trim() && !quarter.value.trim()) {
            // 종목코드가 있고 분기가 빈 상태에서 여러 분기를 보려 할 때는 덮어쓰지 않음
          } else {
            quarter.value = resData.applied_quarter
          }
        }
      }
    } catch (err: any) {
      isOffline.value = true
      tableData.value = []
      totalCount.value = 0
      errorMessage.value = err.message || '통신 오류가 발생했습니다.'
    } finally {
      loading.value = false
    }
  }

  // 3. 필터 리셋
  const resetFilters = () => {
    stkCd.value = ''
    startDate.value = ''
    endDate.value = ''
    quarter.value = ''
    marketFilter.value = ''
    offset.value = 0
  }

  // 3.5 테이블별 기본 필터 주입
  const applyDefaultFiltersForTable = (table: string) => {
    resetFilters()
    
    const today = new Date()
    const todayStr = today.toISOString().split('T')[0]
    
    const oneMonthAgo = new Date()
    oneMonthAgo.setDate(oneMonthAgo.getDate() - 30)
    const oneMonthAgoStr = oneMonthAgo.toISOString().split('T')[0]
    
    const threeDaysAgo = new Date()
    threeDaysAgo.setDate(threeDaysAgo.getDate() - 3)
    const threeDaysAgoStr = threeDaysAgo.toISOString().split('T')[0]

    if (selectedMarket.value === 'kr') {
      if (table === 'stock_info') {
        marketFilter.value = ''
      } else if (table === 'daily_ohlcv' || table === 'daily_ohlcv_adjusted' || table === 'daily_market_cap' || table === 'daily_investor_trade') {
        stkCd.value = '005930'
        startDate.value = oneMonthAgoStr
        endDate.value = todayStr
      } else if (table === 'minute_ohlcv') {
        stkCd.value = '005930'
        startDate.value = threeDaysAgoStr
        endDate.value = todayStr
      } else if (table === 'financial_statements' || table === 'financial_ratios') {
        stkCd.value = '005930'
      } else if (table === 'price_adjustment_factors') {
        stkCd.value = '005930'
        startDate.value = oneMonthAgoStr
        endDate.value = todayStr
      } else if (table === 'minute_target_history') {
        quarter.value = ''
        marketFilter.value = 'KOSPI'
      } else if (table === 'trading_calendar' || table === 'system_milestones') {
        startDate.value = oneMonthAgoStr
        endDate.value = todayStr
      }
    } else if (selectedMarket.value === 'us') {
      if (table === 'us_ticker_master') {
        marketFilter.value = ''
      } else if (table === 'us_daily_price') {
        stkCd.value = 'AAPL'
        startDate.value = oneMonthAgoStr
        endDate.value = todayStr
      } else if (table === 'us_price_adjustment_factors') {
        stkCd.value = 'AAPL'
        startDate.value = oneMonthAgoStr
        endDate.value = todayStr
      } else if (table === 'us_financial_facts' || table === 'us_standard_financials' || table === 'us_share_history' || table === 'us_financial_metrics') {
        stkCd.value = '0000320193'
      } else if (table === 'us_daily_valuation') {
        stkCd.value = '0000320193'
        const sixMonthsAgo = new Date()
        sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6)
        startDate.value = sixMonthsAgo.toISOString().split('T')[0]
        endDate.value = todayStr
      } else if (table === 'us_ticker_history' || table === 'us_collection_blacklist') {
        startDate.value = oneMonthAgoStr
        endDate.value = todayStr
      }
    }
  }

  // 4. 시장 선택 전환
  const setMarket = (market: 'kr' | 'us') => {
    selectedMarket.value = market
    
    const tables = metadata.value[market] || []
    if (tables.length > 0) {
      selectedTable.value = tables[0].table
      applyDefaultFiltersForTable(tables[0].table)
    } else {
      selectedTable.value = ''
      resetFilters()
    }
    tableData.value = []
    totalCount.value = 0
  }

  return {
    metadata,
    selectedMarket,
    selectedTable,
    stkCd,
    startDate,
    endDate,
    quarter,
    marketFilter,
    limit,
    offset,
    loading,
    isOffline,
    tableData,
    totalCount,
    errorMessage,
    fetchMetadata,
    fetchPreviewData,
    resetFilters,
    applyDefaultFiltersForTable,
    setMarket
  }
})
