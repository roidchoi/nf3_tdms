<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useSyncStore } from '@/stores/syncStore'
import { useBackupStore } from '@/stores/backupStore'

const syncStore = useSyncStore()
const backupStore = useBackupStore()

const selectedMarket = ref<'kdms' | 'usdms'>('kdms')
const selectedDirection = ref<'pull' | 'push'>('pull')

// 네트워크 설정용 상태
const peerIpInput = ref('')
const peerPortInput = ref(8000)
const connectionSuccessMsg = ref<string | null>(null)
const connectionErrorMsg = ref<string | null>(null)

// 동기화 실행 관련 상태
const showSyncModal = ref(false)
const confirmInput = ref('')
const syncSuccessMsg = ref<string | null>(null)
const syncErrorMsg = ref<string | null>(null)

// 감사 관련 상태
const showAuditPanel = ref(false)
const auditSuccessMsg = ref<string | null>(null)
const auditErrorMsg = ref<string | null>(null)

// 터미널 엘리먼트 참조
const terminalBody = ref<HTMLElement | null>(null)
let pollingInterval: any = null

const isSyncing = computed(() => syncStore.syncStatus === 'RUNNING')

// 실시간 터미널 로그 스크롤 제어
watch(() => syncStore.syncLogs, () => {
  nextTick(() => {
    if (terminalBody.value) {
      terminalBody.value.scrollTop = terminalBody.value.scrollHeight
    }
  })
}, { deep: true })

onMounted(async () => {
  await backupStore.fetchEnv()
  // 만약 기존 백그라운드 태스크가 실행 중인지 확인하기 위해 상태 1회 조회
  await syncStore.fetchSyncStatus()
  if (isSyncing.value) {
    startStatusPolling()
  }
})

onUnmounted(() => {
  stopStatusPolling()
})

// 폴링 시작/종료 헬퍼
const startStatusPolling = () => {
  stopStatusPolling()
  pollingInterval = setInterval(async () => {
    await syncStore.fetchSyncStatus()
    if (!isSyncing.value) {
      stopStatusPolling()
      if (syncStore.syncStatus === 'SUCCESS') {
        syncSuccessMsg.value = '동기화 전체 파이프라인이 성공적으로 완료되었습니다. 데이터 정합성 검사를 실행할 수 있습니다.'
        showAuditPanel.value = true
        // 완료 시 자동으로 감사 실행 시도
        handleRunAudit()
      } else if (syncStore.syncStatus === 'ERROR') {
        syncErrorMsg.value = `동기화 도중 오류가 발생했습니다: ${syncStore.syncErrorMessage}`
      }
    }
  }, 2000)
}

const stopStatusPolling = () => {
  if (pollingInterval) {
    clearInterval(pollingInterval)
    pollingInterval = null
  }
}

// 1. 연결 검증 테스트
const handleTestConnection = async () => {
  connectionSuccessMsg.value = null
  connectionErrorMsg.value = null
  if (!peerIpInput.value.trim()) {
    connectionErrorMsg.value = '검증할 피어 IP 주소를 입력해 주십시오.'
    return
  }
  try {
    const res = await syncStore.testConnection(peerIpInput.value, peerPortInput.value)
    if (res.connected) {
      connectionSuccessMsg.value = `연결 검증 성공: ${res.message}`
    } else {
      connectionErrorMsg.value = `연결 검증 실패: ${res.message}`
    }
  } catch (err: any) {
    connectionErrorMsg.value = err.message || '연결성 검사 중 오류가 발생했습니다.'
  }
}

// 2. 서버 IP 자동 탐색 및 .env 적용
const handleDetectServerIp = async () => {
  connectionSuccessMsg.value = null
  connectionErrorMsg.value = null
  try {
    const res = await syncStore.detectServerIp()
    if (res.server_ip) {
      peerIpInput.value = res.server_ip
      connectionSuccessMsg.value = `서버 IP 자동 탐색 완료 (${res.method.toUpperCase()}): ${res.server_ip}`
    } else {
      connectionErrorMsg.value = '네트워크 상에서 활성화된 TDMS 서버 PC를 찾지 못했습니다. 수동 설정을 검토하세요.'
    }
  } catch (err: any) {
    connectionErrorMsg.value = err.message || '서버 IP 자동 탐색 중 오류가 발생했습니다.'
  }
}

