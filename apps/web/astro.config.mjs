import svelte from '@astrojs/svelte'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'astro/config'

export default defineConfig({
  output: 'static',
  integrations: [svelte()],
  vite: {
    plugins: [tailwindcss()],
    server: {
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:18080',
          changeOrigin: true
        }
      }
    }
  }
})
