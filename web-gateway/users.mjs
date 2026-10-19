// Local administrator tool. No network registration or password argument.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { passwordRecord, loadUsers, writeUsers } from './auth.mjs';
const root = path.dirname(fileURLToPath(import.meta.url));
const config = JSON.parse(fs.readFileSync(process.env.ASPIA_GATEWAY_CONFIG || path.join(root, 'config.json'), 'utf8'));
const file = path.resolve(root, config.usersFile || 'private/users.json');
const [action, name, role = 'user', hostList = ''] = process.argv.slice(2);
const users = fs.existsSync(file) ? loadUsers(file) : [];
if (!['add', 'disable', 'enable', 'list'].includes(action)) {
  console.error('Usage: node users.mjs add NAME [user|admin] [ID,ID] | disable NAME | enable NAME | list');
  process.exit(1);
}
if (action === 'list') {
  for (const u of users) console.log(`${u.name}\t${u.role}\t${u.disabled ? 'disabled' : 'enabled'}\t${u.hosts.join(',') || 'any authenticated host'}`);
} else {
  if (!/^[a-zA-Z0-9_.-]{1,64}$/.test(name || '') || !['admin', 'user'].includes(role)) throw new Error('Invalid name/role');
  let record = users.find(u => u.name === name);
  if (action === 'add') {
    if (record) throw new Error('User exists. Disable and use a different name; existing sessions must be revoked.');
    const hosts = hostList ? hostList.split(',') : [];
    if (hosts.some(id => !/^[0-9]{1,15}$/.test(id))) throw new Error('Invalid host IDs');
    process.stderr.write('Enter a new password (12+ characters; hidden): ');
    const password = await new Promise((resolve, reject) => {
      let value = '';
      if (process.stdin.isTTY) process.stdin.setRawMode(true);
      process.stdin.setEncoding('utf8'); process.stdin.resume();
      const end = () => { if (process.stdin.isTTY) process.stdin.setRawMode(false); process.stdin.pause(); };
      process.stdin.on('data', chunk => {
        for (const c of chunk) {
          if (c === '\u0003') { end(); reject(new Error('Cancelled')); return; }
          if (c === '\r' || c === '\n') { end(); resolve(value); return; }
          if (c === '\u007f' || c === '\b') value = value.slice(0, -1);
          else if (value.length < 256) value += c;
        }
      });
      process.stdin.on('end', () => { end(); resolve(value); });
    });
    record = { name, role, disabled: false, hosts, ...await passwordRecord(password) };
    users.push(record);
    process.stderr.write('\n');
  } else {
    if (!record) throw new Error('User not found');
    record.disabled = action === 'disable';
    // Changing the generation revokes all existing web logins even if enabled again.
    record.generation = (record.generation || 0) + 1;
  }
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  writeUsers(file, users);
  console.log('Saved. Changes apply within 5 seconds; no service restart required.');
}
