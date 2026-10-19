// Optional: install Playwright and OpenSSL to run this isolated HTTPS UI test.
import fs from 'node:fs';
import http from 'node:http';
import https from 'node:https';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createGateway} from '../server.mjs';
import {passwordRecord,writeUsers} from '../auth.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'aspia-browser-'));
execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',path.join(temp,'key.pem'),'-out',path.join(temp,'cert.pem'),'-days','1','-subj','/CN=localhost'],{stdio:'ignore'});
let port;
const tls=https.createServer({key:fs.readFileSync(path.join(temp,'key.pem')),cert:fs.readFileSync(path.join(temp,'cert.pem'))},(req,res)=>{
  const upstream=http.request({hostname:'127.0.0.1',port,path:req.url,method:req.method,headers:req.headers},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res);});upstream.on('error',()=>{res.writeHead(502);res.end();});req.pipe(upstream);
});
tls.listen(0,'127.0.0.1');await once(tls,'listening');
const origin='https://127.0.0.1:'+tls.address().port;
const users=path.join(temp,'users.json');
writeUsers(users,[{name:'testadmin',role:'admin',disabled:false,hosts:[],...await passwordRecord('Browser test only 123')}]);
const gateway=createGateway({publicOrigin:origin,port:8085,router:{address:'127.0.0.1',port:8060},maxSessions:2,usersFile:users},root,{audit:()=>{},spawnWorker:()=>spawn(process.execPath,[root+'/test/fake-bridge.mjs'],{stdio:['pipe','pipe','pipe']})});
gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening');port=gateway.server.address().port;
const browser=await chromium.launch({executablePath:process.env.PW_EXECUTABLE,headless:true,args:['--no-sandbox']});
try{
  const ctx=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1280,height:900}});
  const page=await ctx.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>console.log('Browser:',m.text()));page.on('response',r=>{if(r.status()>=400)console.log('HTTP error',r.status(),r.url());});
  await page.goto(origin+'/remote/');
  await page.locator('#webUser').fill('testadmin');await page.locator('#webPassword').fill('Browser test only 123');await page.getByRole('button',{name:'Войти',exact:true}).click();
  await page.locator('#connectPanel').waitFor({state:'visible'});
  await page.locator('#routerUser').fill('test');await page.locator('#routerPassword').fill('router-secret');await page.locator('#hostId').fill('123456789');await page.locator('#hostUser').fill('test');await page.locator('#hostPassword').fill('host-secret');
  await page.getByRole('button',{name:'Подключиться',exact:true}).click();
  try { await page.waitForFunction(()=>document.getElementById('desktop').width===1,null,{timeout:8000}); } catch(e) {console.log('Notice:',await page.locator('#notice').textContent());console.log('Errors',errors);await page.screenshot({path:path.join(temp,'error.png')});throw e;}
  assert.equal(await page.locator('#hostPassword').inputValue(),'');
  await page.locator('#textInput').fill('Текст через веб-консоль');await page.getByRole('button',{name:'Ввести текст',exact:true}).click();
  await page.locator('#refreshAdmin').click();await page.waitForFunction(()=>document.getElementById('sessionList').textContent.includes('123456789'));
  await page.screenshot({path:path.join(temp,'connected.png'),fullPage:true});
  await page.locator('#disconnect').click();await page.locator('#connectPanel').waitFor({state:'visible'});
  await page.locator('#logout').click();await page.locator('#loginPanel').waitFor({state:'visible'});
  assert.deepEqual(errors,[]);console.log('Screenshot:',path.join(temp,'connected.png'));console.log('Browser E2E passed: TLS login, cookie, connection, decoded PNG, text, admin listing, stop, logout. Fake native worker only.');
}finally{await browser.close();gateway.close();tls.close();tls.closeAllConnections();fs.rmSync(users,{force:true});}
