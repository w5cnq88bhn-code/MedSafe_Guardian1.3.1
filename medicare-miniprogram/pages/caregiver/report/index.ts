import { API_BASE } from '../../../utils/constants'

/** PDF 下载超时（毫秒），报告生成较慢，给足时间 */
const DOWNLOAD_TIMEOUT = 60000

Page({
  data: {
    generating: false,
  },

  async onDownloadReport() {
    const app = getApp<IAppOption>()
    const pid = app?.globalData?.currentPatientId

    // 防御：未选择患者
    if (!pid) {
      wx.showToast({ title: '请先在监护页选择患者', icon: 'none' })
      return
    }

    // 防止重复点击
    if (this.data.generating) return
    this.setData({ generating: true })

    wx.showLoading({ title: '生成报告中...', mask: true })

    // 防御：token 获取失败时给出提示
    let token = ''
    try {
      token = wx.getStorageSync('token') || app?.globalData?.token || ''
    } catch {
      token = app?.globalData?.token || ''
    }

    if (!token) {
      wx.hideLoading()
      this.setData({ generating: false })
      wx.showToast({ title: '登录已过期，请重新登录', icon: 'none' })
      setTimeout(() => wx.reLaunch({ url: '/pages/login/index' }), 1500)
      return
    }

    const downloadUrl = `${API_BASE}/reports/${pid}`

    wx.downloadFile({
      url: downloadUrl,
      timeout: DOWNLOAD_TIMEOUT,
      header: { Authorization: `Bearer ${token}` },
      success: (res) => {
        wx.hideLoading()

        if (res.statusCode !== 200) {
          console.error('[Report] 下载失败:', res.statusCode)
          wx.showToast({ title: `生成失败（${res.statusCode}）`, icon: 'none' })
          this.setData({ generating: false })
          return
        }

        // 防御：tempFilePath 为空
        if (!res.tempFilePath) {
          wx.showToast({ title: '文件路径异常，请重试', icon: 'none' })
          this.setData({ generating: false })
          return
        }

        this._openPdf(res.tempFilePath)
      },
      fail: (err) => {
        wx.hideLoading()
        this.setData({ generating: false })

        const errMsg: string = (err as any)?.errMsg || ''
        if (errMsg.includes('timeout')) {
          wx.showToast({ title: '报告生成超时，请稍后重试', icon: 'none' })
        } else if (errMsg.includes('fail')) {
          wx.showToast({ title: '下载失败，请检查网络', icon: 'none' })
        } else {
          wx.showToast({ title: '下载失败，请重试', icon: 'none' })
        }
        console.error('[Report] downloadFile 失败:', errMsg)
      },
    })
  },

  _openPdf(filePath: string) {
    wx.openDocument({
      filePath,
      fileType: 'pdf',
      showMenu: true,
      success: () => {
        wx.showToast({ title: '报告已生成', icon: 'success' })
        this.setData({ generating: false })
      },
      fail: (err) => {
        // 部分设备不支持直接打开 PDF，降级到保存文件
        console.warn('[Report] openDocument 失败，尝试保存:', (err as any)?.errMsg)
        this._savePdf(filePath)
      },
    })
  },

  _savePdf(tempFilePath: string) {
    wx.saveFile({
      tempFilePath,
      success: (saveRes) => {
        this.setData({ generating: false })
        wx.showModal({
          title: '报告已保存',
          content: `文件已保存，可在微信"我的文件"中查看`,
          showCancel: false,
        })
      },
      fail: (err) => {
        this.setData({ generating: false })
        console.error('[Report] saveFile 失败:', (err as any)?.errMsg)
        wx.showToast({ title: '保存失败，请重试', icon: 'none' })
      },
    })
  },
})
