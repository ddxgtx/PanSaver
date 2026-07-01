<template>
  <div class="subs-container">
    <div class="action-bar">
      <el-button type="primary" @click="openAddDialog">
        <el-icon class="el-icon--left"><Plus /></el-icon>
        新建订阅任务
      </el-button>
    </div>

    <!-- Subscriptions Table -->
    <div class="glass-panel table-wrapper">
      <el-table :data="subscriptions" empty-text="暂无订阅任务，点击右上角新建" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="任务名称" min-width="150" />
        
        <el-table-column label="订阅类型" width="120">
          <template #default="{ row }">
            <el-tag :type="getTypeTag(row.source_type)" size="small">
              {{ getTypeLabel(row.source_type) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="转存策略" width="130">
          <template #default="{ row }">
            <el-tag type="info" effect="plain" size="small">
              {{ getStrategyLabel(row.transfer_strategy) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="cron_expression" label="Cron 规则" width="120" />
        <el-table-column prop="next_run_at" label="下次执行时间" width="180" />
        
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-switch 
              v-model="row.enabled" 
              :active-value="1" 
              :inactive-value="0"
              @change="toggleStatus(row)"
            />
          </template>
        </el-table-column>

        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button type="success" size="small" @click="triggerTask(row)">
                立即执行
              </el-button>
              <el-button type="primary" size="small" :icon="Edit" @click="openEditDialog(row)">
                编辑
              </el-button>
              <el-button type="danger" size="small" :icon="Delete" @click="handleDelete(row)">
                删除
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Task Dialog (Create / Edit) -->
    <el-dialog 
      v-model="showDialog" 
      :title="isEdit ? '编辑订阅任务' : '新建订阅任务'" 
      width="680px"
      @closed="resetForm"
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-position="top">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="任务名称" prop="name">
              <el-input v-model="form.name" placeholder="请输入任务名称，如: 极客课程自动同步" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="转存网盘账号" prop="account_id">
              <el-select v-model="form.account_id" placeholder="选择转存所用的有效网盘账号">
                <el-option 
                  v-for="acc in accounts" 
                  :key="acc.id" 
                  :label="acc.name" 
                  :value="acc.id" 
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="订阅源类型" prop="source_type">
              <el-select v-model="form.source_type" placeholder="选择监控的源类型">
                <el-option label="百度分享链接" value="baidu_share" />
                <el-option label="RSS 订阅源" value="rss" />
                <el-option label="JSON 接口" value="json" />
                <el-option label="普通网页" value="webpage" />
                <el-option label="正则自定义抓取" value="regex" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="网盘目标路径" prop="target_path">
              <el-input v-model="form.target_path" placeholder="网盘存放目标文件夹，如: /自动转存/课程" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item 
          v-if="form.source_type !== 'baidu_share'" 
          label="订阅源地址 (URL)" 
          prop="source_url"
        >
          <el-input v-model="form.source_url" placeholder="监控页面的 URL，如: https://rsshub.app/..." />
        </el-form-item>

        <el-row :gutter="20" v-if="form.source_type === 'baidu_share'">
          <el-col :span="24">
            <el-form-item label="一键智能解析（在此直接粘贴带提取码的整段网盘分享文本）">
              <el-input 
                v-model="importText" 
                placeholder="粘贴包含链接和密码的文字，如：链接: https://pan.baidu.com/s/xxxx 提取码: abcd" 
                clearable
                @input="handleImportText"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="16">
            <el-form-item label="百度分享链接 (非直链监控可留空)" prop="share_url">
              <el-input v-model="form.share_url" placeholder="如: https://pan.baidu.com/s/..." />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="提取码/密码" prop="share_password">
              <el-input v-model="form.share_password" placeholder="4位分享密码" maxLength="4" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="转存执行策略" prop="transfer_strategy">
              <el-select v-model="form.transfer_strategy" placeholder="文件对比后的处理策略">
                <el-option label="仅检测并通知" value="notify_only" />
                <el-option label="增量转存 (仅复制新文件)" value="incremental" />
                <el-option label="版本归档 (以日期单独存放)" value="version_archive" />
                <el-option label="安全覆盖 (事务回滚覆盖)" value="safe_overwrite" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Cron 执行规则" prop="cron_expression">
              <el-input v-model="form.cron_expression" placeholder="如: */30 * * * * (每30分钟)" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- Advanced configurations collapsed -->
        <el-collapse class="advanced-collapse">
          <el-collapse-item title="高级配置（文件正则过滤与重命名）" name="1">
            <el-form-item label="包含过滤正则">
              <el-input v-model="advanced.include" placeholder="只保存匹配该正则的文件，如: .*\.mp4$" />
            </el-form-item>
            <el-form-item label="排除过滤正则">
              <el-input v-model="advanced.exclude" placeholder="排除符合该正则的文件，如: .*\.tmp$" />
            </el-form-item>
            <el-form-item label="重命名规则列表 (JSON Array)">
              <el-input 
                v-model="advanced.rename_rules" 
                type="textarea" 
                rows="3" 
                placeholder='如: [{"pattern": "^(\\d+)\\.mp4$", "replace": "第\\1集.mp4"}]'
              />
            </el-form-item>
            <el-form-item v-if="form.source_type === 'regex'" label="抓取自定义网页正则">
              <el-input v-model="advanced.regex_pattern" placeholder="自定义解析 HTML 内容的正则表达式" />
            </el-form-item>

            <!-- Rule Tester Container -->
            <div class="rule-tester">
              <div class="tester-title">🔍 正则规则匹配测试工具</div>
              <el-row :gutter="10">
                <el-col :span="18">
                  <el-input 
                    v-model="advanced.test_filenames_raw" 
                    type="textarea" 
                    rows="3" 
                    placeholder="输入测试文件名（一行一个），例如:&#10;Lesson_01_Python.mp4&#10;readme.txt&#10;test.tmp" 
                  />
                </el-col>
                <el-col :span="6">
                  <el-button 
                    type="warning" 
                    class="test-btn" 
                    :loading="testingRules" 
                    @click="testRules"
                  >
                    开始测试
                  </el-button>
                </el-col>
              </el-row>
              
              <!-- Results list -->
              <div v-if="testResults.length > 0" class="test-results-list">
                <div 
                  v-for="(res, idx) in testResults" 
                  :key="idx" 
                  class="test-result-item"
                >
                  <span class="file-name" :title="res.original">{{ res.original }}</span>
                  <div class="result-badge">
                    <el-tag 
                      v-if="res.status === 'allowed'" 
                      type="success" 
                      size="small" 
                      effect="dark"
                    >
                      通过
                    </el-tag>
                    <el-tag 
                      v-else 
                      type="danger" 
                      size="small" 
                      effect="dark"
                    >
                      过滤
                    </el-tag>
                  </div>
                  <span v-if="res.renamed" class="renamed-text">
                    ➔ {{ res.renamed }}
                  </span>
                </div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showDialog = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitForm">
            保存任务
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import api from '../api'

const subscriptions = ref<any[]>([])
const accounts = ref<any[]>([])
const showDialog = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const currentSubId = ref<number | null>(null)
const formRef = ref()
const importText = ref('')

const handleImportText = () => {
  if (!importText.value.trim()) return
  
  // 1. Extract share link
  const urlRegex = /(https?:\/\/pan\.baidu\.com\/s\/[a-zA-Z0-9_-]+)/i
  const urlMatch = importText.value.match(urlRegex)
  if (urlMatch) {
    form.share_url = urlMatch[1]
  }
  
  // 2. Extract password from query string (pwd=xxxx) or text (提取码: xxxx)
  const pwdParamRegex = /[?&]pwd=([a-zA-Z0-9]{4})/i
  const pwdParamMatch = importText.value.match(pwdParamRegex)
  if (pwdParamMatch) {
    form.share_password = pwdParamMatch[1]
  } else {
    const textPwdRegex = /(?:提取码|密码|pwd|提取|码)\s*[:：\s]*\s*([a-zA-Z0-9]{4})/i
    const textPwdMatch = importText.value.match(textPwdRegex)
    if (textPwdMatch) {
      form.share_password = textPwdMatch[1]
    }
  }
  
  // 3. Auto-generate a descriptive name if empty
  if (!form.name.trim()) {
    form.name = `百度分享订阅_${form.share_password || Math.floor(1000 + Math.random() * 9000)}`
  }
}

const form = reactive({
  name: '',
  source_type: 'baidu_share',
  source_url: '',
  share_url: '',
  share_password: '',
  account_id: undefined as number | undefined,
  target_path: '/自动转存',
  cron_expression: '0 2 * * *',
  transfer_strategy: 'incremental',
  enabled: 1
})

const advanced = reactive({
  include: '',
  exclude: '',
  rename_rules: '',
  regex_pattern: '',
  test_filenames_raw: ''
})

const testingRules = ref(false)
const testResults = ref<any[]>([])

const testRules = async () => {
  if (!advanced.test_filenames_raw.trim()) {
    return ElMessage.warning('请输入至少一个待测试的文件名！')
  }
  
  if (advanced.rename_rules.trim()) {
    try {
      JSON.parse(advanced.rename_rules.trim())
    } catch (e) {
      return ElMessage.error('高级配置中「重命名规则」JSON 格式错误，请先检查修正！')
    }
  }
  
  testingRules.value = true
  testResults.value = []
  
  const filterObj = {
    include: advanced.include.trim() || undefined,
    exclude: advanced.exclude.trim() || undefined
  }
  
  const payload = {
    filter_rules: JSON.stringify(filterObj),
    rename_rules: advanced.rename_rules.trim() || undefined,
    test_filenames: advanced.test_filenames_raw.split('\n').map(s => s.trim()).filter(s => s)
  }
  
  try {
    const res = await api.post('/api/subscriptions/test-rules', payload)
    if (res.data.errno === 0) {
      testResults.value = res.data.results
      ElMessage.success('测试运行完成')
    } else {
      ElMessage.error(res.data.error || '测试规则运行失败')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '连接接口失败')
  } finally {
    testingRules.value = false
  }
}

const rules = {
  name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  target_path: [{ required: true, message: '请输入目标转存路径', trigger: 'blur' }],
  cron_expression: [{ required: true, message: '请输入 Cron 规则', trigger: 'blur' }]
}

const getTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    baidu_share: '网盘分享',
    rss: 'RSS 订阅',
    json: 'JSON 接口',
    webpage: '网页监控',
    regex: '正则抓取'
  }
  return map[type] || type
}

const getTypeTag = (type: string) => {
  const map: Record<string, string> = {
    baidu_share: 'primary',
    rss: 'success',
    json: 'info',
    webpage: 'warning',
    regex: 'danger'
  }
  return map[type] || 'info'
}

const getStrategyLabel = (strategy: string) => {
  const map: Record<string, string> = {
    notify_only: '仅检测通知',
    incremental: '增量转存',
    version_archive: '版本归档',
    safe_overwrite: '安全覆盖'
  }
  return map[strategy] || strategy
}

const loadSubscriptions = async () => {
  try {
    const res = await api.get('/api/subscriptions')
    subscriptions.value = res.data
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '加载订阅列表失败。')
  }
}

const loadAccounts = async () => {
  try {
    const res = await api.get('/api/accounts')
    accounts.value = res.data
  } catch (e) {}
}

const triggerTask = async (row: any) => {
  try {
    const res = await api.post(`/api/subscriptions/${row.id}/trigger`)
    if (res.data.errno === 0) {
      ElMessage.success('转存任务已在后台触发，请到运行历史查看详情！')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '手动触发失败。')
  }
}

const toggleStatus = async (row: any) => {
  try {
    await api.put(`/api/subscriptions/${row.id}`, {
      ...row,
      enabled: row.enabled
    })
    ElMessage.success(row.enabled === 1 ? '定时任务已启用' : '定时任务已停用')
    loadSubscriptions()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '状态切换失败。')
  }
}