const handleSyncIpToEnv = async () => {
  connectionSuccessMsg.value = null
  connectionErrorMsg.value = null
  if (!peerIpInput.value.trim()) {
    connectionErrorMsg.value = '동기화할 피어 IP 주소가 비어있습니다.'
    return
  }
  try {
    const targetVar = backupStore.currentEnv === 'dev' ? 'server' : 'dev'
    const res = await syncStore.syncIp(targetVar, peerIpInput.value)
    connectionSuccessMsg.value = `${res.message} (로컬 메모리 및 환경 프로파일 갱신 적용됨)`
  } catch (err: any) {
    connectionErrorMsg.value = err.message || '.env IP 반영 도중 오류가 발생했습니다.'
  }
}

// 3. 동기화 실행 모달 제어
const openSyncModal = () => {
  syncSuccessMsg.value = null
  syncErrorMsg.value = null
  confirmInput.value = ''
  showSyncModal.value = true
}

const closeSyncModal = () => {
  if (isSyncing.value) return
  showSyncModal.value = false
}

const handleStartSync = async () => {
  const requiredConfirmText = selectedDirection.value === 'pull' ? 'PULL FROM SERVER' : 'PUSH TO SERVER'
  if (confirmInput.value !== requiredConfirmText) {
    return
  }

  syncSuccessMsg.value = null
  syncErrorMsg.value = null
  showSyncModal.value = false

  try {
    await syncStore.startSync(selectedMarket.value, selectedDirection.value, confirmInput.value)
    startStatusPolling()
  } catch (err: any) {
    syncErrorMsg.value = err.message || '동기화 실행에 실패했습니다.'
  }
}

// 4. 감사(Audit) 실행
const handleRunAudit = async () => {
  auditSuccessMsg.value = null
  auditErrorMsg.value = null
  try {
    const res = await syncStore.runAudit(selectedMarket.value)
    if (res.status === 'success') {
      auditSuccessMsg.value = `감사 검증 성공: ${res.audit_type} 실행 완료`
    } else {
      auditErrorMsg.value = `감사 검증 실패: ${res.raw_output}`
    }
  } catch (err: any) {
    auditErrorMsg.value = err.message || '감사 실행 중 오류가 발생했습니다.'
  }
}

const getLineClass = (log: string) => {
  if (log.includes('[ERROR]')) return 'line-error'
  if (log.includes('[WARNING]')) return 'line-warning'
  if (log.includes('[INFO]')) return 'line-info'
  return ''
}
</script>

