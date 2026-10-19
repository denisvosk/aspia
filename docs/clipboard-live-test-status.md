# Live clipboard investigation — preview.17 follow-up

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
