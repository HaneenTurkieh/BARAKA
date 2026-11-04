import {seed,validateState} from '../public/engine.js';
const json=(data,status=200,extra={})=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',...extra}});
export default {async fetch(request,env){
 const url=new URL(request.url);
 if(!url.pathname.startsWith('/api/'))return env.ASSETS.fetch(request);
 if(url.pathname==='/api/health')return json({ok:true,storage:'Cloudflare D1',mode:'hackathon-demo'});
 if(url.pathname!=='/api/state')return json({error:'Not found'},404);
 if(!['GET','PUT','DELETE'].includes(request.method))return json({error:'Method not allowed'},405);
 if(request.method!=='GET'&&request.headers.get('Origin')!==url.origin)return json({error:'Origin rejected'},403);
 const cookie=request.headers.get('Cookie')||'';
 const match=cookie.match(/(?:^|;\s*)baraka_session=([a-f0-9-]{36})(?:;|$)/);
 const id=match?.[1]||crypto.randomUUID(),headers={};
 if(!match)headers['Set-Cookie']=`baraka_session=${id}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=604800`;
 try{
 if(request.method==='GET'){
 const row=await env.DB.prepare('SELECT data FROM demo_sessions WHERE id = ?').bind(id).first();
 return json({state:row?JSON.parse(row.data):seed()},200,headers);
 }
 if(request.method==='DELETE'){await env.DB.prepare('DELETE FROM demo_sessions WHERE id = ?').bind(id).run();return json({state:seed()},200,headers);}
 if(Number(request.headers.get('Content-Length'))>100000)return json({error:'Payload too large'},413);
 const raw=await request.text();if(raw.length>100000)return json({error:'Payload too large'},413);
 let state;try{state=JSON.parse(raw);}catch{return json({error:'Invalid JSON'},400);}
 if(!validateState(state))return json({error:'Invalid data'},400);
 await env.DB.prepare('INSERT INTO demo_sessions (id,data,updated_at) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at').bind(id,JSON.stringify(state),Date.now()).run();
 await env.DB.prepare('DELETE FROM demo_sessions WHERE updated_at < ?').bind(Date.now()-7*86400000).run();
 return json({ok:true},200,headers);
 }catch{return json({error:'تعذر الوصول إلى التخزين. حاول مرة أخرى.'},503);}
}};
