# Aspia+ — экспериментальные улучшения Aspia 2.7

**Aspia+ — независимая экспериментальная модификация [Aspia](https://github.com/dchapyshev/aspia).** Это не официальный выпуск авторов Aspia. Проект ориентирован на администраторов, у которых уже развёрнуты Router, Relay и Host линейки 2.7 и которым нужны дополнительные функции без обязательной миграции инфраструктуры.

Лицензия исходного проекта: GPL-3.0. Благодарность автору и участникам оригинальной Aspia.

## Что нового

### Aspia+ Mobile 2.7.2-mobile.8 — Android

- Подключение к существующей инфраструктуре Aspia 2.7 через прежний Router/Relay и Host (протокол удалённого управления не заменялся).
- Встроенная русско-английская клавиатура для ввода на удалённом Windows-компьютере, без верхней панели системной клавиатуры Android.
- Компоновка клавиш по образцу уменьшенной клавиатуры Samsung: обычный цифровой ряд 1–0, «ё» через удержание «е», «ъ» через удержание «ь», более удобные промежутки, широкая клавиша пробела.
- В альбомной ориентации клавиатура занимает около 75% ширины экрана и расположена по центру — клавиши не растягиваются на весь дисплей.
- Отдельная прокручиваемая функциональная лента: **ЛКМ** (с удержанием), **Клав.**, **Вставить**, Ctrl, Alt, Shift, Win, Esc и другие команды.
- Удалена кнопка «Впис.» с ленты, чтобы случайно не сбрасывать масштаб. Поворот доступен через меню с тремя точками.
- При тёмной системной теме надписи ленты светлые, вместо голубого акцентного цвета.
- Ввод Unicode, передача скопированного текста с Android в Windows командой «Вставить», масштабирование и перемещение удалённого изображения двумя пальцами.
- При открытой клавиатуре можно перемещать изображение и выводить нижнюю часть удалённого рабочего стола выше клавиатуры.
- Импорт локальной адресной книги .aab; не требуется публикация адресной книги в облаке.

**Требования:** Android 12+ (API 31), архитектура ARM64. **Статус:** предварительная тестовая версия. [Сборка № 45077247143](https://github.com/denisvosk/aspia/actions/runs/45077247143) прошла проверки исходников, упаковки APK и тест запуска на эмуляторе Android 12. Реальное удобство раскладки и длительная работа на телефонах разных производителей требуют проверки.

**Исходники:** ветка [feature/mobile8-samsung-keyboard](https://github.com/denisvosk/aspia/tree/feature/mobile8-samsung-keyboard), описание компонентов [mobile/README.md](https://github.com/denisvosk/aspia/blob/feature/mobile8-samsung-keyboard/mobile/README.md).

**Подписанный APK 2.7.2-mobile.8:** SHA-256 `2b368794cae7ec87115cad858cc29a128e37e2f873b6557e0da29e1e96b13d6a`; SHA-256 сертификата подписи `9cbb086bc631621623b99fc77957ccbd932ff4a83b7436c2d05d3e9e4891a71c`. Сверяйте эти значения с файлом, полученным от сопровождающего проекта. Артефакт из GitHub Actions — **неподписанный** и не заменяет установочный APK.

### Aspia+ 2.7.2 — Windows, sessions & inventory preview

В предварительной ветке Windows выпускаются **Host, Client, Console и Router** для x86 и x64. Добавлены экспериментальные улучшения учёта сеансов и инвентаризации. Автоматические сборочные, протокольные и MSI-проверки preview.25 прошли; интерактивное тестирование на нескольких реальных компьютерах для отдельных функций ещё требуется.

Существующая инфраструктура Relay 2.7 при подготовке Windows preview не изменялась. Не обновляйте сразу весь парк: сначала протестируйте на отдельных компьютерах, сохранив резервные копии настроек и ключей.

## Где скачать

Публичные выпуски появятся на странице [GitHub Releases](https://github.com/denisvosk/aspia/releases) после публикации сопровождающим проекта. Если сейчас там пусто, это означает, что установочные файлы пока находятся в **Draft** (черновиках). Черновики не доступны обычным посетителям.

[GitHub Actions](https://github.com/denisvosk/aspia/actions) хранит проверочные сборочные артефакты ограниченное время; не путайте их с подписанными публичными релизами.

## English summary

**Aspia+ is an unofficial experimental Aspia fork**, intended for administrators keeping their existing Aspia 2.7 Router/Relay/Host infrastructure.

- **Mobile 8:** Android 12+ ARM64, app-local RU/EN remote keyboard, narrower centered landscape layout, remote paste from the phone, touch zoom/pan and a scrollable control strip.
- **Windows 2.7.2 preview:** x86/x64 Host, Client, Console and Router builds with experimental session and inventory improvements; real-world acceptance testing is ongoing.
- **Downloads:** see the [Releases page](https://github.com/denisvosk/aspia/releases) after the maintainer publishes a prerelease. GitHub Actions artifacts may be unsigned.

Use only builds from a trusted source. Never share your Aspia private connection keys or Android APK signing keystore.
