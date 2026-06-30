import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useExplorerStore } from '@/stores/explorerStore'
import http from '@/api/http'

vi.mock('@/api/http', () => {
  return {
    default: {
      get: vi.fn()
    }
  }
})

describe('explorerStore Pinia Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('fetchMetadata should retrieve metadata and set default table', async () => {
    const mockMetadata = {
      kr: [
        { table: 'stock_info', name: '종목 정보' }
      ],
      us: [
        { table: 'us_ticker_master', name: '미국 티커 정보' }
      ]
    }

    vi.mocked(http.get).mockResolvedValueOnce({ data: mockMetadata })

    const store = useExplorerStore()
    await store.fetchMetadata()

    expect(store.metadata).toEqual(mockMetadata)
    expect(store.selectedTable).toBe('stock_info')
    expect(http.get).toHaveBeenCalledWith('/preview/meta')
  })

  it('fetchPreviewData should fetch preview data successfully', async () => {
    const mockResponse = {
      offline: false,
      table: 'stock_info',
      count: 2,
      data: [{ stk_cd: '005930' }, { stk_cd: '000660' }]
    }

    vi.mocked(http.get).mockResolvedValueOnce({ data: mockResponse })

    const store = useExplorerStore()
    store.selectedTable = 'stock_info'
    store.selectedMarket = 'kr'
    store.stkCd = '005930'
    store.startDate = '2026-06-01'
    store.endDate = '2026-06-10'
    store.limit = 10
    store.offset = 0

    await store.fetchPreviewData()

    expect(store.tableData).toEqual(mockResponse.data)
    expect(store.totalCount).toBe(2)
    expect(store.isOffline).toBe(false)
    expect(http.get).toHaveBeenCalledWith('/preview/kr/stock_info', {
      params: {
        limit: 10,
        offset: 0,
        stk_cd: '005930',
        start_date: '2026-06-01',
        end_date: '2026-06-10'
      }
    })
  })

  it('fetchPreviewData should handle offline fallback correctly', async () => {
    const mockOfflineResponse = {
      offline: true,
      table: 'stock_info',
      count: 0,
      data: [],
      message: 'KDMS offline'
    }

    vi.mocked(http.get).mockResolvedValueOnce({ data: mockOfflineResponse })

    const store = useExplorerStore()
    store.selectedTable = 'stock_info'
    store.selectedMarket = 'kr'

    await store.fetchPreviewData()

    expect(store.tableData).toEqual([])
    expect(store.totalCount).toBe(0)
    expect(store.isOffline).toBe(true)
    expect(store.errorMessage).toBe('KDMS offline')
  })

  it('setMarket should reset filters and switch default table', async () => {
    const mockMetadata = {
      kr: [
        { table: 'stock_info', name: '종목 정보' }
      ],
      us: [
        { table: 'us_ticker_master', name: '미국 티커 정보' }
      ]
    }

    const store = useExplorerStore()
    store.metadata = mockMetadata
    store.selectedMarket = 'kr'
    store.selectedTable = 'stock_info'
    store.stkCd = '005930'

    store.setMarket('us')

    expect(store.selectedMarket).toBe('us')
    expect(store.stkCd).toBe('')
    expect(store.selectedTable).toBe('us_ticker_master')
  })
})
