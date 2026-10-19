// GPL-3.0-or-later. No npm dependencies. Loopback only, HTTPS terminates at Caddy.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { loadUsers, verifyPassword } from './auth.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const base = '/remote';
const token = () => randomBytes(32).toString('hex');
const fatalStates = new Set(['stopped', 'disconnected', 'timeout', 'version_mismatch', 'host_auth_error',
  'router_error', 'protocol_error', 'codec_error', 'screen_too_large', 'decode_error', 'frame_error']);
const fail = (code, message) => Object.assign(new Error(message), { code });
export function validateConfig(c) {
  const origin = new URL(c.publicOrigin);
  if (origin.protocol !== 'https:' || origin.origin !== c.publicOrigin || origin.username || origin.password)
    throw new Error('publicOrigin must be an HTTPS origin without path');
  if (!Number.isInteger(c.port) || c.port < 1024 || c.port > 65535) throw new Error('Invalid loopback port');
  if (!c.router || typeof c.router.address !== 'string' || !/^[a-zA-Z0-9.:-]{1,253}$/.test(c.router.address) ||
      !Number.isInteger(c.router.port) || c.router.port < 1 || c.router.port > 65535) throw new Error('Invalid router');
  if (!Number.isInteger(c.maxSessions) || c.maxSessions < 1 || c.maxSessions > 16) throw new Error('maxSessions must be 1–16');
  return c;
}
export function createGateway(config, root = here, hooks = {}) {
  const c = validateConfig(config);
  const usersFile = path.resolve(root, c.usersFile || 'private/users.json');
  loadUsers(usersFile); // Fail closed if missing or invalid.
  const logins = new Map(), sessions = new Map(), limits = new Map();
  const maxAge = 8 * 3600_000;
  const heartbeatMs = hooks.heartbeatMs || 30_000;
  let hashing = 0;
  const audit = hooks.audit || ((event, fields) => {
    const dir = path.join(root, 'logs'), file = path.join(dir, 'audit.jsonl');
    fs.mkdirSync(dir, { recursive: true });
    if (fs.existsSync(file) && fs.statSync(file).size > 2 * 1024 * 1024) {
      fs.rmSync(file + '.3', { force: true });
      for (let n = 2; n >= 1; --n) if (fs.existsSync(file + '.' + n)) fs.renameSync(file + '.' + n, file + '.' + (n + 1));
      fs.renameSync(file, file + '.1');
    }
    fs.appendFileSync(file, JSON.stringify({ time: new Date().toISOString(), event, ...fields }) + '\n');
  });
  const userNow = login => loadUsers(usersFile).find(u => u.name === login.user && !u.disabled &&
    u.hash === login.hash && (u.generation || 0) === login.generation);
  const permitted = (u, id) => u && (!u.hosts.length || u.hosts.includes(id));
  function send(worker, msg) {
    if (!worker || worker.killed || worker.stdin.destroyed || worker.stdin.writableEnded || worker.stdin.writableLength > 128 * 1024) return false;
    worker.stdin.write(JSON.stringify(msg) + '\n'); return true;
  }
  function stop(s, reason = 'stopped') {
    if (!s || !sessions.has(s.id)) return;
    sessions.delete(s.id);
    const owner = logins.get(s.loginId);
    if (owner) owner.lastEnd = { id: s.id, reason };
    send(s.worker, { type: 'stop' });
    s.worker.stdin.end();
    const timer = setTimeout(() => s.worker.kill(), 1500); timer.unref();
    s.worker.once('exit', () => clearTimeout(timer));
    s.frame = null;
    audit('session_end', { user: s.user, hostId: s.hostId, reason });
  }
  function revoke(id) {
    for (const s of sessions.values()) if (s.loginId === id) stop(s, 'web_login_ended');
    logins.delete(id);
  }
  function limited(key, max, interval) {
    const now = Date.now();
    let entry = limits.get(key);
    if (!entry || entry.until < now) { entry = { count: 0, until: now + interval }; limits.set(key, entry); }
    return ++entry.count > max;
  }
  async function body(req) {
    if (req.headers['content-type']?.split(';')[0] !== 'application/json') throw fail(415, 'JSON required');
    let size = 0; const chunks = [];
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 32768) throw fail(413, 'Request too large');
      chunks.push(chunk);
    }
    try { const b = JSON.parse(Buffer.concat(chunks).toString('utf8')); if (!b || Array.isArray(b) || typeof b !== 'object') throw 0; return b; }
    catch { throw fail(400, 'Invalid JSON'); }
  }
  const server = http.createServer(async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'");
    const reply = (code, data) => { res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify(data)); };
    try {
      if (req.headers.host !== new URL(c.publicOrigin).host) throw fail(403, 'Invalid host');
      if (!['GET', 'POST'].includes(req.method)) throw fail(405, 'Method not allowed');
      if (req.method === 'POST' && req.headers.origin !== c.publicOrigin) throw fail(403, 'Invalid origin');
      if (req.headers['sec-fetch-site'] === 'cross-site') throw fail(403, 'Cross-site request');
      const url = new URL(req.url, c.publicOrigin), route = url.pathname;
      const staticFiles = new Map([[base + '/', ['index.html', 'text/html']], [base + '/app.js', ['app.js', 'text/javascript']], [base + '/style.css', ['style.css', 'text/css']]]);
      if (req.method === 'GET' && staticFiles.has(route)) {
        const [file, type] = staticFiles.get(route);
        res.writeHead(200, { 'Content-Type': type + '; charset=utf-8' });
        res.end(fs.readFileSync(path.join(root, 'public', file))); return;
      }
      if (route === base + '/api/login' && req.method === 'POST') {
        // Caddy overwrites X-Forwarded-For for an untrusted public peer. Never use it for authorization.
        const ip = String(req.headers['x-forwarded-for'] || req.socket.remoteAddress).split(',').at(-1).trim().slice(0, 128);
        if (limited('ip:' + ip, 30, 300_000) || hashing >= 4) throw fail(429, 'Too many login attempts; wait five minutes');
        const b = await body(req);
        if (typeof b.user !== 'string' || !/^[a-zA-Z0-9_.-]{1,64}$/.test(b.user) || typeof b.password !== 'string' || b.password.length > 256)
          throw fail(400, 'Invalid login');
        if (limited('user:' + b.user, 10, 300_000)) throw fail(429, 'Too many login attempts; wait five minutes');
        const u = loadUsers(usersFile).find(x => x.name === b.user && !x.disabled);
        let valid; ++hashing;
        try { valid = await verifyPassword(b.password, u); } finally { --hashing; b.password = ''; }
        if (!valid) { audit('login_failed', { user: b.user }); throw fail(401, 'Invalid login or password'); }
        if (logins.size >= 128) throw fail(503, 'Login capacity reached');
        const id = token(), csrf = token();
        // One web login per user: a fresh login revokes the previous one and its remote session.
        for (const [oldId, old] of logins) if (old.user === u.name) revoke(oldId);
        logins.set(id, { user: u.name, hash: u.hash, generation: u.generation || 0, csrf, expires: Date.now() + maxAge });
        res.setHeader('Set-Cookie', `__Secure-aspia_gateway=${id}; Path=/remote/; Secure; HttpOnly; SameSite=Strict; Max-Age=28800`);
        audit('login', { user: u.name }); reply(200, { user: u.name, role: u.role, csrf, router: c.router }); return;
      }
      const loginId = /(?:^|;\s*)__Secure-aspia_gateway=([a-f0-9]{64})(?:;|$)/.exec(req.headers.cookie || '')?.[1];
      const login = logins.get(loginId);
      const user = login && userNow(login);
      if (!login || !user || login.expires < Date.now()) { if (login) revoke(loginId); throw fail(401, 'Login required'); }
      if (req.method === 'POST' && req.headers['x-csrf-token'] !== login.csrf) throw fail(403, 'Invalid CSRF token');
      if (req.method === 'GET' && route === base + '/api/me') { reply(200, { user: user.name, role: user.role, csrf: login.csrf, router: c.router }); return; }
      if (req.method === 'POST' && route === base + '/api/logout') {
        revoke(loginId); res.setHeader('Set-Cookie', '__Secure-aspia_gateway=; Path=/remote/; Secure; HttpOnly; SameSite=Strict; Max-Age=0'); reply(200, {}); return;
      }
      if (route === base + '/api/sessions' && req.method === 'POST') {
        if (limited('connect:' + user.name, 12, 300_000)) throw fail(429, 'Too many connections');
        if (sessions.size >= c.maxSessions) throw fail(409, 'All remote session slots are busy');
        if ([...sessions.values()].some(s => s.user === user.name)) throw fail(409, 'Disconnect your existing session first');
        const b = await body(req);
        if (typeof b.hostId !== 'string' || !/^[0-9]{1,15}$/.test(b.hostId || '') || !/[1-9]/.test(b.hostId) || !permitted(user, b.hostId)) throw fail(403, 'Host ID not permitted');
        for (const field of ['routerUser', 'routerPassword', 'hostUser', 'hostPassword']) {
          if (typeof b[field] !== 'string' || b[field].length > 256 || (!b[field] && field !== 'hostUser')) throw fail(400, 'Invalid connection credentials');
        }
        // Re-check after reading the asynchronous body: concurrent requests cannot claim two slots.
        if (sessions.size >= c.maxSessions || [...sessions.values()].some(s => s.user === user.name))
          throw fail(409, 'Remote session slot is already occupied');
        if (!userNow(login) || !logins.has(loginId)) throw fail(401, 'Login revoked');
        const worker = hooks.spawnWorker ? hooks.spawnWorker() : spawn(path.resolve(root, c.bridgePath || 'aspia_web_bridge.exe'), [],
          { cwd: root, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
        const s = { id: token(), loginId, user: user.name, hostId: b.hostId, created: Date.now(), seen: Date.now(),
          state: 'starting', frame: null, seq: 0, worker, pending: false, requestAt: 0 };
        sessions.set(s.id, s);
        worker.stdin.on('error', () => stop(s, 'bridge_pipe_error'));
        worker.on('error', () => stop(s, 'bridge_start_error'));
        worker.on('exit', () => stop(s, 'bridge_exit'));
        worker.stderr.resume(); // Never persist native output or credentials.
        let pending = '';
        worker.stdout.setEncoding('utf8');
        worker.stdout.on('data', chunk => {
          pending += chunk;
          if (pending.length > 34 * 1024 * 1024) { stop(s, 'bridge_output_limit'); return; }
          let end;
          while ((end = pending.indexOf('\n')) !== -1) {
            const line = pending.slice(0, end); pending = pending.slice(end + 1);
            try {
              const m = JSON.parse(line);
              if (m.type === 'frame') {
                if (typeof m.png !== 'string' || m.png.length > 32 * 1024 * 1024 ||
                    !Number.isInteger(m.width) || !Number.isInteger(m.height) || m.width <= 0 || m.height <= 0 ||
                    m.width * m.height > 16000000 || !Number.isInteger(m.screenWidth) || !Number.isInteger(m.screenHeight) ||
                    m.screenWidth <= 0 || m.screenHeight <= 0 || m.screenWidth > 32768 || m.screenHeight > 32768) throw 0;
                s.frame = Buffer.from(m.png, 'base64'); ++s.seq; s.pending = false;
                s.width = m.width; s.height = m.height; s.screenWidth = m.screenWidth; s.screenHeight = m.screenHeight;
              } else if (m.type === 'idle') s.pending = false;
              else if (m.type === 'status' && typeof m.state === 'string') {
                s.state = m.state;
                if (fatalStates.has(m.state)) stop(s, m.state);
              } else if (m.type === 'videoStatus') s.videoStatus = m.code;
            } catch { stop(s, 'bridge_protocol_error'); }
          }
        });
        send(worker, { type: 'connect', routerAddress: c.router.address, routerPort: c.router.port,
          hostId: b.hostId, routerUser: b.routerUser, routerPassword: b.routerPassword,
          hostUser: b.hostUser, hostPassword: b.hostPassword, displayName: `Web: ${user.name}` });
        for (const field of ['routerUser', 'routerPassword', 'hostUser', 'hostPassword']) b[field] = '';
        audit('session_start', { user: s.user, hostId: s.hostId }); reply(201, { id: s.id }); return;
      }
      if (route === base + '/api/admin/sessions' && req.method === 'GET') {
        if (user.role !== 'admin') throw fail(403, 'Administrator required');
        reply(200, { sessions: [...sessions.values()].map(s => ({ id: s.id, user: s.user, hostId: s.hostId, created: s.created, state: s.state })) }); return;
      }
      const match = /^\/remote\/api\/sessions\/([a-f0-9]{64})\/(state|frame|input|stop)$/.exec(route);
      if (!match) throw fail(404, 'Not found');
      const s = sessions.get(match[1]), action = match[2];
      if (!s && login.lastEnd?.id === match[1]) throw fail(410, 'Session ended: ' + login.lastEnd.reason);
      if (!s || (s.loginId !== loginId && !(user.role === 'admin' && action === 'stop'))) throw fail(404, 'Session ended or not yours');
      if (req.method === 'POST' && action === 'stop') { stop(s, user.role === 'admin' ? 'admin_or_owner_stop' : 'owner_stop'); reply(200, {}); return; }
      if (!permitted(user, s.hostId)) { stop(s, 'host_permission_revoked'); throw fail(403, 'Host permission revoked'); }
      s.seen = Date.now();
      if (req.method === 'GET' && action === 'state') {
        reply(200, { state: s.state, seq: s.seq, width: s.width, height: s.height, screenWidth: s.screenWidth, screenHeight: s.screenHeight, videoStatus: s.videoStatus }); return;
      }
      if (req.method === 'GET' && action === 'frame') {
        if (!s.pending && Date.now() - s.requestAt >= 200) { s.pending = send(s.worker, { type: 'frame' }); s.requestAt = Date.now(); }
        if (!s.frame || Number(url.searchParams.get('after')) === s.seq) { res.writeHead(204); res.end(); return; }
        res.writeHead(200, { 'Content-Type': 'image/png', 'X-Frame-Sequence': String(s.seq),
          'X-Screen-Width': String(s.screenWidth), 'X-Screen-Height': String(s.screenHeight) });
        res.end(s.frame); return;
      }
      if (req.method === 'POST' && action === 'input') {
        if (limited('input:' + s.id, 250, 1000)) throw fail(429, 'Input rate exceeded');
        const b = await body(req);
        let command;
        if (b.type === 'release') command = { type: 'release' };
        else if (b.type === 'text' && typeof b.text === 'string' && Buffer.byteLength(b.text) <= 8192) command = { type: 'text', text: b.text };
        else if (b.type === 'key' && Number.isInteger(b.code) && b.code >= 0x070004 && b.code <= 0x0700e7 && typeof b.down === 'boolean') command = { type: 'key', code: b.code, down: b.down };
        else if (b.type === 'mouse' && Number.isInteger(b.x) && Number.isInteger(b.y) && Number.isInteger(b.mask) && b.mask >= 0 && b.mask <= 127 &&
          b.x >= 0 && b.x < (s.screenWidth || 1) && b.y >= 0 && b.y < (s.screenHeight || 1)) command = { type: 'mouse', x: b.x, y: b.y, mask: b.mask };
        else throw fail(400, 'Invalid input');
        if (!send(s.worker, command)) { stop(s, 'input_backpressure'); throw fail(503, 'Remote input stalled'); }
        reply(200, {}); return;
      }
      throw fail(405, 'Method not allowed');
    } catch (e) { if (!res.headersSent) reply(e.code >= 400 && e.code <= 599 ? e.code : 500, { error: e.code ? e.message : 'Internal service error' }); else res.destroy(); }
  });
  server.requestTimeout = 15_000; server.headersTimeout = 10_000; server.maxHeadersCount = 40;
  const sweep = setInterval(() => {
    try {
      for (const [id, login] of logins) if (login.expires < Date.now() || !userNow(login)) revoke(id);
      for (const s of sessions.values()) {
        const login = logins.get(s.loginId), u = login && userNow(login);
        if (!permitted(u, s.hostId) || Date.now() - s.seen > heartbeatMs || Date.now() - s.created > maxAge ||
          (!s.frame && Date.now() - s.created > 90_000) || (s.pending && Date.now() - s.requestAt > 20_000)) stop(s, 'expired_or_unresponsive');
      }
      for (const [key, v] of limits) if (v.until < Date.now()) limits.delete(key);
    } catch { for (const id of logins.keys()) revoke(id); }
  }, hooks.sweepMs || 5000); sweep.unref();
  const close = () => { clearInterval(sweep); for (const s of sessions.values()) stop(s, 'service_shutdown'); server.close(); server.closeAllConnections(); };
  return { server, close };
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const configPath = process.env.ASPIA_GATEWAY_CONFIG || path.join(here, 'config.json');
  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  const gateway = createGateway(config);
  gateway.server.listen(config.port, '127.0.0.1', () => console.log('Aspia Web Gateway listening on loopback port ' + config.port));
  process.on('SIGINT', gateway.close); process.on('SIGTERM', gateway.close);
}
