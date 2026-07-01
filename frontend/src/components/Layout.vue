<template>
  <div class="layout-container">
    <!-- Sidebar -->
    <aside class="sidebar glass-panel">
      <div class="brand">
        <el-icon :size="26" color="#6366f1"><Cloudy /></el-icon>
        <span class="brand-text">PanSave</span>
      </div>

      <nav class="nav-menu">
        <router-link 
          v-for="item in menuItems" 
          :key="item.path" 
          :to="item.path"
          class="nav-item"
          active-class="active"
        >
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <span class="nav-text">{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="user-info">
          <el-icon :size="18"><User /></el-icon>
          <span class="username">管理员</span>
        </div>
        <button class="logout-btn" @click="handleLogout">
          <el-icon :size="16"><SwitchButton /></el-icon>
        </button>
      </div>
    </aside>

    <!-- Main Content Area -->
    <div class="main-area">
      <header class="header glass-panel">
        <div class="header-left">
          <h1 class="page-title">{{ currentPageTitle }}</h1>
        </div>
        <div class="header-right">
          <el-tag type="success" effect="dark" round class="status-tag">
            服务运行中
          </el-tag>
        </div>
      </header>

      <main class="content-viewport">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'

const router = useRouter()
const route = useRoute()

const menuItems = [
  { path: '/dashboard', label: '主页概览', icon: 'Odometer' },
  { path: '/accounts', label: '网盘账号', icon: 'UserFilled' },
  { path: '/subscriptions', label: '订阅管理', icon: 'Collection' },
  { path: '/history', label: '运行历史', icon: 'Clock' },
  { path: '/settings', label: '系统设置', icon: 'Setting' }
]

const currentPageTitle = computed(() => {
  const matched = menuItems.find(item => route.path.startsWith(item.path))
  return matched ? matched.label : '控制台'
})

const handleLogout = async () => {
  try {
    await api.post('/api/auth/logout')
  } catch (e) {}
  localStorage.removeItem('pansave_token')
  ElMessage.success('已安全退出登录')
  router.push('/login')
}
</script>

<style scoped>
.layout-container {
  display: flex;
  min-height: 100vh;
  box-sizing: border-box;
}

.sidebar {
  position: fixed;
  top: 15px;
  left: 15px;
  bottom: 15px;
  width: var(--sidebar-width);
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  padding: 25px 15px;
  box-sizing: border-box;
  z-index: 10;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px 30px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.brand-text {
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(135deg, #fff 0%, var(--primary-color) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.nav-menu {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 25px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 15px;
  color: var(--text-secondary);
  text-decoration: none;
  border-radius: 10px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
}

.nav-item.active {
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: #a5b4fc;
}

.sidebar-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 10px 0 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 14px;
}

.logout-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
}

.logout-btn:hover {
  background: rgba(239, 68, 68, 0.12);
  color: var(--danger-color);
}

/* Main Area */
.main-area {
  flex-grow: 1;
  margin-left: calc(var(--sidebar-width) + 30px);
  padding: 15px 15px 15px 0;
  display: flex;
  flex-direction: column;
  gap: 15px;
  box-sizing: border-box;
}

.header {
  height: 64px;
  padding: 0 25px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-radius: 16px;
}

.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.content-viewport {
  flex-grow: 1;
  min-height: 0;
}

/* Page transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
