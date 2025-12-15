import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0', // Allow external connections
    port: 5173,  // Vite default port
    strictPort: false, // If port 5173 is in use, try next available port
    proxy: {
      '/api': {
        target: 'http://localhost:8001',  // Backend default port
        changeOrigin: true,
        rewrite: (path) => path,
        timeout: 300000, 
        proxyTimeout: 300000, 
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            if (req.url.includes('/api/chat')) {
              proxyReq.setTimeout(0)
            }
          })
        }
      },
      '/outputs': {
        target: 'http://localhost:8001',  // Backend default port
        changeOrigin: true,
        rewrite: (path) => path
      },
      '/uploads': {
        target: 'http://localhost:8001',  // Backend default port
        changeOrigin: true,
        rewrite: (path) => path
      }
    }
  }
})

