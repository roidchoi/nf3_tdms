<script setup lang="ts">
import { ref } from 'vue'
import { useHealthStore } from '@/stores/healthStore'
import MilestoneModal from './MilestoneModal.vue'
import type { SystemMilestonePayload } from '@/types/health'

const healthStore = useHealthStore()
const isModalOpen = ref(false)

// 날짜 포맷팅
const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleDateString('ko-KR', {
    month: 'long', day: 'numeric', weekday: 'short'
  })
}

const handleCreateSubmit = async (payload: SystemMilestonePayload) => {
  await healthStore.createMilestone(payload)
  isModalOpen.value = false
}
</script>

<template>
  <div class="timeline-card">
    <div class="header">
      <div class="title-area">
        <h3>📅 시스템 운영 이력</h3>
        <span class="count">{{ healthStore.milestones.length }}건</span>
      </div>
      <button @click="isModalOpen = true" class="add-btn">+ 기록 추가</button>
    </div>

    <div class="timeline-body">
      <div v-if="healthStore.milestones.length === 0" class="empty">
        이력이 없습니다.
      </div>
      
      <div v-else class="timeline">
        <div 
          v-for="(item, index) in healthStore.milestones" 
          :key="index" 
          class="timeline-item"
        >
          <div class="date-col">
            <span class="date-text">{{ formatDate(item.milestone_date) }}</span>
          </div>
          <div class="marker-col">
            <div class="line"></div>
            <div class="dot"></div>
          </div>
          <div class="content-col">
            <div class="title">{{ item.milestone_name }}</div>
            <div class="desc">{{ item.description }}</div>
            <div class="time">{{ new Date(item.updated_at).toLocaleTimeString() }}</div>
          </div>
        </div>
      </div>
    </div>

    <MilestoneModal 
      :is-open="isModalOpen" 
      @close="isModalOpen = false"
      @submit="handleCreateSubmit"
    />
  </div>
</template>

<style scoped>
.timeline-card {
  background: white;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 600px; /* 높이 제한 */
}

.header {
  padding: 1rem 1.2rem;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f8fafc;
}

.title-area { display: flex; align-items: center; gap: 0.5rem; }
h3 { margin: 0; font-size: 1rem; color: #334155; }

.count {
  font-size: 0.8rem;
  color: #64748b;
  background: #e2e8f0;
  padding: 2px 8px;
  border-radius: 12px;
}

.add-btn {
  font-size: 0.85rem;
  color: #2563eb;
  background: #dbeafe;
  border: none;
  padding: 0.4rem 0.8rem;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.2s;
}
.add-btn:hover { background: #bfdbfe; }

.timeline-body {
  flex: 1;
  padding: 1.2rem;
  overflow-y: auto;
  overflow-x: hidden;
}

.empty { color: #94a3b8; text-align: center; padding: 2rem; }

.timeline {
  display: flex;
  flex-direction: column;
}

.timeline-item {
  display: flex;
  gap: 0.8rem;
  padding-bottom: 1.5rem;
  position: relative;
}

.timeline-item:last-child { padding-bottom: 0; }

.date-col {
  width: 60px;
  min-width: 60px;
  text-align: right;
  padding-top: 2px;
}

.date-text {
  font-size: 0.8rem;
  color: #64748b;
  font-weight: 600;
  display: block;
  line-height: 1.2;
}

.marker-col {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 20px;
}

.dot {
  width: 10px;
  height: 10px;
  background: #3b82f6;
  border-radius: 50%;
  z-index: 2;
  margin-top: 6px;
  box-shadow: 0 0 0 3px #dbeafe;
}

.line {
  position: absolute;
  top: 6px;
  bottom: -20px; /* 다음 아이템까지 연결 */
  width: 2px;
  background: #e2e8f0;
  z-index: 1;
}

.timeline-item:last-child .line { display: none; }

.content-col {
  flex: 1;
  background: #f8fafc;
  padding: 0.8rem;
  border-radius: 8px;
  border: 1px solid #f1f5f9;
  min-width: 0;
}

.title {
  font-weight: 600;
  color: #1e293b;
  font-size: 0.9rem;
  margin-bottom: 0.2rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.desc {
  font-size: 0.85rem;
  color: #475569;
  margin-bottom: 0.4rem;
  word-break: keep-all; /* 단어 단위 줄바꿈 */
  line-height: 1.4;
}

.time {
  font-size: 0.75rem;
  color: #94a3b8;
}
</style>