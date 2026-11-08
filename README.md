# Budget-Aware Coding Agent Harness (openJiuwen)

Харнесс кодового агента на базе фреймворка [openJiuwen](https://github.com/openJiuwen-ai/agent-core) ([PyPI `openjiuwen==0.1.19`](https://pypi.org/project/openjiuwen/)) для решения пула из 100 задач в условиях строго фиксированного бюджета токенов и наличия невыполнимых задач (15–25%).

Архитектура опирается на результаты исследований [openJiuwen: Beyond Static Harnesses for Long-Horizon Coding Agents (arXiv:2608.27969)](https://arxiv.org/abs/2608.27969), [How Do AI Agents Spend Your Money? Analyzing and Predicting Token Consumption in Agentic Coding Tasks (arXiv:2604.22750)](https://arxiv.org/abs/2604.22750), [BAGEN: Towards Budget-Aware Agents (arXiv:2606.00198)](https://ragen-ai.github.io/bagen/) и [ImpossibleBench: Measuring LLMs' Propensity of Exploiting Test Cases (arXiv:2510.20270)](https://arxiv.org/abs/2510.20270).

## 1. Ключевые архитектурные решения

1. **Полная совместимость с `--read-only` контейнером и ограничениями среды (`run_agent.py`, `Dockerfile`):**
   - Согласно [технической документации openJiuwen 0.1.19](https://dev.to/reclusivecoder/build-a-custom-multi-step-ai-workflow-graph-with-openjiuwen-agent-core-35oi), при старте SDK создаёт директорию `logs/` в рабочей папке процесса. Поскольку контейнер запускается с флагом `--read-only` и `--tmpfs /tmp:rw,size=2g`, `run_agent.py` до инициализации `openJiuwen` перенаправляет `HOME` и все файловые логгеры в `/tmp/openjiuwen_logs`.
   - Все операции тестирования и модификации кода в задачах `coding` выполняются в изолированных копиях `/tmp/harness_work/<task_id>`, что исключает повреждение исходных файлов или случайное изменение `test_*.py` при параллельной работе до 5 сессий.

2. **Точный учёт бюджета токенов (`harness/planner/budget_tracker.py`):**
   - Все расходы приводятся к выходным токенам по формуле регламента:
     $$\text{Cost}_{\text{eff}} = \frac{\text{Input Tokens}}{10.0} + \text{Output Tokens} + \text{Reasoning Tokens}$$
   - Токены рассуждений (`reasoning_tokens`) извлекаются как из `usage.completion_tokens_details.reasoning_tokens`, так и из корневого поля `usage.reasoning_tokens` (без двойного учёта, если прокси уже включил их в `completion_tokens`).
   - Встроен механизм прогрессивного контроля бюджета по методологии [BAGEN](https://ragen-ai.github.io/bagen/): каждой задаче выделяется динамический потолок `max_token_budget`, при превышении которого без прогресса задача принудительно останавливается (Early Stopping), сохраняя бюджет для следующих задач.

3. **Двухэтапное распознавание невыполнимых задач (`harness/planner/unsolvable_filter.py`):**
   - **Этап 0 — Zero-Token Pre-Filter (0 токенов, чистый Python до вызова LLM):**
     - `search`: индексирует все файлы `kb/*.md` и проверяет наличие запрашиваемых в `instruction` сущностей (людей, компаний, городов) и целостность связей `Employer` / `Mentor`. Если сущность отсутствует или ссылка ведёт в несуществующий файл, задача отбрасывается за 0 токенов.
     - `data_analysis`: проверяет существование и непустоту `.csv` файла, наличие целевых колонок (`order_id`, `region`, `product`, `month`, `units`, `price`) и корректность типов данных.
     - `coding`: запускает `python3 test_*.py` и анализирует AST тестового файла (`ast.parse`). Если в тестах обнаружена синтаксическая ошибка или прямо противоречащие друг другу утверждения `self.assertEqual(f(x), y1)` и `self.assertEqual(f(x), y2)` (паттерн из [ImpossibleBench](https://arxiv.org/abs/2510.20270)), задача помечается как `UNSOLVABLE` за 0 токенов.
     - `math`: проверяет текстовое условие на деление на ноль (`split equally into 0`) и противоречивые ограничения.
   - **Этап 1 — Runtime Verification & Early Stopping:** Если на первом шаге модель возвращает маркер `UNSOLVABLE` или патч в `coding` не уменьшает число падающих тестов в `unittest`, задача снимается с выполнения.

4. **Оценка расхода и планирование по принципу задачи о рюкзаке (`harness/planner/token_estimator.py`, `scheduler.py`):**
   - Модуль `feature_extractor.py` за доли секунды собирает статические признаки всех 100 задач (`task_type`, `reward`, длина инструкции, число файлов, объём байт, число строк CSV, число падающих тестов при первичном прогоне).
   - Оценщик `TokenCostEstimator` (поддерживающий как аналитический профиль, так и веса классической регрессии/бустинга из `harness/models_weights/`) вычисляет вероятность решения $\hat{P}_i$ и ожидаемый расход $\hat{C}_i$ (в приведённых выходных токенах).
   - Поскольку баллы `reward` распределены случайно, планировщик ранжирует все задачи по убыванию удельной выгоды:
     $$\text{ROI}_i = \frac{\text{reward}_i \times \hat{P}_i}{\hat{C}_i}$$
   - Выполнение идёт асинхронными батчами до 5 параллельных сессий (`asyncio.Semaphore(5)`).

5. **Гибридные доменные солверы и маршрутизация 4 моделей Qwen (`harness/agents/`):**
   - Согласно [сравнению моделей Qwen3.6-35B-A3B и Qwen3.8-27B](https://benchlm.ai/compare/qwen3-6-35b-a3b-vs-qwen3-8-27b), [Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) — быстрая MoE-модель (3B активных параметров), а [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) — плотная 27B модель с более высокой точностью в генерации кода.
   - Поскольку в регламенте 1 токен любой модели имеет одинаковый вес в бюджете, а токены рассуждений тарифицируются как дорогие выходные токены, `model_router.py` по умолчанию маршрутизирует запросы в **`qwen3.8-27b-noreason`** и **`qwen3.6-35b-a3b-noreason`**, экономя в 15–40 раз больше токенов на отказе от `<think>`-генерации.
   - Переключение на reasoning-модель (`qwen3.8-27b`) разрешается только как fallback для дорогих задач (`reward >= 4`), если первая попытка не прошла локальные тесты.
   - Для типовых шаблонов `search`, `data_analysis` и `math` встроены локальные детерминированные парсеры, решающие задачи за **0 токенов**; при нестандартной формулировке в LLM передаётся только ужатый срез данных (заголовок CSV или 2–3 релевантные карточки из `kb/`).

6. **Атомарное сохранение результатов (`harness/sandbox/file_guard.py`):**
   - Сразу после решения каждой задачи ответ записывается через временный файл с `os.fsync` и атомарным `os.replace` в `/data/tasks/<task_id>/answer.txt` (и дублируется в `workspace/answer.txt`, если подкаталог `workspace` существует), а также обновляет сводный файл `$OUT` при его наличии. Даже при внезапном отключении прокси все решённые к этому моменту задачи гарантированно засчитываются.

## 2. Структура репозитория

```text
hackathon-harness/
├── Dockerfile                      # Инструкция сборки образа (python:3.11.10-slim-bookworm, < 1 ГБ)
├── .dockerignore                   # Исключение лишних артефактов из контекста сборки
├── requirements.txt                # Зафиксированные версии зависимостей (openjiuwen==0.1.19 и др.)
├── README.md                       # Полное описание архитектуры, сборки, оценщика и траекторий
├── TEAM_WORKPLAN.md                # Пошаговый план работ и разделение зон ответственности на 2 участников
├── run_agent.py                    # Точка входа (/app/run_agent.py)
├── harness/
│   ├── config.py                   # Конфигурация моделей и датаклассы контрактов (TaskContext, SolveResult)
│   ├── planner/                    # [Роль 2] Извлечение фич, фильтр невыполнимых, оценка токенов, планировщик
│   │   ├── feature_extractor.py
│   │   ├── unsolvable_filter.py
│   │   ├── token_estimator.py
│   │   ├── budget_tracker.py
│   │   └── scheduler.py
│   ├── agents/                     # [Роль 1] Обёртка openJiuwen, роутер моделей и 4 доменных солвера
│   │   ├── base_harness.py
│   │   ├── model_router.py
│   │   ├── coding_solver.py
│   │   ├── data_solver.py
│   │   ├── math_solver.py
│   │   ├── search_solver.py
│   │   └── fallback_react.py
│   ├── sandbox/                    # Безопасное исполнение кода с таймаутами и атомарная запись answer.txt
│   │   ├── executor.py
│   │   └── file_guard.py
│   └── models_weights/             # Сериализованные веса классических моделей оценки расхода
├── scripts/                        # Инструменты генерации тренировочного набора и обучения оценщика
│   ├── generate_dataset.py
│   └── train_estimator.py
└── trajectories/                   # Собранные статистики и траектории прогонов
    └── summary_stats.json
```

## 3. Сборка и запуск

Все версии зависимостей и базовый образ (`python:3.11.10-slim-bookworm`) строго зафиксированы. Внешние сетевые обращения во время работы контейнера идут исключительно к `LLM_BASE_URL`.

```bash
mkdir -p "$OUT" && chmod 777 "$OUT"

docker build -t "hack:latest" . && \
timeout -k 1000s 1h docker run --rm --name "run-${TEAM}" \
  --network hack-net \
  -e LLM_BASE_URL -e LLM_API_KEY \
  -v "$TASKS:/data/tasks:rw" \
  --read-only --tmpfs /tmp:rw,size=2g -e HOME=/tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  --cpus 8 --memory 16g --pids-limit 512 \
  --workdir /app --entrypoint python \
  "hack:latest" \
  /app/run_agent.py --tasks-dir /data/tasks
```

## 4. Собранные траектории и калибровка оценщика

В директории `trajectories/summary_stats.json` сохранена сводка калибровочных запусков на эталонном пуле задач (`coding`, `data_analysis`, `math`, `search`):

| Тип задачи | Средний расход (Zero-Token / Fast Path) | Средний расход (`-noreason` LLM Path) | Средний расход (`reason` Fallback) | Примечание |
| :--- | :--- | :--- | :--- | :--- |
| **`search`** | `0.0` токенов | `65–85` токенов | Не требуется | Локальная индексация `kb/*.md` отсекает 90%+ нерелевантных файлов |
| **`data_analysis`** | `0.0` токенов | `80–110` токенов | Не требуется | В промпт передаются только первые 4 строки CSV для генерации скрипта |
| **`math`** | `0.0` токенов | `95–130` токенов | `450–800` токенов | Перевод условия в скрипт `python3 -c` вместо ручного счёта в токенах |
| **`coding`** | `0.0` (если тесты проходят) | `180–320` токенов | `600–1200` токенов | Локализация ошибки через `unittest` до первого вызова модели |
