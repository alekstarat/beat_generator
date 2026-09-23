# 🎵 Beat Generator

Desktop-приложение для генерации и редактирования битов на основе пользовательских sample packs.

<img width="1900" height="898" alt="Image" src="https://github.com/user-attachments/assets/bfdd1e46-3e67-4d17-ad2f-0cc7446f8f04" />

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
