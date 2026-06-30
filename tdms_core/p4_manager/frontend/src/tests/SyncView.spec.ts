import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import SyncView from '../views/SyncView.vue'
import { useSyncStore } from '../stores/syncStore'
import { useBackupStore } from '../stores/backupStore'

describe('SyncView.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('T-010-UI-1: 서버 PC 환경일 경우, 데이터 유입 차단 경고 배너가 보이고 밀어넣기(PUSH)가 차단된다', async () => {
    const backupStore = useBackupStore()
    const syncStore = useSyncStore()
    backupStore.currentEnv = 'server'
    syncStore.syncStatus = 'IDLE'

    const wrapper = mount(SyncView)

    // 서버 경고 배너 검증
    expect(wrapper.text()).toContain('서버 PC 환경 (데이터 유입 차단)')
    expect(wrapper.text()).toContain('외부 개발 PC로부터 수신되는 쓰기 동기화(PUSH TO SERVER) 동작은')

    // PUSH 라디오 및 실행 비활성화 검증
    const pushRadio = wrapper.find('input[value="push"]')
    expect(pushRadio.element.getAttribute('disabled')).toBeDefined()
  })

  it('T-010-UI-2: 개발 PC 환경일 경우, 피어 동기화 배너가 보이고 PUSH/PULL 모두 선택 가능하다', async () => {
    const backupStore = useBackupStore()
    const syncStore = useSyncStore()
    backupStore.currentEnv = 'dev'
    syncStore.syncStatus = 'IDLE'

    const wrapper = mount(SyncView)

    expect(wrapper.text()).toContain('개발 PC 환경 (피어 동기화 기동 활성화)')
    expect(wrapper.text()).toContain('가져오기 (PULL FROM SERVER)')

    const pushRadio = wrapper.find('input[value="push"]')
    expect(pushRadio.element.getAttribute('disabled')).toBeNull()
  })

  it('T-010-UI-3: 네트워크 및 피어 설정에서 자동 탐색, 연결 검증, .env 반영 동작이 트리거된다', async () => {
    const backupStore = useBackupStore()
    const syncStore = useSyncStore()
    backupStore.currentEnv = 'dev'
    syncStore.syncStatus = 'IDLE'

    // 스토어 액션 모킹
    vi.spyOn(syncStore, 'testConnection').mockResolvedValue({ connected: true, message: 'Connected to 192.168.35.10' })
    vi.spyOn(syncStore, 'detectServerIp').mockResolvedValue({ server_ip: '192.168.35.10', method: 'scan' })
    vi.spyOn(syncStore, 'syncIp').mockResolvedValue({ status: 'success', message: 'Sync successful' })

    const wrapper = mount(SyncView)

    // 1. 서버 IP 자동 탐색 클릭 검증
    const detectBtn = wrapper.findAll('button').find(b => b.text().includes('서버 IP 자동 탐색'))
    expect(detectBtn).toBeDefined()
    await detectBtn?.trigger('click')
    expect(syncStore.detectServerIp).toHaveBeenCalled()

    // 2. IP 인풋 바인딩 검증 (detect 완료 후 자동으로 input에 값 세팅)
    const ipInput = wrapper.find('#peer-ip')
    expect((ipInput.element as HTMLInputElement).value).toBe('192.168.35.10')

    // 3. 연결 검증 테스트 클릭 검증
    const testBtn = wrapper.findAll('button').find(b => b.text().includes('연결 검증 테스트'))
    expect(testBtn).toBeDefined()
    await testBtn?.trigger('click')
    expect(syncStore.testConnection).toHaveBeenCalledWith('192.168.35.10', 8000)

    // 4. .env 파일 반영 클릭 검증
    const envBtn = wrapper.findAll('button').find(b => b.text().includes('.env 파일에 반영'))
    expect(envBtn).toBeDefined()
    await envBtn?.trigger('click')
    expect(syncStore.syncIp).toHaveBeenCalledWith('server', '192.168.35.10')
  })

  it('T-010-UI-4: 동기화 기동 시 이중 확인 컨펌 모달이 노출되며 문구 검증 통과 후 기동된다', async () => {
    const backupStore = useBackupStore()
    const syncStore = useSyncStore()
    backupStore.currentEnv = 'dev'
    syncStore.syncStatus = 'IDLE'

    vi.spyOn(syncStore, 'startSync').mockResolvedValue({ status: 'success', message: 'Sync started' })

    const wrapper = mount(SyncView)

    // 1. 모달 팝업 트리거
    const startBtn = wrapper.find('#start-sync-btn')
    await startBtn.trigger('click')

    // 모달 노출 검증
    expect(wrapper.find('.modal-backdrop').exists()).toBe(true)
    expect(wrapper.text()).toContain('물리 볼륨 동기화 덮어쓰기 경고')

    // 2. 오타 입력 시 실행 버튼 비활성화 검증
    const confirmInput = wrapper.find('#sync-confirm-input')
    const confirmBtn = wrapper.find('#confirm-sync-btn')
    
    await confirmInput.setValue('PULL')
    expect(confirmBtn.element.getAttribute('disabled')).toBeDefined()

    // 3. 정확한 텍스트 입력 시 활성화 및 실행 검증
    await confirmInput.setValue('PULL FROM SERVER')
    expect(confirmBtn.element.getAttribute('disabled')).toBeNull()

    await confirmBtn.trigger('click')
    expect(syncStore.startSync).toHaveBeenCalledWith('kdms', 'pull', 'PULL FROM SERVER')

    // 모달 닫힘 검증
    expect(wrapper.find('.modal-backdrop').exists()).toBe(false)
  })
})
