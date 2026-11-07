const RM=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
const K=PREFIX_JSON,pages=PAGES_JSON,store=(k,v)=>localStorage.setItem(K+k,v),get=k=>localStorage.getItem(K+k);
document.querySelectorAll('input[data-k]').forEach(b=>{b.checked=get(b.dataset.k)==='1'});
function stepState(a,anim){const d=a.querySelector('.stepdone').checked;a.classList.toggle('isdone',d);
 const o=get('open:'+a.dataset.k);a.classList.toggle('closed',o?o==='0':d);a.querySelector('.open').setAttribute('aria-expanded',!a.classList.contains('closed'))}
document.querySelectorAll('.step').forEach(a=>stepState(a));
function progress(){const all=document.querySelectorAll('.stepdone'),d=[...all].filter(x=>x.checked).length;
 document.querySelector('.bar i').style.width=(100*d/all.length)+'%';document.querySelector('#cnt').textContent=d+' of '+all.length+' steps';
 document.querySelectorAll('.grid button').forEach(b=>{const s=document.querySelectorAll(`.pg[data-page="${b.dataset.p}"] .stepdone`);b.classList.toggle('fin',[...s].every(x=>x.checked))})}
document.addEventListener('change',e=>{const b=e.target;if(!b.dataset.k)return;store(b.dataset.k,b.checked?'1':'0');
 if(b.classList.contains('stepdone')){const a=b.closest('.step');localStorage.removeItem(K+'open:'+a.dataset.k);stepState(a);
  if(b.checked){let n=a.nextElementSibling;while(n&&!n.classList.contains('step'))n=n.nextElementSibling;
   if(n){n.classList.remove('closed');setTimeout(()=>scrollToEl(n,'start'),250)}
   const sec=a.closest('.pg');if(sec&&[...sec.querySelectorAll('.stepdone')].every(x=>x.checked)){const i=pages.indexOf(+sec.dataset.page);
    if(i>=0&&i<pages.length-1){const nx=pages[i+1];toast('Page '+sec.dataset.page+' done. On to page '+nx+'.');setTimeout(()=>show(nx,1),1300)}else{toast('All done!')}}}}progress()});
function scrollToEl(el,block){const r=el.getBoundingClientRect(),top=block==='center'?scrollY+r.top-innerHeight/2+r.height/2:scrollY+r.top-64;window.scrollTo({top:Math.max(0,top),behavior:RM?'auto':'smooth'})}
function toast(t){let el=document.querySelector('.toast');if(!el){el=document.createElement('div');el.className='toast';document.body.appendChild(el)}el.textContent=t;el.classList.add('on');clearTimeout(el._t);el._t=setTimeout(()=>el.classList.remove('on'),2200)}
document.addEventListener('click',e=>{const o=e.target.closest('.open');if(o){const a=o.closest('.step');a.classList.toggle('closed');store('open:'+a.dataset.k,a.classList.contains('closed')?'0':'1');o.setAttribute('aria-expanded',!a.classList.contains('closed'))}
 const z=e.target.closest('[data-zoom]');if(z&&!e.target.closest('.zoom')){const Z=document.querySelector('.zoom');Z.querySelector('img').src=z.src;Z.classList.add('on');history.pushState({zoom:1},'');return}
 if(e.target.closest('.zx')||e.target.classList.contains('zoom')){closeZoom(true)}});
