import { API_BASE } from '../utils/constants'

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: Record<string, any>
  showLoading?: boolean
  /** 超时毫秒数，默认 10000 */
  timeout?: number
  /** 失败时是否静默（不弹 Toast），默认 false */
  silent?: boolean
}

interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

/** 正在进行中的请求计数，用于防止 loading 提前关闭 */
let _loadingCount = 0

function _showLoading() {
  _loadingCount++
  if (_loadingCount === 1) {
    wx.showLoading({ title: '加载中...', mask: true })
  }
}

function _hideLoading() {
  _loadingCount = Math.max(0, _loadingCount - 1)
  if (_loadingCount === 0) {
    wx.hideLoading()
  }
}

function getToken(): string {
  try {
    const app = getApp<IAppOption>()
    const token = app?.globalData?.token || wx.getStorageSync('token') || ''
    return token
  } catch (e) {
    // getApp() 在某些生命周期可能返回 null，降级到 Storage
    try {
      return wx.getStorageSync('token') || ''
    } catch {
      return ''
    }
  }
}

/** 判断响应体是否是合法的 ApiResponse 格式 */
function _isApiResponse(data: any): data is ApiResponse {
  return (
    data !== null &&
    typeof data === 'object' &&
    typeof data.code === 'number'
  )
}

/** 网络错误重试次数上限 */
const MAX_RETRY = 1

export async function request<T = any>(
  path: string,
  options: RequestOptions = {},
  _retryCount = 0
): Promise<T> {
  const {
    method = 'GET',
    data,
    showLoading = false,
    timeout = 10000,
    silent = false,
  } = options

  // 防御：path 必须以 / 开头
  const safePath = path.startsWith('/') ? path : `/${path}`

  if (showLoading) _showLoading()

  return new Promise((resolve, reject) => {
    const token = getToken()

    wx.request({
      url: `${API_BASE}${safePath}`,
      method,
      data,
      timeout,
      header: {
        'Content-Type': 'application/json',
        Authorization: token ? `Bearer ${token}` : '',
      },
      success(res) {
        if (showLoading) _hideLoading()

        // 防御：响应体可能不是预期格式（如 nginx 返回 HTML 错误页）
        if (!_isApiResponse(res.data)) {
          console.error('[Request] 响应格式异常:', res.statusCode, typeof res.data)
          if (!silent) {
            wx.showToast({ title: '服务器响应异常', icon: 'none' })
          }
          reject(new Error(`响应格式异常: statusCode=${res.statusCode}`))
          return
        }

        const body = res.data as ApiResponse<T>

        if (body.code === 200) {
          resolve(body.data)
          return
        }

        if (body.code === 401) {
          // 清除失效 token，跳转登录
          try {
            wx.removeStorageSync('token')
            const app = getApp<IAppOption>()
            if (app?.globalData) {
              app.globalData.token = ''
            }
          } catch {}
          wx.reLaunch({ url: '/pages/login/index' })
          reject(new Error('登录已过期'))
          return
        }

        if (body.code === 403) {
          if (!silent) {
            wx.showToast({ title: '无权限访问', icon: 'none' })
          }
          reject(new Error(body.message || '无权限'))
          return
        }

        if (body.code === 409) {
          // 冲突类错误（如高危药物冲突），不弹通用 Toast，由调用方处理
          reject(new Error(body.message || '操作冲突'))
          return
        }

        if (body.code >= 500) {
          if (!silent) {
            wx.showToast({ title: '服务器繁忙，请稍后重试', icon: 'none' })
          }
          reject(new Error(body.message || '服务器错误'))
          return
        }

        // 其他业务错误
        if (!silent) {
          wx.showToast({ title: body.message || '请求失败', icon: 'none' })
        }
        reject(new Error(body.message || '请求失败'))
      },
      fail(err) {
        if (showLoading) _hideLoading()

        const errMsg: string = (err as any)?.errMsg || ''

        // 超时错误：尝试重试一次
        if (errMsg.includes('timeout') && _retryCount < MAX_RETRY) {
          console.warn(`[Request] 请求超时，第 ${_retryCount + 1} 次重试: ${safePath}`)
          request<T>(path, options, _retryCount + 1).then(resolve).catch(reject)
          return
        }

        // 网络不可用
        if (errMsg.includes('fail') || errMsg.includes('ERR_CONNECTION')) {
          if (!silent) {
            wx.showToast({ title: '网络连接失败，请检查网络', icon: 'none' })
          }
        } else {
          if (!silent) {
            wx.showToast({ title: '网络错误，请重试', icon: 'none' })
          }
        }

        console.error('[Request] 请求失败:', safePath, errMsg)
        reject(err)
      },
    })
  })
}

export const get = <T>(path: string, data?: Record<string, any>, silent = false) =>
  request<T>(path, { method: 'GET', data, silent })

export const post = <T>(path: string, data?: Record<string, any>, silent = false) =>
  request<T>(path, { method: 'POST', data, showLoading: true, silent })

export const del = <T>(path: string, silent = false) =>
  request<T>(path, { method: 'DELETE', silent })
