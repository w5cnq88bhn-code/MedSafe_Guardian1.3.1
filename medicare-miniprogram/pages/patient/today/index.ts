import { MedicationService, TodayDrug, FoodTip } from '../../../services/medication.service'
import { TIME_SLOT_CN } from '../../../utils/constants'

// 时段图标配置
const SLOT_ICON: Record<string, string> = {
  morning:   '🌅',
  afternoon: '☀️',
  evening:   '🌙',
}

// 药品类型关键词 → 图标 + 背景色
const DRUG_TYPE_MAP: Array<{ keywords: string[]; icon: string; bg: string }> = [
  { keywords: ['氨氯地平', '硝苯地平', '缬沙坦', '厄贝沙坦', '贝那普利', '降压', '高血压', '美托洛尔', '比索洛尔', '卡托普利'], icon: '❤️', bg: '#ffeaea' },
  { keywords: ['二甲双胍', '格列', '阿卡波糖', '胰岛素', '降糖', '糖尿病', '西格列汀', '利格列汀'], icon: '🩸', bg: '#fff0f0' },
  { keywords: ['阿司匹林', '华法林', '氯吡格雷', '利伐沙班', '达比加群', '抗凝', '抗血小板'], icon: '🛡️', bg: '#e8f4fd' },
  { keywords: ['钙', '骨化三醇', '维生素D', '碳酸钙', '葡萄糖酸钙'], icon: '🦴', bg: '#f5f0ff' },
  { keywords: ['阿托伐他汀', '瑞舒伐他汀', '辛伐他汀', '他汀', '降脂', '血脂'], icon: '💉', bg: '#fff8e1' },
  { keywords: ['奥美拉唑', '兰索拉唑', '雷贝拉唑', '胃', '肠'], icon: '🫁', bg: '#f0fff4' },
]

const DEFAULT_DRUG = { icon: '💊', bg: '#f0f4ff' }

function getDrugIcon(drugName: string): { icon: string; iconBg: string } {
  // 防御：drugName 为空时返回默认图标
  if (!drugName) return { icon: DEFAULT_DRUG.icon, iconBg: DEFAULT_DRUG.bg }
  for (const type of DRUG_TYPE_MAP) {
    if (type.keywords.some(kw => drugName.includes(kw))) {
      return { icon: type.icon, iconBg: type.bg }
    }
  }
  return { icon: DEFAULT_DRUG.icon, iconBg: DEFAULT_DRUG.bg }
}

// 饮食贴士严重程度 → 颜色/图标
const SEVERITY_CONFIG: Record<string, { color: string; bg: string; icon: string; label: string }> = {
  high:   { color: '#c0392b', bg: '#fdf0ef', icon: '⚠️', label: '重要' },
  medium: { color: '#d35400', bg: '#fef5ec', icon: '💡', label: '注意' },
  low:    { color: '#27ae60', bg: '#eafaf1', icon: 'ℹ️', label: '提示' },
}

interface GroupedDrugs {
  slot: string
  slotCn: string
  slotIcon: string
  drugs: (TodayDrug & { icon: string; iconBg: string })[]
}

interface FoodTipDisplay extends FoodTip {
  severityColor: string
  severityBg: string
  severityIcon: string
  severityLabel: string
  expanded: boolean
}

Page({
  data: {
    groups: [] as GroupedDrugs[],
    foodTips: [] as FoodTipDisplay[],
    loading: true,
    empty: false,
    tipsExpanded: true,   // 饮食贴士卡片是否展开
  },

  onShow() {
    this.loadTodayDrugs()
  },

  async loadTodayDrugs() {
    const app = getApp<IAppOption>()
    const patientId = app?.globalData?.currentPatientId || app?.globalData?.userId

    if (!patientId || patientId <= 0) {
      console.warn('[Today] 无效 patientId，跳过加载')
      this.setData({ loading: false, empty: true })
      return
    }

    this.setData({ loading: true, empty: false })
    try {
      // 并发加载今日用药和饮食贴士
      const [drugs, rawTips] = await Promise.all([
        MedicationService.getTodayDrugs(patientId),
        MedicationService.getFoodTips(patientId).catch(() => [] as FoodTip[]),
      ])

      const safeDrugs = Array.isArray(drugs) ? drugs : []

      const slotOrder = ['morning', 'afternoon', 'evening']
      const grouped: GroupedDrugs[] = slotOrder
        .map(slot => ({
          slot,
          slotCn: TIME_SLOT_CN[slot] || slot,
          slotIcon: SLOT_ICON[slot] ?? '⏰',
          drugs: safeDrugs
            .filter(d => d?.time_of_day === slot)
            .map(d => ({ ...d, ...getDrugIcon(d.drug_name || '') })),
        }))
        .filter(g => g.drugs.length > 0)

      // 处理饮食贴士显示数据
      const foodTips: FoodTipDisplay[] = (Array.isArray(rawTips) ? rawTips : []).map(tip => {
        const cfg = SEVERITY_CONFIG[tip.severity] || SEVERITY_CONFIG.low
        return {
          ...tip,
          severityColor: cfg.color,
          severityBg:    cfg.bg,
          severityIcon:  cfg.icon,
          severityLabel: cfg.label,
          expanded:      false,
        }
      })

      this.setData({
        groups:    grouped,
        foodTips,
        loading:   false,
        empty:     grouped.length === 0,
      })
    } catch (e) {
      console.error('[Today] 加载今日用药失败:', e)
      this.setData({ loading: false, empty: true })
    }
  },

  async onTake(e: WechatMiniprogram.TouchEvent) {
    const { scheduleId, status, logId } = e.currentTarget.dataset

    // 防御：scheduleId 无效
    if (!scheduleId) {
      console.warn('[Today] onTake: scheduleId 无效')
      return
    }

    if (status === 'taken') {
      wx.showModal({
        title: '撤销服药登记',
        content: '确认撤销本次服药记录？（仅5分钟内有效）',
        success: async ({ confirm }) => {
          if (confirm) {
            if (!logId) {
              wx.showToast({ title: '记录信息异常', icon: 'none' })
              return
            }
            try {
              await MedicationService.undoTake(logId)
              wx.showToast({ title: '已撤销', icon: 'success' })
              this.loadTodayDrugs()
            } catch (e) {
              console.error('[Today] 撤销失败:', e)
            }
          }
        },
      })
      return
    }

    const app = getApp<IAppOption>()
    const pid = app?.globalData?.currentPatientId || app?.globalData?.userId
    if (!pid) {
      wx.showToast({ title: '无法获取患者信息', icon: 'none' })
      return
    }

    try {
      await MedicationService.manualTake(pid, scheduleId)
      wx.showToast({ title: '已登记服药', icon: 'success' })
      this.loadTodayDrugs()
    } catch (e) {
      console.error('[Today] 登记服药失败:', e)
    }
  },

  onAddDrug() {
    wx.navigateTo({ url: '/pages/patient/add-drug/index' })
  },

  // 展开/收起饮食贴士卡片
  onToggleTips() {
    this.setData({ tipsExpanded: !this.data.tipsExpanded })
  },

  // 展开/收起单条贴士详情
  onToggleTipDetail(e: WechatMiniprogram.TouchEvent) {
    const { index } = e.currentTarget.dataset
    const key = `foodTips[${index}].expanded`
    this.setData({ [key]: !this.data.foodTips[index].expanded })
  },
})
