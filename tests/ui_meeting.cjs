// Reference sequence using the shipping frontend and a controlled HTTP contract.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const http=require('node:http');
const root=path.resolve(__dirname,'..');
const friendly=process.argv.includes('--friendship');
const receiptHeading=friendly?'Kelishdik, do‘stim!':'Biz uchun kichkina xat';
const out=path.join(root,friendly?'output/friendship':'output/meeting');

(async()=>{
 await fs.mkdir(out,{recursive:true});
 const files=http.createServer((req,res)=>{
  res.writeHead(200,{'Content-Type':'text/calendar; charset=utf-8','Content-Disposition':'attachment; filename="uchrashuv-1.ics"'});
  res.end('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n');
 });
 await new Promise(resolve=>files.listen(0,'127.0.0.1',resolve));
 const calendarUrl=`http://127.0.0.1:${files.address().port}/uchrashuv-1.ics`;
 const browser=await chromium.launch({headless:true});
 try {
  for(const [name,width,height] of [['mobile',390,844],['desktop',1280,800],['small',280,700]]) {
   const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce',hasTouch:name!=='desktop'});
   const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(({native})=>{let seed=42;Math.random=()=>((seed=(seed*1664525+1013904223)>>>0)/4294967296);window.Telegram={WebApp:{initData:'TEST_FIXTURE',initDataUnsafe:{user:{id:2}},ready(){},expand(){},platform:native?'android':'weba',isVersionAtLeast(){return native;},downloadFile(file,callback){window.calendarDownload=file;callback(!window.cancelCalendarDownload);},HapticFeedback:{impactOccurred(){},notificationOccurred(){}}}};},{native:name==='mobile'});
   let saved=null,fail=true,calendarFail=true,calendarRequests=0,preview=false,posts=[],recipient='Shaxzoda',sender='Javohir';
   const day=new Date(Date.now()+2*86400000).toISOString().slice(0,10);
   const when=day+'T19:00+05:00';
   await context.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:''}));
   await context.route('http://meeting.test/**',async route=>{
    const url=new URL(route.request().url());
    if(url.pathname.endsWith('/calendar')) {
     calendarRequests++;
     if(calendarFail){calendarFail=false;if(name==='desktop')return route.abort('failed');return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Kalendar tayyorlanmadi. Qayta urinib ko‘ring.'})});}
     return route.fulfill({contentType:'application/json',body:JSON.stringify({url:calendarUrl,file_name:'uchrashuv-1.ics'})});
    }
    if(url.pathname.endsWith('/accept')) {
     const body=route.request().postDataJSON();posts.push(body);
     if(fail){fail=false;return route.fulfill({status:502,contentType:'application/json',body:JSON.stringify({error:'Sinov: aloqa uzildi. Qayta urinib ko‘ring.'})});}
     saved=saved||body.meeting_response;
     return route.fulfill({contentType:'application/json',body:JSON.stringify({accepted:true})});
    }
    if(url.pathname.startsWith('/api/')) return route.fulfill({contentType:'application/json',body:JSON.stringify({
     id:1,title:'Uchrashuv',description:'Bir piyola choy ustida suhbatlashamiz.',media_kind:'none',type:'fun',design:'meeting',preview,
     status:saved?'accepted':'ready',details:{meeting_kind:friendly?'friendship':'love',meeting_recipient:recipient,meeting_sender:sender,meeting_slots:name==='small'?[]:[when],meeting_configured:true,meeting_response:saved}
    })});
    const file=url.pathname==='/'?'index.html':path.basename(url.pathname);
    return route.fulfill({contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.ttf')?'font/ttf':'text/html',body:await fs.readFile(path.join(root,'web_minimal',file))});
   });
   const shot=async phase=>{if(name==='mobile'||phase==='letter'||phase==='when'||phase==='question-active')await page.screenshot({path:path.join(out,`${name}-${phase}.png`),fullPage:true,animations:'disabled'});};
   const noOverflow=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.goto('http://meeting.test/?invite=1');
   const slider=page.getByRole('slider');
   const openInvite=()=>slider.press('End');
   await slider.waitFor();
   await noOverflow();await shot('intro');
   if(friendly) {
    assert.equal(await page.locator('.meeting-heart').count(),0);
    assert.equal(await page.locator('.friendship-brand').innerText(),'QADAM / DO‘STONA');
    const hands=page.locator('.friendship-hands span');
    const gap=()=>hands.evaluateAll(([left,right])=>right.offsetLeft-left.offsetLeft);
    const startGap=await gap();
    await slider.press('ArrowRight');
    await slider.press('PageUp');
    assert.ok(await gap()<startGap);

   }
   await openInvite();
   if(friendly) await page.getByText('🤝',{exact:true}).waitFor();
   await page.getByRole('heading',{name:'Shaxzoda, uchrashamizmi?'}).waitFor();await noOverflow();await shot('question');
   const no=page.getByRole('button',{name:'Yo‘q — qochadigan hazil tugmasi'});
   if (!friendly) {
   const initialYes=await page.getByRole('button',{name:'Ha',exact:true}).boundingBox();
   assert.ok(initialYes.height>=72);
   const phrases=['Voy, sirpanib ketdim 🫣','Hali ushlamadingiz 😜','Bu tugma sportchi 🏃','Sekinroq, qo‘rqityapsiz 😂','Choyga ham yo‘qmi? ☕','Bir piyola gaplashamiz? 😌','Kalendar ham kutyapti 📅','Men ham uyatchanman 🙈'];
   let previousLabel='Yo‘q';
   const positions=[];
   // Hover and time passing must not move or count the button.
   await page.emulateMedia({reducedMotion:'no-preference'});
   const idleBox=await no.boundingBox();
   await page.mouse.move(idleBox.x+idleBox.width/2,idleBox.y+idleBox.height/2);
   await page.waitForTimeout(2100);
   assert.deepEqual(await no.boundingBox(),idleBox);
   assert.equal(await no.innerText(),'Yo‘q');
   assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('qadam:meeting:2:1:reply')).attempts),0);
   for(let i=0;i<10;i++){
    if(i<3) { if(name==='desktop') await no.click(); else await no.tap(); }
    else {await no.focus();await page.keyboard.press(i%2?'Enter':'Space');}
    assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('qadam:meeting:2:1:reply')).attempts),i+1,`${name}: attempt ${i+1}`);
    const geometry=await page.evaluate(()=>{
     const rect=selector=>{const r=document.querySelector(selector).getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height};};
     return{no:rect('.meeting-no'),yes:rect('.meeting-choices .yes'),label:rect('.meeting-yes-content'),arena:rect('.meeting-choices')};
    });
    const {no:chip,yes,label,arena}=geometry;
    const labelText=await no.innerText();assert.ok(phrases.includes(labelText));assert.notEqual(labelText,previousLabel);previousLabel=labelText;
    assert.ok(chip.x>=arena.x&&chip.y>=arena.y&&chip.x+chip.w<=arena.x+arena.w+1&&chip.y+chip.h<=arena.y+arena.h+1);
    assert.ok(!(chip.x<label.x+label.w&&chip.x+chip.w>label.x&&chip.y<label.y+label.h&&chip.y+chip.h>label.y),'No chip covers Ha label '+JSON.stringify({name,i,geometry}));
    assert.ok(chip.x<yes.x+yes.w&&chip.x+chip.w>yes.x&&chip.y<yes.y+yes.h&&chip.y+chip.h>yes.y,'No chip must touch Ha border');
    if(positions.length)assert.ok(Math.hypot(chip.x-positions.at(-1)[0],chip.y-positions.at(-1)[1])>35,'Each attempt must visibly move No');
    positions.push([Math.round(chip.x),Math.round(chip.y)]);
   }
   assert.ok(new Set(positions.map(p=>p.join(','))).size>=3);
   assert.ok(new Set(positions.map(p=>p[1])).size>1,'No must move vertically around Ha');
   const grownYes=await page.getByRole('button',{name:'Ha',exact:true}).boundingBox();
   assert.ok(grownYes.height>initialYes.height&&grownYes.width>=initialYes.width);
   await page.getByRole('heading',{name:'Shaxzoda, uchrashamizmi?'}).focus();
   await noOverflow();await shot('question-active');
   // The randomized label remains clickable repeatedly, then stays still.
   const settled=await no.boundingBox();const settledLabel=await no.innerText();
   await page.mouse.move(0,0);await page.waitForTimeout(2100);
   assert.deepEqual(await no.boundingBox(),settled);
   assert.equal(await no.innerText(),settledLabel);
   assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('qadam:meeting:2:1:reply')).attempts),10);
   } else {
    const first=await no.innerText();
    const initial=await no.boundingBox();
    await page.mouse.move(initial.x+initial.width/2,initial.y+initial.height/2);
    await page.waitForTimeout(3100);
    assert.equal(await no.innerText(),first);
    assert.deepEqual(await no.boundingBox(),initial);
    assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('qadam:meeting:2:1:reply')).attempts),0);
    if(name==='desktop') await no.click(); else await no.tap();
    await page.waitForFunction(first=>document.querySelector('.friend-caption').textContent!==first,first);
    assert.notDeepEqual(await no.boundingBox(),initial);
    for(let i=1;i<10;i++) await no.press('Enter');
    await noOverflow(); await shot('question-active');
   }
   assert.equal(posts.length,0);
   const yesButton=page.getByRole('button',{name:'Ha',exact:true});
   if(name==='desktop') await yesButton.click();
   else { await yesButton.focus(); await yesButton.press('Enter'); }
   await page.getByRole('heading',{name:'Ajoyib, uchrashamiz!'}).waitFor();assert.equal(posts.length,0);await shot('celebrate');
   await page.getByRole('button',{name:'Rejani tanlash'}).click();
   await page.getByRole('heading',{name:friendly?'Sanani tanlang':'Kun va vaqtni tanlang'}).waitFor();
   assert.equal(await page.getByRole('button',{name:friendly?'Keyingi — vaqtni tanlash':'Keyingi — rejani tanlash'}).isDisabled(),true);
   if(name!=='small' && !friendly) {
    // Sender suggestions continue to work alongside the calendar.
    await page.locator('input[name="meeting-time"]').first().check();
    assert.equal(await page.getByRole('button',{name:'Keyingi — rejani tanlash'}).isDisabled(),false);
    await page.getByRole('radio',{name:'O‘zimga qulay vaqtni tanlayman'}).check();
   }
   await page.getByRole('group',{name:'Uchrashuv kalendari',exact:true}).waitFor();
   assert.equal(await page.getByRole('button',{name:'Oldingi oy',exact:true}).isDisabled(),true);
   const uzToday=new Date(Date.now()+5*3600000).toISOString().slice(0,10);
   const monthDelta=(Number(day.slice(0,4))-Number(uzToday.slice(0,4)))*12+Number(day.slice(5,7))-Number(uzToday.slice(5,7));
   for(let i=0;i<monthDelta;i++)await page.getByRole('button',{name:'Keyingi oy',exact:true}).click();
   const dateButton=page.locator(`[data-day="${day}"]`);
   await dateButton.click();
   assert.equal(await dateButton.getAttribute('aria-pressed'),'true');
   await dateButton.press('ArrowRight');
   await page.waitForFunction(value=>document.activeElement?.dataset.day!==value,day);
   assert.notEqual(await page.locator(':focus').getAttribute('data-day'),day);
   await dateButton.click();
   if(name==='desktop') {
    // Bound navigation at 366 days, including year/month changes.
    const maxDay=new Date(Date.now()+366*86400000+5*3600000).toISOString().slice(0,10);
    const maxMonths=(Number(maxDay.slice(0,4))-Number(day.slice(0,4)))*12+Number(maxDay.slice(5,7))-Number(day.slice(5,7));
    for(let i=0;i<maxMonths;i++)await page.getByRole('button',{name:'Keyingi oy',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'Keyingi oy',exact:true}).isDisabled(),true);
    const beyond=new Date(maxDay+'T12:00:00Z');beyond.setUTCDate(beyond.getUTCDate()+1);
    if(beyond.toISOString().slice(0,7)===maxDay.slice(0,7))assert.equal(await page.locator(`[data-day="${beyond.toISOString().slice(0,10)}"]`).isDisabled(),true);
    for(let i=0;i<maxMonths;i++)await page.getByRole('button',{name:'Oldingi oy',exact:true}).click();
   }
   await noOverflow();await shot('when');
   const selectClock=async()=>{
    if(friendly) {
     await page.getByRole('button',{name:'Keyingi — vaqtni tanlash'}).click();
     const hour=page.getByRole('spinbutton',{name:'Soat'});
     const minute=page.getByRole('spinbutton',{name:'Daqiqa'});
     await hour.press('End');
     for(let i=0;i<4;i++)await hour.press('ArrowUp');
     await minute.press('Home');
     assert.equal(await hour.getAttribute('aria-valuenow'),'19');
     if(name==='mobile')await shot('clock');
    } else {
     await page.getByLabel('Soat',{exact:true}).selectOption('19');
     await page.getByLabel('Daqiqa',{exact:true}).selectOption('00');
    }
   };
   await selectClock();
   await page.getByRole('button',{name:'Keyingi — rejani tanlash'}).click();
   await page.getByRole('heading',{name:'Reja va tilakni tanlang'}).waitFor();
   if(friendly) assert.equal(await page.getByRole('radio',{name:'Ikki kishilik kechki ovqat'}).count(),0);
   assert.equal(await page.getByRole('button',{name:'Uchrashuvni tasdiqlash'}).isDisabled(),true);
   await page.getByRole('radio',{name:'Qahva va uzoq suhbat'}).check();
   await page.getByLabel('Sizdan bir-ikki og‘iz — ixtiyoriy').fill('Sinov izohi — kelishdik.');
   // Back/forward and reload retain the selections without sending anything.
   await page.getByRole('button',{name:'Vaqtga qaytish'}).click();
   await page.getByRole('button',{name:'Keyingi — rejani tanlash'}).click();await page.reload();
   await page.getByRole('heading',{name:'Reja va tilakni tanlang'}).waitFor();
   assert.equal(await page.getByLabel('Sizdan bir-ikki og‘iz — ixtiyoriy').inputValue(),'Sinov izohi — kelishdik.');
   assert.equal(posts.length,0);await noOverflow();await shot('plan');
   await page.getByRole('button',{name:'Uchrashuvni tasdiqlash'}).click();
   await page.getByText('Sinov: aloqa uzildi. Qayta urinib ko‘ring.').waitFor();
   assert.equal(await page.locator('.meeting-letter').count(),0);
   await page.getByRole('button',{name:'Uchrashuvni tasdiqlash'}).click();
   await page.getByRole('heading',{name:receiptHeading}).waitFor();
   assert.equal(posts.length,2);assert.equal(posts[1].no_attempts,10);
   assert.deepEqual(saved,{when,plan:'coffee',note:'Sinov izohi — kelishdik.'});
   await noOverflow();await shot('letter');
   await page.getByRole('button',{name:'Rejani saqlash',exact:true}).click();
   await page.getByText(name==='desktop'?'Aloqa uzildi. Rejani saqlashga qayta urinib ko‘ring.':'Kalendar tayyorlanmadi. Qayta urinib ko‘ring.',{exact:true}).waitFor();
   if(name==='mobile') {
    await page.getByRole('button',{name:'Rejani saqlash',exact:true}).click();
    await page.getByText('Kalendar faylini ochib, kalendarga qo‘shing.',{exact:true}).waitFor();
    assert.deepEqual(await page.evaluate(()=>window.calendarDownload),{url:calendarUrl,file_name:'uchrashuv-1.ics'});
    await page.evaluate(()=>window.cancelCalendarDownload=true);
    await page.getByRole('button',{name:'Rejani saqlash',exact:true}).click();
    await page.getByText('Saqlash bekor qilindi.',{exact:true}).waitFor();
   } else {
    const downloading=page.waitForEvent('download');
    await page.getByRole('button',{name:'Rejani saqlash',exact:true}).click();
    const file=await downloading;assert.equal(file.suggestedFilename(),'uchrashuv-1.ics');
    await file.saveAs(path.join(out,`${name}-uchrashuv.ics`));
    assert.ok((await fs.readFile(path.join(out,`${name}-uchrashuv.ics`),'utf8')).startsWith('BEGIN:VCALENDAR'));
   }
   assert.equal(posts.length,2);assert.equal(calendarRequests,name==='mobile'?3:2);
   await page.reload();await page.getByRole('heading',{name:receiptHeading}).waitFor();assert.equal(posts.length,2);
   recipient='W'.repeat(120);sender='M'.repeat(120);await page.reload();
   await page.getByRole('heading',{name:receiptHeading}).waitFor();await noOverflow();
   if(name==='small')await page.screenshot({path:path.join(out,'small-long-names.png'),fullPage:true,animations:'disabled'});
   recipient='Shaxzoda';sender='Javohir';
   // Sender can rehearse the full flow; final confirmation cannot write.
   preview=true;saved=null;await page.evaluate(()=>localStorage.clear());await page.reload();
   await openInvite();await page.getByRole('button',{name:'Ha',exact:true}).click();
   await page.getByRole('button',{name:'Rejani tanlash'}).click();
   if(name==='small') {
    for(let i=0;i<monthDelta;i++)await page.getByRole('button',{name:'Keyingi oy',exact:true}).click();
    await page.locator(`[data-day="${day}"]`).click();
    await selectClock();
   } else if(friendly) {
    await page.getByRole('button',{name:/Taklif qilingan/}).first().click();
    await page.getByRole('button',{name:'Keyingi — vaqtni tanlash'}).click();
   } else await page.locator('input[name="meeting-time"]').first().check();
   await page.getByRole('button',{name:'Keyingi — rejani tanlash'}).click();await page.getByRole('radio',{name:'Qahva va uzoq suhbat'}).check();
   assert.equal(await page.getByRole('button',{name:'Uchrashuvni tasdiqlash'}).isDisabled(),true);assert.equal(posts.length,2);
   assert.deepEqual(errors,[]);console.log(`${name}: six steps, inline calendar, month/year bounds, keyboard, hour/minute, slot time, persistence, no early write, retry, receipt, calendar native/browser download and retry/cancel, preview guard PASS`);
   await context.close();
  }
 } finally {await browser.close();await new Promise(resolve=>files.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
