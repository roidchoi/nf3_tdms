<template>
  <div class="schedule-view">
    <div class="view-header">
      <h2 class="view-title">📅 스케줄 및 크론 관리</h2>
      <p class="view-subtitle">한국/미국 데이터 수집 엔진의 크론 배치 일정을 원격 제어합니다.</p>
    </div>

    <!-- 한국/미국 탭 컨트롤 -->
    <div class="tab-controls">
      <button 
        class="tab-btn" 
        :class="{ active: currentMarket === 'kr' }" 
        @click="switchMarket('kr')"
      >
        🇰🇷 대한민국 (KDMS)
      </button>
      <button 
        class="tab-btn" 
        :class="{ active: currentMarket === 'us' }" 
        @click="switchMarket('us')"
      >
        🇺🇸 미국 (USDMS)
      </button>
    </div>

    <div v-if="isLoading" class="loading-state">
      <div class="spinner"></div>
      <p>동기화 중입니다...</p>
    </div>

    <div v-else-if="errorMessage" class="error-banner">
      <span class="error-icon">⚠️</span>
      <p class="error-msg">{{ errorMessage }}</p>
    </div>

    <!-- 스케줄 카드 그리드 -->
    <div v-else class="schedule-grid">
      <div 
        v-for="job in activeSchedules" 
        :key="job.job_id" 
        class="schedule-card"
        :class="{ 'paused-card': job.is_paused }"
      >
        <div class="card-header">
          <span class="status-badge" :class="job.is_paused ? 'badge-paused' : 'badge-active'">
            {{ job.is_paused ? '일시 정지' : '실행 중' }}
          </span>
          <div class="toggle-container">
            <label class="switch">
              <input 
                type="checkbox" 
                :checked="!job.is_paused" 
                @change="onToggleSwitch(job, $event)"
              />
              <span class="slider round"></span>
            </label>
          </div>
        </div>

        <div class="card-body">
          <h4 class="job-name">{{ job.name }}</h4>
          <p class="job-id-label">ID: {{ job.job_id }}</p>
          
          <div class="info-row">
            <span class="info-label">실행 트리거:</span>
            <span class="info-value">{{ job.trigger }}</span>
          </div>

          <div class="info-row">
            <span class="info-label">다음 실행 예정:</span>
            <span class="info-value highlight-time">{{ formatTime(job.next_run_time) }}</span>
          </div>
        </div>

        <div class="card-footer">
          <button class="btn-reschedule" @click="openRescheduleModal(job)">
            일정 변경
          </button>
        </div>
      </div>
    </div>

    <!-- 스케줄 수정 모달 -->
    <ScheduleModal
      :is-open="isModalOpen"
      :market="currentMarket"
      :job="selectedJobForModal"
      @close="closeModal"
      @save="saveNewSchedule"
    />
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted } from 'vue';
import { useScheduleStore, ScheduleJob } from '../stores/scheduleStore';
import ScheduleModal, { ModalJobInfo } from '../components/dashboard/ScheduleModal.vue';

export default defineComponent({
  name: 'ScheduleView',
  components: { ScheduleModal },
  setup() {
    const scheduleStore = useScheduleStore();
    const currentMarket = ref<'kr' | 'us'>('kr');
    
    // 모달 제어 상태
    const isModalOpen = ref(false);
    const selectedJobForModal = ref<ModalJobInfo>({
      job_id: '',
      name: '',
      next_run_time: null,
      trigger: ''
    });

    const isLoading = computed(() => scheduleStore.isLoading);
    const errorMessage = computed(() => scheduleStore.errorMessage);
    
    const activeSchedules = computed(() => {
      return currentMarket.value === 'kr' 
        ? scheduleStore.krSchedules 
        : scheduleStore.usSchedules;
    });

    const switchMarket = (market: 'kr' | 'us') => {
      currentMarket.value = market;
      scheduleStore.fetchSchedules(market);
    };

    // 활성/일시정지 토글 핸들러
    const onToggleSwitch = async (job: ScheduleJob, event: Event) => {
      const input = event.target as HTMLInputElement;
      const action = input.checked ? 'resume' : 'pause';
      try {
        await scheduleStore.toggleJob(currentMarket.value, job.job_id, action);
      } catch {
        // 실패 시 스위치 롤백을 위해 체크박스 상태 강제 동기화
        input.checked = !input.checked;
      }
    };

    const openRescheduleModal = (job: ScheduleJob) => {
      selectedJobForModal.value = {
        job_id: job.job_id,
        name: job.name,
        next_run_time: job.next_run_time,
        trigger: job.trigger
      };
      isModalOpen.value = true;
    };

    const closeModal = () => {
      isModalOpen.value = false;
    };

    const saveNewSchedule = async (payload: { job_id: string, hour: number, minute: number }) => {
      try {
        await scheduleStore.rescheduleJob(currentMarket.value, payload.job_id, payload.hour, payload.minute);
        closeModal();
      } catch (err) {
        console.error('Failed to save new schedule:', err);
      }
    };

    const formatTime = (timeStr: string | null) => {
      if (!timeStr) return '대기 상태 (일시정지됨)';
      try {
        const date = new Date(timeStr);
        return date.toLocaleString('ko-KR', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
          timeZoneName: 'short'
        });
      } catch {
        return timeStr;
      }
    };

    onMounted(() => {
      scheduleStore.fetchSchedules('kr');
    });

    return {
      currentMarket,
      isLoading,
      errorMessage,
      activeSchedules,
      isModalOpen,
      selectedJobForModal,
      switchMarket,
      onToggleSwitch,
      openRescheduleModal,
      closeModal,
      saveNewSchedule,
      formatTime
    };
  }
});
</script>