<template>
  <div class="sync-view-container">
    <!-- 1. 환경 정보 배너 -->
    <div v-if="backupStore.currentEnv === 'server'" class="warning-banner server-banner">
      <span class="warning-icon">⚠️</span>
      <div class="banner-body">
        <h3>서버 PC 환경 (데이터 유입 차단)</h3>
        <p>
          본 장비는 <strong>실서버 운영 환경</strong>입니다. 외부 개발 PC로부터 수신되는 쓰기 동기화(PUSH TO SERVER) 동작은 
          <strong>403 Forbidden으로 원천 차단</strong>됩니다. 
          반대로, 개발 PC에서 본 서버의 데이터를 당겨가는(PULL FROM SERVER) 동기화 요청만 가능하므로 안심하고 안전하게 데이터를 제공할 수 있습니다.
        </p>
      </div>
    </div>

    <div v-else-if="backupStore.currentEnv === 'dev'" class="info-banner dev-banner">
      <span class="info-icon">ℹ️</span>
      <div class="banner-body">
        <h3>개발 PC 환경 (피어 동기화 기동 활성화)</h3>
        <p>
          개발 PC 환경입니다. 실서버 데이터를 로컬로 덮어쓰는 <strong>가져오기 (PULL FROM SERVER)</strong> 및 
          로컬 가공 데이터를 서버에 업로드하는 <strong>밀어넣기 (PUSH TO SERVER)</strong> 물리 복제가 가능합니다.
        </p>
      </div>
    </div>

    <div class="sync-grid">
      <!-- Left Column: Settings and Trigger -->
      <div class="sync-left-column">
        <!-- 2. 피어 및 네트워크 설정 카드 -->
        <section class="control-card card-glassmorphism">
          <h2>🌐 피어(Peer) 및 네트워크 설정</h2>
          <p class="card-desc">동기화를 전송/수신할 원격지 서버와의 연결성 및 IP 정보를 갱신합니다.</p>

          <div class="form-group">
            <label for="peer-ip">원격 피어 IP 주소</label>
            <input 
              id="peer-ip"
              type="text" 
              v-model="peerIpInput" 
              placeholder="예: 192.168.35.xxx" 
              :disabled="isSyncing || syncStore.loading"
            />
          </div>

          <div class="network-actions">
            <button 
              class="btn-secondary" 
              @click="handleTestConnection" 
              :disabled="isSyncing || syncStore.loading || !peerIpInput"
            >
              ⚡ 연결 검증 테스트
            </button>
            <button 
              class="btn-secondary" 
              @click="handleDetectServerIp" 
              :disabled="isSyncing || syncStore.loading"
            >
              🔍 서버 IP 자동 탐색
            </button>
            <button 
              class="btn-primary" 
              @click="handleSyncIpToEnv" 
              :disabled="isSyncing || syncStore.loading || !peerIpInput"
            >
              🔄 .env 파일에 반영
            </button>
          </div>

          <!-- 연결 피드백 메시지 -->
          <transition name="fade">
            <div v-if="connectionSuccessMsg" class="feedback-msg success">
              {{ connectionSuccessMsg }}
            </div>
          </transition>
          <transition name="fade">
            <div v-if="connectionErrorMsg" class="feedback-msg error">
              {{ connectionErrorMsg }}
            </div>
          </transition>
        </section>

        <!-- 3. 물리 동기화 컨트롤러 -->
        <section class="control-card card-glassmorphism mt-6">
          <h2>⚡ DB 물리 동기화 기동 (Stop-and-Copy)</h2>
          <p class="card-desc">양측 데이터베이스 컨테이너를 안전하게 자동 중지 후 압축 블록 파일을 전송합니다.</p>

          <div class="form-group">
            <label>대상 데이터베이스</label>
            <div class="market-radio-group">
              <label class="radio-label">
                <input 
                  type="radio" 
                  v-model="selectedMarket" 
                  value="kdms" 
                  :disabled="isSyncing" 
                />
                <span class="radio-custom"></span>
                🇰🇷 KDMS (한국)
              </label>
              <label class="radio-label">
                <input 
                  type="radio" 
                  v-model="selectedMarket" 
                  value="usdms" 
                  :disabled="isSyncing" 
                />
                <span class="radio-custom"></span>
                🇺🇸 USDMS (미국)
              </label>
            </div>
          </div>

          <div class="form-group">
            <label>동기화 처리 방향</label>
            <div class="market-radio-group">
              <label class="radio-label">
                <input 
                  type="radio" 
                  v-model="selectedDirection" 
                  value="pull" 
                  :disabled="isSyncing" 
                />
                <span class="radio-custom"></span>
                📥 가져오기 (Pull from Server)
              </label>
              <label class="radio-label">
                <input 
                  type="radio" 
                  v-model="selectedDirection" 
                  value="push" 
                  :disabled="isSyncing || backupStore.currentEnv === 'server'" 
                />
                <span class="radio-custom"></span>
                📤 밀어넣기 (Push to Server)
              </label>
            </div>
          </div>

          <button 
            id="start-sync-btn"
            class="btn-danger w-full mt-4" 
            @click="openSyncModal" 
            :disabled="isSyncing || (selectedDirection === 'push' && backupStore.currentEnv === 'server')"
          >
            <span v-if="isSyncing" class="spinner"></span>
            <span v-else>🔄 동기화 파이프라인 시작</span>
          </button>

          <!-- 동기화 피드백 -->
          <transition name="fade">
            <div v-if="syncSuccessMsg" class="feedback-msg success">
              {{ syncSuccessMsg }}
            </div>
          </transition>
          <transition name="fade">
            <div v-if="syncErrorMsg" class="feedback-msg error">
              {{ syncErrorMsg }}
            </div>
          </transition>
        </section>
      </div>

      <!-- Right Column: Console & Audit -->
      <div class="sync-right-column">
        <!-- 4. 실시간 로그 콘솔 터미널 -->
        <section class="history-card card-glassmorphism h-full">
          <div class="history-header">
            <h2>🖥️ 실시간 백그라운드 프로세스 터미널</h2>
            <span class="terminal-status" :class="syncStore.syncStatus.toLowerCase()">
              {{ syncStore.syncStatus }}
            </span>
          </div>

          <div class="terminal-container">
            <div class="terminal-header-bar">
              <span class="terminal-dot red"></span>
              <span class="terminal-dot yellow"></span>
              <span class="terminal-dot green"></span>
              <span class="terminal-title">tdms-sync-pipeline.log</span>
            </div>
            <div class="terminal-body" ref="terminalBody">
              <div 
                v-for="(log, idx) in syncStore.syncLogs" 
                :key="idx" 
                class="terminal-line" 
                :class="getLineClass(log)"
              >
                {{ log }}
              </div>
              <div v-if="syncStore.syncLogs.length === 0" class="terminal-empty">
                대기 중... 동기화 파이프라인을 실행하면 실시간 로그가 여기에 출력됩니다.
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <!-- 5. 감사(Audit) 결과 카드 -->
    <transition name="fade">
      <section v-if="showAuditPanel" class="control-card card-glassmorphism mt-6 text-left">
        <div class="flex justify-between items-center mb-4">
          <h2 class="m-0">🔍 양측 데이터베이스 정밀 감사 검증 리포트</h2>
          <button 
            class="btn-refresh" 
            @click="handleRunAudit" 
            :disabled="syncStore.auditLoading"
          >
            <span v-if="syncStore.auditLoading" class="spinner"></span>
            <span v-else>🔄 감사 재실행</span>
          </button>
        </div>

        <div v-if="syncStore.auditLoading" class="loading-placeholder">
          <span class="spinner"></span>
          <span>원격지와 로컬 DB 테이블 전수 대조 감사 실행 중... (수 초가 소요될 수 있습니다)</span>
        </div>

        <div v-else-if="syncStore.error" class="feedback-msg error">
          {{ syncStore.error }}
        </div>

        <div v-else-if="syncStore.auditReport" class="audit-report-container">
          <pre class="audit-pre">{{ syncStore.auditReport }}</pre>
        </div>
      </section>
    </transition>

    <!-- 6. 이중 컨펌 잠금 모달 -->
    <transition name="fade">
      <div v-if="showSyncModal" class="modal-backdrop" @click.self="closeSyncModal">
        <div class="modal-content card-glassmorphism">
          <div class="modal-header">
            <h3>⚠️ 물리 볼륨 동기화 덮어쓰기 경고</h3>
            <button class="btn-close" @click="closeSyncModal">✕</button>
          </div>
          
          <div class="modal-body">
            <p class="warning-text">
              <strong>{{ selectedMarket.toUpperCase() }} DB</strong>에 대해 
              <strong>{{ selectedDirection === 'pull' ? '가져오기 (PULL)' : '밀어넣기 (PUSH)' }}</strong> 물리 복제를 개시합니다.<br/>
              이 작업은 수신지 DB의 <strong>데이터 볼륨 전체를 완전히 포맷 후 덮어쓰기</strong>하며, 
              안전한 디스크 복제를 위해 **양측 DB 컨테이너와 API 서비스가 즉시 중단(Maintenance Mode)**된 후 재기동됩니다. 
              기존 활성 수집 배치나 락 상태가 취소됩니다.
            </p>
            
            <div class="confirm-step">
              <p class="instruction">
                안전 장치 작동: 오작동을 차단하기 위해 아래 입력창에 정확히 
                <strong class="highlight">
                  {{ selectedDirection === 'pull' ? 'PULL FROM SERVER' : 'PUSH TO SERVER' }}
                </strong>
                를 입력하십시오.
              </p>
              <input 
                id="sync-confirm-input"
                type="text" 
                v-model="confirmInput" 
                :placeholder="selectedDirection === 'pull' ? 'PULL FROM SERVER' : 'PUSH TO SERVER'" 
                class="confirm-input"
              />
            </div>
          </div>

          <div class="modal-footer">
            <button 
              id="confirm-sync-btn"
              class="btn-danger" 
              :disabled="confirmInput !== (selectedDirection === 'pull' ? 'PULL FROM SERVER' : 'PUSH TO SERVER')"
              @click="handleStartSync"
            >
              ⚠️ 데이터 덮어쓰기 및 서비스 일시 중단 동의 실행
            </button>
            <button class="btn-secondary" @click="closeSyncModal">
              취소
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.sync-view-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
}

