const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const designs=['atlas','nafis','gold','envelope','ticket'];
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO5+hc8AAAAASUVORK5CYII=','base64');
const longTitle='Sarlavha & <sinov> '.repeat(15), longAddress='Manzil '.repeat(48), longProgram='Dastur '.repeat(25);
(async()=>{
 const browser=await chromium.launch({headless:true});let count=0;
 try {
  for(const width of [360,1280]) {
   const ctx=await browser.newContext({viewport:{width,height:800},reducedMotion:'reduce'});const page=await ctx.newPage();
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>{window.Telegram={WebApp:{initData:'test',ready(){},expand(){},close(){},openLink(url){window.lastOpened=url}}}});
   await ctx.route('https://telegram.org/**',r=>r.fulfill({body:''}));
   let state={};
   await ctx.route('http://qadam.test/**',async r=>{
    const u=new URL(r.request().url());
    if(u.pathname.endsWith('/media')) return r.fulfill({status:200,contentType:'image/png',body:png});
    if(u.pathname.endsWith('/rsvp')) return r.fulfill({json:{rsvp:{...r.request().postDataJSON(),responded_at:1}}});
    if(u.pathname.startsWith('/api/')) return r.fulfill({json:{id:1,type:'ceremony',design:state.design,share_mode:'open',title:longTitle,description:'Xush kelibsiz',media_kind:state.photo?'photo':'none',status:'ready',preview:state.preview,rsvp:state.answered?{attending:1,guests:2,responded_at:1}:null,details:{event_kind:'wedding',date:'07.11.2030',time:'18:30',address:longAddress,map_url:'https://maps.google.com/?q=Tashkent',program:[longProgram,'<script>alert(1)</script>'],note:'Xush kelibsiz',layout:{text_position:'top'}}}});
    const f=u.pathname==='/'?'index.html':path.basename(u.pathname);
    return r.fulfill({contentType:f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(path.join(root,'web_minimal',f))});
   });
   for(const design of designs) for(const photo of [false,true]) for(const mode of ['preview','open','answered']) {
    state={design,photo,preview:mode==='preview',answered:mode==='answered'};
    await page.goto('http://qadam.test/?invite=1');
    await page.locator(`.ceremony-${design} .ceremony-panel`).waitFor();
    if(photo) { const img=page.locator('.ceremony img.media'); await img.waitFor(); await page.waitForFunction(()=>document.querySelector('.ceremony img.media')?.naturalWidth>0); }
    assert.equal(await page.getByRole('heading',{name:longTitle}).count(),1);
    assert.equal(await page.getByText('<script>alert(1)</script>',{exact:true}).count(),1);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.equal(await page.locator('.sticker,.arena').count(),0);
    assert.equal(await page.locator('#fireworks').evaluate(c=>Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data).some(Boolean)),false);
    assert.ok((await page.locator('.ceremony button').evaluateAll(es=>es.map(e=>e.getBoundingClientRect().height))).every(h=>h>=48));
    assert.equal(await page.getByRole('button',{name:'Xaritada ochish'}).count(),1);
    assert.equal(await page.getByRole('button',{name:'Taqvimga qo‘shish'}).count(),1);
    if(mode==='preview') assert.equal(await page.getByRole('button',{name:'Kelaman',exact:true}).isDisabled(),true);
    if(mode==='answered') assert.equal(await page.getByText('Kelaman · 2 mehmon').count(),1);
    if(mode==='open') {
      await page.getByRole('button',{name:'Kelaman',exact:true}).click();
      await page.getByRole('button',{name:'Javobni yuborish'}).click();
      await page.getByText('Javobingiz uchun rahmat!').waitFor();
    }
    // Panel over a white image is the worst case for its black alpha background.
    const colors=await page.locator('.ceremony-panel').evaluate(el=>({bg:getComputedStyle(el).backgroundColor,fg:getComputedStyle(el).color,card:getComputedStyle(el.querySelector('.ceremony-card')).backgroundColor}));
    const parse=s=>s.match(/[\d.]+/g).map(Number);const bg=parse(colors.bg),fg=parse(colors.fg),card=parse(colors.card);
    const blend=(top,bottom)=>top.slice(0,3).map((v,i)=>v*(top[3]??1)+bottom[i]*(1-(top[3]??1)));
    const lum=rgb=>{const c=rgb.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2]};
    const contrast=(a,b)=>(Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
    const panel=blend(bg,[255,255,255]),cardBg=blend(card,panel);
    assert.ok(contrast(fg,panel)>=4.5,`${design} panel contrast`);assert.ok(contrast(fg,cardBg)>=4.5,`${design} card contrast`);
    const buttonColors=await page.locator('.ceremony-links button').first().evaluate(el=>({fg:getComputedStyle(el).color,bg:getComputedStyle(el).backgroundColor}));
    assert.ok(contrast(parse(buttonColors.fg),parse(buttonColors.bg))>=4.5,`${design} button contrast`);
    count++;
   }
   assert.deepEqual(errors,[]);await ctx.close();
  }
  for(const action of ['click','Enter','Space','timeout']) {
   const context=await browser.newContext({reducedMotion:'no-preference'}),page=await context.newPage();
   await page.addInitScript(()=>{window.Telegram={WebApp:{initData:'test',ready(){},expand(){}}}});
   await context.route('https://telegram.org/**',r=>r.fulfill({body:''}));
   await context.route('http://qadam.test/**',async r=>{
    const u=new URL(r.request().url());
    if(u.pathname.startsWith('/api/')) return r.fulfill({json:{id:1,type:'ceremony',design:'envelope',title:'Salom',media_kind:'none',status:'ready',preview:false,rsvp:null,details:{event_kind:'wedding',date:'07.11.2030',time:'18:30',address:'Manzil',map_url:'',program:[],note:'Salom',layout:{}}}});
    const f=u.pathname==='/'?'index.html':path.basename(u.pathname);return r.fulfill({contentType:f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(path.join(root,'web_minimal',f))});
   });
   await page.goto('http://qadam.test/?invite=1');const intro=page.getByRole('button',{name:'Konvertni ochish, animatsiyani o‘tkazib yuborish'});await intro.waitFor();
   const start=Date.now();if(action==='click') await intro.click();else if(action!=='timeout') await intro.press(action);
   await page.locator('.ceremony-panel').waitFor(); assert.ok(Date.now()-start<(action==='timeout'?2300:1600));count++;await context.close();
  }
  console.log(`M5 ${count} scenarios: five designs, media, responsive layouts, RSVP, AA contrast, envelope skip PASS`);
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
