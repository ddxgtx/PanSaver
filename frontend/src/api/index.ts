import axios from 'axios'

const api = axios.create({
  baseURL: ''
})

// Request Interceptor: Inject JWT token if stored
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('pansave_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config;
  },
  error => {
    return Promise.reject(error)
  }
)

// Response Interceptor: Catch 401 Unauthorized globally
api.interceptors.response.use(
  response => {
    return response;
  },
  error => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('pansave_token')
      // Redirect to login if not already there or in setup
      const path = window.location.hash || window.location.pathname
      if (!path.includes('login') && !path.includes('setup')) {
        window.location.href = '#/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
