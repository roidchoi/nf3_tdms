<script setup lang="ts">
import { reactive, computed } from 'vue'

defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits(['close', 'submit'])

const form = reactive({
  name: '',
  date: new Date().toISOString().split('T')[0],
  description: ''
})

// 이름 유효성 검사 (대문자 자동 변환 및 콜론 체크)
const isValidName = computed(() => {
  return form.name.includes(':') && form.name.length > 5
})

const handleSubmit = () => {
  if (!isValidName.value) {
    alert('마일스톤 이름은 규칙(CATEGORY:SUB:DETAIL)을 따라야 합니다.')
    return
  }
  emit('submit', {
    milestone_name: form.name.toUpperCase(),
    milestone_date: form.date,
    description: form.description
  })
  // 폼 초기화
  form.name = ''
  form.description = ''
}

const close = () => emit('close')
</script>

<template>
  <div v-if="isOpen" class="modal-overlay">
    <div class="modal-content">
      <h3>📌 시스템 마일스톤 등록</h3>
      
      <div class="guide-box">
        <h4>💡 작명 규칙 (Naming Convention)</h4>
        <p><code>대분류:중분류:상세내용_버전</code> 형식을 준수해주세요.</p>
        <ul>
          <li><strong>SYSTEM:LIVE:DAILY_V1</strong> (시스템 공식 오픈)</li>
          <li><strong>DB:MIGRATION:OHLCV_FIX</strong> (데이터 마이그레이션)</li>
          <li><strong>ISSUE:KIS_API:TIMEOUT</strong> (장애 기록)</li>
        </ul>
      </div>

      <div class="form-group">
        <label>마일스톤 이름 (Key)</label>
        <input 
          type="text" 
          v-model="form.name" 
          placeholder="예: SYSTEM:UPDATE:V6"
          class="uppercase-input"
        >
      </div>

      <div class="form-group">
        <label>발생 날짜</label>
        <input type="date" v-model="form.date">
      </div>

      <div class="form-group">
        <label>상세 설명</label>
        <textarea 
          v-model="form.description" 
          rows="3" 
          placeholder="변경 사항이나 이벤트 내용을 상세히 기록하세요."
        ></textarea>
      </div>

      <div class="actions">
        <button @click="close" class="cancel-btn">취소</button>
        <button 
          @click="handleSubmit" 
          class="submit-btn"
          :disabled="!isValidName"
        >
          등록
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
  width: 500px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.1);
}

h3 { margin-top: 0; margin-bottom: 1rem; color: #1e293b; }

.guide-box {
  background: #fffbeb;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1.5rem;
}

.guide-box h4 { margin: 0 0 0.5rem 0; font-size: 0.9rem; color: #92400e; }
.guide-box p { margin: 0; font-size: 0.85rem; color: #b45309; }
.guide-box ul { margin: 0.5rem 0 0 1.2rem; padding: 0; font-size: 0.8rem; color: #78350f; }
.guide-box code { background: rgba(255,255,255,0.5); padding: 2px 4px; border-radius: 4px; font-weight: bold; }

.form-group { margin-bottom: 1rem; }
label { display: block; font-size: 0.9rem; color: #64748b; margin-bottom: 0.4rem; }

input, textarea {
  width: 100%;
  padding: 0.7rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-family: inherit;
}

.uppercase-input { text-transform: uppercase; }

.actions { display: flex; justify-content: flex-end; gap: 0.8rem; margin-top: 2rem; }

.cancel-btn {
  background: white; border: 1px solid #cbd5e1;
  padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer;
}

.submit-btn {
  background: #2563eb; color: white; border: none;
  padding: 0.5rem 1.5rem; border-radius: 6px; cursor: pointer;
}
.submit-btn:disabled { background: #94a3b8; cursor: not-allowed; }
</style>