import { test, before, after } from 'node:test';
import http from 'node:http';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createGateway, validateConfig } from '../server.mjs';
import { passwordRecord, verifyPassword, writeUsers } from '../auth.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'aspia-gateway-'));
const usersFile=path.join(temp,'users.json');
const config={publicOrigin:'https://remote.example.test',port:8085,router:{address:'127.0.0.1',port:8060},usersFile,maxSessions:4};
const audit=[], children=[];
let gateway, url, users, alice, bob, admin;
const password='a test password only 123';
async function rawFetch(url, options={}) {
  return new Promise((resolve,reject)=>{
    const req=http.request(url,{method:options.method||'GET',headers:options.headers},res=>{
      const chunks=[];res.on('data',c=>chunks.push(c));res.on('end',()=>resolve(new Response(res.statusCode===204?null:Buffer.concat(chunks),{status:res.statusCode,headers:res.headers})));
    });req.on('error',reject);req.end(options.body);
  });
}
async function call(route,{login,body,origin=config.publicOrigin,headers={}}={}) {
  const r=await rawFetch(url+'/remote/api/'+route,{method:body===undefined?'GET':'POST',headers:{Host:'remote.example.test',Origin:origin,...(login?{Cookie:login.cookie,'X-CSRF-Token':login.csrf}:{}),...(body!==undefined?{'Content-Type':'application/json'}:{}),...headers},body:body===undefined?undefined:JSON.stringify(body)});
  return r;
}
async function login(name){const r=await call('login',{body:{user:name,password}});assert.equal(r.status,200);const b=await r.json();return {...b,cookie:r.headers.get('set-cookie').split(';')[0]};}
const credentials={hostId:'123456789',routerUser:'router-test',routerPassword:'router-secret',hostUser:'host-test',hostPassword:'host-secret'};
async function connect(login){const r=await call('sessions',{login,body:credentials});assert.equal(r.status,201);return (await r.json()).id;}
before(async()=>{
  const record=await passwordRecord(password);
  users=['alice','bob','admin'].map(name=>({name,role:name==='admin'?'admin':'user',disabled:false,hosts:[],...record}));writeUsers(usersFile,users);
  gateway=createGateway(config,root,{audit:(event,data)=>audit.push({event,...data}),sweepMs:30,heartbeatMs:1000,
    spawnWorker:()=>{const p=spawn(process.execPath,[path.join(root,'test/fake-bridge.mjs')],{stdio:['pipe','pipe','pipe']});children.push(p);return p;}});
  gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening');url='http://127.0.0.1:'+gateway.server.address().port;
  alice=await login('alice');bob=await login('bob');admin=await login('admin');
});
after(async()=>{gateway.close();for(const p of children)if(p.exitCode===null)p.kill();fs.rmSync(temp,{recursive:true,force:true});});
test('password hashing verifies and rejects incorrect secrets',async()=>{
  assert.equal(await verifyPassword(password,users[0]),true);assert.equal(await verifyPassword('incorrect',users[0]),false);assert.equal(await verifyPassword(password,undefined),false);
});
test('config refuses non-HTTPS and invalid resource limits',()=>{
  assert.throws(()=>validateConfig({...config,publicOrigin:'http://example.com'}));assert.throws(()=>validateConfig({...config,maxSessions:999}));
});
test('unauthenticated, wrong origin, host and missing CSRF are rejected',async()=>{
  assert.equal((await call('admin/sessions')).status,401);
  assert.equal((await call('sessions',{login:alice,body:credentials,origin:'https://evil.example'})).status,403);
  assert.equal((await call('sessions',{login:alice,body:credentials,headers:{'X-CSRF-Token':''}})).status,403);
  assert.equal((await call('me',{login:alice,headers:{Host:'evil.example'}})).status,403);
});
test('static server has no path traversal or configuration route',async()=>{
  for(const p of ['/remote/config.json','/remote/private/users.json','/remote/../private/users.json','/remote/%2e%2e/private/users.json']){
    const r=await rawFetch(url+p,{headers:{Host:'remote.example.test',Cookie:alice.cookie}});assert.notEqual(r.status,200);
  }
  const r=await rawFetch(url+'/remote/',{headers:{Host:'remote.example.test'}});assert.equal(r.status,200);assert.match(r.headers.get('content-security-policy'),/frame-ancestors 'none'/);
});
test('external links open public login assets while cross-site API requests remain blocked',async()=>{
  for(const route of ['/remote/','/remote/app.js','/remote/style.css']) {
    const r=await rawFetch(url+route,{headers:{Host:'remote.example.test','Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate'}});
    assert.equal(r.status,200);
  }
  assert.equal((await call('me',{login:alice,headers:{'Sec-Fetch-Site':'cross-site'}})).status,403);
  assert.equal((await call('sessions',{login:alice,body:credentials,headers:{'Sec-Fetch-Site':'cross-site'}})).status,403);
  assert.equal((await call('login',{body:{user:'alice',password},origin:'https://evil.example',headers:{'Sec-Fetch-Site':'cross-site'}})).status,403);
});
test('session ownership protects screen, input, status and stop',async()=>{
  const id=await connect(alice);
  for(const action of ['frame','state'])assert.equal((await call(`sessions/${id}/${action}`,{login:bob})).status,404);
  for(const action of ['input','stop'])assert.equal((await call(`sessions/${id}/${action}`,{login:bob,body:{type:'release'}})).status,404);
  assert.equal((await call(`sessions/${id}/input`,{login:alice,body:{type:'exec',command:'whoami'}})).status,400);
  assert.equal((await call('admin/sessions',{login:bob})).status,403);
  assert.equal((await call(`sessions/${id}/stop`,{login:admin,body:{}})).status,200);
  assert.equal((await call(`sessions/${id}/state`,{login:alice})).status,410);
});
test('real child pipe frame transport and input bounds work',async()=>{
  const id=await connect(alice);
  await call(`sessions/${id}/frame`,{login:alice});
  let r; const deadline=Date.now()+5000;
  do { await new Promise(resolve=>setTimeout(resolve,50)); r=await call(`sessions/${id}/frame?after=-1`,{login:alice}); } while(r.status===204 && Date.now()<deadline);
  assert.equal(r.status,200);assert.equal(r.headers.get('content-type'),'image/png');assert.ok((await r.arrayBuffer()).byteLength>8);
  assert.equal((await call(`sessions/${id}/input`,{login:alice,body:{type:'mouse',x:1919,y:1079,mask:1}})).status,200);
  assert.equal((await call(`sessions/${id}/input`,{login:alice,body:{type:'mouse',x:1920,y:1079,mask:1}})).status,400);
  assert.equal((await call(`sessions/${id}/input`,{login:alice,body:{type:'text',text:'Проверка юникода'}})).status,200);
  assert.equal((await call(`sessions/${id}/stop`,{login:alice,body:{}})).status,200);
});
test('host allowlist is enforced and edits revoke running access',async()=>{
  users[0].hosts=['987654321'];writeUsers(usersFile,users);
  assert.equal((await call('sessions',{login:alice,body:credentials})).status,403);
  users[0].hosts=[];writeUsers(usersFile,users);const id=await connect(alice);
  users[0].hosts=['987654321'];writeUsers(usersFile,users);
  await new Promise(r=>setTimeout(r,90));assert.equal((await call(`sessions/${id}/state`,{login:alice})).status,410);
  users[0].hosts=[];writeUsers(usersFile,users);
});
test('disabling user kills active session and invalidates cookie',async()=>{
  await connect(bob);users[1].disabled=true;writeUsers(usersFile,users);
  await new Promise(r=>setTimeout(r,90));assert.equal((await call('me',{login:bob})).status,401);
  const list=await (await call('admin/sessions',{login:admin})).json();assert.ok(!list.sessions.some(s=>s.user==='bob'));
});
test('abandoned browser session is reclaimed',async()=>{
  const id=await connect(alice);await new Promise(r=>setTimeout(r,1150));
  assert.equal((await call(`sessions/${id}/state`,{login:alice})).status,410);
});
test('fresh login revokes prior cookie and remote session',async()=>{
  await connect(alice);const old=alice;alice=await login('alice');assert.equal((await call('me',{login:old})).status,401);
  const list=await (await call('admin/sessions',{login:admin})).json();assert.ok(!list.sessions.some(s=>s.user==='alice'));
});
test('audit has no passwords, input contents or screen data',()=>{
  const text=JSON.stringify(audit);for(const secret of [password,'router-secret','host-secret','Проверка юникода','iVBOR'])assert.ok(!text.includes(secret));
  assert.ok(audit.some(e=>e.event==='session_start'));assert.ok(audit.some(e=>e.event==='session_end'));
});
