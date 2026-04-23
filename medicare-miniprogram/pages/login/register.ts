import { AuthService } from '../../services/auth.service'

/** 中国大陆手机号正则 */
const PHONE_REGEX = /^1[3-9]\d{9}$/
/** 出生年份合理范围 */
const BIRTH_YEAR_MIN = 1900
const BIRTH_YEAR_MAX = new Date().getFullYear()
/** 姓名最大长度 */
const NAME_MAX_LEN = 50

Page({
  data: {
    form: {
      name: '',
      phone: '',
      birth_year: '',
      diagnosis_disease: '',
    },
    submitting: false,
  },

  onInput(e: WechatMiniprogram.Input) {
    const field = e.currentTarget.dataset.field
    if (!field) return
    this.setData({ [`form.${field}`]: e.detail.value || '' })
  },

  _validateForm(): string | null {
    const { name, phone, birth_year } = this.data.form

    const trimmedName = name.trim()
    if (!trimmedName) return '请输入姓名'
    if (trimmedName.length > NAME_MAX_LEN) return `姓名不能超过${NAME_MAX_LEN}个字符`

    const trimmedPhone = phone.trim()
    if (!trimmedPhone) return '请输入手机号'
    if (!PHONE_REGEX.test(trimmedPhone)) return '请输入正确的手机号（11位）'

    if (!birth_year) return '请输入出生年份'
    const yearNum = Number(birth_year)
    if (isNaN(yearNum) || !Number.isInteger(yearNum)) return '出生年份格式不正确'
    if (yearNum < BIRTH_YEAR_MIN) return `出生年份不能早于${BIRTH_YEAR_MIN}年`
    if (yearNum > BIRTH_YEAR_MAX) return `出生年份不能超过${BIRTH_YEAR_MAX}年`

    return null
  },

  async onSubmit() {
    const validationError = this._validateForm()
    if (validationError) {
      wx.showToast({ title: validationError, icon: 'none' })
      return
    }

    if (this.data.submitting) return
    this.setData({ submitting: true })

    const { name, phone, birth_year, diagnosis_disease } = this.data.form
    try {
      await AuthService.registerPatient({
        name:               name.trim(),
        phone:              phone.trim(),
        birth_year:         Number(birth_year),
        diagnosis_disease:  diagnosis_disease.trim() || undefined,
      })
      wx.showToast({ title: '注册成功', icon: 'success' })
      setTimeout(() => {
        wx.switchTab({ url: '/pages/patient/today/index' })
      }, 1500)
    } catch (e: any) {
      const msg: string = e?.message || ''
      if (msg.includes('phone') || msg.includes('手机号')) {
        wx.showToast({ title: '手机号已被注册', icon: 'none' })
      } else {
        wx.showToast({ title: '注册失败，请重试', icon: 'none' })
      }
      console.error('[Register] 注册失败:', e)
    } finally {
      this.setData({ submitting: false })
    }
  },
})
