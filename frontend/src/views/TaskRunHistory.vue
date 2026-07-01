<template>
  <div class="history-container">
    <!-- Filter Toolbar -->
    <div class="glass-panel filter-bar">
      <el-form :inline="true" :model="filters" size="default">
        <el-form-item label="选择订阅任务">
          <el-select v-model="filters.subId" clearable placeholder="全部任务" style="width: 200px" @change="loadRuns">
            <el-option 
              v-for="sub in subscriptions" 
              :key="sub.id" 
              :label="sub.name" 
              :value="sub.id" 
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadRuns">
            <el-icon class="el-icon--left"><Refresh /></el-icon>
            刷新记录
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- History Table -->
    <div class="glass-panel table-wrapper">
      <el-table :data="runs" empty-text="暂无任务运行记录" style="width: 100%">
        <el-table-column prop="id" label="Run ID" width="80" />
        <el-table-column prop="sub_name" label="任务名称" min-width="150" />
        
        <el-table-column label="执行触发" width="100">
          <template #default="{ row }">
            <el-tag :type="row.trigger_type === 'scheduler' ? 'info' : 'warning'" size="small">
              {{ row.trigger_type === 'scheduler' ? '定时计划' : '手动立即' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="执行状态" width="110">
          <template #default="{ row }">
            <el-tag :type="getStatusTag(row.status)" effect="dark" round size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="started_at" label="开始时间" width="170" />
        <el-table-column prop="finished_at" label="完成时间" width="170" />
        
        <el-table-column label="文件变动统计" min-width="180">
          <template #default="{ row }">
            <div v-if="row.status === 'success'" class="changes-stats">
              <span class="stat green" v-if="row.added_count > 0">+{{ row.added_count }}</span>
              <span class="stat yellow" v-if="row.modified_count > 0">~{{ row.modified_count }}</span>
              <span class="stat red" v-if="row.deleted_count > 0">-{{ row.deleted_count }}</span>
              <span v-if="row.added_count == 0 && row.modified_count == 0 && row.deleted_count == 0" class="text-muted">无变化</span>
            </div>
            <div v-else-if="row.status === 'failed'" class="error-msg text-ellipsis" :title="row.error_message">
              {{ row.error_message || '未知错误' }}
            </div>
            <span v-else class="text-muted">正在传输...</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" plain @click="openLogsDialog(row)">
              运行日志
            </el-button>
            <el-button 
              type="success" 
              size="small" 
              plain 
              :disabled="row.status !== 'success'" 
              @click="openDiffDialog(row)"
            >
              文件差异
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          layout="total, prev, pager, next"
          :total="totalCount"
          @current-change="handlePageChange"
        />
      </div>
    </div>

    <!-- Logs Dialog -->
    <el-dialog 
      v-model="showLogs" 
      title="运行任务终端" 
      width="820px"
    >
      <div class="terminal-container">
        <div class="terminal-header">
          <div class="terminal-dots">
            <span class="dot red"></span>
            <span class="dot yellow"></span>
            <span class="dot green"></span>
          </div>
          <div class="terminal-title">Task Terminal - Run #{{ activeRunId }}</div>
        </div>
        <div class="logs-console">
          <div 
            v-for="(log, idx) in logs" 
            :key="idx" 
            :class="['log-line', log.level]"
          >
            <span class="log-time">[{{ log.created_at }}]</span>
            <span class="log-level">[{{ log.level.toUpperCase() }}]</span>
            <span class="log-stage">[{{ log.stage }}]</span>
            <span class="log-msg">{{ log.message }}</span>
          </div>
          <div v-if="logs.length === 0" class="log-empty">正在加载日志或暂无运行日志...</div>
        </div>
      </div>
    </el-dialog>

    <!-- Diffs Dialog -->
    <el-dialog 
      v-model="showDiffs" 
      :title="'文件变动详情 - Run #' + activeRunId" 
      width="750px"
    >
      <el-tabs v-model="activeTab">
        <el-tab-pane label="新增文件" name="added">
          <div class="diff-list" v-if="diffs.added.length > 0">
            <div v-for="f in diffs.added" :key="f.relative_path" class="diff-item green-text">
              <el-icon><DocumentAdd /></el-icon>
              <span class="diff-path">{{ f.relative_path }}</span>
              <span class="diff-size">({{ formatBytes(f.file_size) }})</span>
            </div>
          </div>
          <el-empty v-else description="无新增文件" />
        </el-tab-pane>

        <el-tab-pane label="修改文件" name="modified">
          <div class="diff-list" v-if="diffs.modified.length > 0">
            <div v-for="f in diffs.modified" :key="f.relative_path" class="diff-item yellow-text">
              <el-icon><EditPen /></el-icon>
              <span class="diff-path">{{ f.relative_path }}</span>
              <span class="diff-size">({{ formatBytes(f.file_size) }})</span>
            </div>
          </div>
          <el-empty v-else description="无修改文件" />
        </el-tab-pane>

        <el-tab-pane label="重命名/移动" name="renamed">
          <div class="diff-list" v-if="diffs.renamed.length > 0">
            <div v-for="f in diffs.renamed" :key="f.from" class="diff-item blue-text">
              <el-icon><RefreshRight /></el-icon>
              <span class="diff-path">「{{ f.from }}」 ➔ 「{{ f.to }}」</span>
            </div>
          </div>
          <el-empty v-else description="无重命名文件" />
        </el-tab-pane>

        <el-tab-pane label="已删除" name="deleted">
          <div class="diff-list" v-if="diffs.deleted.length > 0">
            <div v-for="f in diffs.deleted" :key="f.relative_path" class="diff-item red-text">
              <el-icon><DocumentDelete /></el-icon>
              <span class="diff-path">{{ f.relative_path }}</span>
            </div>
          </div>
          <el-empty v-else description="无删除文件" />
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import api from '../api'

const runs = ref<any[]>([])
const subscriptions = ref<any[]>([])
const totalCount = ref(0)
const currentPage = ref(1)
const pageSize = ref(15)

const showLogs = ref(false)
const showDiffs = ref(false)
const activeRunId = ref<number | null>(null)
const activeTab = ref('added')

const logs = ref<any[]>([])
const diffs = ref({
  added: [] as any[],
  modified: [] as any[],
  deleted: [] as any[],
  renamed: [] as any[]
})

const filters = reactive({
  subId: undefined
})

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    running: '运行中',
    success: '成功',
    failed: '失败',
    cancelled: '已取消'
  }
  return map[status] || status
}

