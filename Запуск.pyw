"""
Файл для запуска программы "Назови" по двойному клику
Использует .pyw расширение для запуска без консоли
"""

import sys
import os

# Установка кодировки UTF-8 для корректного отображения русских символов
if sys.platform == 'win32':
    try:
        # Пытаемся установить UTF-8 кодировку
        if hasattr(sys, 'setdefaultencoding'):
            sys.setdefaultencoding('utf-8')
    except:
        pass

# Переход в директорию скрипта
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Импорт и запуск основного приложения
try:
    from file_renamer import main
    
    if __name__ == "__main__":
        main()
except Exception as e:
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
    except:
        # Если даже диалог не работает, пробуем через консоль
        try:
            print("Ошибка запуска программы:")
            print(str(e))
            print("\nУбедитесь, что установлен Python 3.7+")
            input("\nНажмите Enter для выхода...")
        except:
            pass

