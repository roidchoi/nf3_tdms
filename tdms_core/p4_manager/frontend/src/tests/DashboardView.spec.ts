import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import DashboardView from '../views/DashboardView.vue'
import { useStatusStore } from '../stores/statusStore'

describe('DashboardView.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('F-5: 스토어에 바인딩된 KR/US 백엔드의 온라인 상태가 정상 렌더링되어야 한다', async () => {
    const store = useStatusStore()
    
    // 모킹 데이터 설정
    store.status = {
      kr: {
        status: 'ONLINE',
        freshness: {
          status: 'GREEN',
          latest_trading_date: '2026-06-08',
          daily_coverage_ratio: 0.995,
          is_daily_fresh: true
        },
        tasks: {
          daily_update: { is_running: false, last_run_time: '2026-06-08T17:05:00', last_status: 'success' },
          financial_update: { is_running: false, last_run_time: '2026-06-08T17:05:00', last_status: 'success' }
        }
      },
      us: {
        status: 'OFFLINE',
        freshness: null,
        tasks: {}
      }
    }

    const wrapper = mount(DashboardView)

    // KR 온라인 상태 검증
    expect(wrapper.text()).toContain('한국 시장 (KDMS)')
    expect(wrapper.text()).toContain('ONLINE')
    expect(wrapper.text()).toContain('99.5%')
    expect(wrapper.text()).toContain('2026-06-08')

    // US 오프라인 상태 검증
    expect(wrapper.text()).toContain('미국 시장 (USDMS)')
    expect(wrapper.text()).toContain('OFFLINE')
    expect(wrapper.text()).toContain('오프라인 상태이거나 정보를 가져올 수 없습니다')
  })
})
