/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    basicSsl()
  ],
  build: {
    rollupOptions: {
      output: {
        // Split the stable framework libs into their own long-cached chunk so an
        // app-code change doesn't bust that (large) bundle's cache. Vite 8 /
        // rolldown requires the function form of manualChunks.
        manualChunks(id) {
          if (/[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler|axios)[\\/]/.test(id)) {
            return 'vendor'
          }
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
        secure: false,
      }
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
    include: ['src/**/*.{test,spec}.{js,jsx}'],
    exclude: ['node_modules', 'dist', '.git'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/pages/**', 'src/components/**'],
      exclude: ['**/*.test.*', '**/*.spec.*'],
    },
  },
})
