<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useAdminStore } from '@/stores/adminStore'
import type { ScheduleItem, CronConfig } from '@/types/admin'
import ScheduleModal from '@/components/schedule/ScheduleModal.vue'

const adminStore = useAdminStore()

// 모달 상태
const isModalOpen = ref(false)
const isEditMode = ref(false)
const selectedSchedule = ref<ScheduleItem | null>(null)

onMounted(() => {
  adminStore.fetchSchedules()
})

// [수정] 정렬 기준: 다음 실행 시간(next_run) 오름차순
// 실행 예정인 것이 위로, 일시정지된(next_run이 null) 것은 아래로
const sortedSchedules = computed(() => {
  return [...adminStore.schedules].sort((a, b) => {
    if (!a.next_run) return 1  // a가 일시정지면 뒤로
    if (!b.next_run) return -1 // b가 일시정지면 뒤로
    return new Date(a.next_run).getTime() - new Date(b.next_run).getTime()
  })
})

// 날짜 포맷팅
const formatTime = (isoString?: string | null) => {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('ko-KR', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
  })
}

// [수정] 트리거 포맷팅 (제로 패딩 적용 3:0 -> 03:00)
const formatTrigger = (trigger: string) => {
  // 1. 숫자 추출
  const hourMatch = trigger.match(/hour='(\d+)'/)
  const minMatch = trigger.match(/minute='(\d+)'/)
  
  // 2. 00 포맷팅
  // match 결과가 있으면 패딩하고, 없으면 기본값 '00' 처리
  const hour = (hourMatch && hourMatch[1]) ? hourMatch[1].padStart(2, '0') : '00'
  const min = (minMatch && minMatch[1]) ? minMatch[1].padStart(2, '0') : '00'
  const timeStr = `${hour}:${min}`

  // 3. 요일별 텍스트 결합
  if (trigger.includes('mon-fri')) return `평일(월~금) / ${timeStr}`
  if (trigger.includes('sat')) return `매주 토요일 / ${timeStr}`
  if (trigger.includes('sun')) return `매주 일요일 / ${timeStr}`
  if (trigger.includes('mon')) return `매주 월요일 / ${timeStr}`
  if (trigger.includes('tue')) return `매주 화요일 / ${timeStr}`
  if (trigger.includes('wed')) return `매주 수요일 / ${timeStr}`
  if (trigger.includes('thu')) return `매주 목요일 / ${timeStr}`
  if (trigger.includes('fri')) return `매주 금요일 / ${timeStr}`
  
  // 매칭되지 않는 경우 (Fallback)
  return trigger 
}

// --- 핸들러 ---

const openCreateModal = () => {
  isEditMode.value = false
  selectedSchedule.value = null
  isModalOpen.value = true
}

const openEditModal = (schedule: ScheduleItem) => {
  isEditMode.value = true
  selectedSchedule.value = schedule
  isModalOpen.value = true
}

const handleToggle = async (id: string) => {
  await adminStore.toggleSchedule(id)
}

const handleDelete = async (id: string) => {
  if (confirm('이 스케줄을 정말 삭제하시겠습니까?')) {
    await adminStore.deleteSchedule(id)
  }
}

const handleModalSubmit = async (data: { taskId: string; config: CronConfig }) => {
  if (isEditMode.value && selectedSchedule.value) {
    await adminStore.updateSchedule(selectedSchedule.value.id, data.config)
  } else {
    await adminStore.createSchedule({
      task_id: data.taskId,
      trigger: 'cron',
      config: data.config
    })
  }
  isModalOpen.value = false
}
</script>

<template>
  <div class="schedule-view">
    <div class="page-header">
      <h2>📅 스케줄 관리</h2>
      <button class="create-btn" @click="openCreateModal">+ 스케줄 등록</button>
    </div>

    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>태스크</th>
            <th>실행 주기</th>
            <th>다음 실행</th>
            <th>상태</th>
            <th>관리</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in sortedSchedules" :key="item.id">
            <td>{{ item.task_id }}</td>
            <td>{{ formatTrigger(item.trigger) }}</td>
            <td>{{ formatTime(item.next_run) }}</td>
            <td>
              <span class="badge" :class="item.is_paused ? 'paused' : 'active'">
                {{ item.is_paused ? '일시정지' : '활성' }}
              </span>
            </td>
            <td class="actions">
              <button @click="handleToggle(item.id)" class="icon-btn" title="상태 변경">
                {{ item.is_paused ? '▶' : '⏸' }}
              </button>
              <button @click="openEditModal(item)" class="icon-btn" title="수정">✏️</button>
              <button @click="handleDelete(item.id)" class="icon-btn delete" title="삭제">🗑️</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ScheduleModal
      :is-open="isModalOpen"
      :edit-mode="isEditMode"
      :initial-data="selectedSchedule"
      @close="isModalOpen = false"
      @submit="handleModalSubmit"
    />
  </div>
</template>

<style scoped>
.schedule-view {
  max-width: 1000px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

h2 { margin: 0; color: #1e293b; font-size: 1.5rem; }

.create-btn {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.6rem 1.2rem;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
}

.table-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  overflow: hidden;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  padding: 1rem;
  text-align: left;
  border-bottom: 1px solid #e2e8f0;
}

th {
  background: #f8fafc;
  font-weight: 600;
  color: #64748b;
  font-size: 0.9rem;
}

td {
  color: #334155;
  font-size: 0.95rem;
}

.badge {
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
}

.badge.active { background: #ecfdf5; color: #10b981; }
.badge.paused { background: #f1f5f9; color: #64748b; }

.actions {
  display: flex;
  gap: 0.5rem;
}

.icon-btn {
  background: none;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  width: 32px; height: 32px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-btn:hover { background: #f8fafc; }
.icon-btn.delete:hover { background: #fef2f2; color: #ef4444; border-color: #fecaca; }
</style>