import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const apiTarget = process.env.PATHLAB_DEV_API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
  test: {
    environment: 'jsdom',
    include: ['src/test/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: './src/test/setup.ts',
    testTimeout: 20_000,
    server: {
      deps: {
        inline: ['@phosphor-icons/react'],
      },
    },
  },
  server: {
    proxy: {
      '/api/v1/uploads': 'http://127.0.0.1:8080',
      '/api': apiTarget,
      '/livez': apiTarget,
      '/readyz': apiTarget,
      '/tiles': apiTarget,
    },
  },
})
