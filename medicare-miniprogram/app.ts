App<IAppOption>({
  globalData: {
    token: '',
    userId: 0,
    openid: '',
    currentPatientId: 0,
  },

  onLaunch() {
    // ===== 调试模式：跳过登录，直接看 UI（上线前把这段删掉）=====
    // 身份：张建国（张爷爷患者端，patient_id=1）
    // 如果 token 过期，重新执行：
    // curl -X POST http://localhost:8000/api/v1/auth/wechat-login -H "Content-Type: application/json" -d "{\"code\": \"demo_openid_zhang\"}"
    this.globalData.token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJvcGVuaWQiOiJkZW1vX29wZW5pZF96aGFuZyIsImV4cCI6MTc3NzIxMjQxNn0.xe0RMT8DPnsoyL_szBATSSNPQGO68WY5X-aSf0Az4-c'
    this.globalData.userId = 1
    this.globalData.currentPatientId = 1
    wx.setStorageSync('token', this.globalData.token)
    wx.setStorageSync('userId', 1)
    // ===========================================================
  },
})
