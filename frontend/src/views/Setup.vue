<template>
  <div class="auth-container">
    <div class="glass-panel auth-card">
      <div class="auth-header">
        <h2 class="title">初始化管理员密码</h2>
        <p class="subtitle">欢迎使用 PanSave。请设置您的系统管理员密码以开启后续服务。</p>
      </div>

      <el-form :model="form" :rules="rules" ref="formRef" label-position="top">
        <el-form-item label="管理员密码" prop="password">
          <el-input 
            v-model="form.password" 
            type="password" 
            placeholder="请输入至少6位密码" 
            show-password
          />
        </el-form-item>

        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input 
            v-model="form.confirmPassword" 
            type="password" 
            placeholder="请再次输入密码" 
            show-password
          />
        </el-form-item>

        <el-form-item>
          <el-button 
            type="primary" 
            class="submit-btn" 
            :loading="loading" 
            @click="handleSetup"
          >
            初始化密码并启动
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'

const router = useRouter()
const formRef = ref()
const loading = ref(false)

const form = reactive({
  password: '',
  confirmPassword: ''
})

const validateConfirmPassword = (_rule: any, value: any, callback: any) => {
  if (value === '') {
    callback(new Error('请再次输入密码'))
  } else if (value !== form.password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const rules = {
  password: [
    { required: true, message: '请输入管理员密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于 6 位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

const handleSetup = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    
    loading.value = true
    try {
      const res = await api.post('/api/auth/setup', { password: form.password })
      if (res.data.errno === 0) {
        ElMessage.success('管理员密码初始化成功，请登录！')
        router.push('/login')
      } else {
        ElMessage.error(res.data.error || '设置失败，请重试。')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || '连接服务器出错，请检查后台运行状态。')
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.auth-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  padding: 20px;
}

.auth-card {
  width: 100%;
  max-width: 440px;
  padding: 40px;
  box-sizing: border-box;
}

.auth-header {
  text-align: center;
  margin-bottom: 30px;
}

.title {
  margin: 0 0 10px 0;
  font-size: 24px;
  font-weight: 600;
  background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.submit-btn {
  width: 100%;
  height: 44px;
  margin-top: 15px;
}
</style>
