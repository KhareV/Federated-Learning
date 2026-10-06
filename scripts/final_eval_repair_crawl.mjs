// FINAL-EVAL-REPAIR-001 route crawl (read-only; real Clerk TEST sign-in, fresh profile): visits every route at 4 widths, records facts; reload-tests flagged deep links.
// node final_eval_repair_crawl.mjs port origin usersJson who out shotDir routesJson
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
const FACTS=`(()=>{const t=document.body.innerText;const nm=(e)=>(e.getAttribute('aria-label')||e.textContent||e.getAttribute('title')||'').trim();return{title:document.title,h1:document.querySelectorAll('h1').length,h1text:[...document.querySelectorAll('h1')].map((x)=>x.textContent.trim().slice(0,100)),main:document.querySelectorAll('main').length,path:location.pathname,text:t.slice(0,6000),textLen:t.length,scrollW:document.documentElement.scrollWidth,innerW:innerWidth,unnamedButtons:[...document.querySelectorAll('button,a')].filter((e)=>!nm(e)).length,unlabelledInputs:[...document.querySelectorAll('input:not([type=hidden]),select,textarea')].filter((e)=>!e.getAttribute('aria-label')&&!(e.id&&document.querySelector('label[for="'+e.id+'"]'))&&!e.closest('label')).length,imgNoAlt:[...document.querySelectorAll('img')].filter((e)=>!e.hasAttribute('alt')).length,skipLink:!!document.querySelector('a[href="#main"],a.skip,[data-testid="skip-link"]'),h2:document.querySelectorAll('h2').length}})()`;
for(const r of routes){
 const rec={route:r.path,class:r.cls||null,widths:{}};
 for(const w of [1440,1024,768,390]){
  await viewport(w); reset();
  await cdp.send('Page.navigate',{url:ORIGIN+r.path}); await sleep(r.wait||2500);
  try{ if(r.ready) await waitFor(r.ready,r.readyTo||60000);}catch{rec.readyTimeout=true}
  const f=await ev(FACTS);
  rec.widths[w]={scrollW:f.scrollW,innerW:f.innerW,overflow:f.scrollW>f.innerW+1};
  if(w===1440){Object.assign(rec,{status:cur.doc,landed:f.path,title:f.title,h1:f.h1,h1text:f.h1text,main:f.main,text:f.text,textLen:f.textLen,unnamedButtons:f.unnamedButtons,unlabelledInputs:f.unlabelledInputs,imgNoAlt:f.imgNoAlt,h2:f.h2,hosts:[...cur.hosts].sort(),errors:cur.errors,failed:cur.failed,bad:cur.bad});
   const s=await cdp.send('Page.captureScreenshot',{format:'png'});writeFileSync(`${SHOTS}/${r.path.replace(/[^a-z0-9]+/gi,'_')||'root'}_1440.png`,Buffer.from(s.data,'base64'))}
  if(w===390){const s=await cdp.send('Page.captureScreenshot',{format:'png'});writeFileSync(`${SHOTS}/${r.path.replace(/[^a-z0-9]+/gi,'_')||'root'}_390.png`,Buffer.from(s.data,'base64'))}
 }
 if(r.reload){ reset(); await viewport(1440); await cdp.send('Page.reload'); await sleep(r.wait||2500); try{ if(r.ready) await waitFor(r.ready,r.readyTo||60000);}catch{} const f2=await ev(FACTS); rec.after_reload={path:f2.path,title:f2.title,h1:f2.h1,main:f2.main,textLen:f2.textLen,identityChip:/user_/.test(f2.text),visibleError:/Request failed|Page not found|Something went wrong|Unhandled|status [45]\d\d/i.test(f2.text),errors:cur.errors}; }
 out.routes.push(rec);
}
writeFileSync(OUT,JSON.stringify(out,null,1)); await cdp.send('Browser.close').catch(()=>{}); process.exit(0);
