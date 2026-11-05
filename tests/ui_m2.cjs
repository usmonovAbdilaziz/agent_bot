const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const designs=require('../react_src/designs.json');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  for(const [width,height] of [[360,640],[1280,800]]) {
   for(const design of designs) {
    const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});
    const page=await context.newPage(); let posted=null, gate=false;
    await page.addInitScript(()=>{ window.Telegram={WebApp:{initData:'TEST',ready(){},expand(){},close(){},HapticFeedback:{impactOccurred(){},notificationOccurred(){}}}}; window.drawCalls=0; for(const name of ['fillText','fillRect','arc','ellipse']) { const original=CanvasRenderingContext2D.prototype[name]; CanvasRenderingContext2D.prototype[name]=function(...args){window.drawCalls++; return original.apply(this,args)}; } });
    await context.route('https://telegram.org/**',r=>r.fulfill({body:''}));
    await context.route('http://qadam.test/**',async r=>{
     const u=new URL(r.request().url());
     if(u.pathname.endsWith('/accept')) {posted=r.request().postDataJSON(); return r.fulfill({status:gate?200:500,contentType:'application/json',body:JSON.stringify(gate?{accepted:true}:{error:'Sinov xatosi'})});}
     if(u.pathname.startsWith('/api/')) return r.fulfill({contentType:'application/json',body:JSON.stringify({id:1,title:'Taklif',description:'Sizni taklif qilamiz',media_kind:'none',status:'ready',preview:false,design:design.id,type:'fun',details:{layout:{text_position:'bottom'}}})});
     const file=u.pathname==='/'?'index.html':path.basename(u.pathname);
     return r.fulfill({contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(path.join(root,'web_minimal',file))});
    });
    await page.goto('http://qadam.test/?invite=1');
    await page.locator('.yes').waitFor();
    const colors=await page.locator('.text-panel').evaluate(el=>({foreground:getComputedStyle(el).color,background:getComputedStyle(el).backgroundColor}));
    assert.equal(colors.foreground,'rgb(255, 255, 255)');
    const alpha=Number(colors.background.match(/[\d.]+/g)[3]), white=1-alpha;
    const lum=white<=0.04045?white/12.92:((white+0.055)/1.055)**2.4;
    assert.ok(1.05/(lum+.05)>=4.5,design.id+' contrast');
    const no=page.locator('.no');
    for(let i=1;i<=50;i++) {
     await no.focus(); await page.keyboard.press('Enter');
     const geometry=await page.evaluate(()=>{
      const yes=document.querySelector('.yes').getBoundingClientRect(), no=document.querySelector('.no').getBoundingClientRect(), area=document.querySelector('.arena').getBoundingClientRect();
      return {yes:{x:yes.x,y:yes.y,right:yes.right,bottom:yes.bottom,width:yes.width,height:yes.height},no:{x:no.x,y:no.y,right:no.right,bottom:no.bottom},area:{x:area.x,y:area.y,right:area.right,bottom:area.bottom},vw:innerWidth,vh:innerHeight};
     });
     const {yes,no:nb,area}=geometry;
     assert.ok(nb.x>=area.x-0.1 && nb.right<=area.right+0.1 && nb.y>=area.y-0.1 && nb.bottom<=area.bottom+0.1,`${design.id}/${width}/${i} no outside arena ${JSON.stringify(geometry)}`);
     assert.ok(yes.x>=0 && yes.right<=width && yes.y>=0 && yes.bottom<=height && nb.x>=0 && nb.right<=width && nb.y>=0 && nb.bottom<=height,`${design.id}/${width}/${i} viewport ${JSON.stringify(geometry)}`);
     assert.ok(nb.y>=yes.bottom || nb.x>=yes.right || nb.right<=yes.x || nb.bottom<=yes.y,`${design.id}/${width}/${i} overlap`);
     if([1,5,10,20,50].includes(i)) {
      assert.ok(Math.abs(yes.width-104*(1+Math.min(i*.04,.8)))<1,`scale ${design.id}/${i}`);
      if(i>=5) assert.notEqual(await no.textContent(),'Yo‘q');
      if(i===10) assert.equal(await page.locator('.sticker').isVisible(),true);
      if(i>=20) assert.equal(await page.locator('.strong-reaction').count(),1);
      if(i>=20) assert.equal(await page.locator('.invitation-content').evaluate(el=>getComputedStyle(el).animationName),'none');
     }
    }
    await page.locator('.yes').click();
    await page.getByText('Sinov xatosi').waitFor();
    assert.equal(await page.locator('.success').count(),0); assert.equal(posted.no_attempts,50);
    gate=true; await page.emulateMedia({reducedMotion:'no-preference'}); await page.locator('.yes').click();
    await page.locator('.success').waitFor(); assert.equal(posted.no_attempts,50);
    await page.waitForFunction(()=>window.drawCalls>0);
    assert.equal(await page.locator('#fireworks').evaluate(el=>getComputedStyle(el).pointerEvents),'none');
    await context.close();
   }
   console.log(`${width}px: all ${designs.length} designs, contrast and 50 keyboard attempts passed`);
  }
 } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1});
