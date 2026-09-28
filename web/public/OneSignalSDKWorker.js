// OneSignal Web Push 的 Service Worker（OneSignal Web SDK v16）
//
// 这个文件必须由**域名根路径** `/OneSignalSDKWorker.js` 提供，原因：
//   Service Worker 的默认作用域 = 文件所在目录，只有放在根目录才能覆盖全站；
//   放在 /assets/ 下只能管到 /assets/，推送点击回调等会失效。
//
// 部署形态是 nginx 把 `location /` 全量反代给 FastAPI，并没有把 web/dist 当静态目录暴露，
// 所以后端专门加了 `GET /OneSignalSDKWorker.js` 路由（见 app/main.py）来托管本文件：
//   - 构建后取 web/dist/OneSignalSDKWorker.js（本文件被 Vite 从 public/ 原样拷贝过去）
//   - 未构建时后端返回内联的等价内容兜底
//
// 修改本文件后**无需**改后端常量（后者只是 dist 缺失时的兜底副本），
// 但两处内容要保持一致，避免开发环境与生产环境行为不同。
importScripts('https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js');
