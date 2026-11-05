const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true}); const answers={};
 try {
  for(const [id,attending] of [['user1',true],['user2',false]]) {
   const context=await browser.newContext(); const page=await context.newPage();
   await page.addInitScript(id=>{window.Telegram={WebApp:{initData:id,ready(){},expand(){},close(){},openLink(){}}}},id);
   await context.route('https://telegram.org/**',r=>r.fulfill({body:''}));
   await context.route('http://qadam.test/**',async r=>{
    const req=r.request(), u=new URL(req.url());
    if(u.pathname.endsWith('/rsvp')) { answers[id]={...req.postDataJSON(),responded_at:1}; return r.fulfill({json:{rsvp:answers[id]}}); }
    if(u.pathname.startsWith('/api/')) return r.fulfill({json:{id:1,type:'ceremony',share_mode:'open',design:'ceremony_elegant',title:'Bayram',description:'Xush kelibsiz',media_kind:'none',status:'ready',preview:false,rsvp:answers[id]||null,details:{event_kind:'wedding',date:'07.11.2030',time:'18:00',address:'Toshkent',map_url:'',program:[],note:'Xush kelibsiz',layout:{text_position:'top'}}}});
    const f=u.pathname==='/'?'index.html':path.basename(u.pathname);
    return r.fulfill({contentType:f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(path.join(root,'web_minimal',f))});
   });
   await page.goto('http://qadam.test/?invite=1');
   await page.getByRole('button',{name:attending?'Kelaman':'Kela olmayman',exact:true}).click();
   await page.getByRole('button',{name:'Javobni yuborish'}).click();
   await page.getByText('Javobingiz uchun rahmat!').waitFor();
   await page.reload(); await page.getByText('Siz javob bergansiz').waitFor();
   assert.equal(await page.getByText(attending?'Kelaman · 1 mehmon':'Kela olmayman',{exact:true}).count(),1);
   await context.close();
  }
  assert.equal(answers.user1.attending,1);assert.equal(answers.user2.attending,0);
  console.log('open link: two isolated users and saved responses PASS');
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
