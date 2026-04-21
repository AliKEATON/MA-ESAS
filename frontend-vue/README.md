# frontend-vue

Vue 版 MA-ESAS 前端，严格复用现有 FastAPI 接口。

## 技术栈

- Vue 3
- Vite
- TypeScript
- Vue Router
- Pinia
- Axios
- ECharts / vue-echarts

## 运行方式

```bash
npm install
npm run dev
```

默认后端地址为 `http://localhost:8000`。如需修改，可在运行前设置：

```bash
VITE_API_BASE_URL=http://localhost:8000
```

## 页面目标

- 左侧会话侧边栏，右侧聊天区
- 用户消息使用右侧气泡
- assistant 回复不使用气泡
- 聊天内容区居中显示
- 分析进度作为临时处理态
- 分析结果、图表和证据渲染在 assistant 结果消息中
