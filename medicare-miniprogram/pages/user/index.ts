Page({
  data: {
    userInfo: {} as { name?: string; phone?: string }
  },
  onLoad() {
    const userInfo = wx.getStorageSync('userInfo') || {}
    this.setData({ userInfo })
  },
  onLogout() {
    wx.clearStorageSync()
    wx.reLaunch({ url: '/pages/login/index' })
  }
})
