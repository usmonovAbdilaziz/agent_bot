import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  root: 'react_src',
  publicDir: false,
  plugins: [{ name: 'static-assets-path', transformIndexHtml: { order: 'post', handler: html => html.replaceAll('./app.js', './assets/app.js').replaceAll('./style.css', './assets/style.css') } }],
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
