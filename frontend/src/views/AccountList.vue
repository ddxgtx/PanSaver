<template>
  <div class="accounts-container">
    <div class="action-bar">
      <el-button type="primary" @click="showAddDialog = true">
        <el-icon class="el-icon--left"><Plus /></el-icon>
        添加网盘账号
      </el-button>
    </div>

    <!-- Accounts Grid -->
    <div class="accounts-grid" v-if="accounts.length > 0">
      <div 
        v-for="account in accounts" 
        :key="account.id" 
        class="glass-panel account-card"
      >
        <div class="card-header">
          <div class="user-profile">
            <div class="avatar">
              <el-icon :size="24" color="#6366f1"><UserFilled /></el-icon>
            </div>
            <div class="meta">
              <div class="name">{{ account.name }}</div>
              <div class="id-tag">ID: {{ account.id }}</div>
            </div>
          </div>
          <el-button 
            type="danger" 
            circle 
            plain 
            :icon="Delete" 
            @click="handleDelete(account)"
          />
        </div>

        <div class="card-body">
          <div class="quota-info">
            <div class="quota-labels">
              <span>空间使用量</span>
              <span>{{ formatBytes(account.quota_used) }} / {{ formatBytes(account.quota_total) }}</span>
            </div>
            <el-progress 
              :percentage="getPercentage(account.quota_used, account.quota_total)" 
              :color="quotaColor" 
              :show-text="false"
              class="quota-progress"
            />
          </div>
          
          <div class="card-actions" style="margin-top: 12px; margin-bottom: 12px; display: flex;">
            <el-button 
              type="primary" 
              size="small" 
              plain 
              style="width: 100%;" 
              :disabled="account.status !== 'active'"
              @click="openFileBrowser(account)"
            >
              <el-icon class="el-icon--left"><FolderOpened /></el-icon>
              浏览网盘文件
            </el-button>
          </div>

          <div class="card-footer">
            <el-tag :type="account.status === 'active' ? 'success' : 'danger'" effect="dark" size="small">
              {{ account.status === 'active' ? '正常运行' : '失效/需重绑' }}
            </el-tag>
            <span class="verify-time">校验于: {{ account.last_verified_at || '未校验' }}</span>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-else description="暂无绑定账号，请先添加" />

    <!-- Add Account Dialog -->
    <el-dialog 
      v-model="showAddDialog" 
      title="绑定百度网盘账号" 
      width="500px"
      @open="onDialogOpened"
      @closed="resetForm"
    >
      <el-tabs v-model="activeTab" class="login-tabs">
        <!-- QR Code Login Tab -->
        <el-tab-pane label="扫码登录 (推荐)" name="qr">
          <div class="qr-login-container">
            <div v-if="qrLoading" class="qr-loading-box">
              <el-icon class="is-loading" :size="30" color="#6366f1"><Loading /></el-icon>
              <span class="qr-tip-text">正在生成登录二维码...</span>
            </div>
            <div v-else-if="qrExpired" class="qr-expired-box" @click="initQrCode">
              <div class="qr-refresh-overlay">
                <el-icon :size="40" color="#ffffff"><Refresh /></el-icon>
                <span>二维码已过期，点击刷新</span>
              </div>
              <img :src="qrImgUrl" class="qr-code-img expired" alt="Expired QR Code" />
            </div>
            <div v-else class="qr-code-box">
              <img :src="qrImgUrl" class="qr-code-img" alt="Baidu Login QR Code" />
            </div>
            
            <div class="qr-status-msg" :class="qrStatus">
              <span>{{ qrStatusMessage }}</span>
            </div>
            
            <div class="qr-guide-steps">
              <p>1. 打开手机端 <strong>百度网盘 App</strong></p>
              <p>2. 点击右上角 <strong>「+」 ➔ 「扫一扫」</strong> 进行扫码</p>
              <p>3. 扫码后在手机端点击<strong>确认登录</strong>，系统将自动保存绑定</p>
            </div>
          </div>
        </el-tab-pane>

        <!-- Manual Cookie Input Tab -->
        <el-tab-pane label="手动输入 Cookie" name="manual">
          <el-form :model="form" :rules="rules" ref="formRef" label-position="top" style="margin-top: 15px;">
            <el-form-item label="账号显示名称" prop="name">
              <el-input v-model="form.name" placeholder="请输入自定义名称，如: 备份主账号" />
            </el-form-item>

            <el-form-item label="BDUSS (Cookie)" prop="bduss">
              <el-input 
                v-model="form.bduss" 
                type="textarea" 
                rows="3" 
                placeholder="请输入百度网盘网页登录后的 BDUSS 值" 
              />
            </el-form-item>

            <el-form-item label="STOKEN (Cookie, 选填)" prop="stoken">
              <el-input 
                v-model="form.stoken" 
                type="textarea" 
                rows="2" 
                placeholder="如需创建分享链接，请提供 STOKEN 凭证" 
              />
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <template #footer v-if="activeTab === 'manual'">
        <div class="dialog-footer">
          <el-button 
            type="info" 
            plain 
            :loading="verifying" 
            @click="testConnection"
          >
            测试连接
          </el-button>
          <div>
            <el-button @click="showAddDialog = false">取消</el-button>
            <el-button type="primary" :loading="submitting" @click="submitForm">
              确认绑定
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- Real-time File Browser Dialog -->
    <el-dialog
      v-model="showBrowserDialog"
      :title="`实时网盘内容 - ${currentBrowserAccount?.name}`"
      width="780px"
      destroy-on-close
    >
      <div class="browser-container">
        <div class="browser-actions" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; gap: 10px;">
          <el-button 
            size="small" 
            :disabled="currentPath === '/'" 
            @click="goBackPath"
            :icon="ArrowLeft"
          >
            返回上一级
          </el-button>
          <div class="current-path" style="font-family: monospace; font-size: 13px; color: var(--el-text-color-regular); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 500px;">
            当前路径: {{ currentPath }}
          </div>
          <el-button size="small" type="primary" :icon="Refresh" @click="fetchFiles">刷新</el-button>
        </div>

        <el-table 
          v-loading="loadingFiles" 
          :data="files" 
          height="400px" 
          style="width: 100%"
          empty-text="此文件夹为空"
        >
          <el-table-column label="文件名" min-width="350">
            <template #default="{ row }">
              <div 
                style="display: flex; align-items: center; cursor: pointer; padding: 4px 0;"
                @click="row.isdir === 1 ? enterFolder(row.path) : null"
              >
                <el-icon :size="20" style="margin-right: 8px;" :color="row.isdir === 1 ? '#e6a23c' : '#409eff'">
                  <Folder v-if="row.isdir === 1" />
                  <Document v-else />
                </el-icon>
                <span :style="{ fontWeight: row.isdir === 1 ? '600' : 'normal', color: row.isdir === 1 ? 'var(--el-color-primary)' : 'inherit' }">
                  {{ getFilename(row.path) }}
                </span>
              </div>
            </template>
          </el-table-column>
          
          <el-table-column label="大小" width="120">
            <template #default="{ row }">
              <span>{{ row.isdir === 1 ? '-' : formatBytes(row.size) }}</span>
            </template>
          </el-table-column>
          
          <el-table-column label="修改时间" width="180">
            <template #default="{ row }">
              <span>{{ formatTime(row.mtime) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Loading, Refresh, FolderOpened, Folder, Document, ArrowLeft } from '@element-plus/icons-vue'
import api from '../api'

const accounts = ref<any[]>([])
const showAddDialog = ref(false)
const verifying = ref(false)
const submitting = ref(false)
const formRef = ref()

// QR scan states
const activeTab = ref('qr')
const qrLoading = ref(true)
const qrExpired = ref(false)
const qrImgUrl = ref('')
const qrSessionId = ref('')
const qrStatus = ref('waiting')
const qrStatusMessage = ref('正在准备二维码...')
const pollingTimer = ref<any>(null)

const initQrCode = async () => {
  qrLoading.value = true
  qrExpired.value = false
  qrStatus.value = 'waiting'
  qrStatusMessage.value = '正在加载二维码...'
  
  if (pollingTimer.value) {
    clearTimeout(pollingTimer.value)
    pollingTimer.value = null
  }

  try {
    const res = await api.get('/api/accounts/qr/init')
    if (res.data.errno === 0) {
      qrImgUrl.value = res.data.imgurl
      qrSessionId.value = res.data.session_id
      qrLoading.value = false
      qrStatusMessage.value = '请使用手机端网盘 App 扫描二维码'
      startPolling()
    } else {
      ElMessage.error(res.data.error || '获取登录二维码失败')
    }
  } catch (e) {
    ElMessage.error('初始化扫码登录接口异常')
  }
}

const startPolling = () => {
  const poll = async () => {
    if (!qrSessionId.value || showAddDialog.value === false) return
    
    try {
      const res = await api.get('/api/accounts/qr/status', {
        params: { session_id: qrSessionId.value }
      })
      
      if (res.data.errno === 0) {
        const status = res.data.status
        if (status === 'waiting') {
          qrStatus.value = 'waiting'
          qrStatusMessage.value = '请使用手机端网盘 App 扫描二维码'
          // Schedule next poll only after current one completes
          pollingTimer.value = setTimeout(poll, 1500)
        } else if (status === 'scanned') {
          qrStatus.value = 'scanned'
          qrStatusMessage.value = '已扫描！请在手机上点击确认登录'
          // Schedule next poll
          pollingTimer.value = setTimeout(poll, 1500)
        } else if (status === 'success') {
          qrStatus.value = 'success'
          qrStatusMessage.value = `绑定成功！正在载入账号: ${res.data.nickname}`
          ElMessage.success(`网盘账号「${res.data.nickname}」绑定成功！`)
          
          pollingTimer.value = null
          
          setTimeout(() => {
            showAddDialog.value = false
            loadAccounts()
          }, 1500)
        } else if (status === 'expired') {
          qrExpired.value = true
          qrStatusMessage.value = '二维码已过期，请刷新'
          pollingTimer.value = null
        }
      } else {
        // Retry after delay
        pollingTimer.value = setTimeout(poll, 2000)
      }
    } catch (e) {
      // Retry after delay on network error
      pollingTimer.value = setTimeout(poll, 2000)
    }
  }
  
  // Launch the first poll
  pollingTimer.value = setTimeout(poll, 1500)
}

const onDialogOpened = () => {
  activeTab.value = 'qr'
  initQrCode()
}

const form = reactive({
  name: '',
  bduss: '',
  stoken: ''
})

const rules = {
  name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  bduss: [{ required: true, message: '请输入 BDUSS 凭证', trigger: 'blur' }]
}

const quotaColor = [
  { color: '#10b981', percentage: 60 },
  { color: '#f59e0b', percentage: 85 },
  { color: '#ef4444', percentage: 100 }
]

const formatBytes = (bytes: number, decimals = 2) => {
  if (!bytes) return '0.00 GB'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  if (i < 3) return '0.00 GB'
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
}

const getPercentage = (used: number, total: number) => {
  if (!total) return 0
  return Math.min((used / total) * 100, 100)
}

const loadAccounts = async () => {
  try {
    const res = await api.get('/api/accounts')
    accounts.value = res.data
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '加载账号失败。')
  }
}

