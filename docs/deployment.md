# Руководство по установке и запуску Power Traffic

## Обзор

Power Traffic состоит из трёх типов узлов:
1. **Сервер контроллера** — Ubuntu-машина, запускающая кампании нагрузки
2. **iperf3-серверы** — серверы iperf3, принимающие нагрузку
3. **Windows-хосты** — клиенты iperf3, генерирующие нагрузку

## Требования

### Сервер контроллера (Ubuntu)
- Ubuntu 20.04+ или совместимый дистрибутив
- Python 3.11+
- SSH-доступ до Windows-хостов
- Доступ к iperf3-серверам по VPN
- Консоль с поддержкой ANSI-кодов (опционально)

### iperf3-серверы
- Linux или Windows
- iperf3 версии 3.1+
- Доступность по VPN из контроллера и Windows-хостов
- Открытый порт 5201 (по умолчанию)

### Windows-хосты
- Windows 10/11 или Server 2016+
- OpenSSH Server установлен и запущен
- PowerShell 5.1+
- iperf3 клиент (по умолчанию `C:\Tools\iperf3\iperf3.exe`)
- SSH-ключи для аутентификации

## Установка

### 1. Настройка iperf3-серверов

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install iperf3 -y
sudo systemctl enable iperf3
sudo systemctl start iperf3
```

Проверка работы:
```bash
iperf3 -s
```

#### Windows
1. Скачайте iperf3 с https://iperf.fr/iperf-download.php
2. Распакуйте в `C:\Tools\iperf3\`
3. Запустите сервер:
```powershell
& 'C:\Tools\iperf3\iperf3.exe' -s
```

Для автозапуска создайте службу через `sc` или `nssm`.

### 2. Настройка Windows-хостов

#### Установка OpenSSH Server
```powershell
# Проверьте, установлен ли OpenSSH
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH*'

# Если не установлен, установите
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Запустите службу
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'
# Фаервол
New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (inbound TCP)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22

# Разрешите вход по ключам (опционально, если используется пароль)
# В файле C:\ProgramData\ssh\sshd_config установите:
# PubkeyAuthentication yes
# Перезапустите службу
Restart-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'
```

#### Установка iperf3 клиента
1. Скачайте iperf3 с https://iperf.fr/iperf-download.php
2. Распакуйте в `C:\Tools\iperf3\`
3. Добавьте путь в PATH (опционально)

#### Настройка SSH-ключей
На контроллере:
```bash
#ssh-keygen -t ed25519 -f /opt/power_traffic/keys/host-001
#ssh-keygen -t ed25519 -f ~/.ssh/host-001
#
chmod 600 ~/.ssh/id_rsa
```

На Windows-хосте:
```powershell
# Создайте директорию .ssh
New-Item -Path "$env:USERPROFILE\.ssh" -ItemType Directory -Force

# Скопируйте публичный ключ в authorized_keys
# Содержимое публичного ключа (/opt/power_traffic/keys/host-001.pub) добавьте в:
# C:\Users\<username>\.ssh\authorized_keys
```

Проверка SSH-доступа с контроллера:
```bash
ssh -i /opt/power_traffic/keys/host-001 -p 22 traffic_user@10.200.0.21 powershell -Command "Get-Host"
```

### 3. Установка контроллера на Ubuntu

#### Клонирование проекта
```bash
cd /opt
git clone https://github.com/pavlikoviv/power_traffic.git power_traffic
cd power_traffic
```

#### Установка зависимостей
```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

#### Создание директории для ключей
```bash
mkdir -p /opt/power_traffic/keys
chmod 700 /opt/power_traffic/keys
```

#### Настройка конфигурации
Скопируйте пример конфигурации:
```bash
cp config.example.yaml config.yaml
```

Отредактируйте `config.yaml`:
```yaml
campaign:
  campaign_start_time: "2026-02-23T12:00:00+03:00"
  max_concurrent_hosts: 20
  retry_count: 3
  retry_cooldown_seconds: 30
  background_busy_cooldown_seconds: 120
  continue_on_host_failure: true
  random_server_selection: true
  schedule:
    daily_start_time: "12:00:00+03:00"
    continuous_mode: true
    status_update_interval_seconds: 5

traffic:
  target_rate_mbps: 80
  tolerance_percent: 10
  test_duration_seconds: 120

precheck:
  background_limit_mbps: 10
  background_window_minutes: 3

inventory:
  iperf3_servers:
    - "10.100.0.10"
    - "10.100.0.11"
    - "10.100.0.12"
  hosts:
    - name: "host-001"
      address: "10.200.0.21"
      user: "traffic_user"
      ssh_key_path: "/opt/power_traffic/keys/host-001"
      iperf3_path: "C:\\Tools\\iperf3\\iperf3.exe"
      ssh_port: 22
```

