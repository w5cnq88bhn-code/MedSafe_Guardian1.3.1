import { AuthService } from '../../../services/auth.service'

/** 中国大陆手机号正则：1开头，第二位3-9，共11位 */
const PHONE_REGEX = /^1[3-9]\d{9}$/

Page({
  data: {
    phone: '',
    submitting: false,
  },

  onPhoneInput(e: WechatMiniprogram.Input) {
    // 只保留数字，防止用户粘贴带空格或横线的手机号
    const raw = e.detail.value || ''
    const digits = raw.replace(/\D/g, '').slice(0, 11)
    this.setData({ phone: digits })
  },

  _validatePhone(): string | null {
    const phone = this.data.phone.trim()
    if (!phone) return '请输入手机号'
    if (phone.length !== 11) return '手机号应为11位'
    if (!PHONE_REGEX.test(phone)) return '请输入正确的手机号'
    return null
  },

  async onBind() {
    const validationError = this._validatePhone()
    if (validationError) {
      wx.showToast({ title: validationError, icon: 'none' })
      return
    }

    // 防止重复提交
    if (this.data.submitting) return
    this.setData({ submitting: true })

    try {
      const result = await AuthService.bindPatient(this.data.phone.trim()) as any

      // 防御：result 可能缺少字段
      if (!result || !result.patient_id) {
        wx.showToast({ title: '绑定成功', icon: 'success' })
      } else {
        const name = result.patient_name || '被监护人'
        wx.showToast({ title: `已绑定 ${name}`, icon: 'success' })
        // 更新全局状态
        const app = getApp<IAppOption>()
        if (app?.globalData) {
          app.globalData.currentPatientId = result.patient_id
        }
      }

      setTimeout(() => wx.navigateBack(), 1500)
    } catch (e: any) {
      const msg: string = e?.message || ''
      // 区分不同错误类型给出更明确的提示
      if (msg.includes('404') || msg.includes('未找到')) {
        wx.showToast({ title: '未找到该手机号对应的患者', icon: 'none' })
      } else if (msg.includes('409') || msg.includes('已绑定')) {
        wx.showToast({ title: '已绑定该患者', icon: 'none' })
      } else if (msg.includes('400') || msg.includes('不能绑定自己')) {
        wx.showToast({ title: '不能绑定自己', icon: 'none' })
      } else {
        wx.showToast({ title: '绑定失败，请检查手机号', icon: 'none' })
      }
    } finally {
      this.setData({ submitting: false })
    }
  },
})
