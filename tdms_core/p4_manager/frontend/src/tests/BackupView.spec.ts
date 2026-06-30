import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import BackupView from '../views/BackupView.vue'
import { useBackupStore } from '../stores/backupStore'

describe('BackupView.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('F-16: 서버 PC 환경일 경우, 서버 전용 경고 배너가 나타나고 백업 컨트롤이 비활성화된다', async () => {
    const store = useBackupStore()
    store.currentEnv = 'server'
    store.backups = []

    const wrapper = mount(BackupView)

    // 배너 검증
    expect(wrapper.text()).toContain('서버 PC 환경 (스냅샷 생성 비활성화)')
    expect(wrapper.text()).toContain('물리 스냅샷 직접 백업 및 복구 기능은 강제 비활성화')

    // 버튼 및 인풋 비활성화 검증
    const btn = wrapper.find('.btn-primary')
    expect(btn.element.getAttribute('disabled')).toBeDefined()

    const input = wrapper.find('input')
    expect(input.element.getAttribute('disabled')).toBeDefined()
  })

  it('F-11, F-12: 개발 PC 환경일 경우 백업 생성이 활성화되며 백업 이력이 테이블로 정상 렌더링되어야 한다', async () => {
    const store = useBackupStore()
    store.currentEnv = 'dev'
    store.backups = [
      {
        path: '/app/backups/kdms/manual/physical_checkpoint_kdms_20260610_113000.tar.gz',
        filename: 'physical_checkpoint_kdms_20260610_113000.tar.gz',
        market: 'kdms',
        tag: 'manual',
        created_at: '2026-06-10T11:30:00.000Z',
        size_bytes: 1048576, // 1.00 MB
        verified: true
      }
    ]

    const wrapper = mount(BackupView)

    // 개발 PC 환경 배너 검증
    expect(wrapper.text()).toContain('개발 PC 환경 (백업 허브 활성화)')
    expect(wrapper.text()).toContain('물리 볼륨 백업 및 복구를 수행할 수 있습니다')

    // 백업 생성 버튼 활성화 검증
    const btn = wrapper.find('.btn-primary')
    expect(btn.element.getAttribute('disabled')).toBeNull()

    // 백업 이력 테이블 렌더링 검증
    expect(wrapper.text()).toContain('physical_checkpoint_kdms_20260610_113000.tar.gz')
    expect(wrapper.text()).toContain('KDMS')
    expect(wrapper.text()).toContain('manual')
    expect(wrapper.text()).toContain('1 MB')
    expect(wrapper.text()).toContain('Verified')
    expect(wrapper.text()).toContain('복구 실행')
  })

  it('F-19: 복구 모달에서 이중 안전장치 검증 및 StartupValidator 진단 리포트 표시 검증', async () => {
    const store = useBackupStore()
    store.currentEnv = 'dev'
    store.backups = [
      {
        path: '/app/backups/kdms/manual/physical_checkpoint_kdms_20260610_113000.tar.gz',
        filename: 'physical_checkpoint_kdms_20260610_113000.tar.gz',
        market: 'kdms',
        tag: 'manual',
        created_at: '2026-06-10T11:30:00.000Z',
        size_bytes: 1048576,
        verified: true
      }
    ]

    // restoreBackup 스토어 액션 모킹 및 Spy 지정
    const mockValidationResults = {
      kdms: {
        is_healthy: true,
        is_connected: true,
        missing_tables: [],
        low_row_tables: {},
        hypertable_ok: true
      }
    }
    
    vi.spyOn(store, 'restoreBackup').mockResolvedValue({
      status: 'success',
      validation_results: mockValidationResults
    })

    const wrapper = mount(BackupView)

    // 1. 복구 실행 버튼 클릭하여 모달 팝업
    const restoreBtn = wrapper.find('.btn-restore')
    expect(restoreBtn.element.getAttribute('disabled')).toBeNull()
    await restoreBtn.trigger('click')

    // 모달 표시 확인
    expect(wrapper.text()).toContain('로컬 DB 물리 볼륨 복구')
    expect(wrapper.find('.modal-backdrop').exists()).toBe(true)

    // 2. 이중 승인 입력 비정합 시 복구 실행 버튼 비활성화 검증
    const confirmInput = wrapper.find('#confirm-input')
    const confirmBtn = wrapper.find('#confirm-btn')
    
    await confirmInput.setValue('RESTORE DB')
    expect(confirmBtn.element.getAttribute('disabled')).toBeDefined()

    // 3. 정확한 안전 장치 텍스트 입력 시 활성화 및 실행 검증
    await confirmInput.setValue('RESTORE LOCAL DB')
    expect(confirmBtn.element.getAttribute('disabled')).toBeNull()

    // 4. 복구 실행
    await confirmBtn.trigger('click')
    expect(store.restoreBackup).toHaveBeenCalledWith('kdms', 'manual', 'physical_checkpoint_kdms_20260610_113000.tar.gz', 'RESTORE LOCAL DB')

    // 5. 복구 성공 직후 StartupValidator 자가 진단 결과 리포트 표시 검증
    expect(wrapper.text()).toContain('DB 정합성 자가 진단 결과 리포트 (StartupValidator)')
    expect(wrapper.text()).toContain('KDMS (TimescaleDB)')
    
    // USDMS는 리포트에 미포함이므로 비렌더링 검증
    expect(wrapper.text()).not.toContain('USDMS (TimescaleDB)')
    
    // KDMS 정상 렌더링 확인
    expect(wrapper.text()).toContain('연결 성공')
    expect(wrapper.text()).toContain('정상 (Healthy)')
  })
})
