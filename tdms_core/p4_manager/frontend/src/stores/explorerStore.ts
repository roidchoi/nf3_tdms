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
}

export const useExplorerStore = defineStore('explorer', () => {
  const metadata = ref<PreviewMetadata>({ kr: [], us: [] })
  const selectedMarket = ref<'kr' | 'us'>('kr')
  const selectedTable = ref<string>('')
  
  const stkCd = ref<string>('')
  const startDate = ref<string>('')
  const endDate = ref<string>('')
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
    offset.value = 0
  }

  // 4. 시장 선택 전환
  const setMarket = (market: 'kr' | 'us') => {
    selectedMarket.value = market
    resetFilters()
    
    const tables = metadata.value[market] || []
    if (tables.length > 0) {
      selectedTable.value = tables[0].table
    } else {
      selectedTable.value = ''
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
    setMarket
  }
})
