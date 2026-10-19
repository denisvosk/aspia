// GPL-3.0-or-later
import { randomBytes, scrypt, timingSafeEqual } from 'node:crypto';
import { promisify } from 'node:util';
import fs from 'node:fs';
const derive = promisify(scrypt);
const options = { N: 32768, r: 8, p: 1, maxmem: 64 * 1024 * 1024 };
export async function passwordRecord(password) {
  if (typeof password !== 'string' || password.length < 12 || password.length > 256)
    throw new Error('Password must contain 12–256 characters.');
  const salt = randomBytes(16).toString('hex');
  return { salt, hash: (await derive(password, salt, 32, options)).toString('hex') };
}
export async function verifyPassword(password, record) {
  const salt = record?.salt || '00000000000000000000000000000000';
  const hash = record?.hash || '0'.repeat(64);
  const candidate = await derive(password, salt, 32, options);
  const expected = Buffer.from(hash, 'hex');
  return expected.length === candidate.length && timingSafeEqual(expected, candidate) && !!record;
}
export function loadUsers(file) {
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!Array.isArray(data.users) || data.users.length > 1000) throw new Error('Invalid users file');
  for (const u of data.users) {
    if (!/^[a-zA-Z0-9_.-]{1,64}$/.test(u.name) || !/^[a-f0-9]{32}$/.test(u.salt) ||
        !/^[a-f0-9]{64}$/.test(u.hash) || !['admin', 'user'].includes(u.role) ||
        !Array.isArray(u.hosts) || u.hosts.some(id => !/^[0-9]{1,15}$/.test(id)))
      throw new Error('Invalid user record');
  }
  if (new Set(data.users.map(u => u.name)).size !== data.users.length) throw new Error('Duplicate users');
  return data.users;
}
export function writeUsers(file, users) {
  const tmp = file + '.' + randomBytes(6).toString('hex') + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify({ users }, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
  fs.renameSync(tmp, file);
}
