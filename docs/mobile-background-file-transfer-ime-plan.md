# Aspia+ Mobile: фоновые сеансы, обмен файлами и системная Samsung IME

Дата исследования: 2026-11-23. Это **проектирование**, а не уже реализованные функции. Основа — исходники Aspia 2.7, upstream v3.0.37 / v3.4.3 и Android 12+.

## 1. Почему сеанс сохраняется при блокировке телефона

В исходном Android-клиенте есть `SessionKeeperAndroid` и
`SessionKeeperService.java` — foreground service с уведомлением
`Remote session is active`, специально предназначенная для удержания
процесса при уходе приложения в фон. `DesktopWindow` делает
`session_keeper_->acquire()` после подключения и `release()` при
отключении. `onApplicationStateChanged()` не закрывает рабочий сеанс;
она только пытается восстановить пропавшую связь при возврате.

Ссылка на upstream:
- https://github.com/dchapyshev/aspia/blob/v3.0.37/source/client/android/session_keeper_android.cc
- https://github.com/dchapyshev/aspia/blob/v3.0.37/source/client/android/packaging/src/org/aspia/client/SessionKeeperService.java
- https://github.com/dchapyshev/aspia/blob/v3.0.37/source/client/android/desktop_window.cc

Это полезно для длительных передач файлов, но при просмотре рабочего стола
может впустую расходовать трафик и оставлять забытое удалённое подключение.

### Предлагаемое поведение по умолчанию

1. При `ACTION_SCREEN_OFF` (устройство переходит в неинтерактивное состояние):
   **отключить desktop-сеанс**, остановить video/network workers и
   `SessionKeeper`. Не закрывать всю программу, не стирать адресную книгу.
2. При уходе с экрана Aspia+ в другое приложение / входящем звонке:
   **сразу приостановить поток изображения**, а по истечении, например,
   15 секунд в фоне — полностью завершить desktop-сеанс. При быстром
   возврате до порога можно продолжить текущий сеанс без повторного входа.
3. При повторном входе после отключения: открывать адресную книгу и показывать
   «Подключение завершено при блокировке/сворачивании». **Без тихого
   автоматического переподключения**. Для новой сессии нужна явная команда.
4. Не отключаться от кратковременной биометрической системной панели:
   `Qt::ApplicationInactive` не тождественен экрану, выключенному
   кнопкой питания. Использовать Android `ACTION_SCREEN_OFF`
   (динамическая регистрация `BroadcastReceiver`) и
   `PowerManager.isInteractive()`; для обычного background — отдельный
   отложенный таймер. Проверять `WindowDeactivate`, foreground switch,
   звонок, системный диалог выбора файлов, запрос биометрии.
5. Отдельный тайм-аут **бездействия при включённом экране** можно сделать
   настраиваемым (например, «никогда / 5 / 10 / 30 мин»). Не путать с уходом
   Android в фон.
6. Команда «Закрыть сеанс» должна быть идемпотентной; закрытие
   `DesktopWindow` и уничтожение `WorkerManager` должно освобождать
   видео, канал, мышиные кнопки и SessionKeeper. Подключение к Router/Relay
   заново только по запросу пользователя.

Важно: Android broadcast `ACTION_SCREEN_OFF` нельзя получать через
manifest-declared receiver; только регистрация в работающем компоненте.
https://developer.android.com/reference/android/content/Intent#ACTION_SCREEN_OFF

Реализация TeamViewer не гарантирует такого поведения: в TeamViewer Classic
описан **настраиваемый тайм-аут неактивного сеанса на Windows**, а не
обязательный Android disconnect-on-lock.
https://www.teamviewer.com/en/global/support/knowledge-base/teamviewer-classic/remote-control/out-of-session-features/time-out-inactive-sessions/

## 2. Отдельная передача файлов Android ⇄ Host 2.7

**Уже имеется** UI в upstream v3.0.37:
- `source/client/android/file_transfer_window.{h,cc}`
- `source/client/android/file_panel_widget.{h,cc}`
- `source/client/android/file_progress_sheet.{h,cc}`
- `source/client/file_transfer.{h,cc}`
- `source/common/file_platform_util_android.cc`

В ней локальная панель «This Device», удалённая панель Host, отправка в
обе стороны, фоновые worker и индикатор прогресса. Однако в нашем
`mobile/aspia-mobile-2.7.2.patch` метод
`AndroidMainWindow::openSession()` намеренно отсеивает
`session_type != SESSION_TYPE_DESKTOP`. Прямое снятие этого запрета
не является завершённой реализацией для Host 2.7.

