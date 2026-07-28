<template>
  <div v-if="isOpen" class="modal-overlay" @click.self="close">
    <div class="modal-card">
      <h3 class="modal-title">⏰ 스케줄 실행 일정 변경</h3>
      
      <div class="modal-body">
        <p class="job-info">대상 작업: <strong>{{ job.name }}</strong> ({{ market.toUpperCase() }})</p>
        
        <div class="time-select-group">
          <label>실행 시각 (KST 기준):</label>
          <div class="select-row">
            <select v-model="selectedHour" class="time-select">
              <option v-for="h in 24" :key="h - 1" :value="h - 1">
                {{ String(h - 1).padStart(2, '0') }} 시
              </option>
            </select>
            <span class="colon">:</span>
            <select v-model="selectedMinute" class="time-select">
              <option v-for="m in 60" :key="m - 1" :value="m - 1">
                {{ String(m - 1).padStart(2, '0') }} 분
              </option>
            </select>
          </div>
        </div>

        <div class="day-input-group">
          <label>실행 요일 (day_of_week):</label>
          <input 
            type="text" 
            v-model="selectedDayOfWeek" 
            placeholder="예: mon-fri, wed,sat, * 등" 
            class="day-input"
          />
          <p class="input-tip">
            자주 쓰는 패턴: 
            <span class="tip-badge" @click="selectedDayOfWeek = 'mon-fri'">월-금</span>
            <span class="tip-badge" @click="selectedDayOfWeek = 'tue-sat'">화-토</span>
            <span class="tip-badge" @click="selectedDayOfWeek = 'wed,sat'">수,토</span>
            <span class="tip-badge" @click="selectedDayOfWeek = '*'">매일</span>
          </p>
        </div>

        <!-- 미국 마켓인 경우 현지 시각(EST/EDT) 환산 정보 노출 -->
        <div v-if="market === 'us'" class="timezone-guide">
          <p class="timezone-text">🇺🇸 미국 현지 시각 환산 (EST 기준):</p>
          <p class="converted-time">{{ convertedEstTime }}</p>
        </div>

        <!-- 수집 가동 시간 / 개장 시간 경고 안내 -->
        <div v-if="isTradingOrCollectionTime" class="danger-warning">
          <p class="warning-title">⚠️ 경고: 수집 주기 또는 개장 시간대입니다</p>
          <p class="warning-text">현재 시간대는 주식 데이터 수집 및 거래 시점과 겹쳐서 변경 시 시세 누락이나 시스템 오류가 발생할 수 있습니다.</p>
          <p class="confirm-prompt">변경을 계속하시려면 아래에 <strong>변경승인</strong>을 입력하십시오.</p>
          <input 
            type="text" 
            v-model="safetyConfirmText" 
            placeholder="변경승인 입력" 
            class="safety-input"
          />
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-cancel" @click="close" :disabled="isSubmitting">취소</button>
        <button 
          class="btn btn-confirm" 
          @click="submit" 
          :disabled="isConfirmDisabled"
        >
          {{ isSubmitting ? '변경 중...' : '적용' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import type { PropType } from 'vue';

export interface ModalJobInfo {
  job_id: string;
  name: string;
  next_run_time: string | null;
  trigger: string;
}

export default defineComponent({
  name: 'ScheduleModal',
  props: {
    isOpen: {
      type: Boolean,
      required: true
    },
    market: {
      type: String as PropType<'kr' | 'us'>,
      required: true
    },
    job: {
      type: Object as PropType<ModalJobInfo>,
      required: true
    }
  },
  emits: ['close', 'save'],
  setup(props, { emit }) {
    const selectedHour = ref(17);
    const selectedMinute = ref(0);
    const selectedDayOfWeek = ref('');
    const safetyConfirmText = ref('');
    const isSubmitting = ref(false);

    // 스케줄 시간 및 요일 기본값 세팅
    watch(() => props.isOpen, (newVal) => {
      if (newVal) {
        if (props.job.next_run_time) {
          try {
            const dateObj = new Date(props.job.next_run_time);
            selectedHour.value = dateObj.getHours();
            selectedMinute.value = dateObj.getMinutes();
          } catch {
            selectedHour.value = 17;
            selectedMinute.value = 0;
          }
        }
        
        // job.trigger 에서 day_of_week 추출 (예: cron[hour='17', day_of_week='mon-fri'])
        if (props.job.trigger) {
          const match = props.job.trigger.match(/day_of_week='([^']+)'/);
          selectedDayOfWeek.value = match ? match[1] : '';
        } else {
          selectedDayOfWeek.value = '';
        }
        
        safetyConfirmText.value = '';
      }
    });

    // KST 시각 기준 EST 미국 시간대 환산 (고정 13시간 시차 계산)
    const convertedEstTime = computed(() => {
      let estHour = selectedHour.value - 13;
      if (estHour < 0) {
        estHour += 24;
      }
      return `${String(estHour).padStart(2, '0')}:${String(selectedMinute.value).padStart(2, '0')} EST (서머타임 미적용 시 14시간)`;
    });

    // 안전 확인: 거래/수집 가동 시간대인지 여부 체크 (한국 09:00~16:00, 미국 22:00~06:00 KST)
    const isTradingOrCollectionTime = computed(() => {
      const now = new Date();
      const currentHour = now.getHours();
      
      if (props.market === 'kr') {
        return currentHour >= 9 && currentHour < 16;
      } else {
        return currentHour >= 22 || currentHour < 6;
      }
    });

    // 확인 버튼 비활성화 통제 조건
    const isConfirmDisabled = computed(() => {
      if (isSubmitting.value) return true;
      if (isTradingOrCollectionTime.value) {
        return safetyConfirmText.value !== '변경승인';
      }
      return false;
    });

    const close = () => {
      emit('close');
    };

    const submit = async () => {
      isSubmitting.value = true;
      try {
        emit('save', {
          job_id: props.job.job_id,
          hour: selectedHour.value,
          minute: selectedMinute.value,
          day_of_week: selectedDayOfWeek.value.trim() || undefined
        });
      } finally {
        isSubmitting.value = false;
      }
    };

    return {
      selectedHour,
      selectedMinute,
      selectedDayOfWeek,
      safetyConfirmText,
      isSubmitting,
      convertedEstTime,
      isTradingOrCollectionTime,
      isConfirmDisabled,
      close,
      submit
    };
  }
});
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(8px);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-card {
  background: rgba(30, 30, 45, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
  border-radius: 16px;
  padding: 24px;
  width: 90%;
  max-width: 440px;
  color: #f1f3f5;
  font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
}

.modal-title {
  margin-top: 0;
  margin-bottom: 20px;
  font-size: 1.25rem;
  font-weight: 600;
  color: #3b82f6;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 12px;
}

.modal-body {
  margin-bottom: 24px;
}

.job-info {
  font-size: 0.95rem;
  margin-bottom: 16px;
  color: #a1a1aa;
}

.time-select-group {
  margin-bottom: 18px;
}

.time-select-group label {
  display: block;
  font-size: 0.9rem;
  margin-bottom: 8px;
  color: #cbd5e1;
}

.select-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.time-select {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  color: #f1f3f5;
  padding: 8px 12px;
  font-size: 1rem;
  outline: none;
  cursor: pointer;
  flex: 1;
}

.time-select:focus {
  border-color: #3b82f6;
}

.colon {
  font-weight: bold;
  font-size: 1.25rem;
}

.timezone-guide {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 18px;
}

.timezone-text {
  margin: 0 0 4px 0;
  font-size: 0.85rem;
  color: #60a5fa;
}

.converted-time {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: #93c5fd;
}

.danger-warning {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: 8px;
  padding: 12px;
  margin-top: 16px;
}

.warning-title {
  margin: 0 0 6px 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: #fca5a5;
}

.warning-text {
  margin: 0 0 8px 0;
  font-size: 0.8rem;
  line-height: 1.4;
  color: #f87171;
}

.confirm-prompt {
  margin: 0 0 6px 0;
  font-size: 0.8rem;
  color: #cbd5e1;
}

.safety-input {
  width: 100%;
  box-sizing: border-box;
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(239, 68, 68, 0.4);
  border-radius: 6px;
  color: #fca5a5;
  padding: 8px 10px;
  font-size: 0.9rem;
  outline: none;
}

.safety-input:focus {
  border-color: #ef4444;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.95rem;
  cursor: pointer;
  border: none;
  font-weight: 500;
  transition: all 0.2s ease;
}

.btn-cancel {
  background: rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
}

.btn-cancel:hover {
  background: rgba(255, 255, 255, 0.15);
}

.btn-confirm {
  background: #3b82f6;
  color: #ffffff;
}

.btn-confirm:hover:not(:disabled) {
  background: #2563eb;
}

.btn-confirm:disabled {
  background: rgba(59, 130, 246, 0.3);
  color: rgba(255, 255, 255, 0.4);
  cursor: not-allowed;
}

/* Day input styling */
.day-input-group {
  margin-bottom: 18px;
}

.day-input-group label {
  display: block;
  font-size: 0.9rem;
  margin-bottom: 8px;
  color: #cbd5e1;
}

.day-input {
  width: 100%;
  box-sizing: border-box;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  color: #f1f3f5;
  padding: 8px 12px;
  font-size: 1rem;
  outline: none;
}

.day-input:focus {
  border-color: #3b82f6;
}

.input-tip {
  margin: 6px 0 0 0;
  font-size: 0.8rem;
  color: #64748b;
}

.tip-badge {
  display: inline-block;
  background: rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  padding: 2px 6px;
  border-radius: 4px;
  margin-left: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.tip-badge:hover {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
}
</style>
