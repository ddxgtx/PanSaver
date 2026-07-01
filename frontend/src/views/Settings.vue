<template>
  <div class="settings-container">
    <div class="settings-grid">
      <!-- 1. System General Settings -->
      <div class="glass-panel settings-card">
        <div class="card-header">
          <h3>系统运行设置</h3>
          <el-icon color="#6366f1"><Setting /></el-icon>
        </div>

        <el-form :model="settings.system_settings" label-position="top">
          <el-form-item label="默认全局备份保留数量 (安全覆盖/同名覆盖)">
            <el-input-number v-model="settings.system_settings.backup_retention" :min="1" :max="10" />
          </el-form-item>

          <el-form-item label="最大并发转存线程数">
            <el-input-number v-model="settings.system_settings.max_concurrency" :min="1" :max="5" />
          </el-form-item>

          <el-form-item label="网盘转存请求延迟间隔 (秒)">
            <el-input-number v-model="settings.system_settings.request_delay" :min="0.1" :max="5.0" :step="0.1" />
          </el-form-item>

          <el-form-item label="接口可恢复异常最大重试次数">
            <el-input-number v-model="settings.system_settings.max_retries" :min="0" :max="5" />
          </el-form-item>

          <el-form-item label="远程访问控制">
            <el-switch 
              v-model="settings.system_settings.allow_remote_access" 
              active-text="允许外部网络访问控制台 (绑定 0.0.0.0)"
              inactive-text="仅允许本机构建访问 (安全，绑定 127.0.0.1)"
            />
            <div class="field-desc">修改此选项需要重启后端服务才能生效。</div>
          </el-form-item>
        </el-form>
      </div>

      <!-- 2. Notification Channels Settings -->
      <div class="glass-panel settings-card">
        <div class="card-header">
          <h3>通知渠道配置</h3>
          <el-icon color="#10b981"><Notification /></el-icon>
        </div>

        <el-collapse v-model="activeCollapse">
          <!-- PushPlus -->
          <el-collapse-item title="PushPlus 微信推送" name="pushplus">
            <el-form :model="settings.notification_settings.pushplus" label-position="top">
              <el-form-item label="启用状态">
                <el-switch v-model="settings.notification_settings.pushplus.enabled" />
              </el-form-item>
              <el-form-item label="PushPlus Token">
                <el-input v-model="settings.notification_settings.pushplus.token" placeholder="请输入您的 PushPlus Token" show-password />
              </el-form-item>
            </el-form>
          </el-collapse-item>

          <!-- Bark -->
          <el-collapse-item title="Bark 推送 (iOS)" name="bark">
            <el-form :model="settings.notification_settings.bark" label-position="top">
              <el-form-item label="启用状态">
                <el-switch v-model="settings.notification_settings.bark.enabled" />
              </el-form-item>
              <el-form-item label="Bark App Key">
                <el-input v-model="settings.notification_settings.bark.device_key" placeholder="请输入您的 Bark Device Key" show-password />
              </el-form-item>
              <el-form-item label="Bark 自定义服务器">
                <el-input v-model="settings.notification_settings.bark.url" placeholder="https://api.day.app (默认)" />
              </el-form-item>
            </el-form>
          </el-collapse-item>

          <!-- Webhook -->
          <el-collapse-item title="自定义 Webhook" name="webhook">
            <el-form :model="settings.notification_settings.webhook" label-position="top">
              <el-form-item label="启用状态">
                <el-switch v-model="settings.notification_settings.webhook.enabled" />
              </el-form-item>
              <el-form-item label="Webhook URL">
                <el-input v-model="settings.notification_settings.webhook.url" placeholder="接收 POST 请求的 Webhook 链接" />
              </el-form-item>
            </el-form>
          </el-collapse-item>

          <!-- SMTP -->
          <el-collapse-item title="SMTP 邮件通知" name="smtp">
            <el-form :model="settings.notification_settings.smtp" label-position="top">
              <el-form-item label="启用状态">
                <el-switch v-model="settings.notification_settings.smtp.enabled" />
              </el-form-item>
              <el-row :gutter="20">
                <el-col :span="16">
                  <el-form-item label="SMTP 邮件服务器">
                    <el-input v-model="settings.notification_settings.smtp.host" placeholder="如: smtp.qq.com" />
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="端口">
                    <el-input-number v-model="settings.notification_settings.smtp.port" :min="1" :max="65535" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item>
                <el-checkbox v-model="settings.notification_settings.smtp.ssl">使用 SSL 加密</el-checkbox>
              </el-form-item>
              <el-form-item label="邮箱账户">
                <el-input v-model="settings.notification_settings.smtp.username" placeholder="如: myname@qq.com" />
              </el-form-item>
              <el-form-item label="邮箱授权码/密码">
                <el-input v-model="settings.notification_settings.smtp.password" placeholder="授权码或密码" show-password />
              </el-form-item>
              <el-form-item label="接收邮箱地址">
                <el-input v-model="settings.notification_settings.smtp.to" placeholder="接收日志报告的邮箱" />
              </el-form-item>
            </el-form>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>

    <!-- Sticky Save Actions -->
    <div class="glass-panel footer-actions">
      <el-button type="primary" size="large" :loading="saving" @click="saveAllSettings">
        保存全部系统设置
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const saving = ref(false)
const activeCollapse = ref(['pushplus'])

// Nested settings reactive state
const settings = reactive({
  system_settings: {
    backup_retention: 3,
    max_concurrency: 2,
    request_delay: 0.5,
    max_retries: 3,
    allow_remote_access: false
  },
  notification_settings: {
    pushplus: { enabled: false, token: '' },
    bark: { enabled: false, device_key: '', url: 'https://api.day.app' },
    webhook: { enabled: false, url: '' },
    smtp: { enabled: false, host: '', port: 465, ssl: true, username: '', password: '', to: '' }
  }
})

const loadSettings = async () => {
  try {
    const res = await api.get('/api/settings')
    const data = res.data
    
    // Merge database settings values with defaults to guarantee structure integrity
    if (data.system_settings) {
      Object.assign(settings.system_settings, data.system_settings)
    }
    if (data.notification_settings) {
      // Deeper merge
      for (const k in data.notification_settings) {
        if (settings.notification_settings[k as keyof typeof settings.notification_settings]) {
          Object.assign(settings.notification_settings[k as keyof typeof settings.notification_settings], data.notification_settings[k])
        }
      }
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '获取全局设置失败。')
  }
}

const saveAllSettings = async () => {
  saving.value = true
  try {
    const res = await api.post('/api/settings', {
      system_settings: settings.system_settings,
      notification_settings: settings.notification_settings
    })
    
    if (res.data.errno === 0) {
      ElMessage.success('系统设置已全部保存生效！')
      loadSettings()
    } else {
      ElMessage.error(res.data.error || '保存失败。')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '请求保存异常，请稍后重试。')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.settings-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

@media (max-width: 1024px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}

.settings-card {
  padding: 24px;
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

.field-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 5px;
}

.footer-actions {
  padding: 15px 25px;
  display: flex;
  justify-content: flex-end;
  border-radius: 12px;
}
</style>
