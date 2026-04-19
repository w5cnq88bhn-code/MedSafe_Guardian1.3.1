import { get, post, del } from '../../../services/request'

/** 过敏原名称最大长度 */
const ALLERGEN_MAX_LEN = 100
/** 反应类型最大长度 */
const REACTION_MAX_LEN = 100

Page({
  data: {
    allergies: [] as any[],
    showAdd: false,
    newAllergen: '',
    newReaction: '',
    loading: false,
    submitting: false,
    /** 正在删除的记录 ID 集合，防止重复点击 */
    deletingIds: [] as number[],
  },

  onShow() {
    this.loadAllergies()
  },

  async loadAllergies() {
    const app = getApp<IAppOption>()
    const pid = app?.globalData?.currentPatientId || app?.globalData?.userId

    if (!pid || pid <= 0) {
      console.warn('[Allergy] 无效 patientId，跳过加载')
      return
    }

    this.setData({ loading: true })
    try {
      const data = await get(`/allergies/${pid}`) as any[]
      // 防御：data 可能为 null 或非数组
      this.setData({ allergies: Array.isArray(data) ? data : [] })
    } catch (e) {
      console.error('[Allergy] 加载过敏记录失败:', e)
      this.setData({ allergies: [] })
    } finally {
      this.setData({ loading: false })
    }
  },

  onToggleAdd() {
    this.setData({
      showAdd: !this.data.showAdd,
      // 关闭时清空输入
      newAllergen: this.data.showAdd ? '' : this.data.newAllergen,
      newReaction: this.data.showAdd ? '' : this.data.newReaction,
    })
  },

  onAllergenInput(e: WechatMiniprogram.Input) {
    const val = (e.detail.value || '').slice(0, ALLERGEN_MAX_LEN)
    this.setData({ newAllergen: val })
  },

  onReactionInput(e: WechatMiniprogram.Input) {
    const val = (e.detail.value || '').slice(0, REACTION_MAX_LEN)
    this.setData({ newReaction: val })
  },

  async onAddAllergy() {
    const allergen = this.data.newAllergen.trim()
    if (!allergen) {
      wx.showToast({ title: '请输入过敏药物名称', icon: 'none' })
      return
    }
    if (allergen.length > ALLERGEN_MAX_LEN) {
      wx.showToast({ title: `名称不能超过${ALLERGEN_MAX_LEN}个字符`, icon: 'none' })
      return
    }

    // 防止重复提交
    if (this.data.submitting) return
    this.setData({ submitting: true })

    const app = getApp<IAppOption>()
    const pid = app?.globalData?.currentPatientId || app?.globalData?.userId
    if (!pid || pid <= 0) {
      wx.showToast({ title: '无法获取患者信息', icon: 'none' })
      this.setData({ submitting: false })
      return
    }

    try {
      await post('/allergies', {
        patient_id:            pid,
        drug_id_or_ingredient: allergen,
        reaction_type:         this.data.newReaction.trim() || null,
      })
      wx.showToast({ title: '已添加', icon: 'success' })
      this.setData({ showAdd: false, newAllergen: '', newReaction: '' })
      this.loadAllergies()
    } catch (e) {
      console.error('[Allergy] 添加失败:', e)
    } finally {
      this.setData({ submitting: false })
    }
  },

  async onDelete(e: WechatMiniprogram.TouchEvent) {
    const id = e.currentTarget.dataset.id as number

    // 防御：id 无效
    if (!id || typeof id !== 'number') {
      console.warn('[Allergy] onDelete: 无效 id:', id)
      return
    }

    // 防止重复点击同一条记录
    if (this.data.deletingIds.includes(id)) return

    wx.showModal({
      title: '确认删除',
      content: '确认删除该过敏记录？',
      success: async ({ confirm }) => {
        if (!confirm) return

        // 标记为删除中
        this.setData({ deletingIds: [...this.data.deletingIds, id] })

        try {
          await del(`/allergies/${id}`)
          wx.showToast({ title: '已删除', icon: 'success' })
          this.loadAllergies()
        } catch (e) {
          console.error('[Allergy] 删除失败:', e)
        } finally {
          // 移除删除中标记
          this.setData({
            deletingIds: this.data.deletingIds.filter((d: number) => d !== id)
          })
        }
      },
    })
  },
})
