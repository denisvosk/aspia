# Aspia Web Gateway — Windows x64 prototype

An authenticated browser console for the existing Aspia 2.7 Router/Relay and Host.
The gateway uses the project's native client authentication/transport/decoder. Each
remote session is a separate `aspia_web_bridge.exe` process; credentials enter through
its private stdin pipe. No Router/Relay changes or additional public ports are required.

## What this version does

- Individual web logins, roles `user` and `admin`, optional per-user Host ID allowlist.
- Separate Router login/password and Host ID/login/password for each connection.
- Lossless ZSTD desktop decoded to PNG, mouse, physical USB keyboard events and Unicode text input.
- One remote session and one web login per user; default two simultaneous remote sessions overall.
- Administrator sees user, Host ID, start time and state, and can stop sessions of this gateway.
- Stop/logout, new login replacing the old one, account disable and permission changes terminate access.
- No browser heartbeat for 30 seconds: terminate within the next 5 seconds. Maximum session/login age: 8 hours.
- Local users are scrypt password hashes; remote credentials/screens/input are not persisted or audited.

This is a prototype, not an independently audited production remote-access service.
Automated web tests do not prove a real Windows Host connection. First validate on
the home PC with independent RDP available. Browser access by a particular GPT agent
also depends on that agent's browser/network tools; buying GPT alone does not establish
a connection automatically. The user must authorize the selected machine/session.

The gateway decrypts Aspia traffic and holds credentials in process memory while connected.
It is a trusted endpoint. JS/Qt copies cannot be guaranteed to be cryptographically erased;
credentials never go into command lines, files, cookies, URLs, browser storage or audit logs.
The browser can still offer password-manager saving despite autocomplete hints.
Use an existing trusted HTTPS certificate; never click through a certificate warning.

## Installation on the Caddy machine

1. Download the `aspia-web-gateway-<run>-x64.zip` draft-release asset. Verify its SHA256
   against the accompanying `.sha256` file. Extract the stable `AspiaWebGateway` folder
   to **`C:\AspiaWebGateway`**. Do not put it under `C:\Web` or another Caddy file root:
   it contains the service and private account configuration. Existing download pages
   under `C:\Web` remain in place.
2. The package includes `node.exe`, the native bridge, web assets, licenses and scripts.
   No npm install or Visual Studio is required on the server.
3. In elevated Windows PowerShell:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\AspiaWebGateway\Install-Gateway.ps1" -AdminUser denis
   ```

   Enter a new web password (12+ characters, hidden). No default password exists.
   The script uses your existing `C:\chat_ZPP_bot\nssm.exe`, binds only 127.0.0.1:8085
   and runs as LocalService. Program/private files are restricted to administrators,
   SYSTEM and service read access; only logs are service-writable. No firewall port opens.
   If the gateway cannot reach the public Router from home due to NAT loopback, set
   `router.address` in `config.json` to the Router's LAN IP or 127.0.0.1 if on this machine.
4. Back up `C:\chat_ZPP_bot\Caddyfile`. Insert `Caddy.fragment` **inside the existing
   IP site's block**, before any catch-all `handle`. Do not replace the entire file.
   Keep the current file download handler, TLS configuration and `bot.example.invalid` unchanged.
   The fragment uses `handle`, not `handle_path`, because `/remote/` must be preserved.
5. Validate and reload the active Caddy instance:

   ```powershell
   & "C:\chat_ZPP_bot\caddy.exe" validate --config "C:\chat_ZPP_bot\Caddyfile" --adapter caddyfile
   # Only when validation succeeds:
   & "C:\chat_ZPP_bot\caddy.exe" reload --config "C:\chat_ZPP_bot\Caddyfile" --adapter caddyfile
   ```

6. Open `https://192.0.2.1/remote/`, log in with the web account, then enter the
   Router and Host credentials. The Router address/port are fixed by the local admin;
   users cannot turn the gateway into a proxy to arbitrary servers.

If Caddy's existing block uses `handle_path`/rewrites/routes, inspect the actual full
configuration before inserting the fragment. Its current contents are not included
in this repository. Don't launch a second Caddy process or touch the duplicate service.

## Local account management

Run in elevated PowerShell. Passwords are prompted, never passed in command arguments.

