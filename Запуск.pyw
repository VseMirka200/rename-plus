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
import sys
import os

# Настройка логирования
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.expanduser("~"), ".nazovi.log"), encoding='utf-8'),
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
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception as e:
        logger.debug(f"Не удалось установить кодировку: {e}")

# Переход в директорию скрипта
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Импорт и запуск основного приложения
try:
    from file_renamer import main
    
    if __name__ == "__main__":
        main()
except Exception as e:
    logger.error(f"Критическая ошибка при запуске программы: {e}", exc_info=True)
    # Если произошла ошибка, показываем сообщение
    try:
        import tkinter.messagebox as messagebox
        import tkinter as tk
        
        root = tk.Tk()
        root.withdraw()  # Скрываем главное окно
        
        # Формируем сообщение об ошибке с правильной кодировкой
        error_msg = "Не удалось запустить программу:\n\n"
        error_msg += str(e) + "\n\n"
        error_msg += "Убедитесь, что установлен Python 3.7+"
        
        messagebox.showerror("Ошибка запуска", error_msg)
        root.destroy()
    except Exception as dialog_error:
        logger.error(f"Не удалось показать диалог ошибки: {dialog_error}", exc_info=True)
        # Если даже диалог не работает, пробуем через консоль
        try:
            print("Ошибка запуска программы:")
            print(str(e))
            print("\nУбедитесь, что установлен Python 3.7+")
            input("\nНажмите Enter для выхода...")
        except Exception:
            pass