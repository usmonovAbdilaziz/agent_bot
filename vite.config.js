import { defineConfig } from 'vite';

export default defineConfig({
  base: '/assets/',
  root: 'react_src',
  publicDir: false,
  build: {
    outDir: '../web_minimal',
    emptyOutDir: false,
    rollupOptions: {
      output: {
        entryFileNames: 'app.js',
        assetFileNames: ({ name }) => name?.endsWith('.css') ? 'style.css' : '[name][extname]'
      }
    }
  }
});