const testConnection = async () => {
  if (!form.bduss) {
    return ElMessage.warning('请输入 BDUSS 才能进行测试连接！')
  }
  
  verifying.value = true
  try {
    const res = await api.post('/api/accounts/verify', {
      bduss: form.bduss,
      stoken: form.stoken
    })
    if (res.data.errno === 0) {
      ElMessage.success(`连接测试成功！账号昵称: ${res.data.nickname}`)
    } else {
      ElMessage.error(res.data.error || '测试失败。')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '连接测试异常，请检查凭证是否有效。')
  } finally {
    verifying.value = false
  }
}

const submitForm = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    
    submitting.value = true
    try {
      const res = await api.post('/api/accounts', form)
      if (res.data.errno === 0) {
        ElMessage.success('账号绑定成功！')
        showAddDialog.value = false
        loadAccounts()
      } else {
        ElMessage.error(res.data.error || '绑定失败。')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || '绑定失败，请检查 Cookie 有效性。')
    } finally {
      submitting.value = false
    }
  })
}

const handleDelete = (account: any) => {
  ElMessageBox.confirm(
    `确定要解除网盘账号「${account.name}」的绑定吗？`,
    '安全警告',
    {
      confirmButtonText: '确定解绑',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      const res = await api.delete(`/api/accounts/${account.id}`)
      if (res.data.errno === 0) {
        ElMessage.success('已解除账号绑定')
        loadAccounts()
      } else {
        ElMessage.error(res.data.error || '解除绑定失败')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || '服务器请求异常。')
    }
  }).catch(() => {})
}

