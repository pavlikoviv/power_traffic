# Архитектура Power Traffic

## Обзор

Централизованный контроллер нагрузки на канал интернета для множества Windows-хостов (до 190 штук) через iperf3. Контроллер запускается на Ubuntu, управляет удалёнными хостами по SSH с PowerShell, обеспечивает предчек фонового трафика, лимит параллелизма, ретраи с cooldown, непрерывный цикл по расписанию и наблюдаемость статусов в реальном времени.

## Структура проекта

```
power_traffic/
├── pyproject.toml                 # Манифест проекта и зависимости
├── config.example.yaml             # Пример конфигурации кампании
├── src/
│   └── power_traffic/
│       ├── __init__.py            # Версия пакета
│       ├── config.py              # Модель конфигурации и валидация
│       ├── ssh_exec.py            # SSH-исполнитель PowerShell-команд
│       ├── precheck.py            # Предчек фонового трафика
│       ├── orchestrator.py        # Оркестратор кампании и отчёты
│       └── main.py                # Точка входа CLI
└── docs/
    └── architecture.md            # Этот файл
```

## Компоненты

### 1. Конфигурация ([`config.py`](../src/power_traffic/config.py))

**Классы данных:**

- [`HostConfig`](../src/power_traffic/config.py:13) — параметры хоста: имя, адрес, пользователь, путь к SSH-ключу, путь к iperf3, порт SSH.
- [`ScheduleConfig`](../src/power_traffic/config.py:23) — параметры расписания: ежедневное время запуска, флаг непрерывного режима, интервал обновления статусов.
- [`CampaignConfig`](../src/power_traffic/config.py:30) — параметры кампании: время старта, лимит параллелизма, ретраи, cooldown, политики, расписание, список хостов и iperf3-серверов, параметры нагрузки и предчека.

**Функции:**

- [`load_config()`](../src/power_traffic/config.py:51) — загрузка YAML, валидация типов и диапазонов, возврат [`CampaignConfig`](../src/power_traffic/config.py:23).

### 2. SSH-исполнитель ([`ssh_exec.py`](../src/power_traffic/ssh_exec.py))

- [`SSHExecutionError`](../src/power_traffic/ssh_exec.py:9) — исключение при ошибках SSH.
- [`run_powershell()`](../src/power_traffic/ssh_exec.py:13) — запуск PowerShell-скрипта на Windows-хосте по SSH, возврат stdout.

### 3. Предчек фонового трафика ([`precheck.py`](../src/power_traffic/precheck.py))

- [`BackgroundCheckResult`](../src/power_traffic/precheck.py:9) — результат предчека: хост, средний Mbps, лимит, флаг passed.
- [`check_background_traffic()`](../src/power_traffic/precheck.py:16) — PowerShell-запрос счётчиков за n минут, расчёт среднего Mbps, сравнение с лимитом.

### 4. Оркестратор кампании ([`orchestrator.py`](../src/power_traffic/orchestrator.py))

**Классы данных:**

- [`HostRunResult`](../src/power_traffic/orchestrator.py:16) — результат хоста: статус, выбранный сервер, попытки, фон, ошибка, измеренная скорость, время начала/окончания.
- [`CampaignReport`](../src/power_traffic/orchestrator.py:24) — отчёт кампании: время начала/окончания, общее число хостов, список результатов.

**Функции:**

