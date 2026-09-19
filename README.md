# 🎵 Beat Generator

Desktop-приложение для генерации и редактирования битов на основе пользовательских sample packs.

![BeatGenerator](https://github-production-user-asset-6210df.s3.amazonaws.com/90523142/655041058-bfdd1e46-3e67-4d17-ad2f-0cc7446f8f04.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAVCODYLSA53PQK4ZA%2F20260919%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20260919T053044Z&X-Amz-Expires=300&X-Amz-Signature=83c9a4d9eca017e6197eccc01fe2926a3dca7a4dcc7a08a5a9d6c326e66853b4&X-Amz-SignedHeaders=host&response-content-type=image%2Fpng)

## ✨ Возможности

* Генерация случайных drum patterns
* 16/32-step sequencer
* Kick, Snare, Clap, Hat, Open Hat и Perc
* Настройка BPM, density, complexity, swing и humanize
* Lock / mute / solo отдельных треков
* Drag & drop sample packs
* Прослушивание отдельных samples и готового паттерна
* Экспорт в **WAV** и **MIDI**
* Сохранение и загрузка пресетов в JSON
* Seed для воспроизводимой генерации

## 🛠 Стек

* Python 3
* PySide6
* NumPy

## 🚀 Запуск

```bash
git clone https://github.com/your-username/beat-generator.git
cd beat-generator

pip install -r requirements.txt
python main.py
```

После запуска выберите папку с drum samples через **Browse** или перетащите её в окно приложения.

## 📁 Структура проекта

```text
beat-generator/
├── core/              # Генерация, рендеринг и работа с samples
├── ui/                # PySide6 интерфейс
├── main.py            # Точка входа
├── requirements.txt
└── README.md
```

## 📄 License

MIT
