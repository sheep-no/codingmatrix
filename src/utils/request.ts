/**
 * HTTP 请求封装工具
 * 处理基础 URL、认证头、错误处理等
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

interface RequestOptions {
  method?: string
  headers?: Record<string, string>
  body?: any
  timeout?: number
}

interface RequestResponse<T = any> {
  status: number
  data: T
  headers: Headers
}

class RequestError extends Error {
  status: number
  data?: any

  constructor(message: string, status: number, data?: any) {
    super(message)
    this.name = 'RequestError'
    this.status = status
    this.data = data
  }
}

class Request {
  private baseURL: string
  private timeout: number
  private headers: Record<string, string>

  constructor(baseURL: string, timeout: number = 30000) {
    this.baseURL = baseURL
    this.timeout = timeout
    this.headers = {
      'Content-Type': 'application/json',
    }
  }

  private getFullURL(endpoint: string): string {
    if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
      return endpoint
    }
    return `${this.baseURL}${endpoint}`
  }

  private getAuthHeaders(): Record<string, string> {
    const token = localStorage.getItem('auth_token')
    const headers = { ...this.headers }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    return headers
  }

  async request<T = any>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<RequestResponse<T>> {
    const {
      method = 'GET',
      headers = {},
      body,
      timeout = this.timeout,
    } = options

    const url = this.getFullURL(endpoint)
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    try {
      const response = await fetch(url, {
        method,
        headers: {
          ...this.getAuthHeaders(),
          ...headers,
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        let errorData
        try {
          errorData = await response.json()
        } catch {
          errorData = { message: response.statusText }
        }
        throw new RequestError(
          errorData.message || '请求失败',
          response.status,
          errorData
        )
      }

      const contentType = response.headers.get('Content-Type')
      let data: T

      if (contentType?.includes('application/json')) {
        data = await response.json()
      } else {
        data = await response.text() as any
      }

      return {
        status: response.status,
        data,
        headers: response.headers,
      }
    } catch (error: any) {
      clearTimeout(timeoutId)
      if (error.name === 'AbortError') {
        throw new RequestError('请求超时', 408)
      }
      if (error instanceof RequestError) {
        throw error
      }
      throw new RequestError(error.message || '网络错误', 0)
    }
  }

  get<T = any>(endpoint: string, options?: RequestOptions): Promise<RequestResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'GET' })
  }

  post<T = any>(endpoint: string, data?: any, options?: RequestOptions): Promise<RequestResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'POST', body: data })
  }

  put<T = any>(endpoint: string, data?: any, options?: RequestOptions): Promise<RequestResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'PUT', body: data })
  }

  delete<T = any>(endpoint: string, options?: RequestOptions): Promise<RequestResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' })
  }
}

const request = new Request(BASE_URL)

export default request
export { Request, RequestError }
