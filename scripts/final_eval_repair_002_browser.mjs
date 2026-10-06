// FINAL-EVAL-REPAIR-002 browser audit (read-only): landing + key pages at 4 widths, reduced-motion rAF/animation counting, skip-link keyboard test, landmarks/headings, computed target sizes.
// node final_eval_repair_002_browser.mjs port origin usersJson who out shotDir routesJson   (usersJson '-' = no sign-in)
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
const [, , debugPort, ORIGIN, USERS, WHO, OUT, SHOTS, ROUTES] = process.argv;
mkdirSync(SHOTS, { recursive: true });
const user = USERS === '-' ? null : JSON.parse(readFileSync(USERS))[WHO];
const routes = JSON.parse(readFileSync(ROUTES));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
class Cdp { constructor(u){this.ws=new WebSocket(u);this.id=0;this.p=new Map();this.h=[];this.ready=new Promise((a,b)=>{this.ws.onopen=a;this.ws.onerror=b});this.ws.onmessage=(m)=>{const e=JSON.parse(m.data);if(e.id&&this.p.has(e.id)){const{res,rej}=this.p.get(e.id);this.p.delete(e.id);e.error?rej(new Error(JSON.stringify(e.error))):res(e.result)}else if(e.method)for(const f of this.h)f(e.method,e.params)}}
 send(m,p={}){const id=++this.id;this.ws.send(JSON.stringify({id,method:m,params:p}));return new Promise((res,rej)=>this.p.set(id,{res,rej}))} on(f){this.h.push(f)} }
const t = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(t.find((x)=>x.type==='page').webSocketDebuggerUrl); await cdp.ready;
let cur = { hosts: new Set(), errors: [], failed: [], bad: [], doc: null, reqs: new Map() };
const reset = () => { cur = { hosts: new Set(), errors: [], failed: [], bad: [], doc: null, reqs: new Map() }; };
cdp.on((m,p)=>{
 if(m==='Network.requestWillBeSent'){try{cur.hosts.add(new URL(p.request.url).host)}catch{} cur.reqs.set(p.requestId,p.request.url)}
 if(m==='Network.responseReceived'){ if(p.type==='Document'&&!cur.doc)cur.doc=p.response.status; if(p.response.status>=400)cur.bad.push({url:p.response.url.replace(/^https?:\/\/[^/]+/,''),status:p.response.status}) }
 if(m==='Network.loadingFailed'&&!p.canceled)cur.failed.push({url:(cur.reqs.get(p.requestId)||'').replace(/^https?:\/\/[^/]+/,''),err:p.errorText});
 if(m==='Runtime.exceptionThrown')cur.errors.push(String(p.exceptionDetails?.exception?.description??p.exceptionDetails?.text).slice(0,200));
 if(m==='Runtime.consoleAPICalled'&&p.type==='error')cur.errors.push(p.args.map((a)=>a.value??a.description).join(' ').slice(0,200));
});
for(const d of ['Page','Runtime','Network'])await cdp.send(`${d}.enable`);
await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
const ev=async(e)=>{const r=await cdp.send('Runtime.evaluate',{expression:e,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error('eval');return r.result.value};
const waitFor=async(e,to=60000)=>{const u=Date.now()+to;while(Date.now()<u){let v=null;try{v=await ev(e)}catch{}if(v)return v;await sleep(100)}throw new Error('timeout '+e.slice(0,80))};
const click=(l)=>ev(`(()=>{const e=[...document.querySelectorAll('button,a')].find((x)=>x.textContent.trim()===${JSON.stringify(l)});if(!e||e.disabled)return false;e.click();return true})()`);
const viewport=(w)=>cdp.send('Emulation.setDeviceMetricsOverride',{width:w,height:900,deviceScaleFactor:1,mobile:w<=768});
const out={who:WHO,routes:[],signin:null};
if(user){
 await viewport(1440); await cdp.send('Page.navigate',{url:ORIGIN+'/sign-in'});
 await waitFor(`!!document.querySelector('input[name=identifier]')`);
 await ev(`document.querySelector('input[name=identifier]').focus()`); await cdp.send('Input.insertText',{text:user.email}); await sleep(400); await click('Continue');
 await waitFor(`!!document.querySelector('input[name=password]')`,30000); await sleep(1500);
 await ev(`document.querySelector('input[name=password]').focus()`); await cdp.send('Input.insertText',{text:user.password}); await sleep(600); await click('Continue'); await sleep(4000);
 if((await ev('location.href')).includes('/sign-in')&&/Enter your password/.test(await ev('document.body.innerText')))await click('Continue');
 let trust=false;const until=Date.now()+60000;
 for(;;){const h=await ev('location.href'),tx=await ev('document.body.innerText');if(!h.includes('/sign-in'))break;
  if(!trust&&(h.includes('client-trust')||/Check your email|verification code/i.test(tx))){trust=true;await ev(`document.querySelector('input').focus()`);for(const ch of '424242'){await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:ch,text:ch});await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:ch});await sleep(120)}}
  if(Date.now()>until)throw new Error('signin timeout');await sleep(400)}
 await cdp.send('Page.navigate',{url:ORIGIN+'/app'}); await waitFor(`!!document.querySelector('[data-testid="identity-chip"]')`,60000); out.signin={ok:true};
}

