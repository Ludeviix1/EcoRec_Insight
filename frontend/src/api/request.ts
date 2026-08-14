import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import type { ApiResponse } from '@/types'

const service: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截：统一加日志（可扩展鉴权）
service.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error),
)

// 响应拦截：拆包 ApiResponse -> data，统一错误提示
service.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) {
        return body.data as unknown as typeof response
      }
      ElMessage.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message || `code=${body.code}`))
    }
    return body as unknown as typeof response
  },
  (error) => {
    let msg = '网络异常，请检查后端服务是否启动'
    if (error.response) {
      const status = error.response.status
      const body = error.response.data
      if (body && typeof body === 'object' && 'message' in body) {
        msg = body.message
      } else if (status === 404) {
        msg = '资源不存在'
      } else if (status >= 500) {
        msg = '服务器内部错误'
      }
    } else if (error.code === 'ECONNABORTED') {
      msg = '请求超时'
    }
    ElMessage.error(msg)
    return Promise.reject(error)
  },
)

/** 通用 GET：返回已拆包的 data。 */
export function get<T = unknown>(url: string, params?: Record<string, unknown>, config?: AxiosRequestConfig): Promise<T> {
  return service.get(url, { params, ...config }) as unknown as Promise<T>
}

export default service
