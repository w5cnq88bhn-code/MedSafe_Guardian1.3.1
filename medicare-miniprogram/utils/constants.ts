// 本地调试：用电脑局域网IP（微信模拟器不认localhost，需用实际IP）
// 查IP方法：命令行运行 ipconfig，找 IPv4 地址，替换下面的 192.168.x.x
export const API_BASE = 'http://***********.84:8000/api/v1'

// 连接同学的后端（把下面地址换成同学用 ngrok 生成的地址）
// export const API_BASE = 'https://你同学的ngrok地址/api/v1'

export const TIME_SLOT_CN: Record<string, string> = {
  morning: '早',
  afternoon: '中',
  evening: '晚',
}

export const STATUS_CN: Record<string, string> = {
  taken: '已服',
  missed: '漏服',
  pending: '待服',
}

export const SEVERITY_CN: Record<string, string> = {
  high: '高危',
  medium: '中度',
  low: '轻微',
}

export const SEVERITY_COLOR: Record<string, string> = {
  high: '#e74c3c',
  medium: '#e67e22',
  low: '#f1c40f',
}
