import { get } from '../../../services/request'

const TABS = ['7天', '28天', '14天明细', '长期']

Page({
  data: {
    activeTab: 0,
    tabs: TABS,
    stats7:   null as any,
    stats28:  null as any,
    stats14:  null as any,
    lifetime: null as any,
    loading:  false,
    error:    false,
  },

  onShow() {
    // 每次进入页面重新加载，确保监护人切换患者后数据刷新
    this.setData({ stats7: null, stats28: null, stats14: null, lifetime: null, error: false })
    this.loadCurrentTab()
  },

  onTabChange(e: WechatMiniprogram.TouchEvent) {
    const idx = Number(e.currentTarget.dataset.idx)
    // 防御：idx 越界
    if (idx < 0 || idx >= TABS.length) return
    this.setData({ activeTab: idx, error: false })
    this.loadCurrentTab()
  },

  async loadCurrentTab() {
    const app = getApp<IAppOption>()
    const pid = app?.globalData?.currentPatientId || app?.globalData?.userId

    // 防御：pid 无效
    if (!pid || pid <= 0) {
      console.warn('[History] 无效 patientId，跳过加载')
      this.setData({ loading: false })
      return
    }

    const tab = this.data.activeTab
    this.setData({ loading: true, error: false })

    try {
      if (tab === 0 && !this.data.stats7) {
        const data = await get(`/statistics/7days/${pid}`) as any
        // 防御：data 可能为 null
        this.setData({ stats7: data || { drugs: [] } })

      } else if (tab === 1 && !this.data.stats28) {
        const data = await get(`/statistics/28days/${pid}`) as any
        this.setData({ stats28: data || { total_drug_types: 0, total_taken_count: 0, drugs: [] } })

      } else if (tab === 2 && !this.data.stats14) {
        const data = await get(`/statistics/14days/${pid}`) as any
        this.setData({ stats14: data || { records: [] } })

      } else if (tab === 3 && !this.data.lifetime) {
        const data = await get(`/statistics/lifetime/${pid}`) as any
        this.setData({ lifetime: data || { drugs: [] } })
      }
    } catch (e) {
      console.error('[History] 加载统计数据失败:', e)
      this.setData({ error: true })
    } finally {
      this.setData({ loading: false })
    }
  },

  onRetry() {
    // 清除当前 tab 缓存，重新加载
    const tab = this.data.activeTab
    const clearMap: Record<number, object> = {
      0: { stats7: null },
      1: { stats28: null },
      2: { stats14: null },
      3: { lifetime: null },
    }
    this.setData({ error: false, ...(clearMap[tab] || {}) })
    this.loadCurrentTab()
  },
})
