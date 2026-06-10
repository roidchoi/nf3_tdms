import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import BackupView from '../views/BackupView.vue'
import { useBackupStore } from '../stores/backupStore'

describe('BackupView.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // fetch API 호출 모킹
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('F-16: 서버 PC 환경일 경우, 서버 전용 경고 배너가 나타나고 백업 컨트롤이 비활성화된다', async () => {
    const store = useBackupStore()
    store.currentEnv = 'server'
    store.backups = []

    const wrapper = mount(BackupView)

    // 배너 검증
    expect(wrapper.text()).toContain('서버 PC 환경 (스냅샷 생성 비활성화)')
    expect(wrapper.text()).toContain('물리 스냅샷 직접 백업 기능은 강제 비활성화')

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
        path: '/app/backups/manual/physical_checkpoint_20260610_113000.tar.gz',
        filename: 'physical_checkpoint_20260610_113000.tar.gz',
        tag: 'manual',
        created_at: '2026-06-10T11:30:00.000Z',
        size_bytes: 1048576, // 1.00 MB
        verified: true
      }
    ]

    const wrapper = mount(BackupView)

    // 개발 PC 환경 배너 검증
    expect(wrapper.text()).toContain('개발 PC 환경 (백업 허브 활성화)')
    expect(wrapper.text()).toContain('물리 볼륨 백업을 생성할 수 있습니다')

    // 백업 생성 버튼 활성화 검증
    const btn = wrapper.find('.btn-primary')
    expect(btn.element.getAttribute('disabled')).toBeNull()

    // 백업 이력 테이블 렌더링 검증
    expect(wrapper.text()).toContain('physical_checkpoint_20260610_113000.tar.gz')
    expect(wrapper.text()).toContain('manual')
    expect(wrapper.text()).toContain('1 MB') // 1.00 MB
    expect(wrapper.text()).toContain('Verified')
  })
})
