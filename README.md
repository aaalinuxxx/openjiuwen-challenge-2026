# Budget-Aware Coding Agent Harness (openJiuwen)

Харнесс кодового агента на базе `openJiuwen==0.1.19` для решения пула из 100 задач в условиях жёсткого бюджета токенов и наличия невыполнимых задач (15–25%).

## Архитектура и ключевые решения

1. **Изоляция под `--read-only` контейнер (`run_agent.py`, `harness/config.py`)**:
   - Все логи `openJiuwen`, временные рабочие директории песочницы и чекпоинты перенаправляются в `/tmp` (`--tmpfs /tmp:rw,size=2g`).
   - Исходные файлы задач копируются во временные изолированные воркспейсы `/tmp/work_<task_id>` перед запуском тестов и патчей, что предотвращает порчу данных и защищает `test_*.py` от модификации.

2. **Двухэтапный отсев невыполнимых задач (`harness/planner/unsolvable_filter.py`)**:
   - **Zero-Token Pre-Filter (0 токенов):** До обращения к LLM проверяет целостность задачи средствами Python:
     - `search`: индексирует `kb/*.md` и проверяет, существуют ли упомянутые в вопросе имена собственные и компании в базе знаний, а также нет ли оборванных ссылок `Employer` / `Mentor`.
     - `data_analysis`: проверяет существование CSV-файла, непустоту, наличие требуемых столбцов и валидность числовых диапазонов.
     - `coding`: запускает `python3 -m unittest` за 0 токенов, проверяет синтаксическую корректность тестов и ищет прямо противоречащие друг другу `assertEqual` в AST тестового файла.
     - `math`: проверяет условие на деление на ноль и противоречивые ограничения.
   - **Runtime Probe / Early Stopping (`harness/planner/budget_tracker.py`):** Прерывает задачу, если после первой итерации исправления количество падающих тестов не уменьшилось или превышен выделенный лимит `max_token_budget`.

3. **Оценка стоимости и планировщик очереди (`harness/planner/token_estimator.py`, `scheduler.py`)**:
   - Извлекает статические признаки задачи (`feature_extractor.py`) и предсказывает вероятность успеха `P(solvable)` и ожидаемый расход `E[tokens]` (в выходных токенах по формуле `input / 10 + output + reasoning`).
   - Ранжирует все задачи по убыванию удельной выгоды:
     `ROI = (reward * P_solvable) / E_tokens`.
   - Исполняет задачи асинхронно до 5 параллельных сессий (`asyncio.Semaphore(5)`).

4. **Экономные доменные пайплайны и маршрутизация моделей (`harness/agents/`)**:
   - **Маршрутизация моделей (`model_router.py`):** По умолчанию использует `qwen3.8-27b-noreason` и `qwen3.6-35b-a3b-noreason`, чтобы не тратить выходные токены на `<think>`-рассуждения. Переход на reasoning-модель (`qwen3.8-27b`) разрешён только для задач с высоким `reward`, если первая попытка не прошла локальную верификацию.
   - **Атомарное сохранение (`harness/sandbox/file_guard.py`):** Сразу после решения задачи атомарно записывает `answer.txt` в каталог задачи (и в `workspace/answer.txt`, если подкаталог есть), а также обновляет сводный файл `$OUT` (если задан).

## Сборка и запуск

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

## Разделение работ в команде (2 человека)

- **Участник 1 (`harness/agents/`, `harness/sandbox/`):** Доработка промптов и графов `openJiuwen` (`WorkflowAgent` / `ReActAgent`), улучшение локализации багов в `coding_solver.py`, тюнинг переключения между 4 моделями Qwen.
- **Участник 2 (`harness/planner/`, `scripts/`):** Генерация расширенного тренировочного набора (`scripts/generate_dataset.py`), сбор траекторий, дообучение весов оценщика токенов (`token_estimator.py`) и правил детекции невыполнимых задач (`unsolvable_filter.py`).
