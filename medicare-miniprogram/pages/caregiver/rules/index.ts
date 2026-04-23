import { get } from '../../../services/request'

/** 置信度/支持度有效范围 [0, 1] */
function _safeRate(val: any): number {
  const n = parseFloat(val)
  if (isNaN(n)) return 0
  return Math.min(1, Math.max(0, n))
}

/** 安全转换 lift 值，lift >= 1 才有意义 */
function _safeLift(val: any): number {
  const n = parseFloat(val)
  if (isNaN(n) || n < 0) return 1.0
  return n
}

Page({
  data: {
    rules: [] as any[],
    loading: true,
    error: false,
    empty: false,
  },

  onShow() {
    this.loadRules()
  },

  async loadRules() {
    const app = getApp<IAppOption>()
    const pid = app?.globalData?.currentPatientId

    if (!pid) {
      this.setData({ loading: false, rules: [], empty: true })
      wx.showToast({ title: '请先在监护页选择患者', icon: 'none' })
      return
    }

    this.setData({ loading: true, error: false, empty: false })

    try {
      const data = await get(`/rules/${pid}?limit=10`) as any

      // 防御：后端可能返回 null 或非数组
      const rawRules = Array.isArray(data) ? data : []

      if (rawRules.length === 0) {
        this.setData({ rules: [], loading: false, empty: true })
        return
      }

      const rules = rawRules
        .filter((r: any) => r && typeof r === 'object')
        .map((r: any) => {
          const confidence = _safeRate(r.confidence)
          const support    = _safeRate(r.support)
          const lift       = _safeLift(r.lift)

          return {
            ...r,
            confidence,
            support,
            lift,
            confidence_pct: Math.round(confidence * 100),
            support_pct:    Math.round(support * 100),
            lift_str:       lift.toFixed(2),
            // 置信度进度条宽度百分比（用于 WXML style 绑定）
            confidence_bar_width: `${Math.round(confidence * 100)}%`,
            // 规则描述防御：确保不为空
            rule_description: r.rule_description || '用药关联规则',
            suggestion:       r.suggestion || '建议在服药后检查是否遗漏相关药物',
          }
        })

      this.setData({ rules, loading: false, empty: rules.length === 0 })
    } catch (e) {
      console.error('[Rules] 加载关联规则失败:', e)
      this.setData({ loading: false, error: true, rules: [] })
    }
  },

  onRetry() {
    this.loadRules()
  },
})
