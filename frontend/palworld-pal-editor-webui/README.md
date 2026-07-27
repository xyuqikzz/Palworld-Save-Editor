# Palworld-Save-Editor Web UI

Palworld-Save-Editor 的 Vue 3 前端。它依赖主项目提供的 Flask API，生产构建会被复制到 `src/palworld_pal_editor/webui/` 并随桌面端、Web 模式和发行包一起提供。

## 环境要求

- 当前 LTS 版本的 Node.js
- npm
- 需要联调时，在仓库根目录启动 Python 后端

## 常用命令

```bash
npm ci
npm run dev
npm test
npm run build
```

- `npm run dev`：启动 Vite 开发服务器，并按 `vite.config.js` 代理后端请求。
- `npm test`：运行 `tests/` 中的前端领域与布局契约测试。
- `npm run build`：生成 `dist/`；目录为本地产物，不提交到 Git。

前后端完整启动、测试和贡献说明见仓库根目录 [README.cn.md](../../README.cn.md)。
