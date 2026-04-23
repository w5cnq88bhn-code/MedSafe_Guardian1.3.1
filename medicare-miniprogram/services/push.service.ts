/**
 * 订阅消息授权服务
 * 在需要推送的场景前调用 requestSubscribe()
 */

// 在微信公众平台申请后填入实际模板ID
const TEMPLATE_IDS = [
  'your_reminder_template_id',
  'your_missed_template_id',
]

export class PushService {
  /** 请求订阅消息授权 */
  static requestSubscribe(): Promise<boolean> {
    return new Promise((resolve) => {
      wx.requestSubscribeMessage({
        tmplIds: TEMPLATE_IDS,
        success(res) {
          const allAccepted = TEMPLATE_IDS.every(
            id => res[id] === 'accept'
          )
          resolve(allAccepted)
        },
        fail() {
          resolve(false)
        },
      })
    })
  }
}
