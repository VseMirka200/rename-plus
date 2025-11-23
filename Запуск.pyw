"""
Файл для запуска программы "Назови" по двойному клику
Использует .pyw расширение для запуска без консоли
"""

import sys
import os

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
    import tkinter.messagebox as messagebox
    import tkinter as tk
    
    root = tk.Tk()
    root.withdraw()  # Скрываем главное окно
    messagebox.showerror("Ошибка запуска", 
                        f"Не удалось запустить программу:\n{str(e)}\n\n"
                        "Убедитесь, что установлен Python 3.7+")
    root.destroy()