**Почему нужен адаптер:** в Aspia 2.7 транспорт файлов использует
`proto::FileRequest/FileReply` из пакета `proto`, а в v3.0.37
`proto::file_transfer::Request/Reply` с `request_id` и расширениями
драйв-листа. Номера значительной части Protobuf-полей совпадают,
но нужно проверить несовпадения, корреляцию запросов и legacy
session/channel framing. Нельзя утверждать, что UI v3 работает с
Host 2.7 без новой интеграции и межкомпьютерных тестов.

Предлагаемая реализация:
1. Добавить `LegacyFileTransferAdapter` для отдельного сеанса обмена
   файлами Aspia 2.7 через существующий Router/Relay, не меняя
   установленные Host. Сохранять аутентификацию и право передачи файлов.
2. Показать в меню компьютера «Файлы» (Android ⇄ Windows). На первом этапе
   использовать существующий двухпанельный экран; необязательно встраивать
   файлы в desktop-буфер Android, так как clipboard URI и Windows Explorer
   clipboard — разные механизмы.
3. Выбор файлов на телефоне через **Storage Access Framework**:
   `ACTION_OPEN_DOCUMENT` и `ACTION_OPEN_DOCUMENT_TREE`, потоковый
   `ContentResolver`; не запрашивать полный доступ ко всему хранилищу
   телефона без реальной необходимости. На Android 11+ есть ограничения
   для корня памяти, Downloads в tree-picker, Android/data и Android/obb:
   https://developer.android.com/training/data-storage/shared/documents-files
4. Передавать файлы блоками, с отменой, отображением скорости/прогресса,
   проверкой коллизий имен, защитой путей и корректной обработкой обрыва.
   Не считать докачку и целостность доказанными, пока нет end-to-end тестов.
5. **Только когда пользователь явно запустил передачу:** разрешить
   background/lock до окончания файла, показать Android foreground
   notification с прогрессом и «Отменить». После окончания — завершить
   файловый сеанс и сервис. Когда активных передач нет, не держать
   соединение в фоне. Для Android 14+ учитывать ограничения User Initiated
   Data Transfer Job / Foreground Service.
   https://developer.android.com/develop/background-work/background-tasks/data-transfer-options

Тесты: телефон→Windows, Windows→телефон, русский путь/имя, пустой файл,
большая папка, разрешение denied, переподключение, отмена и блокировка
телефона во время передачи.

## 3. Системная клавиатура Samsung без панели инструментов

Это **возможно настройкой самой Samsung Keyboard**:
Android/Samsung: **Настройки → Общие настройки → Настройки клавиатуры
Samsung → Панель инструментов клавиатуры → Выкл.**
Официальная инструкция:
https://www.samsung.com/us/support/answer/ANS10001592/

Этот переключатель — системная настройка пользователя и влияет на все
приложения, использующие Samsung IME. Публичного стандартного Android
приложенческого API для гарантированного скрытия именно Samsung Toolbar
**только в Aspia+** нет; стороннее приложение не должно менять
настройки чужого IME без пользователя. `TYPE_TEXT_FLAG_NO_SUGGESTIONS`
в `EditorInfo` может повлиять на подсказки, но не гарантирует
отключения OEM-панели с эмодзи/микрофоном.
https://developer.android.com/reference/android/view/inputmethod/EditorInfo

Предлагаемое развитие:
- Выбор в Aspia+ **«Клавиатура Samsung (системная)»** и
  **«Встроенная Aspia+»**. В системном режиме Qt показывает IME и сохраняет
  навигационную KeyBar отдельно от неё.
- **Не возвращать старую отправку только `TextEvent`**: Android
  `inputMethodEvent()` обычно получает Unicode/композицию, а Windows
  Host вводит это через `KEYEVENTF_UNICODE` (VK_PACKET), который
  вложенная Aspia/Qt может не обрабатывать как физическую клавишу.
  Для отдельных символов конвертировать committed text в
  упорядоченные USB скан-коды с видимым интервалом нажатия.
- Держать отдельный Unicode-режим для «Вставить» и неподдерживаемых
  символов. Композицию, автозамену, удаление и русский/английский ввод
  тестировать на реальном Samsung. При USB-нажатиях языковая раскладка
  выбирается Windows, и стандартный Host 2.7 не сообщает её телефону.
- НЕ утверждать, что свайп языка на Samsung автоматически меняет
  раскладку вложенной Windows. Для этого нужна дополнительная
  синхронизация или осознанная ручная настройка удалённой раскладки.

## 4. Приоритет

Сначала улучшить **политику фоновых desktop-сеансов** (не трогая
файловую службу), затем добавить опциональный системный IME/тест
двух последовательных Aspia, затем отдельный Legacy File Transfer.
Изменения должны выходить отдельными preview со стабильным rollback,
не заменяя публичные Host/Router и не заставляя переходить на 3.x.
