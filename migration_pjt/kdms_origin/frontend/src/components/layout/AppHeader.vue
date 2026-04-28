<script setup lang="ts">
import { useAdminStore } from '@/stores/adminStore'

const adminStore = useAdminStore()
</script>

<template>
  <header class="header">
    <div class="header-left">
      <h2 class="page-title">운영 대시보드</h2>
    </div>
    
    <div class="header-right">
      <div class="status-indicator" :class="{ connected: adminStore.wsConnected }">
        <span class="dot"></span>
        {{ adminStore.wsConnected ? '실시간 연결됨' : '연결 끊김' }}
      </div>
    </div>
  </header>
</template>

<style scoped>
.header {
  height: 64px;
  background: white;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2rem;
  position: sticky;
  top: 0;
  z-index: 10;
}

.page-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  color: #ef4444; /* 기본 빨간색 */
  background: #fef2f2;
  padding: 0.4rem 0.8rem;
  border-radius: 20px;
  font-weight: 500;
}

.status-indicator.connected {
  color: #10b981; /* 초록색 */
  background: #ecfdf5;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: currentColor;
}
</style>