// vite.config.ts
import { defineConfig } from "file:///Users/hugo/Desktop/STAGE/PLUGIN1-MEDomics/react_ui/node_modules/vite/dist/node/index.js";
import react from "file:///Users/hugo/Desktop/STAGE/PLUGIN1-MEDomics/react_ui/node_modules/@vitejs/plugin-react/dist/index.js";
var GO_PORT = process.env.STARHE_PORT ?? "8082";
var vite_config_default = defineConfig({
  plugins: [react()],
  // base './' : les assets utilisent des chemins relatifs, compatibles
  // avec le chargement en file:// par Electron (dist/index.html).
  base: "./",
  server: {
    port: 5173,
    proxy: {
      // Proxie les appels API vers le serveur Go
      "/starhe": {
        target: `http://localhost:${GO_PORT}`,
        changeOrigin: true
      },
      "/health": {
        target: `http://localhost:${GO_PORT}`,
        changeOrigin: true
      }
    }
  },
  build: {
    // Sortie dans dist/ pour intégration MEDomics
    outDir: "dist",
    rollupOptions: {
      output: {
        // Chunk unique pour faciliter l'injection dans Electron
        inlineDynamicImports: true
      }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvVXNlcnMvaHVnby9EZXNrdG9wL1NUQUdFL1BMVUdJTjEtTUVEb21pY3MvcmVhY3RfdWlcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIi9Vc2Vycy9odWdvL0Rlc2t0b3AvU1RBR0UvUExVR0lOMS1NRURvbWljcy9yZWFjdF91aS92aXRlLmNvbmZpZy50c1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vVXNlcnMvaHVnby9EZXNrdG9wL1NUQUdFL1BMVUdJTjEtTUVEb21pY3MvcmVhY3RfdWkvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tICd2aXRlJ1xuaW1wb3J0IHJlYWN0IGZyb20gJ0B2aXRlanMvcGx1Z2luLXJlYWN0J1xuXG4vLyBQb3J0IGR1IHNlcnZldXIgR28gXHUyMDE0IHN1cmNoYXJnZWFibGUgdmlhIFNUQVJIRV9QT1JUIChleDogU1RBUkhFX1BPUlQ9OTA5MCAuL3N0YXJ0X3JlYWN0LnNoKVxuY29uc3QgR09fUE9SVCA9IHByb2Nlc3MuZW52LlNUQVJIRV9QT1JUID8/ICc4MDgyJ1xuXG4vLyBodHRwczovL3ZpdGVqcy5kZXYvY29uZmlnL1xuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgcGx1Z2luczogW3JlYWN0KCldLFxuICAvLyBiYXNlICcuLycgOiBsZXMgYXNzZXRzIHV0aWxpc2VudCBkZXMgY2hlbWlucyByZWxhdGlmcywgY29tcGF0aWJsZXNcbiAgLy8gYXZlYyBsZSBjaGFyZ2VtZW50IGVuIGZpbGU6Ly8gcGFyIEVsZWN0cm9uIChkaXN0L2luZGV4Lmh0bWwpLlxuICBiYXNlOiAnLi8nLFxuICBzZXJ2ZXI6IHtcbiAgICBwb3J0OiA1MTczLFxuICAgIHByb3h5OiB7XG4gICAgICAvLyBQcm94aWUgbGVzIGFwcGVscyBBUEkgdmVycyBsZSBzZXJ2ZXVyIEdvXG4gICAgICAnL3N0YXJoZSc6IHtcbiAgICAgICAgdGFyZ2V0OiBgaHR0cDovL2xvY2FsaG9zdDoke0dPX1BPUlR9YCxcbiAgICAgICAgY2hhbmdlT3JpZ2luOiB0cnVlLFxuICAgICAgfSxcbiAgICAgICcvaGVhbHRoJzoge1xuICAgICAgICB0YXJnZXQ6IGBodHRwOi8vbG9jYWxob3N0OiR7R09fUE9SVH1gLFxuICAgICAgICBjaGFuZ2VPcmlnaW46IHRydWUsXG4gICAgICB9LFxuICAgIH0sXG4gIH0sXG4gIGJ1aWxkOiB7XG4gICAgLy8gU29ydGllIGRhbnMgZGlzdC8gcG91ciBpbnRcdTAwRTlncmF0aW9uIE1FRG9taWNzXG4gICAgb3V0RGlyOiAnZGlzdCcsXG4gICAgcm9sbHVwT3B0aW9uczoge1xuICAgICAgb3V0cHV0OiB7XG4gICAgICAgIC8vIENodW5rIHVuaXF1ZSBwb3VyIGZhY2lsaXRlciBsJ2luamVjdGlvbiBkYW5zIEVsZWN0cm9uXG4gICAgICAgIGlubGluZUR5bmFtaWNJbXBvcnRzOiB0cnVlLFxuICAgICAgfSxcbiAgICB9LFxuICB9LFxufSlcbiJdLAogICJtYXBwaW5ncyI6ICI7QUFBMlUsU0FBUyxvQkFBb0I7QUFDeFcsT0FBTyxXQUFXO0FBR2xCLElBQU0sVUFBVSxRQUFRLElBQUksZUFBZTtBQUczQyxJQUFPLHNCQUFRLGFBQWE7QUFBQSxFQUMxQixTQUFTLENBQUMsTUFBTSxDQUFDO0FBQUE7QUFBQTtBQUFBLEVBR2pCLE1BQU07QUFBQSxFQUNOLFFBQVE7QUFBQSxJQUNOLE1BQU07QUFBQSxJQUNOLE9BQU87QUFBQTtBQUFBLE1BRUwsV0FBVztBQUFBLFFBQ1QsUUFBUSxvQkFBb0IsT0FBTztBQUFBLFFBQ25DLGNBQWM7QUFBQSxNQUNoQjtBQUFBLE1BQ0EsV0FBVztBQUFBLFFBQ1QsUUFBUSxvQkFBb0IsT0FBTztBQUFBLFFBQ25DLGNBQWM7QUFBQSxNQUNoQjtBQUFBLElBQ0Y7QUFBQSxFQUNGO0FBQUEsRUFDQSxPQUFPO0FBQUE7QUFBQSxJQUVMLFFBQVE7QUFBQSxJQUNSLGVBQWU7QUFBQSxNQUNiLFFBQVE7QUFBQTtBQUFBLFFBRU4sc0JBQXNCO0FBQUEsTUFDeEI7QUFBQSxJQUNGO0FBQUEsRUFDRjtBQUNGLENBQUM7IiwKICAibmFtZXMiOiBbXQp9Cg==
