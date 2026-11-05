const {chromium}=require('playwright'); const fs=require('node:fs/promises');const path=require('node:path');const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),output=path.join(root,'output','m6');const designs=require('../react_src/designs.json');
const sizes=[[360,640],[390,844],[768,1024],[1280,800]], modes=['preview','ready','answered','no-media','photo','video','media-error'];
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO5+hc8AAAAASUVORK5CYII=','base64');
(async()=>{
 await fs.mkdir(output,{recursive:true});const browser=await chromium.launch({headless:true});const findings=[];let count=0;
 try {
  const seed=await browser.newPage();const bytes=await seed.evaluate(async()=>{const c=document.createElement('canvas');c.width=100;c.height=100;const x=c.getContext('2d');x.fillStyle='#eee';x.fillRect(0,0,100,100);const stream=c.captureStream(10),r=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8'}),parts=[];r.ondataavailable=e=>parts.push(e.data);const done=new Promise(resolve=>r.onstop=resolve);r.start();let frame=0;const tick=setInterval(()=>{x.fillStyle=frame++%2?'#38566e':'#47657e';x.fillRect(5,5,50,50);},60);await new Promise(resolve=>setTimeout(resolve,900));clearInterval(tick);r.stop();await done;stream.getTracks().forEach(t=>t.stop());return Array.from(new Uint8Array(await new Blob(parts).arrayBuffer()));});await seed.close();const video=Buffer.from(bytes);
  for(const [width,height] of sizes){
   const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});const page=await context.newPage();let scenario={};
   await page.addInitScript(()=>{window.Telegram={WebApp:{initData:'test',ready(){},expand(){},close(){},openLink(){},HapticFeedback:{impactOccurred(){},notificationOccurred(){}}}}});
   await context.route('https://telegram.org/**',r=>r.fulfill({body:''}));
   await context.route('http://qadam.test/**',async r=>{const u=new URL(r.request().url()), {d,mode}=scenario;
    if(u.pathname.endsWith('/media')) return mode==='media-error'?r.fulfill({status:502,json:{error:'Media xatosi'}}):r.fulfill({contentType:mode==='video'?'video/webm':'image/png',body:mode==='video'?video:png});
    if(u.pathname.endsWith('/accept'))return r.fulfill({json:{accepted:true}});
    if(u.pathname.endsWith('/rsvp'))return r.fulfill({json:{rsvp:{attending:1,guests:1,responded_at:1}}});
    if(u.pathname.startsWith('/api/'))return r.fulfill({json:{id:1,type:d.type,design:d.id,share_mode:'open',title:'<script>Sarlavha</script> & <b>Uzun nom</b> '.repeat(3),description:'Tavsif & <b>oddiy matn</b> '.repeat(7),media_kind:mode==='video'?'video':(['photo','media-error'].includes(mode)?'photo':'none'),status:mode==='answered'&&d.type==='fun'?'accepted':'ready',preview:mode==='preview',rsvp:mode==='answered'&&d.type==='ceremony'?{attending:1,guests:2,responded_at:1}:null,details:d.type==='fun'?{layout:{text_position:'bottom'}}:{event_kind:'wedding',date:'07.11.2030',time:'18:30',address:'Uzun manzil & <b>matn</b> '.repeat(10),map_url:'https://maps.google.com/?q=Tashkent',program:['<script>alert(1)</script>','Dastur '.repeat(25)],note:'Xush kelibsiz',layout:{text_position:'top'}}}});
    const file=u.pathname==='/'?'index.html':path.basename(u.pathname);return r.fulfill({contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(path.join(root,'web_minimal',file))});});
   for(const d of designs)for(const mode of modes){scenario={d,mode};const id=`${d.id}-${width}x${height}-${mode}`;
    await page.goto('http://qadam.test/?invite=1');await page.locator(mode==='answered'&&d.type==='fun'?'.success':'.invitation').waitFor();
    if(mode==='photo')await page.waitForFunction(()=>document.querySelector('img.media')?.naturalWidth>0);
    if(mode==='video')await page.waitForFunction(()=>document.querySelector('video.media')?.readyState>=2);
    if(mode==='media-error')await page.getByRole('button',{name:'Qayta yuklash'}).waitFor();
    if(mode!=='answered'||d.type!=='fun'){
     assert.equal(await page.locator('h1').textContent(),'<script>Sarlavha</script> & <b>Uzun nom</b> '.repeat(3));
     assert.equal(await page.locator('h1 script,h1 b').count(),0);
    }
    const geometry=await page.evaluate(()=>({vw:innerWidth,scroll:document.documentElement.scrollWidth,buttons:[...document.querySelectorAll('button')].filter(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden').map(e=>{const b=e.getBoundingClientRect();return {label:e.getAttribute('aria-label')||e.innerText,x:b.x,right:b.right,y:b.y,bottom:b.bottom,w:b.width,h:b.height}})}));
    if(geometry.scroll>width) findings.push({id,severity:'medium',problem:'horizontal overflow',geometry});
    for(const b of geometry.buttons)if(b.x<-.5||b.right>width+.5||b.h<47.5)findings.push({id,severity:'medium',problem:'button outside horizontal viewport or under 48px',button:b});
    for(let i=0;i<geometry.buttons.length;i++)for(let j=i+1;j<geometry.buttons.length;j++){const a=geometry.buttons[i],b=geometry.buttons[j];if(Math.min(a.right,b.right)-Math.max(a.x,b.x)>2&&Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)>2)findings.push({id,severity:'medium',problem:'overlapping buttons',a,b});}
    await page.screenshot({path:path.join(output,id+'.png'),fullPage:true,animations:'disabled'});count++;
   }
   await context.close();console.log(`${width}x${height}: ${designs.length*modes.length} scenarios`);
  }
  await fs.writeFile(path.join(output,'matrix.json'),JSON.stringify({count,findings},null,2));console.log(`matrix ${count}, findings ${findings.length}`);if(findings.length){console.error(JSON.stringify(findings.slice(0,12),null,2));process.exitCode=1;}
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
