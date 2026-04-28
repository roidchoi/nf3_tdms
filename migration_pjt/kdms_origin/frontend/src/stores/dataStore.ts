// src/stores/dataStore.ts
import { defineStore } from 'pinia'
import http from '@/api/http'
import type { AxiosError } from 'axios' // [추가] 에러 타입
import type { DataPreviewParams, TableRow } from '@/types/data' // [추가] 데이터 타입

export const useDataStore = defineStore('data', {
  state: () => ({
    tables: [
      "daily_ohlcv", "minute_ohlcv", "financial_statements", 
      "financial_ratios", "stock_info", "price_adjustment_factors",
      "minute_target_history", "system_milestones", "trading_calendar"
    ],
    currentTable: 'daily_ohlcv',
    // [수정] any[] -> TableRow[]
    previewData: [] as TableRow[],
    isLoading: false,
    error: null as string | null
  }),

  actions: {
    // [수정] params: any -> params: DataPreviewParams
    async fetchPreview(tableName: string, params: DataPreviewParams) {
      this.isLoading = true
      this.error = null
      this.currentTable = tableName
      
      try {
        // 응답 데이터의 제네릭 타입 지정
        const response = await http.get<{ data: TableRow[] }>(`/data/preview/${tableName}`, { params })
        this.previewData = response.data.data
      } catch (error) {
        // [수정] catch (err: any) -> catch (error) 후 타입 단언 사용
        const err = error as AxiosError<{ detail: string }>;
        
        console.error('Preview fetch failed:', err)
        // AxiosError 구조에 맞춰 안전하게 접근
        this.error = err.response?.data?.detail || err.message || '데이터 조회 실패'
        this.previewData = []
      } finally {
        this.isLoading = false
      }
    }
  }
})