const openAddDialog = () => {
  isEdit.value = false
  showDialog.value = true
}

const openEditDialog = (row: any) => {
  isEdit.value = true
  currentSubId.value = row.id
  
  // Fill form
  form.name = row.name
  form.source_type = row.source_type
  form.source_url = row.source_url || ''
  form.share_url = row.share_url || ''
  form.share_password = '' // Keep password empty unless changing
  form.account_id = row.account_id
  form.target_path = row.target_path
  form.cron_expression = row.cron_expression
  form.transfer_strategy = row.transfer_strategy
  form.enabled = row.enabled
  
  // Fill advanced
  try {
    if (row.filter_rules) {
      const filters = JSON.parse(row.filter_rules)
      advanced.include = filters.include || ''
      advanced.exclude = filters.exclude || ''
      advanced.regex_pattern = filters.regex_pattern || ''
    }
    if (row.rename_rules) {
      advanced.rename_rules = row.rename_rules
    }
  } catch (e) {}
  
  showDialog.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    
    submitting.value = true
    
    // Compile advanced JSON configs
    const filterObj = {
      include: advanced.include.trim() || undefined,
      exclude: advanced.exclude.trim() || undefined,
      regex_pattern: advanced.regex_pattern.trim() || undefined
    }
    const filter_rules_str = JSON.stringify(filterObj)
    
    let rename_rules_str = ""
    if (advanced.rename_rules.trim()) {
      try {
        JSON.parse(advanced.rename_rules.trim()) // Validate JSON structure
        rename_rules_str = advanced.rename_rules.trim()
      } catch (e) {
        submitting.value = false
        return ElMessage.error('高级配置中「重命名规则」JSON 格式错误，请检查！')
      }
    }
    
    const payload = {
      ...form,
      filter_rules: filter_rules_str,
      rename_rules: rename_rules_str
    }
    
    try {
      let res
      if (isEdit.value && currentSubId.value) {
        res = await api.put(`/api/subscriptions/${currentSubId.value}`, payload)
      } else {
        res = await api.post('/api/subscriptions', payload)
      }
      
      if (res.data.errno === 0) {
        ElMessage.success('订阅任务保存成功！')
        showDialog.value = false
        loadSubscriptions()
      } else {
        ElMessage.error(res.data.error || '保存失败。')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || '服务器处理错误。')
    } finally {
      submitting.value = false
    }
  })
}

