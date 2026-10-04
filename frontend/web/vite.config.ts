import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'web/src');
const PKG = (p: string) => path.join(ROOT, 'packages', p);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: '@', replacement: SRC },
      { find: '@qzdap/web-ui', replacement: PKG('ui/src/index.tsx') },
      { find: '@qzdap/web-api', replacement: PKG('api/src/index.ts') },
      { find: '@qzdap/web-types', replacement: PKG('types/src/index.ts') },
      { find: '@qzdap/web-hooks', replacement: PKG('hooks/src/index.ts') },
      { find: '@qzdap/web-utils', replacement: PKG('utils/src/index.ts') },
    ],
  },
  server: {
    host: true,
    port: Number(process.env.QZDAP_FRONTEND_PORT ?? 5200),
    strictPort: true,
    // 联调：浏览器请求经 pathMap 改写后落到 /v1/*（backend 真路径），
    // 仍走同源 → QZDAP gateway (:9200) → qzdap-app。
    // 保留 /api/* 以便尚未改写完的 pathMap 仍可经网关转发。
    // QZDAP gateway 默认端口 :9200 (bin/qzdap-stack/qzdap-env.sh)。
    proxy: {
      '/v1': {
        target: process.env.VITE_PROXY_TARGET ?? process.env.QZDAP_VITE_PROXY_TARGET ?? 'http://127.0.0.1:9200',
        changeOrigin: true,
        secure: false,
      },
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? process.env.QZDAP_VITE_PROXY_TARGET ?? 'http://127.0.0.1:9200',
        changeOrigin: true,
        secure: false,
      },
      '/healthz': {
        target: process.env.VITE_PROXY_TARGET ?? process.env.QZDAP_VITE_PROXY_TARGET ?? 'http://127.0.0.1:9200',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  preview: { host: true, port: 4173 },
  build: { target: 'es2022', sourcemap: true },
  test: { environment: 'jsdom' },
});
