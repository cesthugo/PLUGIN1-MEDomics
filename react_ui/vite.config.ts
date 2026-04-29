import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxie les appels API vers le serveur Go (port 8080)
      '/starhe': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Sortie dans dist/ pour intégration MEDomics
    outDir: 'dist',
    rollupOptions: {
      output: {
        // Chunk unique pour faciliter l'injection dans Electron
        inlineDynamicImports: true,
      },
    },
  },
})
