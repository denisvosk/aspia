# Live clipboard investigation — 2026-10-18 23:31 UTC

User installed preview.17: Host and Console both report 2.7.1. Text copies in
both directions. Copying a file makes Paste available on the opposite desktop,
but pasting creates no file, in either direction. User has fallback RDP.
This establishes that the advertised file formats reach the destination, but
does not yet prove the FILECONTENTS/GetData/IStream request succeeds.

Compared the local upstream checkout (tag v3.1.1) files:
`common/win/file_object.cc`, `common/win/file_stream.cc`,
`common/clipboard_win.cc`, `common/clipboard_file_transfer.*`.
Upstream uses FILEGROUPDESCRIPTORW / FILECONTENTS / IStream with a separate
logical CHANNEL_ID_FILE for chunks. Our 2.7 implementation is a separate
compatibility implementation using ClipboardEvent on the existing session
channel; it is not a literal backport. Logical channel IDs alone do not imply
separate TCP ports.

No root cause has yet been demonstrated. Existing tests perform synchronous
in-process OLE stream reads and do not establish live Explorer cross-process
behavior or asynchronous network callback delivery. Do not call preview.17
production ready and do not enable the update feed.

`ops/update-server/host/Test-AspiaClipboard.ps1` probes the installed build from
a separate Windows process: descriptor query/read, contents query/read, stream
Stat and first-byte Read. It prints HRESULTs, counts and size, never file content,
and changes neither settings nor clipboard contents. Run on the destination,
wait at its prompt, then copy one nonempty regular file on the source and press
Enter in the probe. This avoids replacing the copied file with the launch command.
It uses the existing MSI; no binary rebuild was launched for this diagnostic.

Next: inspect the user's output to identify the failing COM call, then reproduce
that call with a Windows regression test before changing/rebuilding binaries.