<style scoped>
.schedule-view {
  padding: 30px;
  color: #e2e8f0;
  font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
}

.view-header {
  margin-bottom: 24px;
}

.view-title {
  font-size: 1.75rem;
  font-weight: 700;
  background: linear-gradient(135deg, #60a5fa, #3b82f6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin: 0 0 8px 0;
}

.view-subtitle {
  font-size: 0.95rem;
  color: #94a3b8;
  margin: 0;
}

.tab-controls {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.tab-btn {
  background: rgba(30, 41, 59, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  color: #94a3b8;
  padding: 10px 20px;
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s ease;
}

.tab-btn:hover {
  background: rgba(30, 41, 59, 0.7);
  color: #f1f5f9;
}

.tab-btn.active {
  background: rgba(59, 130, 246, 0.15);
  border-color: rgba(59, 130, 246, 0.35);
  color: #60a5fa;
  box-shadow: 0 0 15px rgba(59, 130, 246, 0.1);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-top: 50px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(255, 255, 255, 0.1);
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-banner {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 12px;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.error-icon {
  font-size: 1.25rem;
}

.error-msg {
  margin: 0;
  font-size: 0.95rem;
  color: #fca5a5;
}

.schedule-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.schedule-card {
  background: rgba(30, 41, 59, 0.45);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.schedule-card:hover {
  transform: translateY(-4px);
  border-color: rgba(255, 255, 255, 0.15);
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
}

.paused-card {
  opacity: 0.55;
  filter: grayscale(40%);
  background: rgba(15, 23, 42, 0.6);
  border-style: dashed;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.status-badge {
  font-size: 0.8rem;
  padding: 4px 8px;
  border-radius: 6px;
  font-weight: 600;
}

.badge-active {
  background: rgba(16, 185, 129, 0.1);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.badge-paused {
  background: rgba(156, 163, 175, 0.1);
  color: #9ca3af;
  border: 1px solid rgba(156, 163, 175, 0.2);
}

.card-body {
  flex-grow: 1;
}

.job-name {
  margin: 0 0 6px 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: #f8fafc;
}

.job-id-label {
  margin: 0 0 16px 0;
  font-size: 0.8rem;
  color: #64748b;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.9rem;
  margin-bottom: 8px;
}

.info-label {
  color: #64748b;
}

.info-value {
  color: #cbd5e1;
  font-weight: 500;
}

.highlight-time {
  color: #60a5fa;
}

.card-footer {
  margin-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 16px;
}

.btn-reschedule {
  width: 100%;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.2);
  color: #60a5fa;
  padding: 8px;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-reschedule:hover {
  background: #3b82f6;
  color: #ffffff;
  border-color: #3b82f6;
}

/* Switch Toggle UI */
.switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.15);
  transition: .3s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: #ffffff;
  transition: .3s;
}

input:checked + .slider {
  background-color: #3b82f6;
}

input:checked + .slider:before {
  transform: translateX(20px);
}

.slider.round {
  border-radius: 24px;
}

.slider.round:before {
  border-radius: 50%;
}
</style>
