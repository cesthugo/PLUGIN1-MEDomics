import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Port du serveur Go — surchargeable via STARHE_PORT (ex: STARHE_PORT=9090 ./start_react.sh)
const GO_PORT = process.env.STARHE_PORT ?? '8082'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // base './' : les assets utilisent des chemins relatifs, compatibles
  // avec le chargement en file:// par Electron (dist/index.html).
  base: './',
  server: {
    port: 5173,
    proxy: {
      // Proxie les appels API vers le serveur Go
      '/starhe': {
        target: `http://localhost:${GO_PORT}`,
        changeOrigin: true,
      },
      '/health': {
        target: `http://localhost:${GO_PORT}`,
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
