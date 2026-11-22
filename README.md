# Aspia+ — неофициальная ветка Aspia 2.7

**Этот репозиторий — независимая экспериментальная модификация [оригинальной Aspia](https://github.com/dchapyshev/aspia), а не официальный релиз её авторов.**

Улучшения по сравнению с Aspia 2.7:

- **Журнал подключений** с учётными записями Router/Host, временем сеансов и CSV-экспортом.
- **Инвентаризация парка ПК**: новый Host отправляет аппаратные сводки, Console готовит HTML/CSV-отчёт.
- **Файлы и папки через Ctrl+C / Ctrl+V** между двумя Windows-машинами в обе стороны; расширенный обмен форматированным текстом и изображениями.
- **Aspia+ Mobile для Android 12+** с подключением к инфраструктуре Router/Relay/Host 2.7, русско-английской клавиатурой и прокручиваемой лентой команд.

**[Описание улучшений, ограничений и статуса сборок](ASPIA_PLUS_RELEASE_NOTES.md)** · [Версия Windows Preview](https://github.com/denisvosk/aspia/tree/feature/audit-inventory-2.7.2) · [Android Mobile 8](https://github.com/denisvosk/aspia/tree/feature/mobile8-samsung-keyboard) · [Releases](https://github.com/denisvosk/aspia/releases)

**Важно:** автоматические проверки не заменяют тестирование на реальных машинах. Черновики Releases (Draft) не видны посетителям GitHub. Старый раздел README ниже сохранён для описания оригинального проекта.

---

Aspia
=====
Remote desktop, file transfer and system information tool.

With Aspia, you can create your own NAT traversal infrastructure (using Router and Relay servers) with connection by ID or use direct connections. Aspia supports many features. Among them, detailed information about the system, audio, text chat.

|Build Status|
|:--:|
|[![Build status](https://github.com/dchapyshev/aspia/actions/workflows/windows.yml/badge.svg?branch=master)](https://github.com/dchapyshev/aspia/actions/workflows/windows.yml) [![Build status](https://github.com/dchapyshev/aspia/actions/workflows/linux.yml/badge.svg?branch=master)](https://github.com/dchapyshev/aspia/actions/workflows/linux.yml) [![Build status](https://github.com/dchapyshev/aspia/actions/workflows/macos.yml/badge.svg?branch=master)](https://github.com/dchapyshev/aspia/actions/workflows/macos.yml)|

Currently supported
-------------------
- Remote desktop management
- Remote desktop view
- File transfer
- System information
- Text chat
- Task manager
- Encryption
- Authorization (it is possible to add users with different access rights)
- Address book with encryption and master-password
- <b>NAT traversal with connection by ID</b> (with using Aspia Router and Aspia Relay)
- Direct connections
- Audio support
- Video recording
- Client and Console for Windows, MacOSX and Linux
- Host for Windows only
- Router/Relay for Windows and Linux
- And much more

System requirements
-------------------
- Windows 7/2008 R2 or higher (x86 or x86_64 CPU)
- Debian 11/Ubuntu 20.04 Linux (x86_64 CPU)
- MacOSX (x86_64 or ARM64 CPU)

Contacts
--------
E-Mail: dmitry@aspia.ru

Group in Telegram: [@aspia_talks](https://t.me/aspia_talks)

News in Telegram: [@aspia_news](https://t.me/aspia_news)

Licensing
---------
Project code is available under the GNU General Public License 3.

For more information, see [license agreement](LICENSE.md).

See also
--------
- [Documentation](https://aspia.org/documentation.html)
- [Instructions for building the project (Windows)](https://aspia.org/docs/building-windows)
- [Instructions for building the project (Linux)](https://aspia.org/docs/building-linux)
- [Instructions for building the project (MacOSX)](https://aspia.org/docs/building-macos)
- [Instructions for translators](https://aspia.org/docs/translators)
- [Code of conduct](CODE_OF_CONDUCT.md)
