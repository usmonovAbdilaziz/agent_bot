import { defineConfig } from 'vite';
import { createHash } from 'node:crypto';

export default defineConfig({
  base: './',
  root: 'react_src',
  publicDir: false,
  plugins: [{ name: 'static-assets-path', transformIndexHtml: { order: 'post', handler(html, { bundle }) {
    for (const file of ['app.js', 'style.css']) {
      const asset = bundle?.[file];
      const version = asset ? '?v=' + createHash('sha256').update(asset.type === 'chunk' ? asset.code : asset.source).digest('hex').slice(0, 12) : '';
      html = html.replaceAll(`./${file}`, `./assets/${file}${version}`);
    }
    return html;
  } } }],
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
