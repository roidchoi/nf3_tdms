<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()

// 메뉴 아이템 정의
const menuItems = [
  { name: '대시보드', path: '/', icon: '📊' },
  { name: '스케줄 관리', path: '/schedules', icon: '📅' },
  { name: '데이터 품질', path: '/health', icon: '❤️' },
  { name: '데이터 탐색', path: '/explorer', icon: '💾' },
  { name: 'API 진단', path: '/api-debugger', icon: '🔍' }, // 신규
]

// 현재 경로 확인 함수
const isActive = (path: string) => route.path === path
</script>

<template>
  <aside class="sidebar">
    <div class="logo-area">
      <h1>KDMS <span class="version">v6.0</span></h1>
    </div>

    <nav class="menu">
      <RouterLink
        v-for="item in menuItems"
        :key="item.path"
        :to="item.path"
        class="menu-item"
        :class="{ active: isActive(item.path) }"
      >
        <span class="icon">{{ item.icon }}</span>
        <span class="text">{{ item.name }}</span>
      </RouterLink>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 200px;
  background-color: #1e293b; /* 짙은 남색 */
  color: white;
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 1000;
}

.logo-area {
  padding: 1.5rem;
  border-bottom: 1px solid #334155;
}

.logo-area h1 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: bold;
  color: #f8fafc;
}

.version {
  font-size: 0.8rem;
  color: #94a3b8;
  margin-left: 5px;
}

.menu {
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.menu-item {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  color: #cbd5e1;
  text-decoration: none;
  border-radius: 6px;
  transition: all 0.2s;
}

.menu-item:hover {
  background-color: #334155;
  color: white;
}

.menu-item.active {
  background-color: #2563eb; /* 파란색 강조 */
  color: white;
  font-weight: 600;
}

.icon {
  margin-right: 10px;
  font-size: 1.1rem;
}
</style>