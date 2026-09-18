# Beat Generator — Desktop Prototype

Полноценный desktop-прототип генератора битов на **Python + PySide6**.

## Возможности

- Drag & drop / Browse sample-pack папки
- Автоматический сканер и классификация WAV (kick / snare / hat / open_hat / clap / perc)
- 16- и 32-step sequencer с визуальной сеткой
- Generate / Regenerate
- **Lock** отдельных дорожек (при regenerate locked-треки сохраняются)
- **Lock** выбранного sample на каждой дорожке
- **Random Samples** — случайный выбор sample для всех дорожек; locked sample не меняется
- Mute / Solo
- Параметры: BPM, Density, Complexity, Swing, Humanize, Bars, Seed
- Выбор конкретного sample на дорожку (или Auto)
- Клик по ячейке sequencer — ручное вкл/выкл хита
- Прослушивание (sounddevice или Qt Multimedia)
- Export WAV (24-bit) и MIDI
- Save / Load пресетов (JSON)
- Seed для воспроизводимых результатов

## Архитектура (готово к портированию в C++/JUCE)

```
beat_generator/
  core/                 ← pure Python, zero UI deps
    types.py            SampleType, Event, Settings, TrackState, Pattern
    scanner.py          classify + scan_samples
    generator.py        generate_pattern (seed, lock support)
    renderer.py         render → numpy, write_wav, write_midi
    preset.py           JSON save/load
  ui/                   ← только Qt
    main_window.py
    sequencer.py
    audio_player.py
  main.py
```

Логика генерации, классификации и рендера полностью изолирована от UI.
При переносе в JUCE достаточно переписать `core/` на C++ (те же структуры данных),
а UI — на JUCE components. Музыкальные правила и seed-детерминизм остаются.

## Быстрый старт

```bash
cd beat_generator
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

### Демо-семплы (синтетика)

Если нет своего pack:

```bash
python generate_example_pack.py
# затем в UI укажи папку ./samples
```

## Структура sample pack

```
samples/
  kick/
  snare/
  hat/
  open_hat/
  clap/
  perc/
```

Или любые WAV в одной папке — классификация по имени файла:
`kick_01.wav`, `snare_03.wav`, `closed_hat.wav`, `open_hat.wav`, …

## Пресеты

JSON содержит:
- все generation-параметры + seed
- lock / mute / solo по дорожкам
- forced sample paths
- путь к sample pack (если был)

## Дальнейший путь к VST3

1. Оставить `core/` как reference implementation.
2. Портировать типы и `generate_pattern` / `render` в C++.
3. JUCE AudioProcessor + custom editor вместо PySide6.
4. Seed + lock semantics уже совпадают — результаты будут идентичны.


## Сборка Windows EXE

На Windows с установленным Python 3.13 запусти:

```bat
build_exe.bat
```

Скрипт автоматически:
1. создаст `.venv`;
2. установит зависимости;
3. установит PyInstaller;
4. соберёт приложение с `icon.ico`;
5. создаст portable-папку `dist\BeatGenerator\`.

Главный файл:

```text
dist\BeatGenerator\BeatGenerator.exe
```

Для переноса на другой Windows-ПК копируй **всю папку `dist\BeatGenerator`**, а не только `.exe`.
## Windows EXE build

On Windows run `build_exe.bat`. The script creates `.venv`, installs dependencies including Pillow and PyInstaller, and builds a portable application in `dist\BeatGenerator\BeatGenerator.exe`.

The project icon is a real multi-size Windows `.ico`.

### Sample locks

Each track has a sample lock button next to the sample selector. A locked sample is preserved by **Random Samples**. If a track has no concrete sample selected when locking, one is selected automatically.

**Random Samples** assigns a different random concrete sample to every unlocked track.

