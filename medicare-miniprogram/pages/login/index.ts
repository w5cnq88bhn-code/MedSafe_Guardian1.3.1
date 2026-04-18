import { AuthService } from '../../services/auth.service'
import { PushService } from '../../services/push.service'

Page({
  data: {
    loading: false,
  },

  async onLogin() {
    if (this.data.loading) return
    this.setData({ loading: true })
    try {
      const result = await AuthService.login()
      // 请求订阅消息授权
      await PushService.requestSubscribe()

      if (result.is_new_user) {
        wx.navigateTo({ url: '/pages/login/register' })
      } else {
        wx.switchTab({ url: '/pages/patient/today/index' })
      }
    } catch (e) {
      wx.showToast({ title: '登录失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },
})
