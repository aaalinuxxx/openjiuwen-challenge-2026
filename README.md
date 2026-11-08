# Budget-Aware Coding Agent Harness (openJiuwen Challenge'26)

Харнесс кодового агента на базе фреймворка [openJiuwen](https://github.com/openJiuwen-ai/agent-core) ([PyPI `openjiuwen==0.1.19`](https://pypi.org/project/openjiuwen/)) для решения пула из 100 задач в рамках фиксированного бюджета токенов (`BUDGET=100000`) и наличия 15–25% заведомо невыполнимых задач.

Архитектура опирается на результаты исследований [openJiuwen: Beyond Static Harnesses for Long-Horizon Coding Agents (arXiv:2608.27969)](https://arxiv.org/abs/2608.27969), [How Do AI Agents Spend Your Money? Analyzing and Predicting Token Consumption in Agentic Coding Tasks (arXiv:2604.22750)](https://arxiv.org/abs/2604.22750), [BAGEN: Towards Budget-Aware Agents (arXiv:2606.00198)](https://ragen-ai.github.io/bagen/) и [ImpossibleBench: Measuring LLMs' Propensity of Exploiting Test Cases (arXiv:2510.20270)](https://arxiv.org/abs/2510.20270).

## 1. Ключевые параметры соревнования и API NeuralDeep

- **Бюджет токенов (`BUDGET`):** Передаётся в переменной окружения `BUDGET` (ориентир — **`100000` выходных токенов** на все 100 задач). Прокси не сообщает остаток бюджета — харнесс ведёт строгий локальный учёт по формуле:
  $$\text{Cost}_{\text{eff}} = \frac{\text{Input Tokens}}{10.0} + \text{Output Tokens} + \text{Reasoning Tokens}$$
- **Платформа и модели (`LLM_BASE_URL`, `LLM_API_KEY`):** Точка входа `https://api.neuraldeep.ru/v1` (OpenAI-совместимый `POST /chat/completions`, лимит 60 запросов/мин, до 16 потоков на аккаунт, контекст 262 144 токенов):
  - `qwen3.8-27b-noreason` — основная быстрая плотная модель без затрат на `<think>`-токены;
  - `qwen3.6-35b-a3b-noreason` — ускоренная MoE-модель (3B активных параметров) для простых запросов;
  - `qwen3.8-27b` и `qwen3.6-35b-a3b` — модели с пошаговым рассуждением (используются только при необходимости глубокого анализа на дорогих задачах).
- **Правило 2 IP при разработке:** Ключ команды разрешает одновременную работу не более чем с **2 внешних IP-адресов** (без прокси/VPN), иначе ключ замораживается на 60 минут.
- **Формат задач и сдачи ответов:**
  - Все 100 задач ограничены 4 типами из примеров (`coding`, `data_analysis`, `math`, `search`). В финальном `task.json` убирается только поле `expected`, а поля `task_id`, `task_type`, `instruction`, `reward` и `check` остаются доступными агенту.
  - Разрешено решать задачи **детерминированно без вызова LLM (за 0 токенов)**, где это возможно, при обязательном использовании `openJiuwen` в архитектуре харнесса.
  - Для решённой задачи ответ записывается строго в файл **`/data/tasks/<task_id>/answer.txt` (рядом с `task.json`)**.
  - Если задача распознана как **невыполнимая** (задача, которую нельзя точно решить при имеющихся данных), **файл `answer.txt` не создаётся** (баллы за пропуск не начисляются, но экономится бюджет токенов).

## 2. Архитектура решения

1. **Совместимость с `--read-only` контейнером (`run_agent.py`, `Dockerfile`):**
   - При старте [openJiuwen 0.1.19](https://dev.to/reclusivecoder/build-a-custom-multi-step-ai-workflow-graph-with-openjiuwen-agent-core-35oi) создаёт директорию логов. Так как контейнер запускается с `--read-only` и `--tmpfs /tmp:rw,size=2g`, `run_agent.py` до импорта SDK перенаправляет `HOME` и логирование в `/tmp/openjiuwen_logs`.
   - Исправление кода и запуск `unittest` в задачах `coding` происходят во временной песочнице `/tmp/harness_work/<task_id>`, и только после 100% прохождения тестов исправленный модуль копируется обратно в `workspace/`.

2. **Двухэтапное распознавание невыполнимых задач (`harness/planner/unsolvable_filter.py`):**
   - **Zero-Token Pre-Filter (0 токенов, до вызова LLM):**
     - `search`: индексирует `kb/*.md` и проверяет существование запрашиваемых людей/компаний и целостность цепочки ссылок (`Employer`, `Mentor`, `Headquarters`, `Born`). Если данные отсутствуют или цепочка оборвана — задача пропускается за 0 токенов без создания `answer.txt`.
     - `data_analysis`: проверяет наличие CSV-файла, непустоту, существование требуемых колонок и запрашиваемых значений фильтра.
     - `coding`: выполняет AST-анализ `test_*.py` на наличие взаимоисключающих `assertEqual` на одних и тех же аргументах ([ImpossibleBench](https://arxiv.org/abs/2510.20270)) и синтаксических ошибок.
     - `math`: проверяет условие на деление на ноль (`split equally into 0`) и противоречивые операции.
   - **Runtime Early Stopping ([BAGEN](https://ragen-ai.github.io/bagen/)):** Если задача не решается детерминированно, а ответ LLM сигнализирует `UNSOLVABLE` или патч не проходит тесты в рамках выделенного лимита токенов, задача немедленно останавливается без создания `answer.txt`.

3. **Детерминированный Zero-Token Fast Path + `openJiuwen` LLM Pipeline (`harness/agents/`):**
   - Задачи `search`, `data_analysis` и `math`, попадающие под известные структурные шаблоны, решаются локальными парсерами за **0 токенов**.
   - Задачи `coding` и нестандартные формулировки решаются через `openJiuwen` с маршрутизацией в `qwen3.8-27b-noreason` / `qwen3.6-35b-a3b-noreason`. Благодаря экономии на первых трёх типах задач почти весь бюджет `100 000` токенов сохраняется для сложных задач и задач с максимальным `reward`.

4. **Планировщик по принципу задачи о рюкзаке (`harness/planner/scheduler.py`):**
   - Оценивает вероятность успеха $\hat{P}_i$ и ожидаемый расход токенов $\hat{C}_i$ (`token_estimator.py`).
   - Сортирует все выполнимые задачи по убыванию удельной выгоды:
     $$\text{ROI}_i = \frac{\text{reward}_i \times \hat{P}_i}{\max(\hat{C}_i, 1.0)}$$
   - Задачи с нулевым ожидаемым расходом (`Zero-Token`) выполняются первыми, мгновенно принося баллы без расхода квоты прокси.

## 3. Структура проекта и командная работа в Git (единая ветка `main`)

Команда из 2 человек работает **в единой ветке `main` без разветвления по feature-веткам**, но каждый участник редактирует свою изолированную папку пакетов, чтобы при `git pull` не возникало конфликтов:

- **Участник 1:** работает в `harness/agents/` и `harness/sandbox/` (доменные солверы, интеграция `openJiuwen`, промпты и песочница).
- **Участник 2:** работает в `harness/planner/`, `scripts/` и `run_agent.py` (извлечение фич, детектор невыполнимых задач, оценщик токенов, генератор тренировочных задач).

**Регламент синхронизации в команде:**
1. Перед началом правок: `git pull --rebase origin main`.
2. После завершения логического шага: `git add <своя_папка> && git commit -m "..." && git push origin main`.
3. Сразу после каждого `git push` пишем напарнику в чат, чтобы он обновил репозиторий (`git pull --rebase`) и посмотрел изменения.

```text
hackathon-harness/
├── Dockerfile                      # Инструкция сборки образа (python:3.11.10-slim-bookworm, < 1 ГБ)
├── .dockerignore                   # Исключение лишних файлов из контекста сборки
├── requirements.txt                # Зафиксированные зависимости (openjiuwen==0.1.19 и др.)
├── README.md                       # Документация проекта
├── TEAM_WORKPLAN.md                # План работ на 2 роли и правила синхронизации
├── run_agent.py                    # Точка входа (/app/run_agent.py), читает BUDGET, TASKS, LLM_BASE_URL
├── harness/
│   ├── config.py                   # Общие датаклассы контрактов (TaskContext, SolveResult)
│   ├── planner/                    # [Участник 2] Фичи, отсев невыполнимых, оценка токенов, планировщик
│   │   ├── feature_extractor.py
│   │   ├── unsolvable_filter.py
│   │   ├── token_estimator.py
│   │   ├── budget_tracker.py
│   │   └── scheduler.py
│   ├── agents/                     # [Участник 1] Мост openJiuwen, роутер моделей и 4 доменных солвера
│   │   ├── base_harness.py
│   │   ├── model_router.py
│   │   ├── coding_solver.py
│   │   ├── data_solver.py
│   │   ├── math_solver.py
│   │   ├── search_solver.py
│   │   └── fallback_react.py
│   ├── sandbox/                    # Изолированный запуск кода в /tmp и атомарная запись answer.txt
│   │   ├── executor.py
│   │   └── file_guard.py
│   └── models_weights/             # Веса классического оценщика расхода токенов
├── scripts/                        # Генератор тренировочного набора и обучение оценщика
│   ├── generate_dataset.py
│   └── train_estimator.py
└── trajectories/                   # Сводная статистика калибровочных запусков
    └── summary_stats.json
```

## 4. Сборка и запуск

```bash
mkdir -p "$OUT" && chmod 777 "$OUT"

docker build -t "hack:latest" . && \
timeout -k 1000s 1h docker run --rm --name "run-${TEAM}" \
  --network hack-net \
  -e LLM_BASE_URL -e LLM_API_KEY -e BUDGET=100000 \
  -v "$TASKS:/data/tasks:rw" \
  --read-only --tmpfs /tmp:rw,size=2g -e HOME=/tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  --cpus 8 --memory 16g --pids-limit 512 \
  --workdir /app --entrypoint python \
  "hack:latest" \
  /app/run_agent.py --tasks-dir /data/tasks
```
