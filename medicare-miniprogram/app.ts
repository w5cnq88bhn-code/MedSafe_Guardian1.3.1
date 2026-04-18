App<IAppOption>({
  globalData: {
    token: '',
    userId: 0,
    openid: '',
    currentPatientId: 0,
  },

  onLaunch() {
    // ===== 调试模式：跳过登录，直接看 UI（上线前把这段删掉）=====
    // 身份：demo_openid_child（已绑定张爷爷 patient_id=1）
    // 如果 token 过期，去 http://172.27.55.84:8000/docs 重新登录拿新 token
    // POST /auth/wechat-login  body: {"code": "demo_openid_child"}
    this.globalData.token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoyLCJvcGVuaWQiOiJkZW1vX29wZW5pZF9jaGlsZCIsImV4cCI6MTc3NjkzMTMyOH0.hE1Y7mce4ZJU19nuu_dpWY_FlZVVgfDFMLZfmp_BBwo'
    this.globalData.userId = 2
    this.globalData.currentPatientId = 1  // 张爷爷，跳过绑定直接看监护页
    wx.setStorageSync('token', this.globalData.token)
    wx.setStorageSync('userId', 2)
    // ===========================================================
  },
})
