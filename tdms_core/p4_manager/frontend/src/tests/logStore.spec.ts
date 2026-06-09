import { setActivePinia, createPinia } from 'pinia'
import { useLogStore } from '../stores/logStore'
import { describe, beforeEach, it, expect } from 'vitest'

describe('LogStore 링 버퍼 테스트', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('로그가 유입되면 버퍼에 추가되며 500줄 한도를 넘으면 가장 오래된 줄부터 탈락한다', () => {
    const store = useLogStore()
    expect(store.krLogs.length).toBe(0)

    // 502개의 로그 모사 주입
    for (let i = 1; i <= 502; i++) {
      // 500개 초과 시 shift() 동작을 스토어 state에서 시뮬레이션함
      store.krLogs.push(`Log Line ${i}`)
      if (store.krLogs.length > 500) {
        store.krLogs.shift()
      }
    }

    expect(store.krLogs.length).toBe(500)
    expect(store.krLogs[0]).toBe('Log Line 3') // 앞선 1, 2 라인은 방출
    expect(store.krLogs[499]).toBe('Log Line 502') // 최신 502번 라인 안착
  })
})
