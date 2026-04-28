<script setup lang="ts">
import { onMounted, onUnmounted, computed, watch } from 'vue'
import { useAdminStore } from '@/stores/adminStore'
import TaskStatusCard from '@/components/dashboard/TaskStatusCard.vue'
import LogTerminal from '@/components/dashboard/LogTerminal.vue'
import type { ScheduleItem } from '@/types/admin'

const adminStore = useAdminStore()
let intervalId: ReturnType<typeof setInterval> | null = null

// [수정] 스케줄 목록을 Map 형태로 변환 (반응성 강화 및 조회 성능 O(1) 최적화)
// 배열을 순회하는 대신, task_id를 키(Key)로 하는 객체를 만들어 템플릿에서 즉시 접근합니다.
const scheduleMap = computed(() => {
  const map: Record<string, ScheduleItem> = {}
  if (adminStore.schedules && adminStore.schedules.length > 0) {
    adminStore.schedules.forEach(s => {
      map[s.task_id] = s
    })
  }
  return map
})

// [디버깅] 스케줄 데이터가 들어오는지 감시
watch(() => adminStore.schedules, (newVal) => {
  console.log('[Dashboard] 스케줄 데이터 수신:', newVal)
}, { deep: true })

onMounted(async () => {
  // 1. 데이터 초기 로드 (순서 보장)
  await adminStore.fetchJobStatuses()
  await adminStore.fetchSchedules() // 스케줄 정보 로드
  
  adminStore.connectWebSocket()

  // 2. 주기적 폴링
  intervalId = setInterval(() => {
    adminStore.fetchJobStatuses()
  }, 2000)
})

onUnmounted(() => {
  adminStore.disconnectWebSocket()
  if (intervalId) clearInterval(intervalId)
})
</script>

<template>
  <div class="dashboard">
    <div class="task-grid">
      <TaskStatusCard
        title="일일 데이터 업데이트"
        taskId="daily_update"
        icon="📅"
        :status="adminStore.statuses.daily_update"
        :schedule="scheduleMap['daily_update']" 
      />
      <TaskStatusCard
        title="재무정보 수집 (PIT)"
        taskId="financial_update"
        icon="💰"
        :status="adminStore.statuses.financial_update"
        :schedule="scheduleMap['financial_update']"
      />
      
      <TaskStatusCard
        title="분봉 백필 (Backfill)"
        taskId="backfill_minute_data"
        icon="⏱️"
        :status="adminStore.statuses.backfill_minute_data"
        :schedule="scheduleMap['backfill_minute_data']"
      />
    </div>

    <div class="log-section">
      <LogTerminal />
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 1.5rem;
}

.log-section {
  height: 500px;
}
</style>