"""Обертка для контекстного меню Windows.

Этот скрипт собирает все файлы из аргументов командной строки
и передает их основной программе одним вызовом.
Использует механизм блокировки для предотвращения множественного запуска.
"""

import sys
import os
import subprocess
import time
import tempfile
import logging

# Импорт для атомарной блокировки (Windows)
if sys.platform == 'win32':
    try:
        import msvcrt
        HAS_MSVCRT = True
    except ImportError:
        HAS_MSVCRT = False
else:
    HAS_MSVCRT = False

# Импорт валидатора путей
try:
    from utils.path_validator import validate_file_paths
    HAS_PATH_VALIDATOR = True
except ImportError:
    HAS_PATH_VALIDATOR = False

# Настройка логирования для отладки
try:
    from config.constants import get_context_menu_wrapper_log_path
    log_file = get_context_menu_wrapper_log_path()
except ImportError:
    # Fallback если константы не загружены
    app_data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(app_data_dir, "logs")
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir, exist_ok=True)
        except (OSError, PermissionError):
            pass
    log_file = os.path.join(logs_dir, "context_menu_wrapper.log")

# Очищаем старый лог при запуске обёртки
if os.path.exists(log_file):
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('')  # Очищаем файл
    except (OSError, PermissionError) as e:
        # Игнорируем ошибки очистки, но логируем
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)

logger.info(f"Обертка запущена. Аргументы: {sys.argv}")

# Получаем путь к основному скрипту
script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
launch_script = os.path.join(script_dir, "Запуск.pyw")
logger.info(f"Путь к скрипту запуска: {launch_script}")

# Получаем путь к Python
python_exe = sys.executable.replace('python.exe', 'pythonw.exe')
if not os.path.exists(python_exe):
    python_exe = sys.executable
logger.info(f"Python executable: {python_exe}")

# Получаем все аргументы (файлы)
files = sys.argv[1:] if len(sys.argv) > 1 else []
logger.info(f"Получено аргументов: {len(files)}")
if files:
    logger.info(f"Первый файл: {files[0]}")

# Валидируем и фильтруем файлы (безопасность)
if HAS_PATH_VALIDATOR:
    valid_files = validate_file_paths(files)
else:
    # Fallback: базовая проверка
    valid_files = []
    for f in files:
        try:
            if f and isinstance(f, str) and os.path.isfile(f) and '..' not in f:
                abs_path = os.path.abspath(f)
                if os.path.isfile(abs_path):
                    valid_files.append(f)
        except (OSError, ValueError):
            continue
logger.info(f"Валидных файлов: {len(valid_files)}")

# Используем временный файл для сбора всех файлов
# Это позволяет собрать файлы даже если обертка вызывается несколько раз
temp_dir = tempfile.gettempdir()
lock_file = os.path.join(temp_dir, "rename_plus_context_menu.lock")
files_list_file = os.path.join(temp_dir, "rename_plus_files_list.txt")

# Записываем файлы в список (даже если их нет, чтобы проверить механизм)
if valid_files:
    try:
        with open(files_list_file, 'a', encoding='utf-8') as f:
            for file_path in valid_files:
                f.write(file_path + '\n')
        logger.info(f"Записано {len(valid_files)} файлов в список")
    except Exception as e:
        logger.error(f"Ошибка при записи файлов в список: {e}")

# Проверяем, есть ли блокировка (программа уже запускается)
# Используем атомарную блокировку для предотвращения race condition
lock_acquired = False
if sys.platform == 'win32' and HAS_MSVCRT:
    # Атомарная блокировка для Windows
    try:
        lock_fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(lock_fd, 'w') as f:
            f.write(str(time.time()))
        lock_acquired = True
        logger.info("Создана атомарная блокировка")
    except (OSError, FileExistsError):
        # Файл уже существует, другой процесс работает
        logger.info("Блокировка уже существует, пропускаем запуск")
        lock_acquired = False
    except Exception as e:
        logger.error(f"Ошибка при создании блокировки: {e}")
        lock_acquired = False
else:
    # Fallback: проверка существования (не атомарно, но лучше чем ничего)
    if not os.path.exists(lock_file):
        try:
            with open(lock_file, 'x') as f:  # 'x' режим создает файл только если его нет
                f.write(str(time.time()))
            lock_acquired = True
            logger.info("Создана блокировка")
        except FileExistsError:
            logger.info("Блокировка уже существует, пропускаем запуск")
            lock_acquired = False
        except (OSError, PermissionError) as e:
            logger.error(f"Ошибка при создании блокировки: {e}")
            lock_acquired = False
    else:
        logger.info("Блокировка уже существует, пропускаем запуск")
        lock_acquired = False

if lock_acquired:
    
    # Небольшая задержка для сбора всех файлов
    logger.info("Ожидание сбора всех файлов...")
    time.sleep(0.8)  # Увеличиваем задержку
    
    # Читаем все файлы из списка
    all_files = []
    if os.path.exists(files_list_file):
        try:
            with open(files_list_file, 'r', encoding='utf-8') as f:
                all_files = [line.strip() for line in f.readlines() if line.strip()]
            logger.info(f"Прочитано {len(all_files)} файлов из списка")
            # Удаляем файл списка
            try:
                os.remove(files_list_file)
            except (OSError, FileNotFoundError):
                pass
        except Exception as e:
            logger.error(f"Ошибка при чтении файлов из списка: {e}")
    
    # Если файлов нет в списке, используем текущие
    if not all_files and valid_files:
        all_files = valid_files
        logger.info("Используем текущие файлы (список пуст)")
    
    # Удаляем дубликаты
    all_files = list(dict.fromkeys(all_files))
    logger.info(f"Всего уникальных файлов: {len(all_files)}")
    
    # Запускаем основную программу со всеми файлами
    if all_files:
        cmd = [python_exe, launch_script] + all_files
        logger.info(f"Запускаем программу с {len(all_files)} файлами")
        logger.info(f"Команда: {python_exe} {launch_script} ... ({len(all_files)} файлов)")
        try:
            process = subprocess.Popen(
                cmd, 
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            logger.info(f"Программа запущена успешно, PID: {process.pid}")
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            logger.error(f"Ошибка при запуске программы: {e}", exc_info=True)
    else:
        logger.warning("Нет файлов для запуска программы")
    
    # Удаляем блокировку через небольшую задержку
    time.sleep(1)
    try:
        if os.path.exists(lock_file):
            os.remove(lock_file)
            logger.info("Блокировка удалена")
    except (OSError, FileNotFoundError) as e:
        logger.error(f"Ошибка при удалении блокировки: {e}")