const handleDelete = (row: any) => {
  ElMessageBox.confirm(
    `确定删除订阅任务「${row.name}」吗？删除后其绑定的定时计划将被注销。`,
    '删除确认',
    {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      const res = await api.delete(`/api/subscriptions/${row.id}`)
      if (res.data.errno === 0) {
        ElMessage.success('订阅任务已删除')
        loadSubscriptions()
      }
    } catch (e) {
      ElMessage.error('删除任务失败')
    }
  }).catch(() => {})
}

const resetForm = () => {
  form.name = ''
  form.source_type = 'baidu_share'
  form.source_url = ''
  form.share_url = ''
  form.share_password = ''
  form.account_id = undefined
  form.target_path = '/自动转存'
  form.cron_expression = '0 2 * * *'
  form.transfer_strategy = 'incremental'
  form.enabled = 1
  
  advanced.include = ''
  advanced.exclude = ''
  advanced.rename_rules = ''
  advanced.regex_pattern = ''
  advanced.test_filenames_raw = ''
  testResults.value = []
  currentSubId.value = null
  importText.value = ''
}

onMounted(() => {
  loadSubscriptions()
  loadAccounts()
})
</script>

<style scoped>
.subs-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.action-bar {
  display: flex;
  justify-content: flex-end;
}

.table-wrapper {
  padding: 15px;
}

.advanced-collapse {
  margin-top: 15px;
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.1);
  padding: 0 10px;
}

/* Custom Element collapse styles overrides */
:deep(.el-collapse-item__header) {
  background-color: transparent !important;
  border-bottom: none !important;
  color: var(--text-secondary) !important;
  font-size: 13px !important;
}

:deep(.el-collapse-item__wrap) {
  background-color: transparent !important;
  border-bottom: none !important;
}

/* Rule Tester Styles */
.rule-tester {
  margin-top: 18px;
  border-top: 1px dashed rgba(255, 255, 255, 0.08);
  padding-top: 15px;
}

.tester-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.test-btn {
  width: 100%;
  height: 100%;
  min-height: 70px;
}

.test-results-list {
  margin-top: 12px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  padding: 8px 12px;
  max-height: 160px;
  overflow-y: auto;
}

.test-result-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.test-result-item:last-child {
  border-bottom: none;
}

.test-result-item .file-name {
  color: var(--text-secondary);
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 280px;
}

.test-result-item .renamed-text {
  color: #818cf8;
  font-family: monospace;
  font-weight: 600;
}
</style>