```powershell
& "C:\AspiaWebGateway\node.exe" "C:\AspiaWebGateway\users.mjs" add colleague user 123456789
& "C:\AspiaWebGateway\node.exe" "C:\AspiaWebGateway\users.mjs" add another user 123456789,987654321
& "C:\AspiaWebGateway\node.exe" "C:\AspiaWebGateway\users.mjs" list
& "C:\AspiaWebGateway\node.exe" "C:\AspiaWebGateway\users.mjs" disable colleague
& "C:\AspiaWebGateway\node.exe" "C:\AspiaWebGateway\users.mjs" enable colleague
```

Omitting the final Host ID list permits any Host ID for which that user supplies valid
Aspia credentials. For colleagues, use an explicit allowlist. Disabling revokes existing
sessions within 5 seconds, including ones re-enabled later. Do not edit files simultaneously
from multiple admin terminals. No public registration or SMTP is used. SMTP is an actual
mail-delivery service/protocol; it does not provide registration without a mail provider.
For now the administrator creates and delivers accounts personally.

## Monitoring and testing

Audit: `logs/audit.jsonl`, up to 2 MiB + three rotated files (about 8 MiB total).
Only login success/failure, username, Host ID, connection start/end/reason are recorded.
No remote passwords, screen capture or typed text. NSSM stdout/stderr are disabled;
for startup configuration errors stop the service and run `node.exe server.mjs` in
an elevated console, then restart the service. Never share private/users.json.

Before coworkers use it:

1. Correct web/Router/Host login produces a desktop. Wrong passwords fail at the right layer.
2. Move/click/drag, scroll, key release on focus loss, Cyrillic text input, secure desktop/UAC.
3. Alice and Bob cannot obtain each other's session screen or send input, even with the other's ID.
4. Stop, disable account, close tab, unplug browser network and stop the service all end the Aspia session.
5. Existing Caddy downloads and Telegram webhook still work. No secrets are reachable as static files.
6. Try the actual agent browser. Agent actions are user-authorized and remain subject to its tool restrictions.

Implemented web tests cover ownership, CSRF/origin/host checks, path traversal,
allowlist revocation, account blocking, process/frame transport, abandoned sessions,
new-login revocation and secret-free audit using an isolated fake native worker.
CI additionally compiles the real worker and tests its PNG encoder and pipe shutdown.
No test claims a real remote Windows session without running one.

## Known limits / next work

Full PNG frames are fetched on demand (up to 5/s internally, browser about 4/s).
This prioritizes correctness/legibility for initial agent testing, not low-bandwidth smoothness.
No WebSocket/WebRTC, audio, camera, browser file clipboard, rich clipboard, disk/USB forwarding,
multi-monitor selector, automatic login or reconnect yet. Native Console/Host clipboard work
remains separate. An interrupted/slow browser request ends the session instead of reconnecting
with stored credentials. Admin monitoring covers this gateway only, not all native Aspia clients.

Updates: stop **AspiaWebGateway** only, retain `config.json`, `private` and `logs`, replace
program files from the next verified package and start it. Do not run Install-Gateway.ps1
again over an existing service. Removing the `/remote/` Caddy handlers and stopping this
service rolls back the prototype without changing Router/Relay/Host or download pages.

Build: `ASPIA_BUILD_WEB_BRIDGE=ON` with the existing Windows v142/Qt5 static toolchain;
target `aspia_web_bridge`. CI packages only x64, reusing the existing dependency cache.
The separate workflow does not rebuild the six clipboard MSI packages.

License: GPL-3.0-or-later, derived from Aspia. Preserve upstream notices and provide
the matching source commit/repository with distributed packages. Node and third-party
licenses are included alongside the executable.

Optional UI smoke test: install Playwright in a disposable development environment, with OpenSSL available, then run `node web-gateway/test/browser-smoke.mjs`. Set `PW_EXECUTABLE` if Chromium is outside Playwright's cache. It uses a loopback-only self-signed TLS endpoint with certificate checking disabled only for that test browser context and a fake native worker. It does not connect to a real Host. The author ran this test successfully for HTTPS login, cookie, rendered PNG, Unicode input, admin list, disconnect and logout.
