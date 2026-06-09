import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import TaskStatusCard from '../components/dashboard/TaskStatusCard.vue'
import { useStatusStore } from '../stores/statusStore'

describe('TaskStatusCard.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('F-1: 기본 상태와 정보들이 올바르게 렌더링되어야 한다', () => {
    const wrapper = mount(TaskStatusCard, {
      props: {
        market: 'kr',
        taskId: 'daily_update',
        title: '일일 업데이트',
        icon: '📅',
        status: { is_running: false, last_run_time: '2026-06-08T17:05:00', last_status: 'success' }
      }
    })

    expect(wrapper.text()).toContain('일일 업데이트')
    expect(wrapper.text()).toContain('📅')
    expect(wrapper.text()).toContain('완료됨')
    expect(wrapper.text()).toContain('success')
  })

  it('F-2: 테스트 모드 토글 Switch UI 조작이 가능해야 한다', async () => {
    const wrapper = mount(TaskStatusCard, {
      props: {
        market: 'kr',
        taskId: 'daily_update',
        title: '일일 업데이트',
        icon: '📅',
        status: { is_running: false, last_run_time: null, last_status: 'none' }
      }
    })

    const checkbox = wrapper.find('input[type="checkbox"]')
    expect((checkbox.element as HTMLInputElement).checked).toBe(true) // 기본값 true

    await checkbox.setValue(false)
    expect((checkbox.element as HTMLInputElement).checked).toBe(false)
  })

  it('F-3: 정규 거래 시간 중 운영 모드로 즉시 실행 시 window.confirm 경고창이 나타나야 한다', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => false)
    
    // 장 운영시간으로 임시 고정 (11:30)
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 5, 9, 11, 30))

    const wrapper = mount(TaskStatusCard, {
      props: {
        market: 'kr',
        taskId: 'daily_update',
        title: '일일 업데이트',
        icon: '📅',
        status: { is_running: false, last_run_time: null, last_status: 'none' }
      }
    })

    // 테스트 모드 해제 (운영 모드)
    const checkbox = wrapper.find('input[type="checkbox"]')
    await checkbox.setValue(false)

    // 즉시 실행 클릭
    const runBtn = wrapper.find('.run-btn')
    await runBtn.trigger('click')

    expect(confirmSpy).toHaveBeenCalled()
    expect(confirmSpy.mock.calls[0][0]).toContain('장중 거래 시간입니다')

    vi.useRealTimers()
    confirmSpy.mockRestore()
  })

  it('F-4: 실행 버튼 클릭 시 statusStore.runTask가 호출되어야 한다', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => true)
    const store = useStatusStore()
    const runTaskSpy = vi.spyOn(store, 'runTask').mockResolvedValue({ status: 'success' })

    const wrapper = mount(TaskStatusCard, {
      props: {
        market: 'us', // 미국 시장
        taskId: 'daily_routine',
        title: 'Daily Routine',
        icon: '🇺🇸',
        status: { is_running: false, last_run_time: null, last_status: 'none' }
      }
    })

    const runBtn = wrapper.find('.run-btn')
    await runBtn.trigger('click')

    expect(confirmSpy).toHaveBeenCalled()
    expect(runTaskSpy).toHaveBeenCalledWith('us', 'daily_routine', false)

    confirmSpy.mockRestore()
    runTaskSpy.mockRestore()
  })
})
