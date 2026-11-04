'use strict';
const tg = window.Telegram?.WebApp;
const content = document.getElementById('content');
const status = document.getElementById('status');
const root = document.getElementById('app');
const reaction = document.getElementById('reaction');
let photoUrl = null;
let me = null;
const states = {draft:'Qoralama',pending:'Admin tasdig‘i kutilmoqda',approved:'Oluvchi kutilmoqda',delivered:'Qabul qilingan',rejected:'Rad etilgan'};
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function button(text, action, cls='secondary') {
  const node = el('button',text,cls); node.type='button';
  node.addEventListener('click',action); return node;
}
function say(text='', error=false) { status.textContent=text; status.classList.toggle('error',error); }
function reset() {
  content.replaceChildren(); say();
  if (photoUrl) { URL.revokeObjectURL(photoUrl); photoUrl=null; }
}
async function api(path, options={}) {
  const headers = {'X-Telegram-Init-Data':tg?.initData || '', ...options.headers};
  if (options.json !== undefined) { options.body=JSON.stringify(options.json); headers['Content-Type']='application/json'; delete options.json; }
  const response = await fetch('/api'+path,{...options,headers});
  if (!response.ok) { const data=await response.json().catch(()=>({})); throw new Error(data.error || 'Amal bajarilmadi. Qayta urinib ko‘ring.'); }
  return options.blob ? response.blob() : response.json();
}
async function busy(node, task) {
  if (node.disabled) return;
  node.disabled=true; say();
  try { await task(); } catch(error) { say(error.message,true); }
  finally { node.disabled=false; }
}
function closePage() { if (tg?.initData) tg.close(); else history.back(); }
function chat() { tg.openTelegramLink(me.bot_url); tg.close(); }
async function loadPhoto(img, id) {
  try {
    const blob=await api(`/messages/${id}/photo`,{blob:true});
    if (!img.isConnected) return;
    photoUrl=URL.createObjectURL(blob); img.src=photoUrl;
  } catch(error) { say(error.message,true); }
}
function photo() { const img=el('img',undefined,'avatar'); img.alt='Yuborilgan rasm'; return img; }
function top(title) {
  const row=el('div',undefined,'topline'); row.append(el('strong',title),button('Orqaga',home)); content.append(row);
}
async function home() {
  try {
    reset(); say('Rasmlar yuklanmoqda…');
    const data=await api('/messages'); reset();
    const line=el('div',undefined,'topline'); line.append(el('strong','Rasmli taklif'),el('span',me.name)); content.append(line);
    content.append(el('h1','Bir rasm. Sizning so‘zlaringiz.'));
    content.append(el('p','Rasm, sarlavha va tavsif qo‘shing. Bir martalik havolani kerakli odamga yuboring.'));
    content.append(button('Yangi rasmli sahifa',()=>compose(), 'primary full'));
    const list=el('div',undefined,'list');
    for (const item of data.messages) {
      const row=button('',()=>detail(item.id),'list-item');
      row.append(el('strong',item.title || 'Sarlavhasiz rasm'),el('span',`${item.owner?'Yuborilgan':'Kelgan'} · ${states[item.status] || item.status}`));
      list.append(row);
    }
    content.append(list);
    if (!data.messages.length) content.append(el('p','Hozircha rasmlar yo‘q. Birinchi sahifangizni yarating.','status'));
    content.append(button('Botdagi suhbatga qaytish',chat,'full secondary'));
  } catch(error) { say(error.message,true); }
}
function field(form, label, name, max, value='', multiline=false) {
  const caption=el('label',label,'field'); caption.htmlFor=name;
  const input=document.createElement(multiline?'textarea':'input');
  input.id=name; input.name=name; input.required=true; input.maxLength=max;
  if (!multiline) input.type='text'; input.value=value;
  form.append(caption,input,el('p',`1–${max} belgi`,'hint')); return input;
}
async function compose(existing=null) {
  reset(); top(existing?'Rasmni tahrirlash':'Yangi rasmli sahifa');
  const form=el('form'); form.noValidate=false;
  let file;
  const preview=photo(); preview.alt='Rasm ko‘rinishi'; preview.hidden=!existing;
  form.append(preview);
  if (existing) loadPhoto(preview,existing.id);
  else {
    const label=el('label','Rasm','field'); label.htmlFor='photo';
    file=el('input'); file.id='photo'; file.type='file'; file.accept='image/jpeg,image/png'; file.required=true;
    form.append(label,file,el('p','JPG yoki PNG, 10 MB gacha. Rasm dumaloq kesimda ko‘rinadi.','hint'));
    file.addEventListener('change',()=>{
      const selected=file.files[0]; if (!selected) return;
      if (selected.size>10*1024*1024) { file.value=''; say('Rasm 10 MB dan oshmasin.',true); return; }
      if (photoUrl) URL.revokeObjectURL(photoUrl);
      photoUrl=URL.createObjectURL(selected); preview.src=photoUrl; preview.hidden=false;
    });
  }
  const title=field(form,'Sarlavha (title)','title',120,existing?.title || '');
  const description=field(form,'Tavsif (description)','description',2000,existing?.description || '',true);
  const targetLabel=el('label','Oluvchi','field'); targetLabel.htmlFor='receiver';
  const target=el('select'); target.id='receiver';
  const linkOption=el('option','Bir martalik havola yaratish'); linkOption.value='0'; target.append(linkOption);
  form.append(targetLabel,target);
  api('/people').then(data=>{ for(const p of data.people) { const o=el('option',p.first_name); o.value=p.tg_id; target.append(o); } }).catch(()=>{});
  const checkLabel=el('label',undefined,'check'); const check=el('input'); check.type='checkbox'; check.required=true;
  checkLabel.append(check,el('span','Rasmim, ismim, sarlavha va tavsifim oluvchiga ko‘rinishiga roziman.')); form.append(checkLabel);
  const save=el('button','Tasdiqlash va havola olish','primary full'); save.type='submit'; form.append(save);
  form.addEventListener('submit',event=>{
    event.preventDefault();
    if (!form.reportValidity()) return;
    busy(save,async()=>{
      let item;
      if (existing) item=await api(`/messages/${existing.id}`,{method:'PATCH',json:{title:title.value,description:description.value}});
      else {
        const data=new FormData(); data.append('photo',file.files[0]); data.append('title',title.value); data.append('description',description.value);
        item=await api('/messages',{method:'POST',body:data});
      }
      // Agar keyingi yuborish uzilsa, saqlangan qoralamani qayta yuklamaymiz.
      existing=item;
      const sent=await api(`/messages/${item.id}/submit`,{method:'POST',json:{confirmed:check.checked,receiver_id:Number(target.value)}});
      await detail(sent.id);
    });
  });
  content.append(form);
}
function evade(no, yes, arena, triesLabel) {
  let attempts=0;
  function run(event) {
    event.preventDefault();
    if (attempts<10) attempts++;
    triesLabel.textContent=`Urinishlar: ${attempts} / 10`;
    const maxX=Math.max(0,arena.clientWidth-no.offsetWidth);
    const maxY=Math.max(0,arena.clientHeight-no.offsetHeight);
    const choices=[[0,.55],[1,.55],[0,1],[1,1],[.5,.75],[1,0]];
    const candidates=choices.map(([x,y])=>[x*maxX,y*maxY]).filter(([x,y])=>{
      const overlap= x<yes.offsetLeft+yes.offsetWidth+8 && x+no.offsetWidth>yes.offsetLeft-8 && y<yes.offsetTop+yes.offsetHeight+8 && y+no.offsetHeight>yes.offsetTop-8;
      return !overlap && Math.hypot(x-no.offsetLeft,y-no.offsetTop)>28;
    });
    const [x,y]=candidates[Math.floor(Math.random()*candidates.length)] || [maxX,maxY];
    no.style.left=`${x}px`; no.style.top=`${y}px`;
    tg?.HapticFeedback?.impactOccurred('light');
    if (attempts===10 && !reaction.open) reaction.showModal();
  }
  no.addEventListener('pointerdown',run);
  no.addEventListener('click',event=>{ if(event.detail===0) run(event); else event.preventDefault(); });
}
async function detail(id) {
  try {
    const item=await api(`/messages/${id}`); reset();
    if (item.owner) top('Mening rasmli sahifam');
    const card=el('section',undefined,'invitation');
    const img=photo(); card.append(img); loadPhoto(img,id);
    card.append(el('h1',item.title || 'Sizga rasm yuborildi'),el('p',item.description || '','description'));
    if (!item.owner && item.status==='approved') {
      const arena=el('div',undefined,'arena'); const tries=el('p','','tries'); tries.setAttribute('aria-live','polite');
      const yes=button('Ha',()=>busy(yes,async()=>{ await api(`/messages/${id}/accept`,{method:'POST'}); await detail(id); }),'primary yes');
      const no=button('Yo‘q',()=>{},'no'); no.setAttribute('aria-label','Yo‘q — qochadigan hazil tugmasi');
      arena.append(yes,no); card.append(arena,tries); evade(no,yes,arena,tries);
      card.append(el('p','“Ha”ni bossangiz, yuboruvchi bilan bot orqali suhbat ochiladi.','notice'));
    } else if (!item.owner) {
      card.append(el('h2',item.session?.status==='closed'?'Suhbat yopilgan':'Suhbat ochildi'));
      card.append(el('p','Xabarlar bot orqali o‘tadi. Admin o‘z suhbatlari va shikoyat qilingan xabarlarni ko‘rishi mumkin.','notice'));
      card.append(button('Suhbatga o‘tish',chat,'primary full'));
    } else {
      card.append(el('p',states[item.status] || item.status,'notice'));
      if (item.status==='draft') card.append(button('Sarlavha va tavsifni to‘ldirish',()=>compose(item),'primary full'));
      if (item.link) {
        const box=el('div',undefined,'link-result'); const label=el('label','Receiverga yuboriladigan havola','field'); label.htmlFor='share-link';
        const input=el('input'); input.id='share-link'; input.type='url'; input.readOnly=true; input.value=item.link;
        const copy=button('Havolani nusxalash',()=>busy(copy,async()=>{ try { await navigator.clipboard.writeText(item.link); say('Havola nusxalandi. Oluvchiga yuboring.'); } catch { input.focus(); input.select(); say('Havolani bosib turing va nusxalang.'); } }),'primary full');
        box.append(label,input,el('p','Havola faqat bir kishi uchun. Uni kerakli odamga o‘zingiz yuboring.','hint'),copy); card.append(box);
      }
      if (item.status==='pending' || item.status==='approved') card.append(button('Holatni yangilash',()=>detail(id),'full secondary'));
    }
    card.append(el('p',`Yuboruvchi: ${item.sender_name}`,'sender'));
    card.append(button('Sahifani yopish',closePage,'close-page'));
    content.append(card);
  } catch(error) { say(error.message,true); }
}
document.getElementById('reaction-close').addEventListener('click',()=>reaction.close());
(async()=>{
  tg?.ready(); tg?.expand();
  root.setAttribute('aria-busy','false');
  if (!tg?.initData) { say('Sahifani Telegram botidagi “Sahifani ochish” tugmasi orqali oching.',true); return; }
  try {
    me=await api('/me');
    const params=new URLSearchParams(location.search);
    const mid=params.get('message');
    if (mid && /^\d+$/.test(mid)) await detail(Number(mid));
    else if (params.has('compose')) await compose();
    else await home();
  } catch(error) { say(error.message,true); }
})();