await cdp.send('Page.addScriptToEvaluateOnNewDocument',{source:`window.__raf=0;window.__intv=0;window.__rafBy={};(()=>{const o=window.requestAnimationFrame.bind(window);window.requestAnimationFrame=(cb)=>{window.__raf++;const k=(cb&&(cb.name||String(cb).replace(/\\s+/g,' ').slice(0,80)))||'?';window.__rafBy[k]=(window.__rafBy[k]||0)+1;return o(cb)};const si=window.setInterval.bind(window);window.setInterval=(f,t,...a)=>{window.__intv++;return si(f,t,...a)}})()`});
const TARGETS=`(()=>{const sel='a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=link],[tabindex]:not([tabindex="-1"])';const out=[];for(const e of document.querySelectorAll(sel)){const r=e.getBoundingClientRect();if(r.width===0||r.height===0)continue;const cs=getComputedStyle(e);if(cs.visibility==='hidden'||cs.display==='none')continue;if(e.closest('[aria-hidden=true],[inert]'))continue;const inline=cs.display==='inline'&&!!e.parentElement&&/^(P|LI|SMALL|SPAN|DD|DT|TD|H\d|LABEL)$/.test(e.parentElement.tagName)&&(e.parentElement.textContent||'').trim().length>(e.textContent||'').trim().length+3;out.push({tag:e.tagName,text:(e.getAttribute('aria-label')||e.textContent||e.value||'').trim().replace(/\s+/g,' ').slice(0,36),cls:String(e.className&&e.className.baseVal!==undefined?e.className.baseVal:e.className).slice(0,40),w:Math.round(r.width*10)/10,h:Math.round(r.height*10)/10,inline})}return out})()`;
const SEM=`(()=>({title:document.title,lang:document.documentElement.lang,main:document.querySelectorAll('main').length,navs:[...document.querySelectorAll('nav')].map((n)=>n.getAttribute('aria-label')||n.getAttribute('aria-labelledby')||null),headings:[...document.querySelectorAll('h1,h2,h3')].map((h)=>h.tagName+':'+h.textContent.trim().replace(/\\s+/g,' ').slice(0,40)).slice(0,60),skipLink:[...document.querySelectorAll('a')].some((a)=>/skip to (main )?content/i.test(a.textContent)),scrollW:document.documentElement.scrollWidth,innerW:innerWidth,imgNoAlt:[...document.querySelectorAll('img')].filter((e)=>!e.hasAttribute('alt')).length,text:document.body.innerText}))()`;
const key=async(k,code,vk)=>{await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:k,code,windowsVirtualKeyCode:vk});await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:k,code,windowsVirtualKeyCode:vk})};
for(const r of routes){
 const rec={route:r.path,widths:{}};
 for(const w of [1440,1024,768,390]){
  await viewport(w); reset(); await cdp.send('Emulation.setEmulatedMedia',{features:[]});
  await cdp.send('Page.navigate',{url:ORIGIN+r.path}); await sleep(r.wait||6000);
  if(r.ready) try{await waitFor(r.ready,60000)}catch{rec.readyTimeout=true}
  const sem=await ev(SEM); const tg=await ev(TARGETS);
  const under=tg.filter((t)=>(t.w<24||t.h<24));
  rec.widths[w]={overflow:sem.scrollW>sem.innerW+1,scrollW:sem.scrollW,innerW:sem.innerW,targets:tg.length,under24:under.filter((t)=>!t.inline),under24_inline:under.filter((t)=>t.inline),errors:cur.errors.length,failed:cur.failed,bad:cur.bad};
  if(w===1440){Object.assign(rec,{title:sem.title,lang:sem.lang,main:sem.main,navs:sem.navs,headings:sem.headings,skipLinkPresent:sem.skipLink,imgNoAlt:sem.imgNoAlt,consoleErrors:cur.errors,textSample:sem.text.slice(0,12000),hosts:[...cur.hosts].sort()});
   const s=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});writeFileSync(`${SHOTS}/${(r.path.replace(/[^a-z0-9]+/gi,'_')||'root')}_1440_full.png`,Buffer.from(s.data,'base64'))}
  if(w===390){const s=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});writeFileSync(`${SHOTS}/${(r.path.replace(/[^a-z0-9]+/gi,'_')||'root')}_390_full.png`,Buffer.from(s.data,'base64'))}
 }
 // keyboard + skip link (1440)
 await viewport(1440); reset(); await cdp.send('Emulation.setEmulatedMedia',{features:[]}); await cdp.send('Page.navigate',{url:ORIGIN+r.path}); await sleep(r.wait||6000);
 await ev('document.activeElement&&document.activeElement.blur&&document.activeElement.blur()');
 await key('Tab','Tab',9); await sleep(150);
 const first=await ev(`(()=>{const e=document.activeElement;if(!e||e===document.body)return null;const r=e.getBoundingClientRect();const cs=getComputedStyle(e);return{text:(e.textContent||'').trim().slice(0,40),href:e.getAttribute('href'),visible:r.top>=0&&r.bottom>0&&r.width>0&&r.height>0&&cs.visibility!=='hidden',top:Math.round(r.top)}})()`);
 let jumped=null; if(first&&first.href&&first.href.startsWith('#')){ await key('Enter','Enter',13); await sleep(400); jumped=await ev(`(()=>{const e=document.activeElement;return{tag:e&&e.tagName,id:e&&e.id,isMain:!!e&&e.tagName==='MAIN'}})()`)}
 rec.keyboard={firstFocus:first,afterActivate:jumped};
 // reduced motion: rAF + interval + running animations over 3s
 await cdp.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]}); await cdp.send('Page.navigate',{url:ORIGIN+r.path}); await sleep(r.wait||6000);
 if(r.ready) try{await waitFor(r.ready,60000)}catch{}
 const a0=await ev('({raf:window.__raf,intv:window.__intv,by:JSON.parse(JSON.stringify(window.__rafBy))})'); await sleep(3000); const a1=await ev(`({by:window.__rafBy,raf:window.__raf,intv:window.__intv,running:document.getAnimations().filter((a)=>a.playState==='running').map((a)=>a.animationName||a.constructor.name).slice(0,10),runningCount:document.getAnimations().filter((a)=>a.playState==='running').length,textLen:document.body.innerText.length,blankCanvases:[...document.querySelectorAll('canvas')].filter((c)=>{try{if(c.width===300&&c.height===150)return false;const x=c.getContext('2d');if(!x)return false;const d=x.getImageData(0,0,c.width,c.height).data;for(let i=3;i<d.length;i+=997)if(d[i])return false;return true}catch{return false}}).length})`);
 rec.reducedMotion={rafCallers:Object.fromEntries(Object.entries(a1.by).map(([k,v])=>[k,v-(a0.by[k]||0)]).filter(([,v])=>v>0)),rafDelta3s:a1.raf-a0.raf,intervalsCreated:a1.intv,runningAnimations:a1.runningCount,runningNames:a1.running,textLen:a1.textLen,blankCanvases:a1.blankCanvases};
 await cdp.send('Emulation.setEmulatedMedia',{features:[]});
 // same page without reduced motion (baseline: shows the loops exist)
 await cdp.send('Page.navigate',{url:ORIGIN+r.path}); await sleep(r.wait||6000);
 const b0=await ev('window.__raf'); await sleep(2000); const b1=await ev('window.__raf'); rec.normalMotion={rafDelta2s:b1-b0};
 out.routes.push(rec);
}
writeFileSync(OUT,JSON.stringify(out,null,1)); await cdp.send('Browser.close').catch(()=>{}); process.exit(0);
