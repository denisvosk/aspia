#!/usr/bin/env python3
"""Source-level regression guard for the native Android Aspia book picker.

This test does not access user books, settings, servers or credentials.
"""
from pathlib import Path
import re
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('Usage: test_document_picker.py /restored/source/client/android/mobile_book_manager.cc')
    source = Path(sys.argv[1]).read_text(encoding='utf-8')
    m = re.search(r'void MobileBookManager::importFile\(\).*?\n\}', source, re.S)
    assert m, 'Import method missing'
    method = m.group(0)
    picker = re.search(r'#ifdef\s+Q_OS_ANDROID(?P<android>.*?)#else(?P<desktop>.*?)#endif', method, re.S)
    assert picker, 'Missing Android-specific MIME picker'
    android = re.sub(r'//[^\n]*', '', picker['android'])
    assert 'setMimeTypeFilters({ QStringLiteral("application/octet-stream") })' in android, 'Android must use all-files MIME filter'
    assert '*.aab' not in android, 'No extension-only filter allowed on Android'
    assert 'QFileDialog::ExistingFile' in android, 'Must select an existing file'
    assert 'picker.exec() != QDialog::Accepted' in android, 'Cancel handling missing'
    assert 'picker.selectedFiles().value(0)' in android, 'Selected URI/file path unused'
    assert 'Книга Aspia (*.aab)' in picker['desktop'], 'Desktop filter changed'
    assert 'AabImporter::kMaxFileSize + 1' in method, 'Bounded read removed'
    assert 'file.atEnd()' in method, 'End-of-file guard removed'
    assert 'QFile file(path)' in method, 'QFile content access removed'
    decoder = re.search(r'bool MobileBookManager::importData\(.*?\n\}', source, re.S)
    assert decoder, 'Import decoder method missing'
    assert 'AabImporter::read(bytes, *password, &book)' in decoder.group(0), 'File content validation removed'
    assert 'AabImporter::replace(Database::instance(), book)' in decoder.group(0), 'Transactional replacement removed'
    print('PASS: Android MIME document picker and bounded, validated AAB import')


if __name__ == '__main__':
    main()
