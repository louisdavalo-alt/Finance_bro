import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // En dev, le frontend tourne sur son propre port (5173) et l'API FastAPI sur 8100 (voir
      // README racine du projet) : ce proxy évite tout souci de CORS/auth cookie, exactement
      // comme en production où ils partagent la même origine.
      '/api': {
        target: 'http://127.0.0.1:8100',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
