# Эксперименты и траектории

Этот документ объясняет, **что проверяли, какие результаты получили и почему выбрали итоговую конфигурацию** харнесса. Он охватывает не только финальный прогон, но и разработки локальных решателей, планировщика, механизма учёта бюджета и проверок результата.

Итоговая конфигурация — `calibrated + csv-roomy` с исходным math-промптом. Экспериментальный результат и факт включения механизма в неё — разные характеристики. Ниже явно отмечены ограничения сравнений и незавершённые проверки.

**Как читать результаты:** экспериментальные пулы в основном авторские; часть тестов и семейств использовалась при разработке повторно. Парное сравнение на таких данных показывает результат проверенных вариантов в конкретном прогоне, но не гарантирует результат на скрытых задачах организаторов. Разные эксперименты могут отличаться набором, бюджетом, моделью, конфигурацией или порядком запуска.

[Фундамент и бенчмарки](#1-фундамент-бюджет-и-контрольные-наборы) · [Поиск](#2-поиск-по-базе-знаний) · [Coding](#3-исправление-кода) · [CSV и-join](#4-анализ-данных-и-join) · [Бюджеты и очередь](#5-лимиты-и-планирование-задач) · [Математика](#6-математические-задачи-и-отклонённые-варианты) · [Выбор релиза](#7-итоговая-проверка-и-выбор-конфигурации) · [Траектории](#8-из-чего-состоят-траектории) · [Индекс файлов](#9-индекс-артефактов)

## 1. Фундамент: бюджет и контрольные наборы

### Учёт запросов и исполнение через SDK

В ранних сериях проверяли корректность механизма до сравнения качества решателей:

- **E24–E27:** резервирование бюджета перед запросом, учёт фактического `usage`, параллельные запросы и обработка неизвестного расхода. Если подтвердить стоимость невозможно, новые платные запросы останавливаются. Оценка входа по UTF-8-байтам с запасом является эвристикой, поэтому резерв нельзя называть гарантированной верхней границей.
- **E28–E29:** отдельный Workflow настоящего `openJiuwen` на задачу и прохождение через CLI. Успешный импорт SDK сам по себе не доказывает корректность работы всего агента; проверялось именно исполнение workflow.
- **E30:** генерация авторских задач четырёх типов и проверка фильтра невыполнимости. Интерпретация `reasoning_tokens` у конкретного ответа не считается универсально доказанным биллинговым контрактом; в выбранном runtime неподтверждённые reasoning-вызовы блокируются до отправки.
- **E34–E40:** повторные проверки ошибок фильтра, формата ответов, CLI и бесплатного локального пути. Исторический локальный E40 при бюджете 0 решил 24 из 32 выполнимых задач на синтетическом наборе, набрав 80 из 113 возможных баллов. Это результат той версии и тех данных, а не гарантия покрытия финального набора.

Планы, контрольные примеры, границы результатов и изменения формулировок гипотез сохранены в [журнале гипотез](../HYPOTHESES.md) и соответствующих файлах `experiments/`.

### Проверка на новых семействах: E41–E46

Команда подготовила набор из **24 авторских задач, из них 19 выполнимых**, включая новые формулировки и семейства. В объединённых завершённых прогонах E43 и E44 получено **9/19 решений и 27/57 баллов**. Проверка обнаружила ложные отказы и ограничения поиска, кодового решателя и работы с CSV.

Последующий прогон E46 с большим бюджетом прервался с неизвестной стоимостью одного запроса. Поэтому его резерв не считается фактическим расходом, а незавершённое сравнение не используется как доказательство качества. [Сводка E46](../experiments/E46_iteration_summary.json).

### Сроки исполнения и локальные проверки: E47–E49

На структурных контролях поиска результат менялся **3/12 → 12/12**; отдельно проверялись дедлайны SDK на пяти масштабированных сценариях (**2/5 → 5/5**). Это локальные проверки механизмов: E49 не является новым измерением качества через API. [Сводка E49](../experiments/E49_iteration_summary.json).

## 2. Поиск по базе знаний

Задачи `search` требуют найти факты в Markdown-карточках и иногда пройти цепочку связей между сущностями. Исследовались полнота контекста, сжатие и проверка доказательств.

| Серия | Что сравнивали | Набор и результат | Вывод / ограничение | Отчёт |
|---|---|---|---|---|
| E50–E51 | Прежнее и расширенное построение контекста KB | 5 парных задач: **2/5 → 5/5 корректных исходов**, включая корректный отказ | Небольшой целевой авторский пилот; сравнивался весь search-путь, а не отдельные компоненты | [E51](../experiments/E51_iteration_summary.json) |
| E52–E53 | Обычное и компактное представление контекста | На 5 сопоставимых запросах расход **276 → 199,4** токена, экономия **27,8%** | В каждой ветви одна ошибка; компактный вариант исследовательский, в стандартный путь не включён | [E53](../experiments/E53_iteration_summary.json) |
| E54–E56 | Обработка конфликтного ответа и структурированное `evidence` | В пилоте по 6 задачам обычный вариант: 3 решения и 2 корректных отказа; evidence: 3 решения и 3 неопределённости | Структурированный формат не добавил решений и стоил 446,5 против 101,7 токена; общий evidence-путь не включён | [E56](../experiments/E56_iteration_summary.json) |
| E110–E111 | Контекст только по прямым связям и с обратными связями | Из 6 выполнимых задач **3 → 6**, 12/15 → 15/15 баллов; 111,9 → 127,8 токена | Целевой набор из 8 задач; преимущество на произвольных графах не доказано | [E111](../experiments/E111_incoming_summary.json) |

E53 — пример того, почему важно рассматривать стоимость вместе с корректностью: меньшее число токенов само по себе не доказывает, что система отвечает надёжно.

## 3. Исправление кода

Coding-решатель определяет целевой модуль, получает тесты и контекст, генерирует исправление и проверяет кандидата. Отдельные серии исследовали передачу ошибок, откат и неоднозначный выбор файла.

- **E09–E10, E31b:** проверка ремонта, передачи неудачного патча с актуальным выводом тестов и сохранения лучшей версии при регрессии. Контроль ограничен доступными тестами; они не эквивалентны скрытым. История и локальные протоколы — в [реестре](../HYPOTHESES.md).
- **E57–E58:** работа с проектами из нескольких модулей при необходимости редактировать только один. Из четырёх целевых задач с явным указанием файла решены **4/4**; всего было решено 4 из 5 выполнимых. Одно перефразирование оставалось неподдержанным. [Отчёт E58](../experiments/E58_iteration_summary.json).
- **E59–E60:** поддержка ограниченного числа перефразировок выбора файла. На четырёх целевых вариантах старая версия решила **1/4**, новая — **4/4**; расход 119,9 против 332,9 токена. Увеличение расхода связано также с разным числом вызовов: это проверка покрытия, не экономии. [Отчёт E60](../experiments/E60_iteration_summary.json).
- **E108–E111:** исправления, связанные с отказами, сохранением регистра, интерпретацией запрета изменения входов и поиском обратных связей. В совместном целевом прогоне E109 проверены **11/11 выполнимых задач**, 28/28 баллов. Это адаптивная регрессия после обнаруженных ошибок, а не независимый контроль. [E109](../experiments/E109_repair_summary.json) · [E111](../experiments/E111_incoming_summary.json).

## 4. Анализ данных и JOIN

В ветке `data_analysis` сравнивались локальные планы, генерация Python и ограниченное JSON-представление. Особое внимание уделялось нескольким CSV, кратности дублирующихся строк и условиям объединения.

### Многотабличный ввод и JSON-планы

| Серия | Проверяемая идея | Наблюдение | Ограничение / решение | Отчёт |
|---|---|---|---|---|
| E61–E64 | Обработка нескольких CSV | На начальных целевых примерах новый путь решил **6/6** выполнимых задач против 1/6; затем найден контрпример с дубликатами | Первое улучшение не доказало общую корректность JOIN | [E62](../experiments/E62_iteration_summary.json) |
| E65–E66 | Модель формирует JSON-план, исполнитель считает локально | На 6 задачах обе ветви решили 5; у JSON 0 неверных ответов и один отказ, у Python — одна ошибка; 792,7 против 1200,7 токена | Набор целевой; проверка схемы не гарантирует правильность перевода условия | [E66](../experiments/E66_iteration_summary.json) |
| E67–E68 | Каскад JSON → Python на неподдержанных условиях | Python **5/5**, каскад **4/5**, один неверный ответ; 1173,8 против 937,1 токена | Экономия не сохранила качество; проверенную политику не приняли как равнозначную | [E68](../experiments/E68_iteration_summary.json) |
| E69–E70 | Предварительная проверка области применимости плана | **5/7 → 6/7**, но остался один неверный ответ | Критерий полного сохранения качества не выполнен | [E70](../experiments/E70_iteration_summary.json) |
| E71–E72 | Поддержка перефразировок с учётом кратности строк | **4/7 → 6/7**, ошибки **3 → 1** | Целевой пилот показывает улучшение в конкретной грамматике | [E72](../experiments/E72_iteration_summary.json) |

### Локальное выполнение и интеграция

- **E73–E74:** распознанные планы исполнялись локально. Обе ветви решили **7 из 8** задач, но запросы к модели сократились **8 → 3**, а расход — **1567,3 → 834,8** токена. В каждой ветви оставалась одна ошибка. [Отчёт E74](../experiments/E74_iteration_summary.json).
- **E75–E76:** локальный разбор условий `OR` и отсутствующих совпадений. На семи задачах результат **5/7 → 6/7**, расход **2170,7 → 429,7** токена. В обоих вариантах одна внешняя по отношению к локальному плану задача не решилась из-за обрезания. Это целевой эксперимент; экономия составляет около **80,2% на этом наборе**. [Отчёт E76](../experiments/E76_iteration_summary.json).
- **E77–E78:** интеграция подхода в общий харнесс. На смешанном наборе из 31 задачи, 26 из которых выполнимы, кандидат решил **20/26** против **14/26** у исходного варианта и получил 60/78 против 42/78 баллов при бюджете 3000. Это не оценка независимого скрытого набора. [E78](../experiments/E78_iteration_summary.json).
- **E79–E80:** увеличение доступного лимита сняло обрезание генераций: **20/26 → 21/26** и 60 → 63 балла. Но критерий приёмки полностью не выполнен: три сохранённых ответа оказались связаны со статусом `FAILED`. В отчёте они отражены как `wrong_answers`, хотя речь не о доказанно неверных числах. [E80](../experiments/E80_iteration_summary.json).
- **E81–E84:** согласование каналов `stdout` и `answer.txt`. В целевом сравнении на 13 data-задачах, 12 из которых выполнимы, проверенных решений стало **11/12 → 12/12**. Это сравнение только data-задач, а не самостоятельный результат на всех 26 задачах смешанного набора. [E84](../experiments/E84_iteration_summary.json).
- **E85–E92:** проверка профиля и числовых JOIN. В полном смешанном прогоне E92 при бюджете **2700** решены **26/26** выполнимых задач, **78/78** баллов, расход **1824,3** токена. Это знакомый адаптивный набор; три из пяти невыполнимых задач получили обоснованный отказ, две завершились без ответа. [E92](../experiments/E92_evening_summary.json).

## 5. Лимиты и планирование задач

### Лимиты для CSV и тесты при ограниченном бюджете

В E94 первая проверка шести ранее отложенных JOIN-задач дала **5/6**; одна генерация обрезалась. После адаптации лимита в E98 — **6/6**. Поскольку второй вариант разработан после первого результата, его нельзя называть проверкой на том же нетронутом holdout. Полный знакомый смешанный прогон E100 сохранил **26/26**. Подробнее: [E104](../experiments/E104_additional_summary.json).

Исследовались несколько правил порядка задач: исходный ROI, сортировка по награде и медианная стоимость типа. В E104 медианная очередь в одном пилоте получила больше баллов, но бюджеты вариантов различались, а задачи включали повторно использованные семейства. Следующая серия сравнивала варианты при равном бюджете.

### Очередь по медианной стоимости: E105–E117

| Проверка | Набор и бюджет | Базовый ROI | Калиброванная очередь | Ограничение / источник |
|---|---|---:|---:|---|
| E105–E107 | 100 задач, 83 выполнимые, бюджет **1000** | **96** баллов, 26 правильных | **122** балла, 37 правильных | У калиброванного варианта обнаружены два неверных `SOLVED`; 76 задач — знакомые копии, 24 — новые авторские. [E107](../experiments/E107_validation_summary.json) |
| E113 | Тот же тип стресс-пула, бюджет **500** | **71** балл | ROI с порогом вывода — **76** | Проверка только конкретного порога и набора. [E113](../experiments/E113_floor_summary.json) |
| E115 | 100 задач, 83 выполнимые, бюджет **500** | ROI: **71**, расход 373,3 | Калиброванная: **105**, расход 373,1 | Сравнение последовательное, две ветви переиспользованы; одна серия на знакомом пуле. [E115](../experiments/E115_interaction_summary.json) |
| E115: взаимодействие | Тот же пул и бюджет **500** | ROI + порог: **76** | Калибровка + порог: **102** | Порог улучшил ROI в этом пилоте, но снизил результат калиброванной очереди с 105 до 102 |
| E117 | Знакомый смешанный набор; см. лимиты в отчёте | — | **26/26**, 78/78 баллов | Интеграционная регрессия, а не оценка скрытого набора. [E117](../experiments/E117_release_summary.json) |

Планировщик по умолчанию использует медианы типов для **порядка** задач. Отдельные эвристики `expected_cost` участвуют в выделении бюджета. Результаты E115 не доказывают, что сочетание гипотез будет столь же эффективно при любом бюджете или на любых данных.

## 6. Математические задачи и отклонённые варианты

| Серия | Идея | Что получилось | Решение / источник |
|---|---|---|---|
| E118–E119 | Короткий первый проход и выборочный повтор | При бюджете 800: **30 против 35** баллов у baseline. При 2000: **49 против 61** | Конкретная двухпроходная политика не прошла критерии и не включена. [E119](../experiments/E119_two_pass_summary.json) |
| E120–E121 | Увеличение резерва на math | При 800: **28 против 35** баллов; при 2000 оба варианта набрали **61**, но кандидат потратил на 201,7 токена больше | Не включено на основании этой проверки. [E121](../experiments/E121_math_budget_summary.json) |
| E122–E123 | Замена math-промпта более коротким | При 800: **38 против 35**; при 2000: **55 против 61** | Условия приёмки не выполнены; кандидат не включён. [E123](../experiments/E123_compact_target_summary.json) |
| E124–E125 | Добавить краткость к исходному math-промпту | В целевом наборе +3 балла при каждом из двух бюджетов; на новом авторском наборе обнаружен один неверный `SOLVED` | Ранний выигрыш не доказал сохранения качества на новом наборе. [E125](../experiments/E125_terse_fresh_summary.json) |
| E126–E127 | Перепроверять подозрительную числовую константу | В адаптивной диагностике **4/10 → 10/10**, 10 новых запросов и 568 токенов | Дополнительный расход и выбранные исторические случаи; это не доказательство выигрыша по итоговым баллам. В релиз не включено. [E127](../experiments/E127_numeric_recheck_summary.json) |
| E131–E132 | Сравнить исходный и короткий math-промпт | По трём завершённым прогонам сумма **140 против 138**; затраты 4276,3 против 3824,7 токена | Выбран исходный вариант по сумме наград; два бюджета применены к одному новому набору. [E131](../experiments/E131_score_selection_summary.json) |

При E125 один запуск прервался с неизвестным `usage`; отдельно проведён ограниченный заменяющий контроль. Два прогона третьего кандидата на этапе окончательного выбора также не завершились. Они не являются доказательством качества или худшего результата этого кандидата.

## 7. Итоговая проверка и выбор конфигурации

### Полная регрессия E129

Знакомый смешанный набор: **31 задача, 26 выполнимых**. Бюджет — **3000** приведённых токенов; дополнительный предел эксперимента — 30 API-вызовов. По авторскому проверяющему коду получено **26/26 корректных решений и 78/78 баллов**, 23 запроса, расход **1820,2**. На этапе E129 зафиксировано **235 тестов**; позднее в итоговом отчёте — 241.

| Домен | Верно решено выполнимых | Баллы |
|---|---:|---:|
| Coding | 5/5 | 15/15 |
| Data analysis | 12/12 | 36/36 |
| Math | 5/5 | 15/15 |
| Search | 4/4 | 12/12 |

[Сводка E129](../experiments/E129_submission_summary.json) · [Полный отчёт](../experiments/E129_submission_baseline_live_20261113T092505061530/report.json) · [Аудит](../experiments/E129_submission_baseline_live_20261113T092505061530/independent_audit.json).

### Сравнение финалистов E131–E132

| Набор | Бюджет | Исходный промпт | Короткий промпт |
|---|---:|---:|---:|
| Расширенный знакомый набор, 43 задачи | 3000 | **99/105** | 94/105 |
| Новый авторский набор, 18 задач | 800 | 15/48 | **17/48** |
| Тот же новый набор, 18 задач | 2000 | 26/48 | **27/48** |
| **Сумма трёх прогонов** | — | **140** | 138 |
| Суммарный известный расход | — | 4276,3 | **3824,7** |

После проверки обнаружено, что одна задача записала правильный `answer.txt`, но получила внутренний статус `FAILED`. Критерий был изменён на оценку правильного сохранённого артефакта; исходные результаты и поправка сохранены. Выбор исходного промпта сделан по сумме наград в **этом сравнении**, а не как гарантия на скрытых данных. [Сводка E131](../experiments/E131_score_selection_summary.json) · [Решение E132](../experiments/E132_final_selection_release.json).

## 8. Из чего состоят траектории

На примере [прогона E129](../experiments/E129_submission_baseline_live_20261113T092505061530/):

| Артефакт | Содержимое и назначение |
|---|---|
| `ranking.json` | Порядок задач и оценки планировщика до выполнения |
| `request_*.json` | Зафиксированные запросы: идентификатор задачи, модель, промпт и параметры |
| `response_*.json` | Ответы API и данные `usage` для конкретных запросов |
| `budget.json` | События резервирования и учёта бюджета, известные и неизвестные расходы |
| `report.json` | Конфигурация, результаты по задачам и типам, итоговые метрики |
| `independent_audit.json` | Аудит учёта запросов и расхода |
| `task_artifacts/` | Снимки файлов задач и сохранённых ответов после прогона |

Траектории позволяют восстановить решение, сравнить прогноз и фактический расход, проверить ошибки и результаты. В E92 медианы стоимости по типам затем использованы для сортировки; наличие исследовательского скрипта обучения не означает, что в итоговом `estimate()` применяется обученный ML-оценщик.

## 9. Индекс артефактов

Ниже автоматически перечислены файлы и папки непосредственно внутри `experiments/`, названия которых начинаются с идентификатора эксперимента. Это **индекс существующих артефактов**, а не утверждение, что каждый номер означает независимый успешно завершённый эксперимент. Один номер может содержать план, контроль, результат, прерванный прогон и несколько повторов. Подробную историю проверок см. в [HYPOTHESES.md](../HYPOTHESES.md).

<details>
<summary>E00–E09 · 13 артефактов</summary>

- [E00_baseline.json](../experiments/E00_baseline.json)
- [E01_conservative_filter.json](../experiments/E01_conservative_filter.json)
- [E02_math_sentence_parser.json](../experiments/E02_math_sentence_parser.json)
- [E03_samples_20261110T181103380513](../experiments/E03_samples_20261110T181103380513/)
- [E03_samples_20261110T181202241902](../experiments/E03_samples_20261110T181202241902/)
- [E04_search_before.json](../experiments/E04_search_before.json)
- [E04b_search_before.json](../experiments/E04b_search_before.json)
- [E05_search_after.json](../experiments/E05_search_after.json)
- [E06_public_after_search.json](../experiments/E06_public_after_search.json)
- [E07_calculation_before.json](../experiments/E07_calculation_before.json)
- [E08_calculation_after.json](../experiments/E08_calculation_after.json)
- [E08b_calculation_exact.json](../experiments/E08b_calculation_exact.json)
- [E09_coding_controls_before.json](../experiments/E09_coding_controls_before.json)

</details>

<details>
<summary>E10–E19 · 12 артефактов</summary>

- [E10_coding_controls_after.json](../experiments/E10_coding_controls_after.json)
- [E11_public_after_calculation.json](../experiments/E11_public_after_calculation.json)
- [E12_robustness_before.json](../experiments/E12_robustness_before.json)
- [E13_compatible_cards.json](../experiments/E13_compatible_cards.json)
- [E14_instruction_scope.json](../experiments/E14_instruction_scope.json)
- [E15_csv_selection.json](../experiments/E15_csv_selection.json)
- [E16_public_scope_regression.json](../experiments/E16_public_scope_regression.json)
- [E17_search_scope_regression.json](../experiments/E17_search_scope_regression.json)
- [E18_calculation_scope_regression.json](../experiments/E18_calculation_scope_regression.json)
- [E19_plan_pairs_fixtures_20261110T183750700100](../experiments/E19_plan_pairs_fixtures_20261110T183750700100/)
- [E19_plan_pairs_fixtures_20261110T184024092645](../experiments/E19_plan_pairs_fixtures_20261110T184024092645/)
- [E19_plan_pairs_live_20261110T184402610394](../experiments/E19_plan_pairs_live_20261110T184402610394/)

</details>

<details>
<summary>E20–E29 · 17 артефактов</summary>

- [E20_final_robustness.json](../experiments/E20_final_robustness.json)
- [E21_plan_policy_replay_20261110T184701575283.json](../experiments/E21_plan_policy_replay_20261110T184701575283.json)
- [E21_plan_policy_replay_20261110T185704107323.json](../experiments/E21_plan_policy_replay_20261110T185704107323.json)
- [E22_plan_pairs_fixtures_20261110T184815270949](../experiments/E22_plan_pairs_fixtures_20261110T184815270949/)
- [E22_plan_pairs_live_20261110T185542127852](../experiments/E22_plan_pairs_live_20261110T185542127852/)
- [E23_extended_plan_fixtures_20261110T190011043064](../experiments/E23_extended_plan_fixtures_20261110T190011043064/)
- [E23_extended_plan_live_20261110T190604537158](../experiments/E23_extended_plan_live_20261110T190604537158/)
- [E24_budget_before.json](../experiments/E24_budget_before.json)
- [E25_budget_after.json](../experiments/E25_budget_after.json)
- [E26_main_zero_budget.json](../experiments/E26_main_zero_budget.json)
- [E26b_main_zero_budget.json](../experiments/E26b_main_zero_budget.json)
- [E27_budget_deferred_queue.json](../experiments/E27_budget_deferred_queue.json)
- [E28_sdk_environment.json](../experiments/E28_sdk_environment.json)
- [E28_sdk_workflow_20261110T194720415887.json](../experiments/E28_sdk_workflow_20261110T194720415887.json)
- [E28_sdk_workflow_20261111T144549116172.json](../experiments/E28_sdk_workflow_20261111T144549116172.json)
- [E28_sdk_workflow_20261111T154417297984.json](../experiments/E28_sdk_workflow_20261111T154417297984.json)
- [E29_sdk_cli_20261110T194843489659.json](../experiments/E29_sdk_cli_20261110T194843489659.json)

</details>

<details>
<summary>E30–E39 · 18 артефактов</summary>

- [E31_improved_coding_control.json](../experiments/E31_improved_coding_control.json)
- [E31b_aligned_coding_control.json](../experiments/E31b_aligned_coding_control.json)
- [E33_synthetic_scheduler_zero_budget.json](../experiments/E33_synthetic_scheduler_zero_budget.json)
- [E34_corrected_dev_pool](../experiments/E34_corrected_dev_pool/)
- [E34_corrected_pool_offline_20261111T143437444797](../experiments/E34_corrected_pool_offline_20261111T143437444797/)
- [E34_corrected_pool_offline_20261111T143537495471](../experiments/E34_corrected_pool_offline_20261111T143537495471/)
- [E34_dataset_validation_20261111T143811286722.json](../experiments/E34_dataset_validation_20261111T143811286722.json)
- [E35_budget_recheck.json](../experiments/E35_budget_recheck.json)
- [E35_coding_recheck.json](../experiments/E35_coding_recheck.json)
- [E35_public_offline_20261111T143647051502](../experiments/E35_public_offline_20261111T143647051502/)
- [E35_scope_recheck.json](../experiments/E35_scope_recheck.json)
- [E36_reasoning_pairs_20261111T143702583437](../experiments/E36_reasoning_pairs_20261111T143702583437/)
- [E37_public_sdk_live_20261111T144136908418](../experiments/E37_public_sdk_live_20261111T144136908418/)
- [E38_coding_prompt_plan.json](../experiments/E38_coding_prompt_plan.json)
- [E38_public_sdk_live_20261111T144358316608](../experiments/E38_public_sdk_live_20261111T144358316608/)
- [E39_coding_budget_plan.json](../experiments/E39_coding_budget_plan.json)
- [E39_corrected_pool_offline_20261111T144541222397](../experiments/E39_corrected_pool_offline_20261111T144541222397/)
- [E39_public_sdk_live_20261111T144508572251](../experiments/E39_public_sdk_live_20261111T144508572251/)

</details>

<details>
<summary>E40–E49 · 43 артефактов</summary>

- [E40_corrected_pool_offline_20261111T144612792750](../experiments/E40_corrected_pool_offline_20261111T144612792750/)
- [E40_review_verification.json](../experiments/E40_review_verification.json)
- [E41_family_shift](../experiments/E41_family_shift/)
- [E42_family_offline_20261111T150910996476](../experiments/E42_family_offline_20261111T150910996476/)
- [E42_family_offline_control_20261111T150910713798.json](../experiments/E42_family_offline_control_20261111T150910713798.json)
- [E43_family_noncoding_live_20261111T150954291259](../experiments/E43_family_noncoding_live_20261111T150954291259/)
- [E43_family_noncoding_live_control_20261111T150954079317.json](../experiments/E43_family_noncoding_live_control_20261111T150954079317.json)
- [E44_family_coding_live_20261111T151136429032](../experiments/E44_family_coding_live_20261111T151136429032/)
- [E44_family_coding_live_control_20261111T151136322255.json](../experiments/E44_family_coding_live_control_20261111T151136322255.json)
- [E45_family_offline_replay_20261111T151927379319](../experiments/E45_family_offline_replay_20261111T151927379319/)
- [E45_family_offline_replay_20261111T154401031548](../experiments/E45_family_offline_replay_20261111T154401031548/)
- [E45_family_offline_replay_control_20261111T151927064153.json](../experiments/E45_family_offline_replay_control_20261111T151927064153.json)
- [E45_family_offline_replay_control_20261111T154400555444.json](../experiments/E45_family_offline_replay_control_20261111T154400555444.json)
- [E45_previous_dev_offline_20261111T151927183388](../experiments/E45_previous_dev_offline_20261111T151927183388/)
- [E45_regression_plan.json](../experiments/E45_regression_plan.json)
- [E45_regressions_after.json](../experiments/E45_regressions_after.json)
- [E45_regressions_before.json](../experiments/E45_regressions_before.json)
- [E45_scope_recheck.json](../experiments/E45_scope_recheck.json)
- [E46_budget_comparison_plan.json](../experiments/E46_budget_comparison_plan.json)
- [E46_family_spacious_live_20261111T151541558005](../experiments/E46_family_spacious_live_20261111T151541558005/)
- [E46_family_spacious_live_control_20261111T151541320071.json](../experiments/E46_family_spacious_live_control_20261111T151541320071.json)
- [E46_iteration_summary.json](../experiments/E46_iteration_summary.json)
- [E47_after_process.json](../experiments/E47_after_process.json)
- [E47_before_process.json](../experiments/E47_before_process.json)
- [E47_search_after_20261111T153820223033.json](../experiments/E47_search_after_20261111T153820223033.json)
- [E47_search_before_20261111T153503829235.json](../experiments/E47_search_before_20261111T153503829235.json)
- [E47_search_context](../experiments/E47_search_context/)
- [E47_search_final_20261111T153934832508.json](../experiments/E47_search_final_20261111T153934832508.json)
- [E48_before_process.json](../experiments/E48_before_process.json)
- [E48_deadline_plan.json](../experiments/E48_deadline_plan.json)
- [E48_deadlines_before_20261111T153509470852](../experiments/E48_deadlines_before_20261111T153509470852/)
- [E48b_after_process.json](../experiments/E48b_after_process.json)
- [E48b_deadline_plan.json](../experiments/E48b_deadline_plan.json)
- [E48b_deadlines_after_20261111T153941259620](../experiments/E48b_deadlines_after_20261111T153941259620/)
- [E48b_deadlines_before_20261111T153653412792](../experiments/E48b_deadlines_before_20261111T153653412792/)
- [E49_family_process.json](../experiments/E49_family_process.json)
- [E49_iteration_summary.json](../experiments/E49_iteration_summary.json)
- [E49_old_dev_process.json](../experiments/E49_old_dev_process.json)
- [E49_previous_dev_offline_20261111T154400648036](../experiments/E49_previous_dev_offline_20261111T154400648036/)
- [E49_public_sdk_process.json](../experiments/E49_public_sdk_process.json)
- [E49_scope_process.json](../experiments/E49_scope_process.json)
- [E49_scope_recheck.json](../experiments/E49_scope_recheck.json)
- [E49_unit_regressions.json](../experiments/E49_unit_regressions.json)

</details>

<details>
<summary>E50–E59 · 48 артефактов</summary>

- [E50_connectivity_check.json](../experiments/E50_connectivity_check.json)
- [E50_live_process.json](../experiments/E50_live_process.json)
- [E50_preflight_process.json](../experiments/E50_preflight_process.json)
- [E50_search_live](../experiments/E50_search_live/)
- [E50_search_live_20261111T155649239479](../experiments/E50_search_live_20261111T155649239479/)
- [E50_search_preflight_20261111T155606870448](../experiments/E50_search_preflight_20261111T155606870448/)
- [E51_iteration_summary.json](../experiments/E51_iteration_summary.json)
- [E51_live_process.json](../experiments/E51_live_process.json)
- [E51_preflight_process.json](../experiments/E51_preflight_process.json)
- [E51_search_live](../experiments/E51_search_live/)
- [E51_search_live_20261111T160047726857](../experiments/E51_search_live_20261111T160047726857/)
- [E51_search_preflight_20261111T155916918566](../experiments/E51_search_preflight_20261111T155916918566/)
- [E52_admission_20261111T163014399025.json](../experiments/E52_admission_20261111T163014399025.json)
- [E52_admission_process.json](../experiments/E52_admission_process.json)
- [E52_kb_compaction](../experiments/E52_kb_compaction/)
- [E52_unit_process.json](../experiments/E52_unit_process.json)
- [E53_compaction_live_20261111T163207400174](../experiments/E53_compaction_live_20261111T163207400174/)
- [E53_compaction_preflight_20261111T163119324558](../experiments/E53_compaction_preflight_20261111T163119324558/)
- [E53_connectivity_check.json](../experiments/E53_connectivity_check.json)
- [E53_iteration_summary.json](../experiments/E53_iteration_summary.json)
- [E53_live_process.json](../experiments/E53_live_process.json)
- [E53_preflight_process.json](../experiments/E53_preflight_process.json)
- [E54_after_tests.json](../experiments/E54_after_tests.json)
- [E54_before.json](../experiments/E54_before.json)
- [E54_conflict_live_20261111T163627676731](../experiments/E54_conflict_live_20261111T163627676731/)
- [E54_conflict_live_plan.json](../experiments/E54_conflict_live_plan.json)
- [E54_conflict_plan.json](../experiments/E54_conflict_plan.json)
- [E54_live_process.json](../experiments/E54_live_process.json)
- [E54_live_started.json](../experiments/E54_live_started.json)
- [E54b_replay_plan.json](../experiments/E54b_replay_plan.json)
- [E54b_replay_process.json](../experiments/E54b_replay_process.json)
- [E54b_response_replay_20261111T163904310532.json](../experiments/E54b_response_replay_20261111T163904310532.json)
- [E54b_tests.json](../experiments/E54b_tests.json)
- [E55_evidence](../experiments/E55_evidence/)
- [E55_scope_counterexample.json](../experiments/E55_scope_counterexample.json)
- [E55_tests.json](../experiments/E55_tests.json)
- [E56_connectivity_check.json](../experiments/E56_connectivity_check.json)
- [E56_evidence_live_20261111T165140161443](../experiments/E56_evidence_live_20261111T165140161443/)
- [E56_evidence_preflight_20261111T165028310494](../experiments/E56_evidence_preflight_20261111T165028310494/)
- [E56_iteration_summary.json](../experiments/E56_iteration_summary.json)
- [E56_live_process.json](../experiments/E56_live_process.json)
- [E56_preflight_process.json](../experiments/E56_preflight_process.json)
- [E57_multimodule](../experiments/E57_multimodule/)
- [E58_iteration_summary.json](../experiments/E58_iteration_summary.json)
- [E58_live_process.json](../experiments/E58_live_process.json)
- [E58_multimodule_live_20261111T170751837729](../experiments/E58_multimodule_live_20261111T170751837729/)
- [E58_multimodule_preflight_20261111T170651561506](../experiments/E58_multimodule_preflight_20261111T170651561506/)
- [E59_target_selection](../experiments/E59_target_selection/)

</details>

<details>
<summary>E60–E69 · 24 артефактов</summary>

- [E60_iteration_summary.json](../experiments/E60_iteration_summary.json)
- [E60_live_process.json](../experiments/E60_live_process.json)
- [E60_target_live_20261111T171835906195](../experiments/E60_target_live_20261111T171835906195/)
- [E60_target_preflight_20261111T171757264184](../experiments/E60_target_preflight_20261111T171757264184/)
- [E61_csv_join](../experiments/E61_csv_join/)
- [E62_csv_live_20261111T172729299185](../experiments/E62_csv_live_20261111T172729299185/)
- [E62_csv_preflight_20261111T172642422281](../experiments/E62_csv_preflight_20261111T172642422281/)
- [E62_iteration_summary.json](../experiments/E62_iteration_summary.json)
- [E62_live_process.json](../experiments/E62_live_process.json)
- [E63_join_multiplicity_replay.json](../experiments/E63_join_multiplicity_replay.json)
- [E64_join_confirmation](../experiments/E64_join_confirmation/)
- [E64_join_live_20261111T172948319398](../experiments/E64_join_live_20261111T172948319398/)
- [E64_live_process.json](../experiments/E64_live_process.json)
- [E65_join_plan](../experiments/E65_join_plan/)
- [E66_iteration_summary.json](../experiments/E66_iteration_summary.json)
- [E66_join_plan_live_20261111T184917606241](../experiments/E66_join_plan_live_20261111T184917606241/)
- [E66_join_plan_preflight_20261111T184825334598](../experiments/E66_join_plan_preflight_20261111T184825334598/)
- [E66_live_process.json](../experiments/E66_live_process.json)
- [E67_join_cascade](../experiments/E67_join_cascade/)
- [E68_iteration_summary.json](../experiments/E68_iteration_summary.json)
- [E68_join_cascade_live_20261111T192416238494](../experiments/E68_join_cascade_live_20261111T192416238494/)
- [E68_join_cascade_preflight_20261111T192335510533](../experiments/E68_join_cascade_preflight_20261111T192335510533/)
- [E68_live_process.json](../experiments/E68_live_process.json)
- [E69_join_scope](../experiments/E69_join_scope/)

</details>

<details>
<summary>E70–E79 · 26 артефактов</summary>

- [E70_iteration_summary.json](../experiments/E70_iteration_summary.json)
- [E70_join_scope_live_20261111T193451914965](../experiments/E70_join_scope_live_20261111T193451914965/)
- [E70_join_scope_preflight_20261111T193325571527](../experiments/E70_join_scope_preflight_20261111T193325571527/)
- [E70_join_scope_preflight_20261111T193351568177](../experiments/E70_join_scope_preflight_20261111T193351568177/)
- [E70_live_process.json](../experiments/E70_live_process.json)
- [E71_join_scope_v2](../experiments/E71_join_scope_v2/)
- [E72_iteration_summary.json](../experiments/E72_iteration_summary.json)
- [E72_join_scope_v2_live_20261111T194153615816](../experiments/E72_join_scope_v2_live_20261111T194153615816/)
- [E72_join_scope_v2_preflight_20261111T194121030693](../experiments/E72_join_scope_v2_preflight_20261111T194121030693/)
- [E72_live_process.json](../experiments/E72_live_process.json)
- [E73_local_join](../experiments/E73_local_join/)
- [E74_iteration_summary.json](../experiments/E74_iteration_summary.json)
- [E74_live_process.json](../experiments/E74_live_process.json)
- [E74_local_join_live_20261111T195446466652](../experiments/E74_local_join_live_20261111T195446466652/)
- [E74_local_join_preflight_20261111T195410172202](../experiments/E74_local_join_preflight_20261111T195410172202/)
- [E75_join_or](../experiments/E75_join_or/)
- [E76_iteration_summary.json](../experiments/E76_iteration_summary.json)
- [E76_join_or_live_20261111T200417736373](../experiments/E76_join_or_live_20261111T200417736373/)
- [E76_join_or_preflight_20261111T200340401200](../experiments/E76_join_or_preflight_20261111T200340401200/)
- [E76_live_process.json](../experiments/E76_live_process.json)
- [E77_mixed_integration](../experiments/E77_mixed_integration/)
- [E78_iteration_summary.json](../experiments/E78_iteration_summary.json)
- [E78_live_process.json](../experiments/E78_live_process.json)
- [E78_mixed_live_20261111T201608442567](../experiments/E78_mixed_live_20261111T201608442567/)
- [E78_mixed_offline_20261111T201509931987](../experiments/E78_mixed_offline_20261111T201509931987/)
- [E79_budget_allocation](../experiments/E79_budget_allocation/)

</details>

<details>
<summary>E80–E89 · 17 артефактов</summary>

- [E80_allocation_live_20261111T202642547670](../experiments/E80_allocation_live_20261111T202642547670/)
- [E80_allocation_offline_20261111T202558174651](../experiments/E80_allocation_offline_20261111T202558174651/)
- [E80_iteration_summary.json](../experiments/E80_iteration_summary.json)
- [E80_live_process.json](../experiments/E80_live_process.json)
- [E83_output_contract](../experiments/E83_output_contract/)
- [E84_contract_live_20261112T183041218847](../experiments/E84_contract_live_20261112T183041218847/)
- [E84_contract_offline_20261112T182952520740](../experiments/E84_contract_offline_20261112T182952520740/)
- [E84_contract_replay_20261112T182938180807](../experiments/E84_contract_replay_20261112T182938180807/)
- [E84_iteration_summary.json](../experiments/E84_iteration_summary.json)
- [E84_live_process.json](../experiments/E84_live_process.json)
- [E85_evening](../experiments/E85_evening/)
- [E86_mixed_profile_live_20261112T184718872839](../experiments/E86_mixed_profile_live_20261112T184718872839/)
- [E86_mixed_profile_offline_20261112T184629194636](../experiments/E86_mixed_profile_offline_20261112T184629194636/)
- [E87_numeric_joins](../experiments/E87_numeric_joins/)
- [E88_numeric_joins_live_20261112T185006706656](../experiments/E88_numeric_joins_live_20261112T185006706656/)
- [E88_numeric_joins_offline_20261112T184904104134](../experiments/E88_numeric_joins_offline_20261112T184904104134/)
- [E89_compact_code](../experiments/E89_compact_code/)

</details>

<details>
<summary>E90–E99 · 14 артефактов</summary>

- [E90_compact_code_live_20261112T185243149892](../experiments/E90_compact_code_live_20261112T185243149892/)
- [E90_compact_code_offline_20261112T185216936203](../experiments/E90_compact_code_offline_20261112T185216936203/)
- [E91_final_evening](../experiments/E91_final_evening/)
- [E92_evening_summary.json](../experiments/E92_evening_summary.json)
- [E92_final_mixed_live_20261112T185457604685](../experiments/E92_final_mixed_live_20261112T185457604685/)
- [E92_final_mixed_offline_20261112T185414256185](../experiments/E92_final_mixed_offline_20261112T185414256185/)
- [E93_holdout](../experiments/E93_holdout/)
- [E94_join_holdout_live_20261112T190446912551](../experiments/E94_join_holdout_live_20261112T190446912551/)
- [E94_join_holdout_offline_20261112T190413382377](../experiments/E94_join_holdout_offline_20261112T190413382377/)
- [E95_scheduling](../experiments/E95_scheduling/)
- [E97_csv_output_budget](../experiments/E97_csv_output_budget/)
- [E98_csv_output_budget_live_20261112T190902195039](../experiments/E98_csv_output_budget_live_20261112T190902195039/)
- [E98_csv_output_budget_offline_20261112T190820067893](../experiments/E98_csv_output_budget_offline_20261112T190820067893/)
- [E99_csv_mixed](../experiments/E99_csv_mixed/)

</details>

<details>
<summary>E100–E109 · 23 артефактов</summary>

- [E100_csv_mixed_live_20261112T191039806739](../experiments/E100_csv_mixed_live_20261112T191039806739/)
- [E100_csv_mixed_offline_20261112T190955570624](../experiments/E100_csv_mixed_offline_20261112T190955570624/)
- [E101_scheduling_plans](../experiments/E101_scheduling_plans/)
- [E102_scheduling_reward_live_20261112T191503082994](../experiments/E102_scheduling_reward_live_20261112T191503082994/)
- [E102_scheduling_reward_offline_20261112T191224838249](../experiments/E102_scheduling_reward_offline_20261112T191224838249/)
- [E102_scheduling_roi_live_20261112T191340531205](../experiments/E102_scheduling_roi_live_20261112T191340531205/)
- [E102_scheduling_roi_offline_20261112T191224828262](../experiments/E102_scheduling_roi_offline_20261112T191224828262/)
- [E103_calibrated_ranking](../experiments/E103_calibrated_ranking/)
- [E104_additional_summary.json](../experiments/E104_additional_summary.json)
- [E104_calibrated_live_20261112T191758178660](../experiments/E104_calibrated_live_20261112T191758178660/)
- [E104_calibrated_offline_20261112T191711776345](../experiments/E104_calibrated_offline_20261112T191711776345/)
- [E105_ranking_validation](../experiments/E105_ranking_validation/)
- [E106_ranking_validation_plans](../experiments/E106_ranking_validation_plans/)
- [E107_failure_diagnostics.json](../experiments/E107_failure_diagnostics.json)
- [E107_validation_calibrated_live_20261112T193830637442](../experiments/E107_validation_calibrated_live_20261112T193830637442/)
- [E107_validation_calibrated_offline_20261112T193737362434](../experiments/E107_validation_calibrated_offline_20261112T193737362434/)
- [E107_validation_roi_live_20261112T193957745214](../experiments/E107_validation_roi_live_20261112T193957745214/)
- [E107_validation_roi_offline_20261112T193737357365](../experiments/E107_validation_roi_offline_20261112T193737357365/)
- [E107_validation_summary.json](../experiments/E107_validation_summary.json)
- [E108_regression_fixes](../experiments/E108_regression_fixes/)
- [E109_regression_fixes_live_20261113T063318602203](../experiments/E109_regression_fixes_live_20261113T063318602203/)
- [E109_regression_fixes_offline_20261113T063235865030](../experiments/E109_regression_fixes_offline_20261113T063235865030/)
- [E109_repair_summary.json](../experiments/E109_repair_summary.json)

</details>

<details>
<summary>E110–E119 · 36 артефактов</summary>

- [E110_incoming_context](../experiments/E110_incoming_context/)
- [E111_forward_live_20261113T071534217956](../experiments/E111_forward_live_20261113T071534217956/)
- [E111_forward_offline_20261113T071508218618](../experiments/E111_forward_offline_20261113T071508218618/)
- [E111_incoming_live_20261113T071642353161](../experiments/E111_incoming_live_20261113T071642353161/)
- [E111_incoming_offline_20261113T071508218618](../experiments/E111_incoming_offline_20261113T071508218618/)
- [E111_incoming_summary.json](../experiments/E111_incoming_summary.json)
- [E112_output_floor](../experiments/E112_output_floor/)
- [E113_baseline_live_20261113T072447407100](../experiments/E113_baseline_live_20261113T072447407100/)
- [E113_baseline_offline_20261113T072353443599](../experiments/E113_baseline_offline_20261113T072353443599/)
- [E113_floor_live_20261113T072604402179](../experiments/E113_floor_live_20261113T072604402179/)
- [E113_floor_offline_20261113T072353472630](../experiments/E113_floor_offline_20261113T072353472630/)
- [E113_floor_summary.json](../experiments/E113_floor_summary.json)
- [E114_policy_interaction](../experiments/E114_policy_interaction/)
- [E115_calibrated_baseline_live_20261113T073618652336](../experiments/E115_calibrated_baseline_live_20261113T073618652336/)
- [E115_calibrated_baseline_offline_20261113T073507160423](../experiments/E115_calibrated_baseline_offline_20261113T073507160423/)
- [E115_calibrated_floor_live_20261113T073723124343](../experiments/E115_calibrated_floor_live_20261113T073723124343/)
- [E115_calibrated_floor_offline_20261113T073507187270](../experiments/E115_calibrated_floor_offline_20261113T073507187270/)
- [E115_interaction_summary.json](../experiments/E115_interaction_summary.json)
- [E115_roi_baseline_offline_20261113T073507147902](../experiments/E115_roi_baseline_offline_20261113T073507147902/)
- [E115_roi_floor_offline_20261113T073507170963](../experiments/E115_roi_floor_offline_20261113T073507170963/)
- [E116_production_ranking](../experiments/E116_production_ranking/)
- [E117_production_ranking_live_20261113T074600607836](../experiments/E117_production_ranking_live_20261113T074600607836/)
- [E117_production_ranking_offline_20261113T074153611544](../experiments/E117_production_ranking_offline_20261113T074153611544/)
- [E117_production_ranking_offline_20261113T074250196822](../experiments/E117_production_ranking_offline_20261113T074250196822/)
- [E117_production_ranking_offline_20261113T074513797456](../experiments/E117_production_ranking_offline_20261113T074513797456/)
- [E117_release_summary.json](../experiments/E117_release_summary.json)
- [E118_two_pass](../experiments/E118_two_pass/)
- [E119_baseline_2000_live_20261113T080944482753](../experiments/E119_baseline_2000_live_20261113T080944482753/)
- [E119_baseline_800_live_20261113T080601885281](../experiments/E119_baseline_800_live_20261113T080601885281/)
- [E119_baseline_800_offline_20261113T080424251277](../experiments/E119_baseline_800_offline_20261113T080424251277/)
- [E119_baseline_800_offline_20261113T080511255353](../experiments/E119_baseline_800_offline_20261113T080511255353/)
- [E119_two_pass_2000_live_20261113T080817436293](../experiments/E119_two_pass_2000_live_20261113T080817436293/)
- [E119_two_pass_800_live_20261113T080712278073](../experiments/E119_two_pass_800_live_20261113T080712278073/)
- [E119_two_pass_800_offline_20261113T080424251277](../experiments/E119_two_pass_800_offline_20261113T080424251277/)
- [E119_two_pass_800_offline_20261113T080511252557](../experiments/E119_two_pass_800_offline_20261113T080511252557/)
- [E119_two_pass_summary.json](../experiments/E119_two_pass_summary.json)

</details>

<details>
<summary>E120–E129 · 29 артефактов</summary>

- [E120_math_budget](../experiments/E120_math_budget/)
- [E121_math_budget_2000_live_20261113T081433603684](../experiments/E121_math_budget_2000_live_20261113T081433603684/)
- [E121_math_budget_800_live_20261113T081343489446](../experiments/E121_math_budget_800_live_20261113T081343489446/)
- [E121_math_budget_800_offline_20261113T081250049504](../experiments/E121_math_budget_800_offline_20261113T081250049504/)
- [E121_math_budget_summary.json](../experiments/E121_math_budget_summary.json)
- [E122_compact_math](../experiments/E122_compact_math/)
- [E123_compact_target_summary.json](../experiments/E123_compact_target_summary.json)
- [E123_fresh_baseline_offline_20261113T083227475017](../experiments/E123_fresh_baseline_offline_20261113T083227475017/)
- [E123_fresh_compact_offline_20261113T083227492121](../experiments/E123_fresh_compact_offline_20261113T083227492121/)
- [E123_mixed_offline_20261113T083227492121](../experiments/E123_mixed_offline_20261113T083227492121/)
- [E123_target_2000_live_20261113T083411260381](../experiments/E123_target_2000_live_20261113T083411260381/)
- [E123_target_800_live_20261113T083310708365](../experiments/E123_target_800_live_20261113T083310708365/)
- [E123_target_800_offline_20261113T083227469827](../experiments/E123_target_800_offline_20261113T083227469827/)
- [E124_terse_math](../experiments/E124_terse_math/)
- [E125_fresh_baseline_live_20261113T084025749274](../experiments/E125_fresh_baseline_live_20261113T084025749274/)
- [E125_fresh_baseline_replacement_live_20261113T084305977445](../experiments/E125_fresh_baseline_replacement_live_20261113T084305977445/)
- [E125_fresh_compact_live_20261113T084436544360](../experiments/E125_fresh_compact_live_20261113T084436544360/)
- [E125_target_2000_live_20261113T083841780100](../experiments/E125_target_2000_live_20261113T083841780100/)
- [E125_target_800_live_20261113T083726724471](../experiments/E125_target_800_live_20261113T083726724471/)
- [E125_target_800_offline_20261113T083648876204](../experiments/E125_target_800_offline_20261113T083648876204/)
- [E125_terse_fresh_summary.json](../experiments/E125_terse_fresh_summary.json)
- [E125_terse_target_summary.json](../experiments/E125_terse_target_summary.json)
- [E126_numeric_recheck](../experiments/E126_numeric_recheck/)
- [E127_numeric_recheck_live_20261113T092050095895](../experiments/E127_numeric_recheck_live_20261113T092050095895/)
- [E127_numeric_recheck_offline_20261113T091749750275](../experiments/E127_numeric_recheck_offline_20261113T091749750275/)
- [E127_numeric_recheck_summary.json](../experiments/E127_numeric_recheck_summary.json)
- [E128_submission_acceptance](../experiments/E128_submission_acceptance/)
- [E129_submission_baseline_live_20261113T092505061530](../experiments/E129_submission_baseline_live_20261113T092505061530/)
- [E129_submission_summary.json](../experiments/E129_submission_summary.json)

</details>

<details>
<summary>E130–E139 · 12 артефактов</summary>

- [E130_score_selection](../experiments/E130_score_selection/)
- [E131_known_3000_baseline_live_20261113T094259283535](../experiments/E131_known_3000_baseline_live_20261113T094259283535/)
- [E131_known_3000_terse_live_20261113T094446234677](../experiments/E131_known_3000_terse_live_20261113T094446234677/)
- [E131_known_3000_terse_recheck_live_20261113T094730269617](../experiments/E131_known_3000_terse_recheck_live_20261113T094730269617/)
- [E131_known_3000_terse_recheck_offline_20261113T094208513368](../experiments/E131_known_3000_terse_recheck_offline_20261113T094208513368/)
- [E131_known_3000_terse_recheck_replacement_live_20261113T095202895650](../experiments/E131_known_3000_terse_recheck_replacement_live_20261113T095202895650/)
- [E131_new_2000_baseline_live_20261113T121539956990](../experiments/E131_new_2000_baseline_live_20261113T121539956990/)
- [E131_new_2000_terse_live_20261113T121647421292](../experiments/E131_new_2000_terse_live_20261113T121647421292/)
- [E131_new_800_baseline_live_20261113T121435301685](../experiments/E131_new_800_baseline_live_20261113T121435301685/)
- [E131_new_800_terse_live_20261113T121326610258](../experiments/E131_new_800_terse_live_20261113T121326610258/)
- [E131_score_selection_summary.json](../experiments/E131_score_selection_summary.json)
- [E132_final_selection_release.json](../experiments/E132_final_selection_release.json)

</details>
