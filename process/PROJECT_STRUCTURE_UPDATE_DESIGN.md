# 项目目录结构更新设计概要

## 核心目标
1. 基于当前仓库真实状态更新 `docs/3.项目目录结构.md`
2. 以 `backend/`、`frontend-vue/`、`docs/` 的现有代码和文档为准，不补充猜测内容
3. 明确当前主系统是 `backend + frontend-vue`，忽略 `frontend-streamlit` 的历史原型地位
4. 修正文档中与实际目录不一致的页面、组件、依赖描述

## 主要文件
- `docs/3.项目目录结构.md` - 需要更新的目录结构文档
- `docs/2.系统整体架构图.md` - 架构边界和主链路参考
- `docs/5.API接口定义.md` - 前后端接口边界参考
- `backend/app/main.py` - 后端入口
- `backend/app/services/conversation_service.py` - 统一消息入口服务
- `backend/app/services/analysis_service.py` - 任务化分析服务
- `frontend-vue/src/main.ts` - 前端入口
- `frontend-vue/src/router/index.ts` - 前端实际路由
- `frontend-vue/src/views/` - 前端实际页面目录
- `frontend-vue/src/components/` - 前端实际组件目录

## 更新策略
- 只更新目录结构说明文档，不调整实际代码目录
- 目录说明以真实存在的文件和目录为准
- 对“已弃用但仍保留”的目录单独标注，不作为当前主系统核心结构
- 对生成产物目录继续标记为非核心源码

## 关键判断
- 前端主系统以 `frontend-vue` 为准
- 后端主链路以 `ConversationService -> AnalysisService -> AnalysisWorkflow` 为准
- `frontend-vue/src/views`、`frontend-vue/src/components` 的说明必须按当前真实文件收敛
- 文档中的旧组件名、旧页面名、旧依赖描述需要校正