- [`wait_until_start()`](../src/power_traffic/orchestrator.py:39) — ожидание времени старта кампании.
- [`wait_until_next_daily()`](../src/power_traffic/orchestrator.py:46) — ожидание следующего ежедневного запуска.
- [`_print_status_table()`](../src/power_traffic/orchestrator.py:118) — вывод таблицы статусов в консоль.
- [`_write_status_file()`](../src/power_traffic/orchestrator.py:130) — запись статусов в JSON-файл.
- [`_start_status_updater()`](../src/power_traffic/orchestrator.py:137) — запуск фонового потока обновления статусов.
- [`_build_iperf_command()`](../src/power_traffic/orchestrator.py:59) — формирование команды iperf3 с JSON-выводом.
- [`_parse_measured_mbps()`](../src/power_traffic/orchestrator.py:65) — парсинг JSON iperf3, расчёт Mbps.
- [`_within_tolerance()`](../src/power_traffic/orchestrator.py:71) — проверка попадания измеренной скорости в target_rate ± tolerance_percent.
- [`_run_for_host()`](../src/power_traffic/orchestrator.py:77) — полный цикл хоста: предчек → host_background_busy с cooldown → выбор сервера → запуск iperf3 → ретраи с cooldown → финальный статус, с колбэком статусов.
- [`run_campaign()`](../src/power_traffic/orchestrator.py:153) — запуск кампании: ожидание старта, параллельное выполнение с лимитом `max_concurrent_hosts`, обновление статусов в реальном времени, сбор отчёта.
- [`run_continuous()`](../src/power_traffic/orchestrator.py:198) — непрерывный цикл: запуск кампании, сохранение отчёта с таймштампом, ожидание следующего ежедневного запуска.

### 5. Точка входа ([`main.py`](../src/power_traffic/main.py))

- [`build_parser()`](../src/power_traffic/main.py:10) — CLI-аргументы: `--config`, `--report`, `--status-file`, `--continuous`.
- [`main()`](../src/power_traffic/main.py:21) — загрузка конфигурации, запуск кампании или непрерывного режима, сохранение JSON-отчёта.

## Конфигурация

Пример: [`config.example.yaml`](../config.example.yaml)

**Секции:**

- `campaign` — время старта, лимит параллелизма, число ретраев, cooldown между ретраями, cooldown после `host_background_busy`, политика продолжения при сбое хоста, флаг случайного выбора сервера, расписание.
- `campaign.schedule` — ежедневное время запуска, флаг непрерывного режима, интервал обновления статусов.
- `traffic` — целевая скорость (Mbps), допустимая погрешность (%), длительность теста (сек).
- `precheck` — лимит фонового трафика (Mbps), окно измерения (мин).
- `inventory` — список iperf3-серверов, список хостов с параметрами подключения.

## Статусы хоста

- `planned` — хост в очереди.
- `host_background_busy` — фон превышает лимит, ожидание `background_busy_cooldown_seconds`.
- `running` — нагрузка выполняется.
- `retrying` — повторная попытка после ошибки или выхода за погрешность.
- `completed` — успешно завершено, измеренная скорость в пределах погрешности.
- `skipped_after_retries` — исчерпаны ретраи.
- `failed_unreachable` — недоступен по SSH или ошибка предчека.

## Отчёт кампании

JSON-файл (по умолчанию `campaign_report.json`) с полями:

- `started_at` — ISO-8601 время начала.
- `finished_at` — ISO-8601 время окончания.
- `total_hosts` — общее число хостов.
- `results` — массив [`HostRunResult`](../src/power_traffic/orchestrator.py:13) по каждому хосту.

## Запуск

### Одиночный запуск

```bash
pip install -e .
power-traffic --config config.example.yaml --report campaign_report.json
```

### Непрерывный режим по расписанию

```bash
power-traffic --config config.example.yaml --continuous
```

В непрерывном режиме:
- Кампания запускается ежедневно в `schedule.daily_start_time`
- Статусы хостов обновляются в консоли и файле `campaign_status.json` каждые `status_update_interval_seconds`
- Отчёты сохраняются с таймштампом: `campaign_report_YYYYMMDD_HHMMSS.json`
- Цикл продолжается бесконечно до остановки процесса

## Зависимости

- Python ≥3.11
- PyYAML ≥6.0.1
- SSH-ключи для доступа к Windows-хостам
- iperf3 на Windows-хостах (по умолчанию `C:\Tools\iperf3\iperf3.exe`)
- iperf3-серверы, доступные по VPN
- Консоль с поддержкой ANSI-кодов для обновления статусов в реальном времени
