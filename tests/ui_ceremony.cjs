const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  for(const width of [360,1280]) {
   const context=await browser.newContext({viewport:{width,height:800},reducedMotion:'reduce'}); const page=await context.newPage();
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   let existing=null, fail=true, loadFail=false, unsafe=false, empty=false, posted=null;
   await page.addInitScript(()=>{window.opened=[];window.Telegram={WebApp:{initData:'test',ready(){},expand(){},close(){window.didClose=true},openLink(url){window.opened.push(url)}}}});
   await context.route('https://telegram.org/**',r=>r.fulfill({body:''}));
   await context.route('http://qadam.test/**',async r=>{
    const u=new URL(r.request().url());
    if(u.pathname.endsWith('/rsvp')){posted=r.request().postDataJSON();return r.fulfill({status:fail?502:200,contentType:'application/json',body:JSON.stringify(fail?{error:'Aloqa uzildi'}:{rsvp:{...posted,responded_at:1}})});}
    if(u.pathname.startsWith('/api/')) {
     if(loadFail) return r.fulfill({status:502,contentType:'application/json',body:JSON.stringify({error:'Yuklash xatosi'})});
     return r.fulfill({contentType:'application/json',body:JSON.stringify({id:1,type:'ceremony',design:'ceremony_elegant',title:'Ali va Vali '+('uzun'.repeat(70)),description:'Xush kelibsiz',media_kind:'none',status:'ready',preview:false,rsvp:existing,details:{event_kind:'nikah',date:'07.11.2030',time:'23:30',address:'Toshkent '+('manzil'.repeat(40)),map_url:unsafe?'https://maps.google.com.evil.example/':'https://maps.google.com/?q=Toshkent',program:empty?[]:['<script>alert(1)</script>','Marosim '+('tadbir'.repeat(30))],note:empty?'':'Xush kelibsiz',layout:{text_position:'top'}}})});
    }
    const f=u.pathname==='/'?'index.html':path.basename(u.pathname);
    return r.fulfill({contentType:f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(path.join(root,'web_minimal',f))});
   });
   loadFail=true; await page.goto('http://qadam.test/?invite=1');
   await page.getByRole('button',{name:'Qayta urinish'}).waitFor();
   loadFail=false;await page.getByRole('button',{name:'Qayta urinish'}).click();
   await page.getByRole('heading',{name:'Sana va vaqt'}).waitFor();
   if(width===360) await page.screenshot({path:'/tmp/qadam-m4-mobile.png'});
   assert.equal(await page.getByText('payshanba, 7-noyabr 2030 · 23:30').count(),1);
   assert.equal(await page.getByRole('heading',{name:'Manzil'}).count(),1);
   assert.equal(await page.getByText('<script>alert(1)</script>').count(),1);
   assert.equal(await page.locator('script:not([src])').count(),0);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   const buttons=await page.locator('.ceremony button').evaluateAll(nodes=>nodes.map(el=>el.getBoundingClientRect().height));
   assert.ok(buttons.every(size=>size>=48));
   await page.getByRole('button',{name:'Xaritada ochish'}).click();
   await page.getByRole('button',{name:'Taqvimga qo‘shish'}).click();
   const urls=await page.evaluate(()=>window.opened);
   assert.equal(new URL(urls[0]).hostname,'maps.google.com');
   const calendar=new URL(urls[1]);assert.equal(calendar.hostname,'calendar.google.com');
   assert.equal(calendar.searchParams.get('ctz'),'Asia/Tashkent');
   assert.equal(calendar.searchParams.get('dates'),'20301107T233000/20301108T023000');
   await page.getByRole('button',{name:'Kelaman',exact:true}).click();
   const add=page.getByRole('button',{name:'Mehmonni qo‘shish'});
   for(let i=1;i<10;i++) await add.click();
   assert.equal(await add.isDisabled(),true);
   await page.getByRole('button',{name:'Mehmonni kamaytirish'}).click();
   await page.getByRole('button',{name:'Javobni yuborish'}).click();
   await page.getByRole('alert').waitFor();
   assert.equal(await page.getByText('Javobingiz uchun rahmat!').count(),0);
   assert.deepEqual(posted,{attending:1,guests:9});
   fail=false; await page.getByRole('button',{name:'Javobni yuborish'}).click();
   await page.getByText('Javobingiz uchun rahmat!').waitFor();
   await page.getByRole('button',{name:'Telegramga qaytish'}).click();
   assert.equal(await page.evaluate(()=>window.didClose),true);
   existing={attending:0,guests:0,responded_at:1};unsafe=true;
   await page.goto('http://qadam.test/?invite=1');
   await page.getByText('Siz javob bergansiz').waitFor();
   assert.equal(await page.getByRole('button',{name:'Xaritada ochish'}).count(),0);
   assert.equal(await page.getByRole('button',{name:'Javobni yuborish'}).count(),0);
   assert.equal(await page.getByText('Kela olmayman').count(),1);
   existing=null; empty=true; await page.goto('http://qadam.test/?invite=1');
   await page.getByRole('button',{name:'Kela olmayman'}).click();
   assert.equal(await page.getByRole('heading',{name:'Dastur'}).count(),0);
   assert.equal(await page.getByRole('heading',{name:'Qo‘shimcha ma’lumot'}).count(),0);
   assert.equal(await page.getByRole('button',{name:'Mehmonni qo‘shish'}).count(),0);
   await page.getByRole('button',{name:'Javobni yuborish'}).click();
   await page.getByText('Javobingiz uchun rahmat!').waitFor();
   assert.deepEqual(posted,{attending:0,guests:0});
   assert.deepEqual(errors,[]); await context.close();
   console.log(`ceremony ${width}px: cards, long text, safe links, stepper, retry and saved RSVP PASS`);
  }
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