const resetForm = () => {
  if (pollingTimer.value) {
    clearTimeout(pollingTimer.value)
    pollingTimer.value = null
  }
  qrSessionId.value = ''
  qrImgUrl.value = ''
  form.name = ''
  form.bduss = ''
  form.stoken = ''
}

// File Browser states
const showBrowserDialog = ref(false)
const currentBrowserAccount = ref<any>(null)
const currentPath = ref('/')
const files = ref<any[]>([])
const loadingFiles = ref(false)

const openFileBrowser = (account: any) => {
  currentBrowserAccount.value = account
  currentPath.value = '/'
  showBrowserDialog.value = true
  fetchFiles()
}

const fetchFiles = async () => {
  if (!currentBrowserAccount.value) return
  loadingFiles.value = true
  try {
    const res = await api.get(`/api/accounts/${currentBrowserAccount.value.id}/files`, {
      params: { path: currentPath.value }
    })
    if (res.data.errno === 0) {
      files.value = res.data.list || []
    } else {
      ElMessage.error(res.data.error || '获取网盘文件列表失败')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '请求网盘文件列表异常')
  } finally {
    loadingFiles.value = false
  }
}

const enterFolder = (path: string) => {
  currentPath.value = path
  fetchFiles()
}

const goBackPath = () => {
  if (currentPath.value === '/') return
  const parts = currentPath.value.split('/')
  parts.pop()
  const parent = parts.join('/')
  currentPath.value = parent === '' ? '/' : parent
  fetchFiles()
}

