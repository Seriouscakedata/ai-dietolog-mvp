# AI Dietolog MVP

Этот репозиторий содержит минимальный каркас проекта для MVP -бота по ведению дневника питания.

## Структура

```
ai_dietolog/
├── bot/               # логика взаимодействия с Telegram
│   ├── telegram_bot.py
├── agents/            # агенты для работы с OpenAI и формирования данных
│   ├── profile_collector.py
├── core/              # общий слой: хранение, модели, логика
│   ├── storage.py
│   ├── schema.py
│   └── logic.py
├── data/              # здесь создаются подкаталоги <tg_user_id>/ с JSON -файлами пользователя
├── config.json        # основные настройки проекта
└── requirements.txt   # зависимости Python
```

Проект хранит данные каждого пользователя локально в отдельной директории `data/<tg_user_id>`.  Внутри создаются файлы `profile.json`, `today.json` и т. д. в соответствии с описанной схемой.

## Быстрый старт на Windows

1. Склонируйте репозиторий и перейдите в созданную директорию.
2. Установите [Python](https://www.python.org/) 3.10+ и убедитесь, что
   ``python`` доступен в командной строке.
3. В ``cmd`` или PowerShell создайте виртуальное окружение и активируйте его:

   **PowerShell**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **cmd**
   ```cmd
   python -m venv .venv
   .\.venv\Scripts\activate.bat
   ```

4. Установите зависимости:

   ```
   pip install -r requirements.txt
   ```

5. Укажите токены через переменные окружения или заполните ``config.json``.

   **PowerShell**
   ```powershell
   $env:OPENAI_API_KEY="sk…"
   $env:TELEGRAM_BOT_TOKEN="..."
   ```

   **cmd**
   ```cmd
   set OPENAI_API_KEY=sk…
   set TELEGRAM_BOT_TOKEN=...
   ```

6. Запустите бота:

   ```cmd
   python -m ai_dietolog.bot.telegram_bot
   ```

## Конфигурация

В файле `config.json` задаются ключевые параметры: интервалы проверок, пороги для анализа, а также значения по умолчанию, используемые для расчётов.  Изменяя этот файл, вы можете адаптировать поведение системы без модификации кода.
Опция `use_llm_norms` включает расчёт норм с помощью модели OpenAI вместо
встроенных формул.

## Документация

Подробное описание модулей находится в [docs/MODULES.md](docs/MODULES.md).
