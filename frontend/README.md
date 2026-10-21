# 私厨助手 · 前端 (Vue 3 + Vite)

个人私厨 LangGraph 项目的前端，纯本地测试用。

## 运行

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173

> 开发服务器把 `/api` 代理到后端 `http://127.0.0.1:8000`（见 `vite.config.js`）。
> 后端端口不一致时改 `vite.config.js` 里的 `server.proxy['/api'].target`。

## 功能

- 新建对话（每次新建后端生成一个 `thread_id`）
- 左侧历史对话列表：查看 / 删除
- 对话发送支持三种形式：纯文字 / 文字+图片 / 纯图片
- 图片在前端选择后本地预览，发送时以 multipart/form-data 上传

## 目录

```
frontend/
  index.html
  vite.config.js
  package.json
  src/
    main.js
    style.css
    App.vue          # 全部 UI 与交互逻辑
    api/index.js      # 后端接口封装（接口契约都在这里）
```

接口契约见同级目录 `../接口需求文档.md`。
