import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
const binary=process.argv[2];
for(const explicitStop of [true,false]){
  const child=spawn(binary,[],{stdio:['pipe','pipe','pipe'],windowsHide:true});
  let output='',error='';child.stdout.on('data',b=>output+=b);child.stderr.on('data',b=>error+=b);
  const done=new Promise((resolve,reject)=>{child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(new Error('Native bridge exit '+code)));});
  const timeout=setTimeout(()=>child.kill(),8000);
  child.stdin.on('error',()=>{});
  child.stdin.write(JSON.stringify({type:'connect',routerAddress:'127.0.0.1',routerPort:1,routerUser:'smoke',routerPassword:'never-log-this-test-secret',hostId:'123456789',hostUser:'test',hostPassword:'never-log-this-test-secret',displayName:'CI smoke'})+'\n');
  if(explicitStop)child.stdin.write('{"type":"stop"}\n');
  child.stdin.end();
  try{await done;}finally{clearTimeout(timeout);}
  assert.ok(!output.includes('never-log-this-test-secret')&&!error.includes('never-log-this-test-secret'));
  const messages=output.trim().split('\n').filter(Boolean).map(line=>JSON.parse(line));
  assert.ok(messages.some(m=>m.state==='stopped'));
}
console.log('Native pipe stop / EOF and no-secret smoke tests passed. No remote host was used.');
