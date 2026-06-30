import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import ExplorerView from '../views/ExplorerView.vue'
import { useExplorerStore } from '../stores/explorerStore'

describe('ExplorerView.vue Component Test', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('F-1: 메타데이터에 있는 테이블 옵션들이 셀렉트 박스에 렌더링되어야 한다', async () => {
    const store = useExplorerStore()
    
    // 모킹 데이터 바인딩
    store.metadata = {
      kr: [
        { table: 'stock_info', name: '종목 정보' },
        { table: 'daily_ohlcv', name: '일봉 시세' }
      ],
      us: []
    }
    store.selectedMarket = 'kr'
    store.selectedTable = 'stock_info'

    const wrapper = mount(ExplorerView)

    const select = wrapper.find('select#table-select')
    expect(select.exists()).toBe(true)
    
    const options = select.findAll('option')
    expect(options).toHaveLength(2)
    expect(options[0].text()).toContain('종목 정보')
    expect(options[1].text()).toContain('일봉 시세')
  })

  it('F-2: 로딩 상태일 때 스켈레톤 로더가 화면에 렌더링되어야 한다', async () => {
    const store = useExplorerStore()
    store.loading = true
    store.tableData = []

    const wrapper = mount(ExplorerView)

    expect(wrapper.find('.skeleton-wrapper').exists()).toBe(true)
    expect(wrapper.find('.data-table').exists()).toBe(false)
  })

  it('F-3: 조회 성공 시 동적 헤더 및 데이터 셀들이 정확히 테이블 형태로 렌더링되어야 한다', async () => {
    const store = useExplorerStore()
    store.loading = false
    store.isOffline = false
    store.tableData = [
      { stk_cd: '005930', stk_nm: '삼성전자', price: 72000 }
    ]
    store.totalCount = 1

    const wrapper = mount(ExplorerView)

    const table = wrapper.find('.data-table')
    expect(table.exists()).toBe(true)

    // 헤더 검증
    const ths = table.findAll('th')
    expect(ths).toHaveLength(3)
    expect(ths[0].text()).toBe('stk_cd')
    expect(ths[1].text()).toBe('stk_nm')
    expect(ths[2].text()).toBe('price')

    // 데이터 행 검증
    const tds = table.findAll('td')
    expect(tds).toHaveLength(3)
    expect(tds[0].text()).toBe('005930')
    expect(tds[1].text()).toBe('삼성전자')
    expect(tds[2].text()).toBe('72000')
  })

  it('F-4: 백엔드가 오프라인 상태일 때 장애 격리 에러 배너가 노출되어야 한다', async () => {
    const store = useExplorerStore()
    store.loading = false
    store.isOffline = true
    store.errorMessage = 'KDMS connection timeout'
    store.tableData = []

    const wrapper = mount(ExplorerView)

    const errorState = wrapper.find('.error-state')
    expect(errorState.exists()).toBe(true)
    expect(errorState.text()).toContain('통신 실패')
    expect(errorState.text()).toContain('장애 격리')
    expect(errorState.text()).toContain('KDMS connection timeout')
  })
})