.warning-banner, .info-banner {
  display: flex;
  gap: 1.25rem;
  padding: 1.25rem 1.5rem;
  border-radius: 16px;
  line-height: 1.5;
  text-align: left;
}

.server-banner {
  background: rgba(244, 63, 94, 0.1);
  border: 1px solid rgba(244, 63, 94, 0.3);
  border-left: 5px solid var(--color-rose);
}

.server-banner h3 {
  color: #fda4af;
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
}

.server-banner p {
  color: #fecdd3;
  margin: 0;
  font-size: 0.95rem;
}

.dev-banner {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-left: 5px solid var(--color-emerald);
}

.dev-banner h3 {
  color: #a7f3d0;
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
}

.dev-banner p {
  color: #d1fae5;
  margin: 0;
  font-size: 0.95rem;
}

.warning-icon, .info-icon {
  font-size: 2rem;
  display: flex;
  align-items: center;
}

.sync-grid {
  display: grid;
  grid-template-columns: 1.2fr 1.8fr;
  gap: 1.5rem;
}

@media (max-width: 1024px) {
  .sync-grid {
    grid-template-columns: 1fr;
  }
}

.sync-left-column {
  display: flex;
  flex-direction: column;
}

.sync-right-column {
  display: flex;
  flex-direction: column;
}

