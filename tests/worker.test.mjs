import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/worker.js';
import {seed} from '../public/engine.js';
const rows=new Map();
const env={DB:{prepare(sql){return {bind(...args){return {async first(){return rows.has(args[0])?{data:rows.get(args[0])}:null;},async run(){if(sql.startsWith('INSERT'))rows.set(args[0],args[1]);if(sql.startsWith('DELETE')&&sql.includes('id ='))rows.delete(args[0]);return {};}};}};}},ASSETS:{fetch:()=>new Response('asset')}};
const request=(method='GET',body,headers={})=>new Request('https://baraka.example/api/state',{method,headers,...(body?{body:JSON.stringify(body)}:{})});
test('isolated sessions persist state and reset without leaking to other sessions',async()=>{
 const initial=await worker.fetch(request(),env);assert.equal(initial.status,200);const cookie=initial.headers.get('set-cookie');assert.match(cookie,/HttpOnly; Secure; SameSite=Strict/);const headers={Cookie:cookie.split(';')[0],Origin:'https://baraka.example'};
 const s=seed();s.organization='اختبار';assert.equal((await worker.fetch(request('PUT',s,headers),env)).status,200);
 assert.equal((await (await worker.fetch(request('GET',null,headers),env)).json()).state.organization,'اختبار');
 assert.equal((await (await worker.fetch(request(),env)).json()).state.organization,'مطبخ الزيتون');
 assert.equal((await worker.fetch(request('DELETE',null,headers),env)).status,200);
 assert.equal((await (await worker.fetch(request('GET',null,headers),env)).json()).state.organization,'مطبخ الزيتون');
});
test('cross-origin writes, unsupported methods, invalid JSON and invalid states are rejected',async()=>{
 assert.equal((await worker.fetch(request('PUT',seed(),{Origin:'https://evil.example'}),env)).status,403);
 assert.equal((await worker.fetch(request('POST',seed()),env)).status,405);
 assert.equal((await worker.fetch(request('PUT',{}, {Origin:'https://baraka.example'}),env)).status,400);
 const req=new Request('https://baraka.example/api/state',{method:'PUT',headers:{Origin:'https://baraka.example'},body:'not json'});assert.equal((await worker.fetch(req,env)).status,400);
});
test('database failures return a retryable error without internal details',async()=>{const res=await worker.fetch(request(),{DB:{prepare(){throw Error('secret');}}});assert.equal(res.status,503);assert.ok(!(await res.text()).includes('secret'));});
