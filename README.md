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

## Быстрый старт

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="sk …"
export TELEGRAM_BOT_TOKEN="..."
python -m bot.telegram_bot
```

## Конфигурация

В файле `config.json` задаются ключевые параметры: интервалы проверок, пороги для анализа, а также значения по умолчанию, используемые для расчётов.  Изменяя этот файл, вы можете адаптировать поведение системы без модификации кода.
