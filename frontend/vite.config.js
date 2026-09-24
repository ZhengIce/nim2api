import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: '/static/',
  plugins: [vue()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/admin': 'http://127.0.0.1:5010',
      '/v1': 'http://127.0.0.1:5010',
    },
  },
})
