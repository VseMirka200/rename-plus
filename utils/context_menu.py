"""Модуль для работы с контекстным меню Windows.

Обеспечивает добавление и удаление пунктов в контекстное меню Windows
для интеграции с приложением Ренейм+.
"""

import logging
import os
import sys
import subprocess

logger = logging.getLogger(__name__)

# Флаг доступности winreg
HAS_WINREG = False
try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False


class ContextMenuManager:
    """Класс для управления контекстным меню Windows."""
    
    # Ключ реестра для контекстного меню файлов
    CONTEXT_MENU_KEY = r"*\shell\RenamePlusConverter"
    # Ключ реестра для контекстного меню папок
    FOLDER_CONTEXT_MENU_KEY = r"Directory\shell\RenamePlusConverter"
    
    def __init__(self):
        """Инициализация менеджера контекстного меню."""
        self.is_available = HAS_WINREG and sys.platform == 'win32'
        if not self.is_available:
            logger.debug("Контекстное меню недоступно (не Windows или winreg не найден)")
    
    def get_script_path(self) -> str:
        """Получение пути к скрипту запуска программы.
        
        Returns:
            Абсолютный путь к скрипту запуска
        """
        # Получаем путь к текущему скрипту
        if getattr(sys, 'frozen', False):
            # Если программа упакована (например, PyInstaller)
            script_path = sys.executable
        else:
            # Если запущена как скрипт
            script_path = os.path.abspath(__file__)
            # Переходим к корню проекта
            project_root = os.path.dirname(os.path.dirname(script_path))
            # Ищем файл запуска
            launch_file = os.path.join(project_root, "Запуск.pyw")
            if os.path.exists(launch_file):
                script_path = launch_file
            else:
                # Fallback на file_renamer.py
                script_path = os.path.join(project_root, "file_renamer.py")
        
        return os.path.normpath(script_path)
    
    def get_python_executable(self) -> str:
        """Получение пути к исполняемому файлу Python.
        
        Returns:
            Путь к python.exe или pythonw.exe
        """
        if getattr(sys, 'frozen', False):
            # Если программа упакована, используем sys.executable
            return sys.executable
        
        # Ищем pythonw.exe (для запуска без консоли)
        pythonw = sys.executable.replace('python.exe', 'pythonw.exe')
        if os.path.exists(pythonw):
            return pythonw
        return sys.executable
    
    def is_installed(self) -> bool:
        """Проверка, установлено ли контекстное меню.
        
        Returns:
            True если установлено, False иначе
        """
        if not self.is_available:
            return False
        
        try:
            # Проверяем ключ для файлов
            key_path = self.CONTEXT_MENU_KEY
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key_path):
                return True
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Ошибка при проверке контекстного меню: {e}", exc_info=True)
            return False
    
    def install(self) -> tuple[bool, str]:
        """Установка контекстного меню.
        
        Returns:
            Кортеж (успех, сообщение)
        """
        if not self.is_available:
            return False, "Контекстное меню недоступно (только для Windows)"
        
        try:
            script_path = self.get_script_path()
            python_exe = self.get_python_executable()
            
            # Создаем ключ для файлов
            key_path = self.CONTEXT_MENU_KEY
            key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path)
            winreg.SetValue(key, None, winreg.REG_SZ, "Добавить в конвертер Ренейм+")
            
            # Устанавливаем флаг для поддержки множественного выбора
            # MultiSelectModel = "Document" позволяет обрабатывать множественный выбор
            # и передавать все файлы одним вызовом команды
            try:
                winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Document")
            except Exception:
                # Если не удалось установить, продолжаем без множественного выбора
                pass
            
            # Создаем подключ command
            command_key = winreg.CreateKey(key, "command")
            
            # Команда для запуска программы с файлами
            # Windows вызывает команду для каждого файла отдельно, даже с MultiSelectModel="Document"
            # Поэтому используем механизм, который уже реализован в обёртке:
            # обёртка собирает файлы через временный файл и блокировку
            if script_path.endswith('.pyw') or script_path.endswith('.py'):
                # Определяем путь к Python-скрипту обёртке
                script_dir = os.path.dirname(script_path)
                wrapper_script = os.path.join(script_dir, "utils", "context_menu_wrapper.py")
                
                # Проверяем, что обертка существует
                if not os.path.exists(wrapper_script):
                    # Если обертка не найдена, используем прямой вызов
                    logger.warning(f"Обертка не найдена: {wrapper_script}, используем прямой вызов")
                    # Используем %1 для одного файла (Windows вызывает команду для каждого файла отдельно)
                    command = f'"{python_exe}" "{script_path}" "%1"'
                else:
                    # Используем обёртку напрямую
                    # Windows будет вызывать команду для каждого файла отдельно
                    # Обёртка соберёт все файлы через временный файл и блокировку
                    # %1 передаёт один файл за раз, обёртка соберёт их все
                    command = f'"{python_exe}" "{wrapper_script}" "%1"'
            else:
                command = f'"{script_path}" "%1"'
            
            winreg.SetValue(command_key, None, winreg.REG_SZ, command)
            
            winreg.CloseKey(command_key)
            winreg.CloseKey(key)
            
            logger.info("Контекстное меню успешно установлено")
            return True, "Контекстное меню успешно установлено"
            
        except PermissionError:
            error_msg = "Недостаточно прав для установки контекстного меню. Запустите программу от имени администратора."
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Ошибка при установке контекстного меню: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def uninstall(self) -> tuple[bool, str]:
        """Удаление контекстного меню.
        
        Returns:
            Кортеж (успех, сообщение)
        """
        if not self.is_available:
            return False, "Контекстное меню недоступно (только для Windows)"
        
        try:
            # Удаляем ключ для файлов
            key_path = self.CONTEXT_MENU_KEY
            try:
                winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, key_path + r"\command")
                winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, key_path)
            except FileNotFoundError:
                # Ключ уже не существует
                pass
            
            logger.info("Контекстное меню успешно удалено")
            return True, "Контекстное меню успешно удалено"
            
        except PermissionError:
            error_msg = "Недостаточно прав для удаления контекстного меню. Запустите программу от имени администратора."
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Ошибка при удалении контекстного меню: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

