import { MedicationService } from '../../../services/medication.service'
import { today } from '../../../utils/date'

// 剂量单位选项
const DOSAGE_UNITS = ['mg', 'g', 'ml', '片', '粒', '袋', 'IU', 'μg', '滴']
// 时段默认时间映射
const SLOT_DEFAULT_TIME: Record<string, string> = {
  morning:   '08:00',
  afternoon: '12:00',
  evening:   '20:00',
}
// 搜索防抖延迟（毫秒）
const SEARCH_DEBOUNCE_MS = 300
// 剂量合理范围
const DOSAGE_MIN = 0.001
const DOSAGE_MAX = 99999

Page({
  data: {
    keyword: '',
    searchResults: [] as any[],
    selectedDrug: null as any,
    dosageUnits: DOSAGE_UNITS,
    dosageUnitIndex: 0,
    form: {
      dosage: '',
      dosage_unit: 'mg',
      frequency: 1,
      time_of_day: 'morning',
      time_point: '08:00',
      start_date: today(),
      end_date: '',
    },
    conflictResult: null as any,
    showConflictModal: false,
    submitting: false,
    searching: false,
  },

  /** 防抖定时器 ID */
  _searchTimer: 0 as any,

  onKeywordInput(e: WechatMiniprogram.Input) {
    const keyword = e.detail.value || ''
    this.setData({ keyword })

    // 防抖搜索：用户停止输入 300ms 后再发请求
    clearTimeout(this._searchTimer)
    if (!keyword.trim()) {
      this.setData({ searchResults: [] })
      return
    }
    this._searchTimer = setTimeout(() => {
      this.onSearch()
    }, SEARCH_DEBOUNCE_MS)
  },

  async onSearch() {
    const keyword = this.data.keyword.trim()
    if (!keyword) return

    // 防御：关键词过短可能导致大量结果
    if (keyword.length < 1) {
      wx.showToast({ title: '请输入至少1个字符', icon: 'none' })
      return
    }

    this.setData({ searching: true })
    try {
      const results = await MedicationService.searchDrugs(keyword)
      // 防御：results 可能为 null/undefined
      this.setData({ searchResults: Array.isArray(results) ? results as any[] : [] })
    } catch (e) {
      console.error('[AddDrug] 搜索药物失败:', e)
      this.setData({ searchResults: [] })
    } finally {
      this.setData({ searching: false })
    }
  },

  onSelectDrug(e: WechatMiniprogram.TouchEvent) {
    const drug = e.currentTarget.dataset.drug
    if (!drug || !drug.id) {
      console.warn('[AddDrug] 选择的药物数据异常:', drug)
      return
    }
    this.setData({ selectedDrug: drug, searchResults: [], keyword: drug.generic_name || '' })
  },

  onClearDrug() {
    this.setData({ selectedDrug: null, keyword: '', searchResults: [], conflictResult: null })
  },

  onFormChange(e: WechatMiniprogram.Input | WechatMiniprogram.PickerChange) {
    const field = (e.currentTarget as any).dataset.field
    if (!field) return
    this.setData({ [`form.${field}`]: (e as any).detail.value })
  },

  onUnitChange(e: WechatMiniprogram.PickerChange) {
    const idx = Number(e.detail.value)
    if (idx < 0 || idx >= DOSAGE_UNITS.length) return
    this.setData({
      dosageUnitIndex: idx,
      'form.dosage_unit': DOSAGE_UNITS[idx],
    })
  },

  onFrequencyChange(e: WechatMiniprogram.PickerChange) {
    const idx = Number(e.detail.value)
    // frequency 范围 1-3
    const freq = Math.min(3, Math.max(1, idx + 1))
    this.setData({ 'form.frequency': freq })
  },

  onSlotChange(e: WechatMiniprogram.PickerChange) {
    const slots = ['morning', 'afternoon', 'evening']
    const idx = Number(e.detail.value)
    if (idx < 0 || idx >= slots.length) return
    const slot = slots[idx]
    this.setData({
      'form.time_of_day': slot,
      'form.time_point': SLOT_DEFAULT_TIME[slot] || '08:00',
    })
  },

  async onCheckConflict() {
    if (!this.data.selectedDrug) {
      wx.showToast({ title: '请先选择药物', icon: 'none' })
      return
    }

    const app = getApp<IAppOption>()
    const pid = app?.globalData?.currentPatientId || app?.globalData?.userId
    if (!pid) {
      wx.showToast({ title: '无法获取患者信息', icon: 'none' })
      return
    }

    try {
      const result = await MedicationService.checkConflict(pid, [this.data.selectedDrug.id]) as any
      // 防御：result 可能为 null
      if (!result) {
        wx.showToast({ title: '冲突检测失败，请重试', icon: 'none' })
        return
      }
      this.setData({ conflictResult: result, showConflictModal: true })
    } catch (e) {
      console.error('[AddDrug] 冲突检测失败:', e)
    }
  },

  onCloseModal() {
    this.setData({ showConflictModal: false })
  },

  _validateForm(): string | null {
    const { selectedDrug, form } = this.data

    if (!selectedDrug) return '请选择药物'

    const dosage = parseFloat(form.dosage)
    if (!form.dosage || isNaN(dosage)) return '请填写每次剂量'
    if (dosage < DOSAGE_MIN) return `剂量不能小于 ${DOSAGE_MIN}`
    if (dosage > DOSAGE_MAX) return `剂量不能超过 ${DOSAGE_MAX}`

    if (!form.time_point || !/^\d{2}:\d{2}$/.test(form.time_point)) {
      return '请填写正确的服药时间（HH:MM）'
    }

    if (!form.start_date) return '请选择开始日期'

    if (form.end_date && form.end_date < form.start_date) {
      return '结束日期不能早于开始日期'
    }

    return null
  },

  async onSubmit() {
    // 表单校验
    const validationError = this._validateForm()
    if (validationError) {
      wx.showToast({ title: validationError, icon: 'none' })
      return
    }

    // 防止重复提交
    if (this.data.submitting) return
    this.setData({ submitting: true })

    const app = getApp<IAppOption>()
    const pid = app?.globalData?.currentPatientId || app?.globalData?.userId
    if (!pid) {
      wx.showToast({ title: '无法获取患者信息', icon: 'none' })
      this.setData({ submitting: false })
      return
    }

    const { form, selectedDrug } = this.data
    try {
      await MedicationService.addSchedule({
        patient_id:  pid,
        drug_id:     selectedDrug.id,
        dosage:      parseFloat(form.dosage),
        dosage_unit: form.dosage_unit || 'mg',
        frequency:   form.frequency || 1,
        time_of_day: form.time_of_day || 'morning',
        time_point:  form.time_point.includes(':') ? `${form.time_point}:00` : form.time_point,
        start_date:  form.start_date,
        end_date:    form.end_date || undefined,
      })
      wx.showToast({ title: '添加成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 1500)
    } catch (e: any) {
      // 409 高危冲突由服务端拦截，给出明确提示
      const msg: string = e?.message || ''
      if (msg.includes('冲突') || msg.includes('409')) {
        wx.showModal({
          title: '高危冲突',
          content: '存在高危药物冲突或过敏风险，无法添加',
          showCancel: false,
        })
      }
      // 其他错误已由 request.ts 统一处理
    } finally {
      this.setData({ submitting: false })
    }
  },
})
