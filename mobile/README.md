# Aspia+ Mobile 2.7.2-mobile.14

Android-only follow-up to Mobile13. No changes to desktop Console, Host, Router or Relay.

- The accepted Samsung-style dot popup and its layout are preserved.
- Ё/Ъ use a full-sized, bordered popup on the surrounding window, with blue drag selection, explicit tap selection and no automatic letter on long-hold.
- HID/TXT/BUF: current mode highlighted; dragging highlights the actual target button before release.
- BUF is no longer a hidden draft. Selecting it explicitly requires acknowledgment of clipboard overwrite and the lack of a legacy clipboard ACK. Each typed character (or queued adjacent text batch) uses the existing clipboard protocol followed by a paced physical Ctrl+V, with a 650 ms settling delay and a 250 ms gap after release. No guaranteed nested-session synchronization is claimed. Clipboard disabled/unavailable: do not send a paste. Passwords and commands should not be entered in BUF.
- Physical shortcuts and special keys retain the existing queue. Pending clipboard actions are cancelled on app backgrounding, keyboard close, mode change, remote touch or session transition.
- KeyBar Paste uses the same clipboard path in BUF; HID and TXT retain their existing Unicode paste behavior.

Source candidate only; CI and real-device acceptance required. Successful CI does not prove clipboard delivery on original 2.7 Hosts. Signed APK not produced by this commit.

## Previous version
# Aspia+ Mobile 2.7.2-mobile.13 — Samsung-style key popups

Source candidate based on Mobile12, without changes to Windows components, Router, Relay or input transport.

- Dot short tap: period. Long hold: five columns and three row-heights, with two selectable rows separated by an empty middle row.
- Top row: `: ^ % $ #`; bottom row: `@ ' ! ? ,`. Colon replaces the Samsung pencil/customization icon. The comma cell is aligned directly above the period.
- Hold and slide, release over a symbol to choose it. The Mobile12 stationary hold/release shortcut for comma is retained; release outside the menu cancels.
- In Russian layout, long hold Е or Ь opens a visible popup showing ё/Ё or ъ/Ъ according to Shift. No automatic insertion. Slide onto the alternative or release on the original key and explicitly tap the visible choice. Short taps enter ordinary Е/Ь.
- Popups do not take focus, are dismissed by other keys, closing the keyboard or resizing. One-shot Shift is consumed only after an alternative letter is selected.
- HID/TXT/BUF, key bar, keyboard layout and existing transport code are unchanged.

Build uses `mobile/prepare-source.py` and `.github/workflows/mobile-v13-build.yml`.
The source checks and Android startup smoke test do not replace real-device testing.
No signed APK or stable release is implied by this source candidate.

## Previous base: Mobile12

# Aspia+ Mobile 2.7.2-mobile.12 — три режима ввода и удержание точки

**Экспериментальная Android-сборка**, основана на Mobile 11. Настольные
Host/Client/Console, Router и Relay и их протоколы не изменены.

### Нижний ряд Samsung-подобной клавиатуры

`!#1 | HID/TXT/BUF | ‹ Русский › | . | Enter`

- Небольшая клавиша **слева от пробела**, на месте запятой. **Удержание 500 мс**
  открывает меню HID/TXT/BUF; выбор отдельным нажатием на пункт или жестом
  удержать–сдвинуть–отпустить. **Короткое касание не меняет режим**.
  Клавиши и высота самой клавиатуры не увеличены.
- **HID** по умолчанию: упорядоченные физические USB скан-коды (тайминг 32+6 мс
  из Mobile 11). Реальный язык ввода определяется удалённой Windows/Linux.
  Для вложенных Aspia/RDP/AnyDesk это самый подходящий режим.
- **TXT**: символы отправляются через оригинальный `TextEvent`; не зависят
  от раскладки Windows, но могут игнорироваться вложенными удалёнными
  клиентами (Windows `VK_PACKET`).
- **BUF**: нажатия накапливают локальный черновик до 4096 символов.
  Короткое нажатие **BUF** при непустом черновике открывает подтверждение
  отправки черновика, **но не переключает режим**:
  «Передать в буфер» / «Удалить черновик» / «Продолжить набор».
  При подтверждении отправляется clipboard event по уже существующему
  каналу, **не автоматическое Ctrl+V**. После синхронизации пользователь
  сам нажимает Ctrl+V в нужной удалённой системе. Исходный буфер
  Windows/Android при синхронизации может быть перезаписан — об этом
  выдаётся явное предупреждение. Сохранность/восстановление старых
  форматов буфера не обещается. Для паролей этот режим не рекомендуется.
- **Точка**: короткое нажатие вводит `.`; удержание около 460 мс
  открывает панель частых символов, в том числе **запятую**.
  Можно вести палец над символами, отпустить для выбора. По умолчанию
  удержание и отпускание без движения выбирает запятую. Панель не
  перехватывает фокус и не вызывает системную клавиатуру.
- **Ё/Ъ**: старые удержания Е/Ь сохранены. В HID Ё использует USB usage
  `0x070035` (grave/tilde, слева от 1), Ъ — `0x070030` (right bracket).
  Реальный символ зависит от раскладки Windows/Linux.
- Настоящий Ctrl+C и Ctrl+V в нижней ленте по-прежнему работают с обычным
  буфером удалённой машины; команда «Вставить» отдельно читает Android
  буфер и использует `TextEvent`.
- Пиктограммы Shift/Backspace, трёхрежимный Shift, размер букв, масштаб,
  жесты и конфигурация Host остаются как в Mobile11.

### Ограничения и тестирование

Зелёный CI означает только успешную компиляцию, проверки исходников
и запуск в эмуляторе Android12. Реальный тест точного выбора запятой
при удержании, HID Ё/Ъ, BUF-синхронизации через вложенные терминалы
и сохранения обычного Ctrl+C обязателен перед стабильным релизом.

В репозитории остались релиз Preview25 (Windows + Mobile9), черновики
и проверенная подписанная Mobile11. Mobile12 в публичный релиз не
помещать до проверки пользователем.

Файл исходника Overlay: `mobile/mobile12-input-modes.py`.
GitHub Actions: `.github/workflows/mobile-v12-build.yml`.
