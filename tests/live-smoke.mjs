import assert from 'node:assert/strict';
const base=process.argv[2];
if(!base||!base.startsWith('https://'))throw Error('Pass the deployed HTTPS origin');
const page=await fetch(base);assert.equal(page.status,200);assert.match(await page.text(),/بَرَكة/);assert.ok(page.headers.get('content-security-policy'));console.log('PASS public HTML and security headers');
for(const path of ['/app.js','/style.css','/engine.js','/favicon.svg']){const res=await fetch(base+path);assert.equal(res.status,200);assert.ok((await res.text()).length>100);}console.log('PASS all public assets');
const health=await fetch(base+'/api/health');assert.equal((await health.json()).ok,true);console.log('PASS Worker health');
const first=await fetch(base+'/api/state');assert.equal(first.status,200);const cookie=first.headers.get('set-cookie')?.split(';')[0];assert.ok(cookie);const {state}=await first.json();assert.equal(state.batches.length,5);const headers={Cookie:cookie,Origin:base,'Content-Type':'application/json'};
try{
 state.organization='جلسة اختبار النشر';const put=await fetch(base+'/api/state',{method:'PUT',headers,body:JSON.stringify(state)});assert.equal(put.status,200);
 const read=await fetch(base+'/api/state',{headers:{Cookie:cookie}});assert.equal((await read.json()).state.organization,state.organization);console.log('PASS D1 write and read');
 const other=await fetch(base+'/api/state');assert.equal((await other.json()).state.organization,'مطبخ الزيتون');console.log('PASS visitor isolation');
 const rejected=await fetch(base+'/api/state',{method:'PUT',headers:{...headers,Origin:'https://example.com'},body:JSON.stringify(state)});assert.equal(rejected.status,403);console.log('PASS cross-origin write protection');
}finally{const reset=await fetch(base+'/api/state',{method:'DELETE',headers});assert.equal(reset.status,200);console.log('PASS test session cleanup');}
