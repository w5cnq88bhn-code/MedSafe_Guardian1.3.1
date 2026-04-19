import { get } from '../../../services/request'

const SLOT_CN: Record<string, string> = {
  morning: '早',
  afternoon: '中',
  evening: '晚',
}
const SLOT_CN_FULL: Record<string, string> = {
  morning: '早间',
  afternoon: '午间',
  evening: '晚间',
}

/** 漏服概率高风险阈值 */
const HIGH_RISK_THRESHOLD = 0.7
/** 柱状图最大高度（rpx） */
const BAR_MAX_HEIGHT = 200

/**
 * 安全转换概率值，防止后端返回非数值类型
 */
function _safeProb(val: any): number {
  const n = parseFloat(val)
  if (isNaN(n)) return 0
  return Math.min(1, Math.max(0, n))
}

Page({
  data: {
    slots: [] as any[],
    loading: true,
    error: false,
    patientName: '',
  },

  onShow() {
    this.loadPredictions()
  },

  async loadPredictions() {
    const app = getApp<IAppOption>()
    const pid = app?.globalData?.currentPatientId

    // 防御：未选择患者时给出提示
    if (!pid) {
      this.setData({ loading: false, slots: [], error: false })
      wx.showToast({ title: '请先在监护页选择患者', icon: 'none' })
      return
    }

    this.setData({ loading: true, error: false })

    try {
      const data = await get(`/predictions/${pid}?days=3`) as any

      // 防御：data 或 data.slots 可能为 null/undefined
      const rawSlots = Array.isArray(data?.slots) ? data.slots : []

      if (rawSlots.length === 0) {
        // 无预测数据，展示空状态而非报错
        this.setData({ slots: [], loading: false })
        return
      }

      const slots = rawSlots.map((s: any) => {
        const prob = _safeProb(s?.miss_probability)
        const timeSlot = typeof s?.time_slot === 'string' ? s.time_slot : 'morning'
        const dayOffset = typeof s?.day_offset === 'number' ? s.day_offset : 1

        return {
          ...s,
          day_offset:       dayOffset,
          time_slot:        timeSlot,
          miss_probability: prob,
          // 柱高：概率 * 最大高度，最小显示 4rpx 保证可见性
          bar_height:       Math.max(4, Math.round(prob * BAR_MAX_HEIGHT)),
          prob_pct0:        Math.round(prob * 100),
          prob_pct1:        (prob * 100).toFixed(1),
          slot_cn:          SLOT_CN[timeSlot] || timeSlot,
          slot_cn_full:     SLOT_CN_FULL[timeSlot] || timeSlot,
          is_high_risk:     prob > HIGH_RISK_THRESHOLD,
        }
      })

      this.setData({ slots, loading: false })
    } catch (e) {
      console.error('[Prediction] 加载预测数据失败:', e)
      this.setData({ loading: false, error: true, slots: [] })
    }
  },

  onRetry() {
    this.loadPredictions()
  },
})