## Запуск

### Одиночный запуск кампании
```bash
cd /opt/power_traffic
source venv/bin/activate
power-traffic --config config.yaml --report campaign_report.json
```

### Непрерывный режим по расписанию
```bash
cd /opt/power_traffic
source venv/bin/activate
power-traffic --config config.yaml --continuous
```

### Запуск как службы (systemd)

Создайте файл `/etc/systemd/system/power-traffic.service`:
```ini
[Unit]
Description=Power Traffic Controller
After=network.target

[Service]
Type=simple
User=traffic_user
WorkingDirectory=/opt/power_traffic
Environment="PATH=/opt/power_traffic/venv/bin"
ExecStart=/opt/power_traffic/venv/bin/power-traffic --config /opt/power_traffic/config.yaml --continuous
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активируйте службу:
```bash
sudo systemctl daemon-reload
sudo systemctl enable power-traffic
sudo systemctl start power-traffic
sudo systemctl status power-traffic
```

## Мониторинг

### Консольный вывод
В консоли отображается таблица статусов в реальном времени:
```
Host                 Status                    Server               Attempts   Bg Mbps    Meas Mbps
----------------------------------------------------------------------------------------------------
host-001             running                   10.100.0.10          1 5.234       -
host-002             host_background_busy       -                     1 15.678      -
host-003             completed                 10.100.0.11          1 3.456       79.876
```

### Файл статусов
`campaign_status.json` обновляется каждые `status_update_interval_seconds`:
```json
[
  {
    "host": "host-001",
    "status": "running",
    "selected_server": "10.100.0.10",
    "attempts": 1,
    "background_mbps": 5.234,
    "error": null,
    "measured_mbps": null,
    "started_at": "2026-02-23T12:00:01.123456",
    "finished_at": null
  }
]
```

### Итоговые отчёты
В непрерывном режиме отчёты сохраняются с таймштампом:
```
campaign_report_20260223_120000.json
campaign_report_20260224_120000.json
```

## Тестирование

### Проверка SSH-доступа
```bash
ssh -i /opt/power_traffic/keys/host-001 -p 22 traffic_user@10.200.0.21 powershell -Command "Get-Host"
```

### Проверка iperf3-сервера
```bash
iperf3 -c 10.100.0.10 -t 5
```

### Проверка предчека фонового трафика
Запустите одиночный хост для проверки:
```bash
# Создайте тестовую конфигурацию с одним хостом
power-traffic --config test_config.yaml --report test_report.json
```

## Устранение неполадок

### Ошибка SSH-доступа
- Проверьте, что OpenSSH Server запущен: `Get-Service sshd`
- Проверьте правила брандмауэра: `New-NetFirewallRule -DisplayName "SSH" -Direction Inbound -LocalPort 22 -Protocol TCP -Action Allow`
- Проверьте права на файл authorised_keys: `icacls C:\Users\<username>\.ssh\authorized_keys`

### Ошибка iperf3
- Проверьте путь к iperf3 на Windows-хосте
- Проверьте, что iperf3-сервер доступен: `iperf3 -c <server> -t 5`
- Проверьте правила брандмауэра на порту 5201

### Ошибка предчека фонового трафика
- Проверьте, что PowerShell выполняется: `powershell -Command "Get-Host"`
- Проверьте наличие счётчиков: `Get-Counter -ListSet 'Network Interface'`
- Убедитесь, что на хосте есть активный сетевой интерфейс

### Проблемы с расписанием
- Проверьте часовой пояс в `campaign_start_time` и `daily_start_time`
- Проверьте, что системное время синхронизировано: `timedatectl status`
- Проверьте логи службы: `journalctl -u power-traffic -f`

## Безопасность

### Рекомендации
- Используйте отдельного пользователя `traffic_user` на Windows-хостах
- Ограничьте права SSH-ключей: `chmod 600 /opt/power_traffic/keys/*`
- Используйте VPN для изоляции трафика
- Регулярно обновляйте iperf3 и OpenSSH Server
- Логируйте все SSH-соединения

### Аудит
- Проверяйте логи SSH: `/var/log/auth.log` на контроллере
- Проверяйте логи Windows: `Get-WinEvent -LogName Security | Where-Object Id -eq 4624`
- Анализируйте отчёты кампаний для выявления аномалий
