import { post, get } from './request'

export interface LoginResult {
  token: string
  openid: string
  user_id: number
  is_new_user: boolean
}

export class AuthService {
  /** 微信一键登录 */
  static async login(): Promise<LoginResult> {
    return new Promise((resolve, reject) => {
      wx.login({
        success: async ({ code }) => {
          try {
            const result = await post<LoginResult>('/auth/wechat-login', { code })
            wx.setStorageSync('token', result.token)
            wx.setStorageSync('userId', result.user_id)
            const app = getApp<IAppOption>()
            app.globalData.token  = result.token
            app.globalData.userId = result.user_id
            app.globalData.openid = result.openid
            resolve(result)
          } catch (e) {
            reject(e)
          }
        },
        fail: reject,
      })
    })
  }

  /** 完善患者信息 */
  static async registerPatient(data: {
    name: string
    phone: string
    birth_year: number
    diagnosis_disease?: string
  }) {
    return post('/patients/register', data)
  }

  /** 子女绑定患者 */
  static async bindPatient(patient_phone: string, relationship = 'child') {
    return post('/caregivers/bind', { patient_phone, relationship })
  }

  /** 获取绑定患者列表 */
  static async getBoundPatients() {
    return get('/caregivers/patients')
  }
}
