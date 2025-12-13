"""Файл запуска приложения "Ренейм+".

Этот файл предназначен для запуска приложения по двойному клику.
Использует расширение .pyw для запуска без отображения консольного окна.

Основные функции:
- Настройка логирования
- Установка кодировки UTF-8 для Windows
- Импорт и запуск основного модуля приложения
- Обработка критических ошибок с показом диалогового окна
"""

import logging
import os
import sys

# Проверка версии Python
if sys.version_info < (3, 7):
    print("Ошибка: Требуется Python 3.7 или выше")
    print(f"Текущая версия: {sys.version}")
    sys.exit(1)

# Настройка логирования
# Используем WARNING по умолчанию, DEBUG только если установлена переменная окружения
log_level = logging.DEBUG if os.getenv('DEBUG', '').lower() == 'true' else logging.WARNING

# Получаем путь к файлу лога из констант
try:
    from config.constants import get_log_file_path
    log_file_path = get_log_file_path()
except ImportError:
    # Если не удалось импортировать, используем директорию скрипта
    app_data_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(app_data_dir, "logs")
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir, exist_ok=True)
        except (OSError, PermissionError):
            pass
    log_file_path = os.path.join(logs_dir, "rename-plus.log")

# Очищаем старый лог при запуске
if os.path.exists(log_file_path):
    try:
        with open(log_file_path, 'w', encoding='utf-8') as f:
            f.write('')  # Очищаем файл
    except (OSError, PermissionError):
        pass  # Игнорируем ошибки очистки

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(
            log_file_path,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Установка кодировки UTF-8 для корректного отображения русских символов
# В Python 3 кодировка по умолчанию уже UTF-8, поэтому setdefaultencoding не нужен
# Если нужна настройка для вывода в консоль Windows:
if sys.platform == 'win32':
    try:
        # Настройка кодировки для stdout/stderr в Windows
        if sys.stdout.encoding != 'utf-8':
            import io
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding='utf-8'
            )
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding='utf-8'
            )
    except (OSError, AttributeError, ValueError) as e:
        logger.debug(f"Не удалось установить кодировку: {e}")

# Переход в директорию скрипта
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Импорт и запуск основного приложения
try:
    # Фильтруем аргументы командной строки ПЕРЕД любыми импортами
    # Удаляем аргументы, которые выглядят как опции, но не являются файлами
    # Это предотвращает ошибки "unknown option" при запуске через контекстное меню
    # ВАЖНО: Эта фильтрация должна происходить ДО любого импорта, который может использовать argparse
    
    # Логирование для отладки - ВСЕГДА логируем, даже если аргументов нет
    try:
        debug_msg = f"Запуск программы. Исходные аргументы (всего {len(sys.argv)}): {sys.argv}"
        logger.info(debug_msg)
        if len(sys.argv) > 1:
            logger.info(f"Аргументы для обработки: {sys.argv[1:]}")
        else:
            logger.info("Аргументы командной строки отсутствуют")
    except (OSError, AttributeError) as e:
        logger.error(f"Ошибка при логировании аргументов: {e}")
    
    filtered_args = [sys.argv[0]]  # Сохраняем имя скрипта
    
    # Обрабатываем все аргументы
    for arg in sys.argv[1:]:
        # Пропускаем пустые аргументы
        if not arg or not arg.strip():
            continue
            
        # Пропускаем аргументы, которые выглядят как опции (начинаются с -)
        # но проверяем, не является ли это путем к файлу
        if arg.startswith('-'):
            # Проверяем, существует ли это как файл
            # Сначала пробуем как есть
            normalized_arg = os.path.normpath(arg)
            
            # Проверяем как абсолютный путь
            file_exists = False
            if os.path.exists(normalized_arg) and os.path.isfile(normalized_arg):
                file_exists = True
            else:
                # Проверяем как относительный путь от текущей директории
                try:
                    abs_path = os.path.abspath(normalized_arg)
                    if os.path.exists(abs_path) and os.path.isfile(abs_path):
                        file_exists = True
                except (OSError, ValueError):
                    pass
            
            # Если это файл, добавляем его
            if file_exists:
                filtered_args.append(arg)
            # Иначе пропускаем (это опция, которую мы не знаем, например -state)
        else:
            # Обычный аргумент (не начинается с -), добавляем
            filtered_args.append(arg)
    
    # Заменяем sys.argv на отфильтрованные аргументы ДО импорта
    # Это критически важно - если импорт использует argparse, он не увидит неизвестные опции
    sys.argv = filtered_args
    
    # Логирование для отладки - ВСЕГДА логируем результат фильтрации
    try:
        debug_msg = f"Отфильтрованные аргументы (всего {len(filtered_args)}): {filtered_args}"
        logger.info(debug_msg)
        if len(filtered_args) > 1:
            logger.info(f"Файлы для передачи в программу: {filtered_args[1:]}")
        else:
            logger.info("После фильтрации файлов не осталось")
    except (OSError, AttributeError) as e:
        logger.error(f"Ошибка при логировании отфильтрованных аргументов: {e}")
    
    from file_renamer import main
    
    if __name__ == "__main__":
        main()
except Exception as e:
    logger.error(f"Критическая ошибка при запуске программы: {e}", exc_info=True)
    # Если произошла ошибка, показываем сообщение
    try:
        import tkinter as tk
        import tkinter.messagebox as messagebox
        
        root = tk.Tk()
        root.withdraw()  # Скрываем главное окно
        
        # Формируем сообщение об ошибке с правильной кодировкой
        error_msg = "Не удалось запустить программу:\n\n"
        error_msg += str(e) + "\n\n"
        error_msg += "Убедитесь, что установлен Python 3.7+"
        
        messagebox.showerror("Ошибка запуска", error_msg)
        root.destroy()
    except (tk.TclError, AttributeError, RuntimeError) as dialog_error:
        logger.error(f"Не удалось показать диалог ошибки: {dialog_error}", exc_info=True)
        # Если даже диалог не работает, пробуем через консоль
        try:
            print("Ошибка запуска программы:")
            print(str(e))
            print("\nУбедитесь, что установлен Python 3.7+")
            input("\nНажмите Enter для выхода...")
        except (EOFError, KeyboardInterrupt, OSError):
            pass