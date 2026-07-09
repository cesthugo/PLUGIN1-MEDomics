import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Go server port — overridable via STARHE_PORT (e.g. STARHE_PORT=9090 ./start_react.sh)
const GO_PORT = process.env.STARHE_PORT ?? '8082'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // base './' : assets use relative paths, compatible
  // with file:// loading by Electron (dist/index.html).
  base: './',
  server: {
    port: 5173,
    proxy: {
      // Proxies the API calls to the Go server
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
    // Output to dist/ for MEDomics integration
    outDir: 'dist',
    rollupOptions: {
      output: {
        // Single chunk to ease injection into Electron
        inlineDynamicImports: true,
      },
    },
  },
})
