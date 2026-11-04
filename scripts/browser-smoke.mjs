// Real Chromium smoke test using the DevTools protocol; no browser-test dependency.
import {spawn} from 'node:child_process';
import {mkdir,writeFile,mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import assert from 'node:assert/strict';
const base=process.env.BARAKA_TEST_URL||'http://127.0.0.1:8081';
const profile=await mkdtemp(join(tmpdir(),'baraka-browser-'));
const browser=spawn(process.env.CHROMIUM||'chromium',['--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--remote-debugging-port=9222','--remote-allow-origins=http://localhost:9222',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
let ws;const pending=new Map();let seq=0;const errors=[];
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(fn,label){for(let i=0;i<100;i++){try{if(await fn())return;}catch{}await pause(100);}throw Error('Timed out: '+label);}
try{
 await wait(async()=> (await fetch('http://127.0.0.1:9222/json/version')).ok,'Chromium');
 const page=await(await fetch('http://127.0.0.1:9222/json/new?'+encodeURIComponent(base),{method:'PUT'})).json();
 ws=new WebSocket(page.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);};
 const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
 const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;};
 await call('Runtime.enable');await call('Page.enable');await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await call('Page.navigate',{url:base});
 await wait(()=>evaluate("!!document.querySelector('[data-action=full]')"),'initial screen');
 await mkdir('docs/screenshots',{recursive:true});
 async function screenshot(name){const s=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(`docs/screenshots/${name}.png`,Buffer.from(s.data,'base64'));}
 await screenshot('today');
 await evaluate("document.querySelector('[data-action=full]').click()");
 await wait(()=>evaluate("!!document.querySelector('[data-action=export]') && !document.querySelector('#content.loading')"),'complete demo');
 const result=await evaluate("fetch('/api/lab').then(r=>r.json())");
 assert.equal(result.stage,'reoptimized');assert.equal(result.impact.expired_with,0);assert.ok(result.impact.expired_without>0);assert.ok(result.impact.prevented>0);
 assert.equal(result.impact.final_surplus,result.impact.human+result.impact.organic+result.impact.disposed);
 await evaluate("document.querySelector('[data-action=export]').closest('section').scrollIntoView()");await screenshot('impact');
 await evaluate("document.querySelector('[data-tab=weekly]').click()");
 await wait(()=>evaluate("document.querySelectorAll('.daybar').length===7"),'weekly forecast');await evaluate('window.scrollTo(0,0)');await screenshot('weekly');
 await evaluate("document.querySelector('[data-tab=validation]').click()");
 await wait(()=>evaluate("!!document.querySelector('svg.chart')"),'model validation');await screenshot('validation');
 await evaluate("document.querySelector('[data-tab=today]').click()");await wait(()=>evaluate("!!document.querySelector('[data-action=reset]')"),'return to demo');
 await evaluate("window.confirm=()=>true;document.querySelector('[data-action=reset]').click()");
 await wait(()=>evaluate("!!document.querySelector('[data-action=start]')"),'reset');
 // Exercise manual entry, safety approval, solve and delay through actual UI controls.
 for(const action of ['start','intervene']){await evaluate(`document.querySelector('[data-action=${action}]').click()`);await wait(()=>evaluate("!document.querySelector('#content.loading')"),action);}
 await evaluate("document.querySelector('#approval').click()");await wait(()=>evaluate("!document.querySelector('#content.loading')"),'approval');
 for(const action of ['optimize','delay']){await evaluate(`document.querySelector('[data-action=${action}]').click()`);await wait(()=>evaluate("!document.querySelector('#content.loading')"),action);}
 const second=await evaluate("fetch('/api/lab').then(r=>r.json())");assert.deepEqual(second.impact,result.impact);
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await evaluate('window.scrollTo(0,0)');await screenshot('mobile');
 assert.equal(await evaluate('document.documentElement.scrollWidth<=window.innerWidth'),true,'No mobile page overflow');assert.deepEqual(errors,[]);
 console.log(JSON.stringify({browser:'Chromium',flow:'full + manual + reset deterministic',weekly_days:7,impact:result.impact,console_errors:errors,screenshots:'docs/screenshots'},null,2));
}finally{ws?.close();browser.kill();await pause(300);await rm(profile,{recursive:true,force:true});}