.mt-6 {
  margin-top: 1.5rem;
}

.mt-4 {
  margin-top: 1rem;
}

.m-0 {
  margin: 0;
}

.w-full {
  width: 100%;
}

.flex {
  display: flex;
}

.justify-between {
  justify-content: space-between;
}

.items-center {
  align-items: center;
}

.mb-4 {
  margin-bottom: 1rem;
}

.card-glassmorphism {
  background: rgba(30, 41, 59, 0.45);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 20px;
  padding: 2rem;
  text-align: left;
  display: flex;
  flex-direction: column;
}

.control-card h2, .history-card h2 {
  font-size: 1.35rem;
  color: #f1f5f9;
  margin: 0 0 0.5rem 0;
}

.card-desc {
  color: #94a3b8;
  font-size: 0.9rem;
  margin: 0 0 1.5rem 0;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.form-group label {
  color: #cbd5e1;
  font-size: 0.85rem;
  font-weight: 600;
}

.form-group input {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #f8fafc;
  padding: 10px 14px;
  font-size: 0.95rem;
  outline: none;
  transition: all 0.2s;
}

.form-group input:focus {
  border-color: var(--color-indigo);
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.4);
}

.market-radio-group {
  display: flex;
  gap: 1.5rem;
  margin-top: 0.25rem;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #cbd5e1;
  font-size: 0.9rem;
  cursor: pointer;
}

.radio-label input {
  display: none;
}

.radio-custom {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  position: relative;
  transition: all 0.2s;
}

.radio-label input:checked + .radio-custom {
  border-color: var(--color-indigo);
  background: var(--color-indigo);
}

