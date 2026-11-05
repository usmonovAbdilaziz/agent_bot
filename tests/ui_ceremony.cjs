const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  for(const width of [360,1280]) for(const preview of [false,true]) {
   const context=await browser.newContext({viewport:{width,height:800}}); const page=await context.newPage();
   const errors=[]; page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>{window.Telegram={WebApp:{initData:'test',ready(){},expand(){}}}});
   await context.route('https://telegram.org/**',r=>r.fulfill({body:''}));
   await context.route('http://qadam.test/**',async r=>{
    const u=new URL(r.request().url());
    if(u.pathname.startsWith('/api/')) return r.fulfill({contentType:'application/json',body:JSON.stringify({id:1,type:'ceremony',design:'ceremony_elegant',title:'Ali va Vali',description:'Xush kelibsiz',media_kind:'none',status:'ready',preview,details:{layout:{text_position:'top'}}})});
    const f=u.pathname==='/'?'index.html':path.basename(u.pathname);
    return r.fulfill({contentType:f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(path.join(root,'web_minimal',f))});
   });
   await page.goto('http://qadam.test/?invite=1');
   await page.getByRole('heading',{name:'Ali va Vali'}).waitFor();
   assert.equal(await page.locator('.invitation.position-top').count(),1);
   assert.equal(await page.locator('button').count(),0);
   assert.equal(await page.getByText('Xush kelibsiz').count(),1);
   assert.deepEqual(errors,[]);
   await context.close();
  }
  console.log('ceremony temporary receiver: 360/1280px, sender and receiver, no action buttons: PASS');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