function closeZoom(back){const Z=document.querySelector('.zoom');if(!Z.classList.contains('on'))return false;Z.classList.remove('on');if(back&&history.state&&history.state.zoom)history.back();return true}
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(!closeZoom(true))closePart(true)}});
let cur=+((location.hash.match(/^#p=(-?\d+)/)||[])[1])||+get('page')||pages[0];if(!pages.includes(cur))cur=pages[0];
function show(p,scroll){cur=p;store('page',p);document.querySelectorAll('.pg').forEach(s=>s.hidden=+s.dataset.page!==p);
 const i=pages.indexOf(p);document.querySelector('#prev').disabled=i<=0;document.querySelector('#next').disabled=i>=pages.length-1;
 document.querySelector('#pl').textContent=p===-2?'Setup':p===-1?'Inventory':'Page '+p+' · '+(RANGES[p].includes('–')?'Steps ':'Step ')+RANGES[p];document.querySelectorAll('.grid button').forEach(b=>b.classList.toggle('cur',+b.dataset.p===p));
 if(scroll)window.scrollTo({top:0,behavior:RM?'auto':'smooth'});if(location.hash!=='#p='+p)history.replaceState(history.state,'','#p='+p)}
document.querySelector('#prev').onclick=()=>show(pages[pages.indexOf(cur)-1],1);document.querySelector('#next').onclick=()=>show(pages[pages.indexOf(cur)+1],1);
const sh=document.querySelector('.sheet');document.querySelector('.pick').onclick=()=>sh.classList.add('on');
sh.onclick=e=>{const b=e.target.closest('.grid button');if(b){show(+b.dataset.p,1)}if(b||e.target===sh)sh.classList.remove('on')};
function invUpdate(){document.querySelectorAll('.ir[data-need],.fs').forEach(r=>{let u=0;r.querySelectorAll('.use').forEach(c=>{const d=localStorage.getItem(K+c.dataset.k)==='1';c.classList.toggle('done',d);if(d)u+=+c.dataset.n});r.querySelectorAll('.used').forEach(b=>b.textContent=u);r.querySelectorAll('.left').forEach(b=>b.textContent=Math.max(0,+b.dataset.need-u));const pf=r.querySelector('.pfill'),L=r.querySelector('.left');if(pf&&L)pf.style.width=(100*u/Math.max(1,+L.dataset.need))+'%'})}
let flt='all';function invFilter(){const q=(document.querySelector('#q')||{}).value||'',fp=(document.querySelector('#fpg')||{}).value||'',fs=(document.querySelector('#fst')||{}).value||'';
 const st=[...document.querySelectorAll('.fpanel input:checked')].map(x=>x.value);const sm=document.querySelector('.fmenu summary');if(sm)sm.textContent='Filter: '+(st.length===0||st.length===3?'all':st.map(v=>({all:'found all',some:'found some',none:'not found'})[v]).join(', '))+' ▾';
 document.querySelectorAll('#invlist .ir').forEach(r=>{let ok=r.dataset.name.includes(q.toLowerCase());const sn=+r.dataset.seen,nd=+r.dataset.need,cl=sn>=nd?'all':(sn>0?'some':'none');if(st.length&&st.length<3)ok=ok&&st.includes(cl);
 const us=r.dataset.uses.split(' ');if(fp)ok=ok&&us.some(x=>x.startsWith('p'+fp+'s'));if(fs)ok=ok&&us.some(x=>x.endsWith('s'+fs));r.style.display=ok?'':'none'})}
document.addEventListener('change',e=>{if(e.target.id==='fpg'||e.target.id==='fst'||e.target.closest('.fpanel'))invFilter()});
const FS=document.getElementById('fs');document.body.appendChild(FS);   // must live outside the hidden Inventory page to be visible everywhere
if(location.hash.startsWith('#part-'))setTimeout(()=>openPart(location.hash.slice(6)),300);
function openPart(el){const t=document.getElementById('inv-'+el);if(!t)return;FS.querySelector('.fsin').innerHTML=t.querySelector('.det').innerHTML;invUpdate();
 FS.querySelectorAll('.use').forEach(c=>{const d=localStorage.getItem(K+c.dataset.k)==='1';c.classList.toggle('done',d)});FS.classList.add('on');history.pushState({fs:el},'')}
function closePart(back){if(!FS.classList.contains('on'))return;FS.classList.remove('on');if(back&&history.state&&history.state.fs)history.back()}
window.addEventListener('popstate',()=>{if(!closeZoom(false))closePart()});
function gotoPart(pg,st,el){closePart();show(pg,0);const a=document.querySelector(`.pg[data-page="${pg}"] .step[data-k="p${pg}-step${st}"]`);if(!a)return;a.classList.remove('closed');
 const row=a.querySelector(`.part[data-el="${el}"]`)||a;setTimeout(()=>{scrollToEl(row,'center');row.classList.remove('flash');void row.offsetWidth;row.classList.add('flash')},300)}
document.addEventListener('input',e=>{if(e.target.id==='q')invFilter()});

document.addEventListener('click',e=>{const t=e.target.closest('#invlist .ir');if(t){openPart(t.dataset.el);return}
 if(e.target.closest('#fsx,#fsx2')){closePart(true);return}
 const ti=e.target.closest('.toinv');if(ti){e.preventDefault();openPart(ti.dataset.el);return}
 const ub=e.target.closest('.fs .srow.built');if(ub){gotoPart(+ub.dataset.pg,ub.dataset.st,ub.dataset.el);return}
 const f=e.target.closest('.flt button');if(f){document.querySelectorAll('.flt button').forEach(b=>b.classList.toggle('on',b===f));flt=f.dataset.f;invFilter()}
 });
document.addEventListener('change',()=>invUpdate());
document.addEventListener('error',e=>{const t=e.target;if(t.tagName==='IMG'&&!t.dataset.fb){t.dataset.fb='1';t.src='noimg.png'}},true);
function partFold(){document.querySelectorAll('.part').forEach(r=>{const c=r.querySelector('.phead input');if(c)r.classList.toggle('got',c.checked)})}
document.addEventListener('change',e=>{const r=e.target.closest('.part');if(r&&e.target.closest('.phead')){r.classList.toggle('got',e.target.checked);r.classList.remove('peek')}});
document.addEventListener('click',e=>{const x=e.target.closest('.pexp');if(x){x.closest('.part').classList.toggle('peek')}});
function markUpTo(lastIdx){const all=[...document.querySelectorAll('.stepdone')];let n=0;
 for(let i=0;i<=lastIdx&&i<all.length;i++){const c=all[i];if(!c.checked)n++;c.checked=true;store(c.dataset.k,'1');const a=c.closest('.step');
  a.querySelectorAll('.part .phead input').forEach(x=>{x.checked=true;store(x.dataset.k,'1')});stepState(a)}
 partFold();progress();invUpdate();toast(n?('Marked '+n+' step'+(n===1?'':'s')+' done.'):'Those steps were already done.')}
document.addEventListener('click',e=>{const u=e.target.closest('.upto');if(!u)return;const all=[...document.querySelectorAll('.stepdone')];
 if(u.classList.contains('stepbtn')){const me=u.closest('.step').querySelector('.stepdone');const i=all.indexOf(me);if(confirm('Mark this step and every step before it as done?'))markUpTo(i)}
 else{const sec=u.closest('.pg');const first=sec.querySelector('.stepdone');const i=all.indexOf(first)-1;if(i<0){toast('This is the first page.');return}
  const pg_=+sec.dataset.page;if(confirm('Mark every step on the pages before page '+pg_+' as done?'))markUpTo(i)}});
show(cur);progress();invUpdate();partFold();
// ---- sounds (made in the browser, no files) and confetti ----
let AC=null,sndOn=localStorage.getItem(K+'sound')!=='0';
function sndBtn(){const s=document.getElementById('snd');if(s)s.textContent=sndOn?'🔊':'🔇'}sndBtn();
document.getElementById('snd').onclick=e=>{e.stopPropagation();sndOn=!sndOn;localStorage.setItem(K+'sound',sndOn?'1':'0');sndBtn();if(sndOn)tone(660,.08,'triangle',.12)};
function tone(f,d,type,vol,when){if(!sndOn)return;try{AC=AC||new (window.AudioContext||window.webkitAudioContext)();const t=AC.currentTime+(when||0),o=AC.createOscillator(),g=AC.createGain();o.type=type||'sine';o.frequency.setValueAtTime(f,t);g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(vol||.15,t+.01);g.gain.exponentialRampToValueAtTime(.0001,t+d);o.connect(g);g.connect(AC.destination);o.start(t);o.stop(t+d+.02)}catch(e){}}
function snap(){tone(1800,.035,'square',.06);tone(900,.05,'triangle',.08,.015)}
function chime(){tone(784,.12,'triangle',.13);tone(1175,.22,'triangle',.13,.09)}
function fanfare(){[523,659,784,1047].forEach((f,i)=>tone(f,i===3?.45:.14,'triangle',.14,i*.11))}
function confetti(){if(RM)return;const cols=['#e3000b','#ffcf00','#0057a8','#00852b','#ff7f00','#ffffff','#a0a5a9'];const box=document.createElement('div');box.className='cf';document.body.appendChild(box);
 for(let i=0;i<46;i++){const p=document.createElement('i');const w=10+Math.random()*12;p.style.cssText=`left:${Math.random()*100}vw;width:${w}px;height:${w*0.6}px;background:${cols[i%cols.length]};animation-delay:${Math.random()*.35}s;animation-duration:${1.3+Math.random()*.9}s;--r:${(Math.random()*720-360)|0}deg;--x:${(Math.random()*120-60)|0}px`;box.appendChild(p)}
 setTimeout(()=>box.remove(),2800)}
document.addEventListener('change',e=>{const b=e.target;if(!b.dataset||!b.dataset.k||!b.checked)return;
 if(b.classList.contains('stepdone')){const a=b.closest('.step'),sec=a&&a.closest('.pg');a&&a.classList.add('pop');setTimeout(()=>a&&a.classList.remove('pop'),500);
  if(sec&&[...sec.querySelectorAll('.stepdone')].every(x=>x.checked)){fanfare();confetti()}else chime()}else snap()});
// ---- page links in the address (#p=5) and a reset ----
window.addEventListener('hashchange',()=>{const m=location.hash.match(/^#p=(-?\d+)/);if(m&&pages.includes(+m[1])&&+m[1]!==cur){closePart();closeZoom(false);sh.classList.remove('on');show(+m[1],1)}});
document.addEventListener('click',e=>{if(!e.target.closest('.reset'))return;if(!confirm('Clear every tick in this guide?'))return;
 Object.keys(localStorage).filter(k=>k.startsWith(K)).forEach(k=>localStorage.removeItem(k));location.replace(location.pathname+'#p='+pages[0]);location.reload()});
