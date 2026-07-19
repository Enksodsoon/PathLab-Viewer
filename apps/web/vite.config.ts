import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
  server: {
    proxy: {
      '/api/v1/uploads': 'http://127.0.0.1:8080',
      '/api': 'http://127.0.0.1:8000',
      '/livez': 'http://127.0.0.1:8000',
      '/readyz': 'http://127.0.0.1:8000',
      '/tiles': 'http://127.0.0.1:8000',
    },
  },
})
