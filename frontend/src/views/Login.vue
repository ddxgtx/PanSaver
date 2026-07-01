<template>
  <div class="auth-container">
    <div class="glass-panel auth-card">
      <div class="auth-header">
        <div class="logo-box">
          <el-icon :size="40" color="#6366f1"><Lock /></el-icon>
        </div>
        <h2 class="title">PanSave 控制台登录</h2>
        <p class="subtitle">输入管理员密码进入订阅与网盘自动转存中心</p>
      </div>

      <el-form :model="form" ref="formRef" @submit.prevent="handleLogin">
        <el-form-item 
          prop="password"
          :rules="[{ required: true, message: '请输入管理员密码', trigger: 'blur' }]"
        >
          <el-input 
            v-model="form.password" 
            type="password" 
            placeholder="请输入管理员密码" 
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button 
            type="primary" 
            class="submit-btn" 
            :loading="loading" 
            @click="handleLogin"
          >
            登录系统
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
  password: ''
})

const handleLogin = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    
    loading.value = true
    try {
      const res = await api.post('/api/auth/login', { password: form.password })
      if (res.data.errno === 0) {
        localStorage.setItem('pansave_token', res.data.token)
        ElMessage.success('登录成功，欢迎回来！')
        router.push('/dashboard')
      } else {
        ElMessage.error(res.data.error || '登录失败，请重试。')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || '密码错误或连接异常，请重试。')
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
  max-width: 420px;
  padding: 40px 30px;
  box-sizing: border-box;
}

.auth-header {
  text-align: center;
  margin-bottom: 30px;
}

.logo-box {
  display: inline-flex;
  padding: 12px;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: 12px;
  margin-bottom: 15px;
}

.title {
  margin: 0 0 10px 0;
  font-size: 22px;
  font-weight: 600;
  background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.submit-btn {
  width: 100%;
  height: 42px;
  margin-top: 10px;
}
</style>
