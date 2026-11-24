const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const image = execFileSync('python3', ['-c', "import sys; from wedding import render_wedding; sys.stdout.buffer.write(render_wedding({'groom':'Farrux','bride':'Nasiba','date':'12.11.2027','time':'17:00','address':'Qamashi tumani, Shirinabonu to‘yxonasi'}))"], { cwd: root });
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [280, 390, 1280]) {
      const page = await browser.newPage({ viewport: { width, height: 844 } });
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(() => { window.Telegram = { WebApp: { initData: 'fixture', ready(){}, expand(){} } }; });
      await page.route('https://telegram.org/**', route => route.fulfill({ contentType: 'application/javascript', body: '' }));
      let imageRequests=0;
      await page.route('http://qadam.test/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname.endsWith('/wedding-image') && ++imageRequests === 1) return route.fulfill({status:503,json:{error:'Rasm yuklanmadi'}});
        if (url.pathname.endsWith('/wedding-image')) return route.fulfill({ contentType: 'image/png', body: image });
        if (url.pathname.startsWith('/api/')) return route.fulfill({ contentType: 'application/json', json: { id: 1, type: 'wedding', design: 'wedding_classic', status: 'ready', preview: false, details:{groom:'Farrux',bride:'Nasiba',date:'12.11.2027',time:'17:00',address:'Qamashi tumani, Shirinabonu to‘yxonasi'} } });
        const file = url.pathname === '/' ? 'index.html' : path.basename(url.pathname);
        return route.fulfill({ contentType: file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html', body: await fs.readFile(path.join(root,'web_minimal',file)) });
      });
      await page.goto('http://qadam.test/?invite=1');
      await page.getByText('Qamashi tumani, Shirinabonu to‘yxonasi',{exact:true}).waitFor();
      await page.getByRole('button',{name:'Qayta yuklash'}).click();
      await page.locator('img[alt="To‘y taklifnomasi"]').waitFor();
      await page.waitForFunction(() => document.querySelector('img').naturalWidth > 0);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      assert.equal(await page.locator('.yes, .no').count(), 0);
      assert.deepEqual(errors, []);
      if (width === 390) await page.screenshot({path:'/tmp/qadam-wedding-mobile.png', fullPage:true});
      await page.close();
    }
    console.log('Wedding image layout and no fun controls: 280, 390, 1280px PASS');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode=1; });
