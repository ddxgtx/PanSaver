<template>
  <div class="dashboard-container">
    <!-- Storage & Stats Overview -->
    <div class="overview-grid">
      <!-- Storage Quota Card -->
      <div class="glass-panel stat-card storage-card">
        <div class="card-header">
          <h3>网盘容量统计</h3>
          <el-icon color="#06b6d4"><Cpu /></el-icon>
        </div>
        <div class="quota-container">
          <el-progress 
            type="dashboard" 
            :percentage="quotaPercentage" 
            :color="colors"
            :stroke-width="10"
            :width="150"
          >
            <template #default="{ percentage }">
              <div class="percentage-value">{{ percentage.toFixed(1) }}%</div>
              <div class="percentage-label">已用容量</div>
            </template>
          </el-progress>
          <div class="quota-details">
            <div class="detail-item">
              <span class="label">总容量:</span>
              <span class="value">{{ formatBytes(stats.accounts.quota_total) }}</span>
            </div>
            <div class="detail-item">
              <span class="label">已使用:</span>
              <span class="value cyan-text">{{ formatBytes(stats.accounts.quota_used) }}</span>
            </div>
            <div class="detail-item">
              <span class="label">剩余空间:</span>
              <span class="value green-text">{{ formatBytes(stats.accounts.quota_total - stats.accounts.quota_used) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Quick Metrics Grid -->
      <div class="metrics-subgrid">
        <!-- Metric Card 1 -->
        <div class="glass-panel metric-card">
          <div class="metric-icon bg-indigo">
            <el-icon><UserFilled /></el-icon>
          </div>
          <div class="metric-info">
            <div class="metric-label">网盘账号</div>
            <div class="metric-value">{{ stats.accounts.active }} / {{ stats.accounts.total }}</div>
            <div class="metric-desc">有效 / 总数</div>
          </div>
        </div>
        <!-- Metric Card 2 -->
        <div class="glass-panel metric-card">
          <div class="metric-icon bg-cyan">
            <el-icon><Collection /></el-icon>
          </div>
          <div class="metric-info">
            <div class="metric-label">启用订阅</div>
            <div class="metric-value">{{ stats.subscriptions.enabled }} / {{ stats.subscriptions.total }}</div>
            <div class="metric-desc">监控进行中</div>
          </div>
        </div>
        <!-- Metric Card 3 -->
        <div class="glass-panel metric-card">
          <div class="metric-icon bg-success">
            <el-icon><CircleCheck /></el-icon>
          </div>
          <div class="metric-info">
            <div class="metric-label">今日成功转存</div>
            <div class="metric-value green-text">{{ stats.runs_today.success }}</div>
            <div class="metric-desc">次</div>
          </div>
        </div>
        <!-- Metric Card 4 -->
        <div class="glass-panel metric-card">
          <div class="metric-icon bg-danger">
            <el-icon><CircleClose /></el-icon>
          </div>
          <div class="metric-info">
            <div class="metric-label">今日运行失败</div>
            <div class="metric-value red-text">{{ stats.runs_today.failed }}</div>
            <div class="metric-desc">次错误警报</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Recent Run Logs Section -->
    <div class="glass-panel recent-runs-card">
      <div class="card-header">
        <h3>最近运行记录</h3>
        <el-button type="primary" link @click="$router.push('/history')">
          查看全部历史
          <el-icon class="el-icon--right"><ArrowRight /></el-icon>
        </el-button>
      </div>

      <el-table :data="stats.recent_runs" empty-text="暂无运行历史" style="width: 100%">
        <el-table-column prop="id" label="Run ID" width="100" />
        <el-table-column prop="sub_name" label="任务名称" />
        <el-table-column label="执行状态" width="150">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" effect="dark" round size="small">
              {{ row.status === 'success' ? '执行成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="运行时间" width="200">
          <template #default="{ row }">
            {{ row.started_at }}
          </template>
        </el-table-column>
        <el-table-column label="文件变动" width="180">
          <template #default="{ row }">
            <span class="green-text" v-if="row.added_count > 0">+{{ row.added_count }} 新文件</span>
            <span v-else class="text-muted">无变化</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const stats = ref({
  accounts: { total: 0, active: 0, quota_total: 0, quota_used: 0 },
  subscriptions: { total: 0, enabled: 0 },
  runs_today: { success: 0, failed: 0 },
  recent_runs: []
})

const colors = [
  { color: '#10b981', percentage: 50 },
  { color: '#eab308', percentage: 80 },
  { color: '#ef4444', percentage: 100 },
]

const quotaPercentage = computed(() => {
  const total = stats.value.accounts.quota_total
  if (!total) return 0
  return (stats.value.accounts.quota_used / total) * 100
})

const formatBytes = (bytes: number, decimals = 2) => {
  if (!bytes) return '0.00 GB'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  // We keep it minimum GB for better visualization
  if (i < 3) return '0.00 GB'
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
}

const loadStats = async () => {
  try {
    const res = await api.get('/api/system/stats')
    if (res.data.errno === 0) {
      stats.value = res.data
    } else {
      ElMessage.error('无法获取系统状态数据')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '连接服务器失败。')
  }
}

onMounted(() => {
  loadStats()
})
</script>

<style scoped>
.dashboard-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.overview-grid {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 20px;
}

@media (max-width: 1024px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 12px;
}

.card-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-card {
  padding: 24px;
  box-sizing: border-box;
}

.quota-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  margin-top: 10px;
}

.percentage-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.percentage-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.quota-details {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  padding-top: 15px;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

.detail-item .label {
  color: var(--text-secondary);
}

.detail-item .value {
  font-weight: 600;
}

.metrics-subgrid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 15px;
}

.metric-card {
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 20px;
}

.metric-icon {
  display: flex;
  padding: 12px;
  border-radius: 12px;
  font-size: 24px;
}

.bg-indigo {
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: #818cf8;
}

.bg-cyan {
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.2);
  color: #22d3ee;
}

.bg-success {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
  color: #34d399;
}

.bg-danger {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #f87171;
}

.metric-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.metric-desc {
  font-size: 11px;
  color: var(--text-muted);
}

.recent-runs-card {
  padding: 24px;
}

.cyan-text {
  color: var(--secondary-color);
}

.green-text {
  color: var(--success-color);
}

.red-text {
  color: var(--danger-color);
}
</style>
