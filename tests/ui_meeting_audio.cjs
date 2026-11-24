const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--autoplay-policy=no-user-gesture-required']});
 try {
  for(const blocked of [false,true]) {
   const context=await browser.newContext({viewport:{width:390,height:844}});
   const page=await context.newPage();page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(({blocked})=>{
    window.Telegram={WebApp:{initData:'test',ready(){},expand(){}}};
    if(blocked){let touched=false;const play=HTMLMediaElement.prototype.play;
     document.addEventListener('pointerdown',()=>touched=true,true);
     document.addEventListener('keydown',()=>touched=true,true);
     HTMLMediaElement.prototype.play=function(){return touched?play.call(this):Promise.reject(new DOMException('Gesture required','NotAllowedError'));};
    }
   },{blocked});
   await context.route('https://telegram.org/**',r=>r.fulfill({body:''}));
   let audioRequests=0;
   await context.route('http://music.test/**',async r=>{
    const url=new URL(r.request().url());
    if(url.pathname.startsWith('/api/'))return r.fulfill({json:{id:1,type:'fun',design:'meeting',title:'Malika',description:'Bir piyola choy?',status:'ready',media_kind:'none',details:{meeting_recipient:'Malika',meeting_sender:'Javohir',meeting_slots:[]}}});
    if(url.pathname.endsWith('.mp3')) audioRequests++;
    const file=url.pathname==='/'?'index.html':path.basename(url.pathname);
    return r.fulfill({contentType:file.endsWith('.mp3')?'audio/mpeg':file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(path.join(root,'web_minimal',file))});
   });
   console.log('Scenario',blocked);
   await page.goto('http://music.test/?invite=1');
   await page.getByRole('slider').waitFor();
   await page.getByRole('slider').press('ArrowRight');
   assert.equal(await page.locator('audio').getAttribute('src'),null);
   assert.equal(audioRequests,0);
   await page.getByRole('button',{name:'Musiqani yoqish',exact:true}).click();
   await page.waitForFunction(()=>{const a=document.querySelector('audio');return !a.paused&&a.currentTime>0.1&&a.readyState>=2});
   console.log('Audio started');
   const duration=await page.locator('audio').evaluate(a=>a.duration);assert.ok(duration>30,'Real supplied MP3 decoded');
   await page.waitForTimeout(2200);
   assert.ok(await page.locator('audio').evaluate(a=>a.volume>0.2&&a.volume<=0.23));
   const before=await page.locator('audio').evaluate(a=>a.currentTime);
   await page.getByRole('slider').press('End');
   await page.getByRole('button',{name:'Ha',exact:true}).click();
   await page.locator('.reaction-yes').waitFor();
   assert.ok(await page.locator('audio').evaluate((a,t)=>a.currentTime>=t&&!a.paused,before),'Music survives phase transition');
   await page.waitForTimeout(2000);
   assert.equal(await page.locator('.sticker-balloon').evaluate(e=>getComputedStyle(e).opacity),'0');
   await page.getByRole('button',{name:'Ovozni o‘chirish',exact:true}).click();
   assert.equal(await page.locator('audio').evaluate(a=>a.paused),true);
   console.log('Mute saved');
   await page.reload();await page.getByRole('button',{name:'Musiqani yoqish',exact:true}).waitFor();
   assert.equal(await page.locator('audio').evaluate(a=>a.paused),true,'Mute persists');
   await page.getByRole('button',{name:'Musiqani yoqish',exact:true}).click();
   await page.waitForFunction(()=>!document.querySelector('audio').paused);
   await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));
   assert.equal(await page.locator('audio').evaluate(a=>a.paused),true,'Closing pauses audio');
   await page.evaluate(()=>window.dispatchEvent(new Event('pageshow')));
   await page.waitForFunction(()=>!document.querySelector('audio').paused);
   assert.deepEqual(errors,[]);
   console.log(`${blocked?'Blocked autoplay fallback':'Explicit music activation'}: real MP3, fade, continuous phases, sticker pop, mute persistence, close/resume PASS`);
   await context.close();
  }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
