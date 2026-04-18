/**
 * MedicationService - 统一服药登记服务
 * 所有页面的服药登记都通过此服务调用，确保逻辑一致。
 * 防御性处理：所有公开方法在调用前校验参数有效性。
 */
import { post, del, get } from './request'

export interface TodayDrug {
  schedule_id:  number
  drug_id:      number
  drug_name:    string
  brand_name:   string
  dosage:       number
  dosage_unit:  string
  time_of_day:  string
  time_point:   string
  status:       'pending' | 'taken' | 'missed'
  log_id:       number | null
}

export interface FoodTip {
  drug_name:     string
  avoid_foods:   string[]
  caution_foods: string[]
  timing_tips:   string[]
  reason:        string
  severity:      'high' | 'medium' | 'low'
}

/** 校验 ID 是否有效（正整数） */
function _validId(id: any): boolean {
  return typeof id === 'number' && Number.isInteger(id) && id > 0
}

/** 校验 patientId，无效时抛出错误 */
function _assertPatientId(patientId: any): void {
  if (!_validId(patientId)) {
    throw new Error(`无效的 patientId: ${patientId}`)
  }
}

export class MedicationService {
  /**
   * 登记服药（核心方法，所有页面统一调用）
   * @param patientId  患者ID（必须为正整数）
   * @param scheduleId 服药计划ID（必须为正整数）
   * @param dose       实际剂量（可选，默认使用计划剂量）
   */
  static async manualTake(
    patientId: number,
    scheduleId: number,
    dose?: number
  ): Promise<{ id: number }> {
    _assertPatientId(patientId)
    if (!_validId(scheduleId)) {
      throw new Error(`无效的 scheduleId: ${scheduleId}`)
    }
    if (dose !== undefined && (typeof dose !== 'number' || dose <= 0 || isNaN(dose))) {
      throw new Error(`无效的 dose: ${dose}`)
    }

    return post('/logs', {
      patient_id:  patientId,
      schedule_id: scheduleId,
      actual_time: new Date().toISOString(),
      dose,
      source: 'manual',
    })
  }

  /**
   * 撤销服药登记（5分钟内有效）
   * @param logId 服药记录ID
   */
  static async undoTake(logId: number) {
    if (!_validId(logId)) {
      throw new Error(`无效的 logId: ${logId}`)
    }
    return del(`/logs/${logId}`)
  }

  /**
   * 获取今日待服药物列表
   * @param patientId 患者ID
   */
  static async getTodayDrugs(patientId: number): Promise<TodayDrug[]> {
    _assertPatientId(patientId)
    const result = await get(`/schedules/today/${patientId}`)
    // 防御：后端可能返回 null，统一转为空数组
    return Array.isArray(result) ? result as TodayDrug[] : []
  }

  /**
   * 搜索药物库
   * @param keyword 搜索关键词（至少1个字符）
   */
  static async searchDrugs(keyword: string) {
    if (!keyword || typeof keyword !== 'string' || !keyword.trim()) {
      return []
    }
    // 截断超长关键词，防止请求被后端拒绝
    const safeKeyword = keyword.trim().slice(0, 50)
    return get('/drugs/search', { keyword: safeKeyword })
  }

  /**
   * 冲突检测
   * @param patientId  患者ID
   * @param newDrugIds 新药 ID 列表
   */
  static async checkConflict(patientId: number, newDrugIds: number[]) {
    _assertPatientId(patientId)
    if (!Array.isArray(newDrugIds) || newDrugIds.length === 0) {
      throw new Error('newDrugIds 不能为空')
    }
    // 过滤无效 ID
    const validIds = newDrugIds.filter(id => _validId(id))
    if (validIds.length === 0) {
      throw new Error('newDrugIds 中没有有效的药物 ID')
    }
    return post('/drugs/check-conflict', {
      patient_id:   patientId,
      new_drug_ids: validIds,
    })
  }

  /**
   * 添加服药计划
   */
  static async addSchedule(data: {
    patient_id:  number
    drug_id:     number
    dosage:      number
    dosage_unit: string
    frequency:   number
    time_of_day: string
    time_point:  string
    start_date:  string
    end_date?:   string
  }) {
    // 参数校验
    _assertPatientId(data.patient_id)
    if (!_validId(data.drug_id)) throw new Error(`无效的 drug_id: ${data.drug_id}`)
    if (!data.dosage || data.dosage <= 0) throw new Error(`无效的 dosage: ${data.dosage}`)
    if (!data.start_date) throw new Error('start_date 不能为空')

    return post('/schedules', data)
  }

  /**
   * 停用服药计划
   * @param scheduleId 计划ID
   */
  static async removeSchedule(scheduleId: number) {
    if (!_validId(scheduleId)) {
      throw new Error(`无效的 scheduleId: ${scheduleId}`)
    }
    return del(`/schedules/${scheduleId}`)
  }

  /**
   * 获取今日服药状态（子女端）
   * @param patientId 患者ID
   */
  static async getTodayStatus(patientId: number) {
    _assertPatientId(patientId)
    const result = await get(`/logs/status/today/${patientId}`) as any
    // 防御：后端可能返回 null，提供默认值
    if (!result || typeof result !== 'object') {
      return { total: 0, taken: 0, missed: 0, pending: 0, missed_list: [] }
    }
    if (!Array.isArray(result.missed_list)) {
      result.missed_list = []
    }
    return result
  }

  /**
   * 一键提醒漏服
   * @param patientId 患者ID
   * @param logId     服药记录ID
   */
  static async sendReminder(patientId: number, logId: number) {
    _assertPatientId(patientId)
    if (!_validId(logId)) {
      throw new Error(`无效的 logId: ${logId}`)
    }
    return post(`/remind/${patientId}`, { log_id: logId })
  }

  /**
   * 获取今日饮食小贴士（药物-食物相互作用）
   * @param patientId 患者ID
   */
  static async getFoodTips(patientId: number): Promise<FoodTip[]> {
    _assertPatientId(patientId)
    const result = await get(`/food-tips/${patientId}`)
    return Array.isArray(result) ? result as FoodTip[] : []
  }
}
