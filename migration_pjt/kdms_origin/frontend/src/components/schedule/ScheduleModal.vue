<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { ScheduleItem, CronConfig } from '@/types/admin'

const props = defineProps<{
  isOpen: boolean;
  editMode: boolean; // true: 수정, false: 생성
  initialData?: ScheduleItem | null; // 수정 시 기존 데이터
}>()

const emit = defineEmits(['close', 'submit'])

// 폼 데이터
const form = reactive({
  taskId: 'daily_update',
  dayOfWeek: 'mon-fri',
  hour: 16,
  minute: 0
})

// 수정 모드일 때 초기값 세팅 (정규식 파싱)
watch(() => props.initialData, (newVal) => {
  if (props.editMode && newVal) {
    form.taskId = newVal.task_id
    // Trigger 문자열 파싱 (예: cron[day_of_week='mon', ...])
    const dayMatch = newVal.trigger.match(/day_of_week='([^']+)'/)
    const hourMatch = newVal.trigger.match(/hour='([^']+)'/)
    const minMatch = newVal.trigger.match(/minute='([^']+)'/)
    
    if (dayMatch && dayMatch[1]) {
      form.dayOfWeek = dayMatch[1]
    }
    
    if (hourMatch && hourMatch[1]) {
      form.hour = parseInt(hourMatch[1])
    }
    
    if (minMatch && minMatch[1]) {
      form.minute = parseInt(minMatch[1])
    }
    
  } else {
    // 초기화
    form.taskId = 'daily_update'
    form.dayOfWeek = 'mon-fri'
    form.hour = 16
    form.minute = 0
  }
})

const handleSubmit = () => {
  const config: CronConfig = {
    day_of_week: form.dayOfWeek,
    hour: form.hour,
    minute: form.minute
  }
  
  // 부모에게 데이터 전달
  emit('submit', {
    taskId: form.taskId,
    config: config
  })
}
</script>

<template>
  <div v-if="isOpen" class="modal-overlay">
    <div class="modal-content">
      <h3>{{ editMode ? '스케줄 수정' : '새 스케줄 등록' }}</h3>
      
      <div class="form-group">
        <label>대상 태스크</label>
        <select v-model="form.taskId" :disabled="editMode">
          <option value="daily_update">일일 데이터 업데이트</option>
          <option value="financial_update">재무정보 수집</option>
          <option value="backfill_minute_data">분봉 백필</option>
        </select>
      </div>

      <div class="form-group">
        <label>요일 설정</label>
        <select v-model="form.dayOfWeek">
          <option value="mon-fri">평일 (월~금)</option>
          <option value="sat">매주 토요일</option>
          <option value="sun">매주 일요일</option>
          <option value="mon">매주 월요일</option>
          </select>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>시 (Hour)</label>
          <input type="number" v-model="form.hour" min="0" max="23">
        </div>
        <div class="form-group">
          <label>분 (Minute)</label>
          <input type="number" v-model="form.minute" min="0" max="59">
        </div>
      </div>

      <div class="actions">
        <button @click="emit('close')" class="cancel-btn">취소</button>
        <button @click="handleSubmit" class="submit-btn">
          {{ editMode ? '저장' : '등록' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0; left: 0;
  width: 100%; height: 100%;
  background: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  padding: 2rem;
  border-radius: 12px;
  width: 400px;
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

h3 { margin-top: 0; margin-bottom: 1.5rem; color: #1e293b; }

.form-group {
  margin-bottom: 1rem;
}

.form-row {
  display: flex;
  gap: 1rem;
}

.form-row .form-group { flex: 1; }

label {
  display: block;
  font-size: 0.9rem;
  color: #64748b;
  margin-bottom: 0.4rem;
}

select, input {
  width: 100%;
  padding: 0.6rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-family: inherit;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.8rem;
  margin-top: 2rem;
}

.cancel-btn {
  background: white;
  border: 1px solid #cbd5e1;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
}

.submit-btn {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
}
</style>