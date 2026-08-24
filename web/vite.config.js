import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// El frontend va por el 5173 y la API por el 8000, pero los dos se pueden
// mover: en esta maquina el 5173 lo tiene otro proyecto y el 8000 esta
// reservado por el sistema.
//
//   CUADRE_WEB_PUERTO=5180 CUADRE_API=http://127.0.0.1:8010 npm run dev
//
// El proxy de /api evita tener que pensar en CORS mientras se desarrolla, y en
// produccion lo hace nginx, asi que el codigo usa siempre rutas relativas.
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.CUADRE_WEB_PUERTO || 5173),
    proxy: {
      '/api': {
        target: process.env.CUADRE_API || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
