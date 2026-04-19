import { MedicationService } from '../../../services/medication.service'
import { get } from '../../../services/request'

Page({
  data: {
    patients: [] as any[],
    currentPatient: null as any,
    todayStatus: null as any,
    loading: true,
    statusLoading: false,
  },

  async onShow() {
    await this.loadPatients()
  },

  async loadPatients() {
    this.setData({ loading: true })
    try {
      const patients = await get('/caregivers/patients') as any[]

      // 防御：patients 可能为 null 或非数组
      const safePatients = Array.isArray(patients) ? patients : []
      this.setData({ patients: safePatients })

      if (safePatients.length > 0) {
        const app = getApp<IAppOption>()
        // 优先使用上次选中的患者，找不到则默认第一个
        const savedPid = app?.globalData?.currentPatientId
        const matched = savedPid
          ? safePatients.find((p: any) => p?.id === savedPid)
          : null
        const currentPatient = matched || safePatients[0]

        // 防御：currentPatient 可能缺少 id 字段
        if (!currentPatient?.id) {
          console.warn('[Caregiver] 患者数据缺少 id 字段:', currentPatient)
          this.setData({ loading: false })
          return
        }

        if (app?.globalData) {
          app.globalData.currentPatientId = currentPatient.id
        }
        this.setData({ currentPatient })
        await this.loadTodayStatus(currentPatient.id)
      }
    } catch (e) {
      console.error('[Caregiver] 加载患者列表失败:', e)
    } finally {
      this.setData({ loading: false })
    }
  },

  async loadTodayStatus(patientId: number) {
    // 防御：patientId 无效时跳过
    if (!patientId || patientId <= 0) {
      console.warn('[Caregiver] loadTodayStatus: 无效 patientId:', patientId)
      return
    }

    this.setData({ statusLoading: true })
    try {
      const data = await MedicationService.getTodayStatus(patientId) as any

      // 防御：data 可能为 null，提供默认值
      const safeData = data || { total: 0, taken: 0, missed: 0, pending: 0, missed_list: [] }

      // 防御：missed_list 可能为 null
      if (!Array.isArray(safeData.missed_list)) {
        safeData.missed_list = []
      }

      this.setData({ todayStatus: safeData })
    } catch (e) {
      console.error('[Caregiver] 加载今日状态失败:', e)
      // 失败时设置空状态，避免页面显示旧数据
      this.setData({
        todayStatus: { total: 0, taken: 0, missed: 0, pending: 0, missed_list: [] }
      })
    } finally {
      this.setData({ statusLoading: false })
    }
  },

  onSwitchPatient(e: WechatMiniprogram.PickerChange) {
    const idx = Number(e.detail.value)
    const patients = this.data.patients

    // 防御：idx 越界
    if (idx < 0 || idx >= patients.length) {
      console.warn('[Caregiver] onSwitchPatient: idx 越界:', idx)
      return
    }

    const patient = patients[idx]
    if (!patient?.id) {
      console.warn('[Caregiver] onSwitchPatient: 患者数据异常:', patient)
      return
    }

    const app = getApp<IAppOption>()
    if (app?.globalData) {
      app.globalData.currentPatientId = patient.id
    }
    this.setData({ currentPatient: patient, todayStatus: null })
    this.loadTodayStatus(patient.id)
  },

  async onRemind(e: WechatMiniprogram.TouchEvent) {
    const logId = e.currentTarget.dataset.logId
    const app = getApp<IAppOption>()
    const pid = app?.globalData?.currentPatientId

    // 防御：logId 或 pid 无效
    if (!logId) {
      wx.showToast({ title: '记录信息异常', icon: 'none' })
      return
    }
    if (!pid) {
      wx.showToast({ title: '请先选择患者', icon: 'none' })
      return
    }

    try {
      await MedicationService.sendReminder(pid, logId)
      wx.showToast({ title: '提醒已发送', icon: 'success' })
    } catch (e) {
      console.error('[Caregiver] 发送提醒失败:', e)
      // 错误 Toast 已由 request.ts 统一处理
    }
  },

  onBindPatient() {
    wx.navigateTo({ url: '/pages/caregiver/bind/index' })
  },

  onRefresh() {
    this.loadPatients()
  },
})