.radio-label input:checked + .radio-custom::after {
  content: '';
  width: 6px;
  height: 6px;
  background: #ffffff;
  border-radius: 50%;
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.network-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.network-actions .btn-primary {
  grid-column: span 2;
}

.btn-primary {
  background: linear-gradient(135deg, var(--color-indigo) 0%, #4f46e5 100%);
  border: none;
  border-radius: 12px;
  color: #ffffff;
  padding: 12px;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
}

.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  border-radius: 12px;
  padding: 10px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: #f8fafc;
}

.btn-secondary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-danger {
  background: linear-gradient(135deg, var(--color-rose) 0%, #e11d48 100%);
  border: none;
  border-radius: 12px;
  color: #ffffff;
  padding: 12px;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(244, 63, 94, 0.3);
}

.btn-danger:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(244, 63, 94, 0.4);
}

.btn-danger:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

.btn-refresh {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-refresh:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #f8fafc;
}

/* 터미널 스타일 */
.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.terminal-status {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.5px;
  background: rgba(255, 255, 255, 0.1);
  color: #94a3b8;
}

.terminal-status.idle {
  background: rgba(148, 163, 184, 0.15);
  color: #cbd5e1;
}

.terminal-status.running {
  background: rgba(99, 102, 241, 0.2);
  color: #a5b4fc;
  animation: pulse 1.5s infinite;
}

.terminal-status.success {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
}

.terminal-status.error {
  background: rgba(244, 63, 94, 0.2);
  color: #f87171;
}

.terminal-container {
  display: flex;
  flex-direction: column;
  background: #090d16;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  height: 400px;
  overflow: hidden;
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.8);
}

.terminal-header-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  background: #0f172a;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.terminal-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.terminal-dot.red { background: #ef4444; }
.terminal-dot.yellow { background: #f59e0b; }
.terminal-dot.green { background: #10b981; }

.terminal-title {
  color: #64748b;
  font-family: 'Fira Code', monospace;
  font-size: 0.75rem;
  margin-left: 8px;
}

.terminal-body {
  padding: 1rem;
  flex-grow: 1;
  overflow-y: auto;
  font-family: 'Fira Code', 'Courier New', Courier, monospace;
  font-size: 0.85rem;
  line-height: 1.45;
  color: #e2e8f0;
  text-align: left;
}

.terminal-line {
  margin-bottom: 0.35rem;
  white-space: pre-wrap;
  word-break: break-all;
}

.line-info {
  color: #38bdf8;
}

.line-warning {
  color: #fbbf24;
}

.line-error {
  color: #f87171;
}

.terminal-empty {
  color: #475569;
  text-align: center;
  margin-top: 8rem;
  font-size: 0.85rem;
}

/* 감사 리포트 */
.audit-report-container {
  background: #090d16;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 1.5rem;
  max-height: 400px;
  overflow-y: auto;
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.8);
}

.audit-pre {
  font-family: 'Fira Code', 'Courier New', Courier, monospace;
  font-size: 0.85rem;
  line-height: 1.5;
  color: #38bdf8;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.feedback-msg {
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 0.85rem;
  line-height: 1.4;
  margin-top: 1rem;
  text-align: left;
}

.feedback-msg.success {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
  color: #34d399;
}

.feedback-msg.error {
  background: rgba(244, 63, 94, 0.1);
  border: 1px solid rgba(244, 63, 94, 0.2);
  color: #f87171;
}

.loading-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 3rem 0;
  color: #a5b4fc;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* 모달 */
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(15, 23, 42, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 999;
}

.modal-content {
  max-width: 650px;
  width: 90%;
  max-height: 85vh;
  overflow-y: auto;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding-bottom: 1rem;
  margin-bottom: 1rem;
}

.modal-header h3 {
  color: #f8fafc;
  margin: 0;
  font-size: 1.25rem;
}

.btn-close {
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 1.25rem;
  cursor: pointer;
}

.btn-close:hover {
  color: #f8fafc;
}

.warning-text {
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 8px;
  padding: 0.85rem 1.25rem;
  font-size: 0.9rem;
  line-height: 1.5;
  margin-bottom: 1.5rem;
}

.confirm-step {
  margin-bottom: 1.5rem;
}

.confirm-step .instruction {
  color: #cbd5e1;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

.confirm-step .highlight {
  color: #f43f5e;
  font-weight: 700;
}

.confirm-input {
  width: 100%;
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  color: #ffffff;
  padding: 10px 14px;
  font-size: 1rem;
  text-align: center;
  letter-spacing: 1.5px;
  outline: none;
}

.confirm-input:focus {
  border-color: #f43f5e;
  box-shadow: 0 0 10px rgba(244, 63, 94, 0.3);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 페이드 트랜지션 */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
