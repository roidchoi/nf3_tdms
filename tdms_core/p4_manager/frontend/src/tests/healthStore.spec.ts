import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useHealthStore } from '@/stores/healthStore'

describe('healthStore Pinia Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn())
  })

  it('fetchFreshness should retrieve status data correctly', async () => {
    const mockData = { status: 'GREEN', latest_trading_date: '2026-06-09', total_active_stocks: 2500 }
    
    // fetch 모킹
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => mockData
    } as Response)

    const store = useHealthStore()
    await store.fetchFreshness('kr')

    expect(store.krFreshness).toEqual(mockData)
    expect(fetch).toHaveBeenCalledWith('/api/mgr/health/freshness/kr')
  })

  it('fetchFreshness should handle HTTP fetch failure and fallback to RED offline status', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('Network Error'))

    const store = useHealthStore()
    await store.fetchFreshness('us')

    expect(store.usFreshness?.status).toBe('RED')
    expect(store.usFreshness?.offline).toBe(true)
  })

  it('fetchBlacklist should retrieve US blacklist items correctly', async () => {
    const mockBlacklist = {
      status: 'success',
      blocked_count: 1,
      blacklist: [
        {
          cik: '0000320193',
          ticker: 'AAPL',
          reason_cd: 'SEC_TIMEOUT',
          detail: 'Failed 3 times',
          is_blocked: true
        }
      ]
    }

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => mockBlacklist
    } as Response)

    const store = useHealthStore()
    await store.fetchBlacklist()

    expect(store.blacklist).toHaveLength(1)
    expect(store.blacklist[0].ticker).toBe('AAPL')
    expect(store.blacklistOffline).toBe(false)
  })

  it('releaseBlacklist should send POST request and trigger refresh', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true } as Response) // release api
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ blacklist: [], offline: false })
      } as Response) // fetchBlacklist api refresh

    const store = useHealthStore()
    await store.releaseBlacklist('0000320193')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/mgr/health/us/blacklist/0000320193/release', { method: 'POST' })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/mgr/health/us/blacklist')
  })
})
