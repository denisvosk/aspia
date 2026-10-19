/* GPL-3.0-or-later. Credentials and frames are never written to browser storage. */
'use strict';
const $ = id => document.getElementById(id);
let csrf = '', role = '', session = '', sequence = -1, screenWidth = 1, screenHeight = 1;
let stopped = false, busy = false, queue = [], draining = false;
const canvas = $('desktop'), context = canvas.getContext('2d');
const stateText = { starting:'Запуск подключения', router_connecting:'Подключение к маршрутизатору', router_connected:'Маршрутизатор подключён', host_connecting:'Подключение к хосту', waiting_host:'Ожидание хоста', connected:'Подключено', waiting_router:'Ожидание маршрутизатора' };
function notice(text) { $('notice').textContent = text; }
async function request(route, data) {
  const options = { credentials:'same-origin', cache:'no-store' };
  if (data !== undefined) Object.assign(options, { method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify(data) });
  const r = await fetch('/remote/api/' + route, options);
  const value = await r.json();
  if (!r.ok) throw new Error(value.error || `Ошибка ${r.status}`);
  return value;
}
function signedIn(value) {
  csrf = value.csrf; role = value.role;
  $('identity').textContent = value.user;
  $('router').textContent = value.router.address + ':' + value.router.port;
  $('loginPanel').hidden = true; $('connectPanel').hidden = false; $('logout').hidden = false;
  $('adminPanel').hidden = role !== 'admin';
  notice('Можно подключиться к компьютеру по ID.');
  if (role === 'admin') refreshAdmin();
}
$('loginForm').onsubmit = async e => {
  e.preventDefault(); const button = e.submitter; button.disabled = true;
  const data = { user:$('webUser').value, password:$('webPassword').value }; $('webPassword').value = '';
  try { signedIn(await request('login', data)); } catch(e) { notice(e.message); }
  finally { data.password = ''; button.disabled = false; }
};
$('connectForm').onsubmit = async e => {
  e.preventDefault(); if (busy) return; busy = true; e.submitter.disabled = true;
  const data = { hostId:$('hostId').value.replace(/\s/g,'') };
  for (const field of ['routerUser','routerPassword','hostUser','hostPassword']) { data[field] = $(field).value; $(field).value = ''; }
  try {
    const result = await request('sessions', data); session = result.id; stopped = false; sequence = -1;
    $('connectPanel').hidden = true; $('desktopPanel').hidden = false; queue = [];
    context.clearRect(0,0,canvas.width,canvas.height); notice('Подключаемся…'); poll();
  } catch(e) { notice(e.message); }
  finally { for (const k of Object.keys(data)) data[k] = ''; busy = false; e.submitter.disabled = false; }
};
function endView(message) {
  session = ''; stopped = true; queue = []; sequence = -1;
  context.clearRect(0,0,canvas.width,canvas.height);
  $('desktopPanel').hidden = true; $('connectPanel').hidden = false;
  $('textInput').value = ''; notice(message);
}
async function disconnect() {
  const id = session; if (!id) return;
  try { await request(`sessions/${id}/stop`, {}); } catch(e) { notice(e.message); }
  endView('Сеанс завершён.'); if (role === 'admin') refreshAdmin();
}
$('disconnect').onclick = disconnect;
$('logout').onclick = async () => { try { await request('logout', {}); } finally { location.reload(); } };
async function poll() {
  const id = session;
  if (!id || stopped) return;
  try {
    const state = await request(`sessions/${id}/state`);
    if (session !== id) return;
    $('connectionState').textContent = stateText[state.state] || state.state;
    notice(state.state === 'connected' ? 'Сеанс активен. Вы можете завершить его в любой момент.' : (stateText[state.state] || state.state));
    const r = await fetch(`/remote/api/sessions/${id}/frame?after=${sequence}`, {cache:'no-store'});
    if (r.status === 200) {
      const bitmap = await createImageBitmap(await r.blob());
      if (session === id) {
        canvas.width = bitmap.width; canvas.height = bitmap.height;
        context.drawImage(bitmap,0,0); sequence = Number(r.headers.get('X-Frame-Sequence'));
        screenWidth = Number(r.headers.get('X-Screen-Width')); screenHeight = Number(r.headers.get('X-Screen-Height'));
      }
      bitmap.close();
    } else if (r.status !== 204) throw new Error('Сеанс завершён или соединение потеряно.');
  } catch(e) {
    if (session === id) { endView(e.message); request(`sessions/${id}/stop`, {}).catch(()=>{}); }
  }
  if (session === id) setTimeout(poll, 250);
}
function input(command) {
  if (!session || stopped) return;
  // Preserve key/button order, coalesce only adjacent mouse-motion events.
  if (command.motion && queue.at(-1)?.motion) queue[queue.length-1] = command;
  else queue.push(command);
  if (queue.length > 256) { queue = [{type:'release'}]; notice('Ввод не успевает передаваться; клавиши отпущены.'); }
  drain();
}
async function drain() {
  if (draining) return; draining = true; const id = session;
  try {
    while (queue.length && session === id) {
      const command = queue.shift(); delete command.motion;
      await request(`sessions/${id}/input`, command);
    }
  } catch(e) { queue = []; notice(e.message); request(`sessions/${id}/input`, {type:'release'}).catch(()=>{}); }
  finally { draining = false; if(queue.length) drain(); }
}
function mouse(e, wheel = 0, motion = false) {
  if (sequence < 0) return;
  const r = canvas.getBoundingClientRect();
  const mask = (e.buttons & 1) | ((e.buttons & 2) << 1) | ((e.buttons & 4) >> 1) | ((e.buttons & 8) << 2) | ((e.buttons & 16) << 2) | wheel;
  input({type:'mouse', x:Math.max(0,Math.min(screenWidth-1,Math.floor((e.clientX-r.left)*screenWidth/r.width))),
    y:Math.max(0,Math.min(screenHeight-1,Math.floor((e.clientY-r.top)*screenHeight/r.height))), mask, motion});
}
canvas.onpointerdown = e => {e.preventDefault(); canvas.focus(); canvas.setPointerCapture(e.pointerId); mouse(e);};
canvas.onpointerup = e => {e.preventDefault(); mouse(e); if(canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);};
canvas.onpointermove = e => mouse(e,0,true);
canvas.onpointercancel = () => input({type:'release'});
canvas.oncontextmenu = e => e.preventDefault();
canvas.addEventListener('wheel',e=>{e.preventDefault();mouse(e,e.deltaY<0?8:16);},{passive:false});
const keys = {Enter:40,Escape:41,Backspace:42,Tab:43,Space:44,Minus:45,Equal:46,BracketLeft:47,BracketRight:48,Backslash:49,Semicolon:51,Quote:52,Backquote:53,Comma:54,Period:55,Slash:56,CapsLock:57,PrintScreen:70,ScrollLock:71,Pause:72,Insert:73,Home:74,PageUp:75,Delete:76,End:77,PageDown:78,ArrowRight:79,ArrowLeft:80,ArrowDown:81,ArrowUp:82,NumLock:83,NumpadDivide:84,NumpadMultiply:85,NumpadSubtract:86,NumpadAdd:87,NumpadEnter:88,Numpad0:98,NumpadDecimal:99,ContextMenu:101,ControlLeft:224,ShiftLeft:225,AltLeft:226,MetaLeft:227,ControlRight:228,ShiftRight:229,AltRight:230,MetaRight:231};
for(let i=0;i<26;i++) keys['Key'+String.fromCharCode(65+i)]=4+i;
for(let i=1;i<=9;i++){keys['Digit'+i]=29+i;keys['Numpad'+i]=88+i;} keys.Digit0=39;
for(let i=1;i<=12;i++)keys['F'+i]=57+i;
canvas.onkeydown = e => { if(e.code==='Escape'){input({type:'key',code:0x070029,down:true});input({type:'key',code:0x070029,down:false});canvas.blur();e.preventDefault();return;} if(keys[e.code]){e.preventDefault();input({type:'key',code:0x070000+keys[e.code],down:true});} };
canvas.onkeyup = e => {if(keys[e.code]){e.preventDefault();input({type:'key',code:0x070000+keys[e.code],down:false});}};
canvas.onblur = () => input({type:'release'});
window.addEventListener('blur',()=>input({type:'release'}));
$('release').onclick=()=>input({type:'release'});
function chord(codes){input({type:'release'});for(const code of codes)input({type:'key',code:0x070000+code,down:true});for(const code of [...codes].reverse())input({type:'key',code:0x070000+code,down:false});}
$('altTab').onclick=()=>chord([226,43]);$('startMenu').onclick=()=>chord([227]);
$('fit').onclick=()=>{canvas.classList.toggle('actual');$('fit').textContent=canvas.classList.contains('actual')?'Масштаб: 100%':'Масштаб: по ширине';};
$('textForm').onsubmit=e=>{e.preventDefault();input({type:'release'});input({type:'text',text:$('textInput').value});$('textInput').value='';};
async function refreshAdmin(){
  try{const data=await request('admin/sessions');const list=$('sessionList');list.replaceChildren();
    if(!data.sessions.length)list.textContent='Активных сеансов нет.';
    for(const s of data.sessions){const row=document.createElement('div');row.className='session';const text=document.createElement('span');text.textContent=`${s.user} → ID ${s.hostId} · ${stateText[s.state]||s.state} · ${new Date(s.created).toLocaleTimeString()}`;
      const button=document.createElement('button');button.textContent='Завершить';button.onclick=async()=>{try{await request(`sessions/${s.id}/stop`,{});await refreshAdmin();}catch(e){notice(e.message);}};row.append(text,button);list.append(row);}
  }catch(e){notice(e.message);}
}
$('refreshAdmin').onclick=refreshAdmin;
setInterval(()=>{if(role==='admin'&&!document.hidden)refreshAdmin();},5000);
window.addEventListener('pagehide',()=>{if(session)fetch(`/remote/api/sessions/${session}/stop`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}',keepalive:true}).catch(()=>{});});
request('me').then(signedIn).catch(()=>{});