const getFilename = (path: string) => {
  if (path === '/') return '/'
  const parts = path.split('/')
  return parts[parts.length - 1] || path
}

const formatTime = (timestamp: any) => {
  if (!timestamp) return '-'
  const date = new Date(Number(timestamp) * 1000)
  const Y = date.getFullYear()
  const M = String(date.getMonth() + 1).padStart(2, '0')
  const D = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const m = String(date.getMinutes()).padStart(2, '0')
  const s = String(date.getSeconds()).padStart(2, '0')
  return `${Y}-${M}-${D} ${h}:${m}:${s}`
}

onMounted(() => {
  loadAccounts()
})
</script>

<style scoped>
.accounts-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.action-bar {
  display: flex;
  justify-content: flex-end;
}

.accounts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.account-card {
  padding: 24px;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 15px;
}

.avatar {
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.15);
  padding: 10px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.id-tag {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

.card-body {
  margin-top: 24px;
}

.quota-labels {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.quota-progress {
  margin-bottom: 20px;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  padding-top: 15px;
}

.verify-time {
  font-size: 11px;
  color: var(--text-muted);
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  width: 100%;
}

/* QR login panel styling */
.login-tabs :deep(.el-tabs__header) {
  margin-bottom: 20px;
}

.qr-login-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 0;
  text-align: center;
}

.qr-loading-box, .qr-expired-box, .qr-code-box {
  width: 180px;
  height: 180px;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--panel-border);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  cursor: pointer;
}

.qr-tip-text {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 12px;
}

.qr-code-img {
  width: 160px;
  height: 160px;
  display: block;
}

.qr-code-img.expired {
  filter: blur(4px) opacity(0.3);
}

.qr-refresh-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 5;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 12px;
  color: #ffffff;
  font-weight: 500;
}

.qr-status-msg {
  margin-top: 15px;
  font-size: 13px;
  font-weight: 600;
  padding: 6px 16px;
  border-radius: 20px;
  transition: all 0.3s;
}

.qr-status-msg.waiting {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-secondary);
}

.qr-status-msg.scanned {
  background: rgba(234, 179, 8, 0.1);
  border: 1px solid rgba(234, 179, 8, 0.2);
  color: #facc15;
}

.qr-status-msg.success {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
  color: #34d399;
}

.qr-guide-steps {
  margin-top: 20px;
  text-align: left;
  width: 100%;
  max-width: 380px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 12px 20px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.qr-guide-steps p {
  margin: 4px 0;
}
</style>
