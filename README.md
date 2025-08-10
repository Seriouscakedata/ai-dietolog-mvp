# AI Dietolog MVP

Этот репозиторий содержит минимальный каркас проекта для MVP -бота по ведению дневника питания.

## Структура

```
ai_dietolog/
├── bot/               # взаимодействие с Telegram и обработчики
│   ├── telegram_bot.py
│   └── handlers/
│       ├── profile_setup.py    # настройка и редактирование профиля
│       ├── meal_logging.py     # приём и изменение блюд
│       └── daily_review.py     # завершение дня и отчёты
├── agents/            # LLM‑агенты для обработки данных
│   ├── intake.py             # распознаёт описание/фото блюда
│   ├── meal_editor.py        # уточняет состав блюда по комментарию
│   ├── contextual.py         # анализирует новый приём в контексте дня
│   ├── daily_review.py       # формирует сводку дня
│   ├── norms_ai.py           # рассчитывает нормы через LLM
│   ├── profile_collector.py  # строит профиль пользователя
│   └── profile_editor.py     # обновляет существующий профиль
├── core/              # конфигурация, модели и бизнес‑логика
│   ├── config.py
│   ├── llm.py
│   ├── logic.py
│   ├── prompts.py / prompts.yaml
│   ├── schema.py
│   └── storage.py
├── data/              # каталоги <tg_user_id>/ с JSON‑файлами пользователя
├── docs/              # документация проекта
├── config.json        # настройки по умолчанию (опционально)
└── requirements.txt   # зависимости Python
```

Проект хранит данные каждого пользователя локально в отдельной директории `data/<tg_user_id>`.  Внутри создаются файлы `profile.json`, `today.json` и т. д. в соответствии с описанной схемой.

## Агенты и взаимодействие

Телеграм‑обработчики вызывают специализированные агенты:

* `profile_setup` → `profile_collector.build_profile` и `profile_editor.update_profile` для создания и редактирования профиля.
* `meal_logging` → `intake.intake` для распознавания блюда, `contextual.analyze_context` для обновления дневной статистики и `meal_editor.edit_meal` для изменений.
* `daily_review` → `daily_review.analyze_day` для генерации итогового комментария.

Агенты используют `core.llm.ask_llm` и шаблоны из `core.prompts`, а настройки провайдера и модели берутся из `core.config`.  Структурированные данные описаны в `core.schema` и сохраняются через `core.storage`.

## Зависимости

Ключевые библиотеки перечислены в [requirements.txt](requirements.txt):

* [python-telegram-bot](https://python-telegram-bot.org/) — работа с Telegram.
* [openai](https://pypi.org/project/openai/) и [google-generativeai](https://pypi.org/project/google-generativeai/) — обращения к LLM‑провайдерам OpenAI и Gemini.
* [pydantic](https://docs.pydantic.dev/) — валидация данных.
* [filelock](https://pypi.org/project/filelock/) — безопасная работа с JSON‑файлами.
* [jinja2](https://palletsprojects.com/p/jinja/) и [pyyaml](https://pyyaml.org/) — шаблоны промтов.
* [colorama](https://pypi.org/project/colorama/) — цветной вывод в консоль.
* [apscheduler](https://apscheduler.readthedocs.io/) — планирование задач (зарезервировано на будущее).

Полный список версий смотрите в `requirements.txt`.

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
   $env:GEMINI_API_KEY="..."
   $env:TELEGRAM_BOT_TOKEN="..."
   ```

   **cmd**
   ```cmd
   set OPENAI_API_KEY=sk…
   set GEMINI_API_KEY=...
   set TELEGRAM_BOT_TOKEN=...
   ```

6. Запустите бота:

   ```cmd
   python -m ai_dietolog.bot.telegram_bot
   ```

   При запуске в консоль выводится статус подключения к OpenAI и Google
   Gemini.  Сообщения подсвечиваются зелёным при успешном соединении и
   красным при ошибке.

## Конфигурация

В файле `config.json` задаются ключевые параметры: интервалы проверок, пороги для анализа, а также значения по умолчанию, используемые для расчётов.  Изменяя этот файл, вы можете адаптировать поведение системы без модификации кода.
Опция `use_llm_norms` включает расчёт норм с помощью LLM. Поле `llm_provider`
задаёт используемый сервис (`openai` или `gemini`) по умолчанию. Для каждого
провайдера нужно указать соответствующий API‑ключ (`openai_api_key` или
`gemini_api_key`). В блоке `agents` можно задать модель и провайдера для
каждого агента отдельно, что позволяет одновременно подключать разные LLM.
Файл допускает строки комментариев, начинающиеся с `#` или `//`, поэтому можно
кратко пояснить назначение агентов прямо в конфигурации. Если `provider`
пропущен, используется значение из `llm_provider`.

Пример настройки агента в `config.json`:

```json
{
  "agents": {
    "intake": {"provider": "gemini", "model": "gemini-pro"}
  }
}
```

## Документация

Подробное описание модулей находится в [docs/MODULES.md](docs/MODULES.md).
