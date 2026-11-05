// Browser-only fixture checks. No real Telegram identity, token or messages.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const out=path.join(root,'output/minimal');
(async()=>{
 await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true});
 const results=[];
 try {
  for(const [name,width,height] of [['mobile',390,844],['desktop',1280,800],['small',280,600]]) {
   const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});
   const page=await context.newPage();
   let accepted=0, fail=true;
   const counts=[];
   const errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.addInitScript(()=>{window.Telegram={WebApp:{initData:'TEST_FIXTURE',ready(){},expand(){},close(){window.didClose=true;},HapticFeedback:{impactOccurred(){},notificationOccurred(){}}}};});
   let kind='none', preview=false, design='classic', videoBytes=null, videoType='video/webm';
   await context.route('https://telegram.org/**',route=>route.fulfill({contentType:'application/javascript',body:''}));
   await context.route('http://qadam.test/**',async route=>{
    const url=new URL(route.request().url());
    if(url.pathname.endsWith('/accept')) {
     accepted++;
     counts.push(route.request().postDataJSON().no_attempts);
     return route.fulfill({status:fail?502:200,contentType:'application/json',body:JSON.stringify(fail?{error:'Aloqa uzildi. Qayta urinib ko‘ring.'}:{accepted:true})});
    }
    if(url.pathname.endsWith('/media') && kind==='video') return route.fulfill({contentType:videoType,body:videoBytes});
    if(url.pathname.endsWith('/media')) return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180"><rect width="180" height="180" fill="#dde8f0"/><text x="90" y="112" text-anchor="middle" font-family="sans-serif" font-size="64" fill="#38566e">M</text></svg>'});
    if(url.pathname.startsWith('/api/') || url.pathname.startsWith('/bot/api/')) return route.fulfill({contentType:'application/json',body:JSON.stringify({id:1,title:'Munis',description:'Siz bilan uchrashsam bo‘ladimi?\nBir piyola choy ustida suhbatlashamiz.',media_kind:kind,status:'ready',preview,design})});
    const file=url.pathname==='/' || url.pathname==='/bot/'?'index.html':path.basename(url.pathname);
    return route.fulfill({contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(path.join(root,'web_minimal',file))});
   });
   await page.goto('http://qadam.test/?invite=1');
   await page.getByRole('button',{name:'Ha',exact:true}).waitFor();
   assert.equal(await page.locator('button').count(),2);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:path.join(out,`${name}-no-media.png`),fullPage:true});
   const no=page.locator('.no');
   for(let i=0;i<10;i++) {await no.focus(); await page.keyboard.press('Enter');}
   assert.equal(await page.locator('.sticker').isVisible(),true);
   assert.equal(accepted,0);
   const before=await no.boundingBox();
   await no.dispatchEvent('pointerdown',{pointerType:'touch'});
   const after=await no.boundingBox();
   assert.notDeepEqual([before.x,before.y],[after.x,after.y]);
   const yes=await page.locator('.yes').boundingBox();
   assert.ok(after.y>=yes.y+yes.height || after.x>=yes.x+yes.width || after.x+after.width<=yes.x);
   await page.screenshot({path:path.join(out,`${name}-sticker.png`),fullPage:true});
   await page.reload();
   await page.getByRole('button',{name:'Ha',exact:true}).waitFor();
   await page.getByRole('button',{name:'Ha',exact:true}).click();
   await page.getByText('Aloqa uzildi. Qayta urinib ko‘ring.').waitFor();
   assert.equal(await page.locator('.yes').isEnabled(),true);
   fail=false;
   await page.emulateMedia({reducedMotion:'no-preference'});
   await page.getByRole('button',{name:'Ha',exact:true}).click();
   await page.getByRole('heading',{name:'Tanlovingiz uchun rahmat!'}).waitFor();
   assert.equal(accepted,2);
   assert.deepEqual(counts,[11,11]);
   await page.screenshot({path:path.join(out,`${name}-accepted.png`),fullPage:true});
   await page.waitForFunction(()=>window.didClose===true);
   preview=true;kind='photo';
   await page.goto('http://qadam.test/?invite=1');
   await page.locator('img.media').waitFor();
   await page.waitForFunction(()=>document.querySelector('img').naturalWidth>0);
   assert.equal(await page.locator('.yes').isDisabled(),true);
   assert.equal(await page.locator('.no').isDisabled(),true);
   await page.screenshot({path:path.join(out,`${name}-preview.png`),fullPage:true});
   for (const option of ['romantic','playful','elegant']) {
    design=option;
    await page.goto('http://qadam.test/?invite=1');
    await page.locator(`.invitation.design-${option}`).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.equal(await page.locator('.yes').isDisabled(),true);
   }
   await page.goto('http://qadam.test/bot/?invite=1');
   await page.locator('.invitation.design-elegant').waitFor();
   // A browser-encoded video fixture exercises actual playback and sound controls.
   if(name==='mobile') {
    const encoded=await page.evaluate(async()=>{
     const canvas=document.createElement('canvas');canvas.width=180;canvas.height=180;
     const ctx=canvas.getContext('2d');ctx.fillStyle='#dde8f0';ctx.fillRect(0,0,180,180);
     const stream=canvas.captureStream(10);
     const mime='video/webm;codecs=vp8';
     const recorder=new MediaRecorder(stream,{mimeType:mime});const parts=[];
     recorder.ondataavailable=e=>parts.push(e.data);
     const done=new Promise(resolve=>recorder.onstop=resolve);
     recorder.start();ctx.fillStyle='#38566e';ctx.fillRect(50,50,80,80);
     let frame=0;const tick=setInterval(()=>{ctx.fillStyle=frame++%2?'#38566e':'#47657e';ctx.fillRect(50,50,80,80);},60);
     await new Promise(resolve=>setTimeout(resolve,900));clearInterval(tick);recorder.stop();await done;
     stream.getTracks().forEach(track=>track.stop());
     return {mime,bytes:Array.from(new Uint8Array(await new Blob(parts).arrayBuffer()))};
    });
    videoBytes=Buffer.from(encoded.bytes);videoType=encoded.mime;kind='video';preview=false;
    await page.goto('http://qadam.test/?invite=1');
    await page.locator('video.media').waitFor();
    await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
    assert.equal(await page.locator('video').evaluate(v=>v.muted),true);
    await page.getByRole('button',{name:'Ovozni yoqish'}).click();
    assert.equal(await page.locator('video').evaluate(v=>v.muted),false);
    await page.screenshot({path:path.join(out,'mobile-video.png'),fullPage:true});
    results.push('video: decoded browser video fixture, circular rendering, mute/unmute PASS');
   }
   assert.deepEqual(errors,[]);
   results.push(`${name}: layout, 10 attempts, sticker, continued movement, failed accept retry, fireworks/close, photo preview PASS`);
   await context.close();
  }
  await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify(results,null,2));
  console.log(results.join('\n'));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
