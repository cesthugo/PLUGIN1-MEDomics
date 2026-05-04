import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // base './' : les assets utilisent des chemins relatifs, compatibles
  // avec le chargement en file:// par Electron (dist/index.html).
  base: './',
  server: {
    port: 5173,
    proxy: {
      // Proxie les appels API vers le serveur Go (port 8080)
      '/starhe': {
        target: 'http://localhost:8082',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8082',
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
