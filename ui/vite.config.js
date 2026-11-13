import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 8191,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8198',
        changeOrigin: true
      },
      '/stream.mjpg': {
        target: 'http://127.0.0.1:8198',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
});

