# Диагностика запуска Aspia+ Mobile

Сначала нужен журнал падения установленной сборки. Для Logcat достаточно
обычного подписанного APK; пересобирать его или удалять приложение не нужно.
Успешная компиляция и проверка подписи не подтверждают запуск на телефоне.

## Windows: собрать журнал одним скриптом

1. В Android Studio откройте **SDK Manager → SDK Tools** и установите
   **Android SDK Platform-Tools**.
2. На телефоне включите «Для разработчиков → Отладка по USB», подключите USB
   и подтвердите запрос разрешения отладки на самом телефоне.
3. Сохраните рядом `Collect-Mobile-Startup.ps1` и запустите в PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Temp\Collect-Mobile-Startup.ps1" -OutputDirectory "C:\Temp\Aspia-Diagnostics"
```

Скрипт ищет ADB в `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`,
затем в PATH. Если SDK находится в другом месте:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Temp\Collect-Mobile-Startup.ps1" -AdbPath "D:\Android\Sdk\platform-tools\adb.exe" -OutputDirectory "C:\Temp\Aspia-Diagnostics"
```

Если одновременно подключены телефон и эмулятор, укажите нужный serial из
вывода `adb devices` параметром `-Serial "SERIAL"`. Используется приложение
текущего пользователя Android. Устройство должно иметь статус `device`;
при `unauthorized` подтвердите запрос на телефоне.

Сценарий принудительно останавливает и снова запускает **только Aspia+ Mobile**,
ждёт 15 секунд и создаёт новую папку `Aspia-startup-...` внутри указанной.
В течение этих секунд не разблокируйте приложение, не импортируйте книгу
и не запускайте подключение: нужен именно старт. Время можно изменить,
например `-Seconds 30`.

Получатся:

| Файл | Что содержит |
| --- | --- |
| `device-and-app.json` | Модель телефона, Android/API, ABI, размер страницы памяти, версия APK и результат проверки процесса |
| `launch.txt` | Ответ Android на запуск Activity |
| `startup-logcat.txt` | Записи UID приложения за время запуска, даже если процесс уже завершился |
| `crash.txt` | Полные Java/native блоки падения, в которых назван процесс Aspia+ Mobile |

При отказе Android предоставить журнал появится файл с суффиксом `-error`.
Отсутствие блока в `crash.txt` само по себе не означает успешный запуск.
Эти четыре файла позволяют продолжить диагностику; сама книга `.aab` не нужна.

Скрипт совместим с Windows PowerShell 5.1. Он не очищает данные приложения
и Logcat, не переустанавливает APK, не читает книгу или базу и ничего никуда
не отправляет. Основной журнал фильтруется по UID. Буфер native-падений
просматривается за тот же короткий интервал; в файл записываются только
блоки с именем процесса Aspia+ Mobile, а не общий журнал других приложений.

## Android Studio: посмотреть причину вручную

Откройте **View → Tool Windows → Logcat**, выберите подключённый телефон
или запущенный виртуальный телефон и задайте фильтр:

```text
package:org.aspiaplus.client
```

Затем запустите Aspia+ Mobile. Нужен первый `FATAL EXCEPTION`,
`UnsatisfiedLinkError`, `Abort message` или native stack, включая строки
`Caused by`. Не ограничивайте просмотр только PID: при мгновенном вылете
процесс уже может исчезнуть из списка. Скрипт выше также подбирает native
блоки от `crash_dump`, которые могут не попасть в фильтр пакета Android Studio.

Документация Android: [Logcat в Android Studio](https://developer.android.com/studio/debug/logcat)
и [командная строка Logcat](https://developer.android.com/tools/logcat).

## Локальная сборка и Android Studio

Это приложение на **C++/Qt**, собираемое CMake, с Android-оболочкой на Java.
Корень Aspia+ содержит пакет патчей; открыть его как обычный Gradle-проект
и нажать Run недостаточно. Сначала восстанавливается полное дерево исходников,
затем CMake собирает native-библиотеки, а Qt создаёт Gradle-проект и APK.

Для чтения исходников без скачивания submodule-зависимостей, из корня этой ветки:

```powershell
py -3 mobile\prepare-source.py --output C:\Aspia\mobile-src --no-submodules
```

Выберите новый или пустой каталог: сценарий сохраняет существующие файлы и
останавливается, если каталог непустой. `--no-submodules` подходит для чтения
и поиска ошибки; для полной сборки требуются зависимости vcpkg.

Проверенная последовательность сборки этой версии находится в
[`.github/workflows/mobile-v2-build.yml`](../.github/workflows/mobile-v2-build.yml).
Её среда — Linux/Ubuntu, JDK 21, CMake 3.30–3.x, Ninja, Qt 6.11.1 для хоста
и Android ARM64, SDK 36, Build Tools 36.0.0, NDK 27.2.12479018 и OpenSSL из
`ci/build-android-openssl.sh`. Если Windows — основной компьютер, эту
последовательность можно воспроизвести в отдельной среде Ubuntu/WSL2;
ADB и Android Studio при этом удобно оставить в Windows. Подключение USB
к WSL для получения Logcat не требуется.

После сборки Gradle-проект находится в восстановленном дереве:

```text
builds/mobile-android-linux/source/client/android-build
```

Он полезен для просмотра Android-оболочки в Studio. Его Gradle-задачи сами
по себе не заменяют сборку C++ через CMake: изменения в native-коде необходимо
сначала пересобрать соответствующим preset. Сгенерированные пути относятся
к среде сборки, поэтому перенос этого каталога из Linux в Windows не создаёт
готовую Windows-конфигурацию.

Для расшифровки native stack нужны неурезанные `.so`/символы **точно той же
сборки**, что упала. Чтобы интерактивно подключать native debugger, требуется
отладочная конфигурация APK; для обычного Logcat это не требуется. Если
приложение уже установлено, обновление с сохранением данных должно иметь
тот же application ID, допустимый versionCode и тот же сертификат подписи.
Случайная подпись стандартным debug-ключом не заменяет ключ релиза.

Документация Qt: [androiddeployqt](https://doc.qt.io/qt-6/android-deploy-qt-tool.html)
и [каталог Android-оболочки](https://doc.qt.io/qt-6/cmake-target-property-qt-android-package-source-dir.html).

## Виртуальные телефоны

Текущий APK содержит `arm64-v8a`. Обычный образ эмулятора `x86_64` подходит
только при рабочей трансляции ARM64; иначе нужна сборка под `x86_64` или
совместимый ARM64-образ. `INSTALL_FAILED_NO_MATCHING_ABIS` означает
несовместимость архитектур и не является воспроизведением падения приложения.
Проверяйте ABI устройства в `device-and-app.json`.

Для первого запуска достаточно пустого приложения. Импорт книги и доступ
к рабочему Router для выяснения причины стартового вылета не нужны.