const getStatusTag = (status: string) => {
  const map: Record<string, string> = {
    running: 'primary',
    success: 'success',
    failed: 'danger',
    cancelled: 'info'
  }
  return map[status] || 'info'
}

const formatBytes = (bytes: number, decimals = 2) => {
  if (!bytes) return '0.00 GB'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  if (i < 3) return '0.00 GB'
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
}

const loadRuns = async () => {
  try {
    const params: any = {
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value
    }
    if (filters.subId) {
      params.subscription_id = filters.subId
    }
    
    const res = await api.get('/api/tasks/runs', { params })
    runs.value = res.data
    // For pagination total estimation (mock or read total from headers)
    totalCount.value = res.data.length + (res.data.length === pageSize.value ? 20 : 0)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '无法获取运行历史。')
  }
}

const loadSubscriptions = async () => {
  try {
    const res = await api.get('/api/subscriptions')
    subscriptions.value = res.data
  } catch (e) {}
}

const openLogsDialog = async (row: any) => {
  activeRunId.value = row.id
  showLogs.value = true
  logs.value = []
  
  try {
    const res = await api.get(`/api/tasks/runs/${row.id}/logs`)
    logs.value = res.data
  } catch (e) {
    ElMessage.error('获取日志失败。')
  }
}

const openDiffDialog = async (row: any) => {
  activeRunId.value = row.id
  showDiffs.value = true
  activeTab.value = 'added'
  diffs.value = { added: [], modified: [], deleted: [], renamed: [] }
  
  try {
    const res = await api.get(`/api/tasks/runs/${row.id}/diff`)
    diffs.value = res.data
  } catch (e) {
    ElMessage.error('获取文件差异详情失败。')
  }
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadRuns()
}

onMounted(() => {
  loadRuns()
  loadSubscriptions()
})
</script>

<style scoped>
.history-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.filter-bar {
  padding: 15px 20px;
}

.filter-bar :deep(.el-form-item) {
  margin-bottom: 0 !important;
}

.table-wrapper {
  padding: 15px;
  display: flex;
  flex-direction: column;
}

.pagination-bar {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.changes-stats {
  display: flex;
  gap: 8px;
  font-weight: 600;
  font-size: 13px;
}

.stat {
  padding: 2px 6px;
  border-radius: 4px;
}

.stat.green {
  background: rgba(16, 185, 129, 0.1);
  color: var(--success-color);
}

.stat.yellow {
  background: rgba(245, 158, 11, 0.1);
  color: var(--warning-color);
}

.stat.red {
  background: rgba(239, 68, 68, 0.1);
  color: var(--danger-color);
}

.error-msg {
  color: var(--danger-color);
  font-size: 12px;
  max-width: 250px;
}

.text-ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Console logs styling */
.terminal-container {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  border: 1px solid var(--panel-border);
}

.terminal-header {
  background-color: #1e293b;
  height: 36px;
  display: flex;
  align-items: center;
  padding: 0 15px;
  position: relative;
}

.terminal-dots {
  display: flex;
  gap: 6px;
}

.terminal-dots .dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}

.terminal-dots .dot.red { background-color: #ef4444; }
.terminal-dots .dot.yellow { background-color: #eab308; }
.terminal-dots .dot.green { background-color: #10b981; }

.terminal-title {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  font-family: monospace;
}

.logs-console {
  background-color: #080c14;
  padding: 20px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
  line-height: 1.6;
  max-height: 480px;
  overflow-y: auto;
  color: #e2e8f0;
}

.log-line {
  margin-bottom: 6px;
}

.log-line.error {
  color: #f87171;
}

.log-line.warning {
  color: #fbbf24;
}

.log-time {
  color: #6b7280;
  margin-right: 8px;
}

.log-level {
  color: #818cf8;
  margin-right: 8px;
}

.log-stage {
  color: #22d3ee;
  margin-right: 8px;
}

.log-empty {
  color: #6b7280;
  text-align: center;
  padding: 20px;
}

/* Diff viewer styling */
.diff-list {
  max-height: 400px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 0;
}

.diff-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-radius: 6px;
}

.diff-path {
  font-family: monospace;
  flex-grow: 1;
}

.diff-size {
  color: var(--text-muted);
  font-size: 12px;
}

.green-text { color: var(--success-color); }
.yellow-text { color: var(--warning-color); }
.red-text { color: var(--danger-color); }
.blue-text { color: var(--secondary-color); }
</style>
