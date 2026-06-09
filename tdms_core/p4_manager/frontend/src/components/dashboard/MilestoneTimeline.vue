<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useHealthStore } from '@/stores/healthStore'
import type { Milestone } from '@/stores/healthStore'

const healthStore = useHealthStore()
const showAddModal = ref(false)

const newMilestone = ref<Milestone>({
  milestone_name: '',
  milestone_date: new Date().toISOString().split('T')[0],
  description: ''
})

const submitting = ref(false)
const errorMessage = ref('')

onMounted(async () => {
  await healthStore.fetchMilestones()
})

const openAddModal = () => {
  newMilestone.value = {
    milestone_name: '',
    milestone_date: new Date().toISOString().split('T')[0],
    description: ''
  }
  errorMessage.value = ''
  showAddModal.value = true
}

const handleAddMilestone = async () => {
  if (!newMilestone.value.milestone_name || !newMilestone.value.milestone_date) {
    errorMessage.value = '이름과 날짜를 채워주세요.'
    return
  }
  
  submitting.value = true
  errorMessage.value = ''
  try {
    await healthStore.createMilestone(newMilestone.value)
    showAddModal.value = false
  } catch (err: any) {
    errorMessage.value = err.message || '마일스톤 등록 중 오류가 발생했습니다.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="milestone-timeline-container">
    <div class="header-row">
      <h3>🇰🇷 수집 및 정제 마일스톤 이력</h3>
      <button class="add-btn" @click="openAddModal">
        ➕ 새 마일스톤 추가
      </button>
    </div>

    <!-- 로딩바 -->
    <div v-if="healthStore.loadingMilestones" class="loading-state">
      <span class="spinner"></span> 마일스톤 데이터를 불러오는 중...
    </div>

    <!-- 비어있을 때 -->
    <div v-else-if="healthStore.milestones.length === 0" class="empty-state">
      등록된 한국 마일스톤 이력이 없습니다.
    </div>

    <!-- 타임라인 리스트 -->
    <div v-else class="timeline">
      <div 
        v-for="(item, idx) in healthStore.milestones" 
        :key="idx" 
        class="timeline-item"
      >
        <div class="timeline-badge">
          <span class="badge-dot"></span>
        </div>
        <div class="timeline-content">
          <div class="content-header">
            <h4 class="name">{{ item.milestone_name }}</h4>
            <span class="date">{{ item.milestone_date }}</span>
          </div>
          <p v-if="item.description" class="desc">{{ item.description }}</p>
        </div>
      </div>
    </div>

    <!-- 새 마일스톤 추가 모달 (글래스모피즘 오버레이) -->
    <div v-if="showAddModal" class="modal-overlay">
      <div class="modal-card">
        <h3>새 마일스톤 등록</h3>
        <p class="modal-subtitle">한국 시장 운영 데이터 및 시스템 랜드마크 기록</p>
        
        <div class="form-group">
          <label>마일스톤 코드/이름 *</label>
          <input 
            type="text" 
            v-model="newMilestone.milestone_name" 
            placeholder="예: KDMS_INIT_2026"
            :disabled="submitting"
          />
        </div>

        <div class="form-group">
          <label>기준 일자 *</label>
          <input 
            type="date" 
            v-model="newMilestone.milestone_date"
            :disabled="submitting"
          />
        </div>

        <div class="form-group">
          <label>설명 (옵션)</label>
          <textarea 
            v-model="newMilestone.description" 
            placeholder="마일스톤에 대한 상세 내용을 입력하세요."
            rows="3"
            :disabled="submitting"
          ></textarea>
        </div>

        <p v-if="errorMessage" class="error-msg">{{ errorMessage }}</p>

        <div class="modal-actions">
          <button 
            class="cancel-btn" 
            @click="showAddModal = false"
            :disabled="submitting"
          >
            취소
          </button>
          <button 
            class="confirm-btn" 
            @click="handleAddMilestone"
            :disabled="submitting"
          >
            <span v-if="submitting" class="mini-spinner"></span>
            등록 완료
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.milestone-timeline-container {
  background: var(--card-bg, rgba(30, 41, 59, 0.45));
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 24px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-row h3 {
  margin: 0;
  font-size: 1.15rem;
  color: var(--color-light, #f8fafc);
}

.add-btn {
  background: linear-gradient(135deg, var(--color-indigo, #6366f1) 0%, #4f46e5 100%);
  border: none;
  color: #fff;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);
}

.add-btn:hover {
  transform: translateY(-1px);
  filter: brightness(1.1);
}

.loading-state, .empty-state {
  text-align: center;
  padding: 30px;
  color: var(--color-muted, #94a3b8);
  font-size: 0.9rem;
}

.timeline {
  position: relative;
  padding-left: 20px;
  margin-top: 10px;
}

.timeline::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 6px;
  bottom: 6px;
  width: 2px;
  background: rgba(255, 255, 255, 0.1);
}

.timeline-item {
  position: relative;
  margin-bottom: 24px;
}

.timeline-item:last-child {
  margin-bottom: 0;
}

.timeline-badge {
  position: absolute;
  left: -20px;
  top: 4px;
  width: 12px;
  height: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-indigo, #6366f1);
  box-shadow: 0 0 8px var(--color-indigo, #6366f1);
}

.timeline-content {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 14px 16px;
  transition: all 0.25s ease;
}

.timeline-content:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.1);
  transform: translateX(2px);
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.content-header .name {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: #f1f5f9;
}

.content-header .date {
  font-size: 0.75rem;
  color: var(--color-amber, #f59e0b);
  font-family: monospace;
}

.desc {
  margin: 0;
  font-size: 0.85rem;
  color: #94a3b8;
  line-height: 1.4;
}

/* 모달 양식 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}

.modal-card {
  background: rgba(30, 41, 59, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  padding: 28px;
  width: 480px;
  max-width: 90%;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
  animation: modalEnter 0.2s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes modalEnter {
  from { transform: scale(0.95); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

.modal-card h3 {
  margin: 0 0 4px 0;
  font-size: 1.2rem;
  color: #fff;
}

.modal-subtitle {
  margin: 0 0 20px 0;
  font-size: 0.8rem;
  color: #94a3b8;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 0.8rem;
  color: #cbd5e1;
  margin-bottom: 6px;
  font-weight: 500;
}

.form-group input, .form-group textarea {
  width: 100%;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  padding: 10px 12px;
  color: #fff;
  font-size: 0.85rem;
  box-sizing: border-box;
}

.form-group input:focus, .form-group textarea:focus {
  outline: none;
  border-color: var(--color-indigo, #6366f1);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}

.error-msg {
  color: #f87171;
  font-size: 0.8rem;
  margin: 0 0 16px 0;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

.cancel-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
}

.cancel-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

.confirm-btn {
  background: linear-gradient(135deg, var(--color-indigo, #6366f1) 0%, #4f46e5 100%);
  border: none;
  color: #fff;
  padding: 8px 18px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.confirm-btn:hover {
  filter: brightness(1.1);
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.2);
  border-radius: 50%;
  border-top-color: var(--color-indigo, #6366f1);
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
  margin-right: 6px;
}

.mini-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.2);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
