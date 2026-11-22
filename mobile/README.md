# Aspia+ Mobile 2.7.2-mobile.4 — Android .aab picker fix

Mobile.3 starts successfully on Android 12 but Samsung One UI's native document
picker can grey out a valid `.aab` file. Qt's Android picker translates the
original `*.aab` name filter into MIME types, but `.aab` has no registered
Android MIME type. This blocks selection before the file decoder runs.

Mobile.4 uses Qt's documented `application/octet-stream` all-files MIME filter
for Android, still only permits existing files, and validates the actual AAB
content, size and password before transactionally replacing the local book.
The desktop `*.aab` filter remains unchanged. The server-book download feature
is not enabled. Router/Relay/Host 2.7 and signing identity are unchanged.

The exact v3.0.37 upstream, patches, overlay, and newly added picker patch are
SHA-256 pinned in `source-lock.json`. Recreate sources with:

```sh
python3 mobile/prepare-source.py --output ../aspia-mobile-src
```

Build / Android 12 startup CI: `.github/workflows/mobile-v4-build.yml`.
Source-regression guard: `mobile/test_document_picker.py`.
A passing startup test does *not* prove interaction with the Android document
picker, Samsung-specific behavior, book decryption or remote connections.
Those require physical-device verification before declaring the feature fixed.

Previous mobile.3 release notes: see Git history and run
https://github.com/denisvosk/aspia/actions/runs/44962292397
