# Live clipboard investigation — transfer works; Explorer responsiveness follow-up

## Live result, 2026-10-19

After the interactive-user ownership fix (remote commit e4f8da38, Windows run
39178214773, both architectures successful), the user confirmed files AND folders
copy in both directions. The separate-process probe successfully obtained a
95744-byte stream and read a byte. QueryGetData still reported DV_E_FORMATETC,
but GetData and actual paste succeeded; that advisory query is not the blocker.

Remaining behavior: pasting a folder shows no progress and blocks the destination
Explorer window throughout copying. A large individual file shows the legacy
Windows progress dialog with Cancel, but its destination Explorer window is also
unresponsive/cannot be dragged. The screenshot is consistent with modal Shell
copying; it does not establish that the whole explorer.exe process is hung.

## Current change and acceptance still needed

Expose IDataObjectAsyncCapability (the original IAsyncOperation IID) and enable
it before OleSetClipboard. Explorer can negotiate background extraction. Keep
all object/stream calls marshaled to the existing clipboard STA; do not mark the
single-threaded protocol engine agile or add new network threads/ports. Hold the
data object through StartOperation/EndOperation. Releasing unfinished streams
retains the existing CANCEL behavior and keeps the offer available for repaste.

Set FD_PROGRESSUI on directory descriptors too; it was previously set only on
regular files, including in the inspected upstream 3.1.1 implementation.
Do not invent folder byte sizes or add an unrelated Aspia progress window.

Extend the Windows OLE tests to check folder/file progress flags, asynchronous
negotiation, completion, cancellation and repaste. A separate Windows PowerShell
5.1 process tests reading a folder child on a background STA with asynchronous
negotiation. These check the provider contract, not Explorer UI responsiveness.
Local Linux validation covers PowerShell parsing and embedded C# compilation.
Actual Windows compilation/COM tests run in Actions.

After the new build, use the home test PC/RDP fallback to verify BOTH directions:
large file, folder with the same large file, and a folder with many small files.
Check that the destination Explorer window can be moved/navigated while copying,
that progress appears, Cancel stops the transfer, and a subsequent paste works.
This remains a candidate fix until those live checks pass. No production rollout.

The same candidate also adds negotiated rich Windows clipboard content: RTF,
complete CF_HTML and PNG/DIB, atomically with the legacy text fallback. Optional
ClipboardEvent field 3 holds formats; DesktopConfig field 8 enables them after
rich_clipboard_v1 capability discovery. No existing field numbers change. Old
peers receive text only. Rich text does not require file-transfer permission.
It uses the existing desktop clipboard path; file streams remain in the user UI.
Payloads have 4 MiB wire / 16 MiB decoded limits and 64 MiB decoded image bounds.
Clipboard/ZSTD bounds, format-only changes and atomic text fallback are covered
by platform-independent tests. Windows tests cover CF_HTML style retention, RTF
binary payloads, embedded-picture preference, PNG/DIB and invalid input.
Word/Word and Paint tests on two machines remain outstanding; no claim of exact
Office fidelity or Explorer responsiveness is made from those unit tests alone.

References:
- https://learn.microsoft.com/en-us/windows/win32/api/shldisp/nn-shldisp-idataobjectasynccapability
- https://learn.microsoft.com/en-us/windows/win32/shell/datascenarios#dragging-and-dropping-shell-objects-asynchronously
- https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/ns-shlobj_core-filedescriptorw

## Earlier preview.17 investigation

User installed preview.17: Host and Console both report 2.7.1. Text copies in
both directions. Copying a file enables Paste, but pasting creates no file.
Fallback RDP is available on the home test machine. No production rollout.

The separate-process probe now runs (the ambiguous C# STATSTG name is fixed).
Observed: OleInitialize/OleGetClipboard/descriptor QueryGetData/GetData succeed,
FILEGROUPDESCRIPTOR contains one entry, but FILECONTENTS QueryGetData and GetData
return 0x80040064 (DV_E_FORMATETC). No network content read is reached.

## Candidate cause and change

Upstream checkout v3.1.1 owns Host clipboard in the interactive UI process
(source/host/ui/host_window.cc), whereas preview.17 owns it in the SYSTEM desktop
agent. A firsthand Windows report describes the same descriptor-success /
FileContents-0x80040064 failure across SYSTEM/user COM boundaries:
https://learn.microsoft.com/en-us/answers/questions/1168537/oleclipboard-and-idataobject-under-local-system-ac
This is a strong hypothesis, not a reproduced proof of the user's root cause.

Move only Host file clipboard ownership into the existing interactive Host UI
UserSessionAgent. Service forwards file events over authenticated existing UI IPC.
Keep session negotiation, clipboard/file-transfer permission gates, peer IDs,
path validation and disconnect invalidation. Reissue negotiation on UI reconnect.
Invalidate UI file streams on pause/lock/secure desktop; resume on normal desktop.
Plain text remains in the desktop agent. No global COM security relaxation,
new TCP ports, Router/Relay changes or update-feed publication.

The transport remains our 2.7-compatible implementation over ClipboardEvent;
it is not a literal 3.x backport. Upstream uses a separate logical file channel.

## Validation and next step

Added a Windows OLE regression that publishes a virtual file and asks a separate
Windows PowerShell 5.1 process to query the descriptor and stream, Stat and read
an expected byte. Parent STA pumps COM messages; child has a bounded timeout.
This covers cross-process OLE in one user identity, not the full installed Host
service/user-IPC/network path. Existing protocol and same-process tests remain.

Allow same-version MSI replacement for Host, Client and Console previews.
Host CI checks both original 2.7.0 -> current and preview.17 -> current 2.7.1,
configuration preservation, running service, and installed executable hashes.
AllowSameVersionUpgrades also allows installing an older 2.7.1 preview; use the
intended new preview and verify its workflow, not merely the displayed version.

Local Linux checks: PowerShell parser for changed scripts, embedded C# compile,
git diff whitespace check. Windows compilation/COM/MSI tests must run in Actions.
After success, test one ordinary nonempty file both directions on the home PC
using RDP fallback, then folder/large-file/disconnect behavior before rollout.
If still failing, repeat the probe to distinguish COM access from stream timeout.
