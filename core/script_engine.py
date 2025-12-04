"""Модуль для выполнения пользовательских скриптов."""

import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ScriptEngine:
    """Класс для выполнения пользовательских скриптов."""
    
    def __init__(self):
        """Инициализация движка скриптов."""
        self.scripts_dir = os.path.join(
            os.path.expanduser("~"),
            ".rename_plus_scripts"
        )
        self._ensure_scripts_dir()
    
    def _ensure_scripts_dir(self):
        """Создание директории для скриптов."""
        try:
            os.makedirs(self.scripts_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Не удалось создать директорию для скриптов: {e}")
    
    def execute_script(self, script_path: str, context: Dict[str, Any]) -> Optional[Any]:
        """Выполнение скрипта.
        
        Args:
            script_path: Путь к скрипту
            context: Контекст выполнения (file_data, methods и т.д.)
            
        Returns:
            Результат выполнения скрипта или None
        """
        if not os.path.exists(script_path):
            logger.error(f"Скрипт не найден: {script_path}")
            return None
        
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                script_code = f.read()
            
            # Безопасное выполнение скрипта
            # Ограничиваем доступные функции
            safe_globals = {
                '__builtins__': {
                    'len': len,
                    'str': str,
                    'int': int,
                    'float': float,
                    'bool': bool,
                    'list': list,
                    'dict': dict,
                    'tuple': tuple,
                    'range': range,
                    'enumerate': enumerate,
                    'zip': zip,
                    'min': min,
                    'max': max,
                    'sum': sum,
                    'abs': abs,
                    'round': round,
                },
                'os': os,
                're': __import__('re'),
            }
            
            # Добавляем контекст
            safe_globals.update(context)
            
            # Выполняем скрипт
            exec(script_code, safe_globals)
            
            # Возвращаем результат, если есть функция main
            if 'main' in safe_globals and callable(safe_globals['main']):
                return safe_globals['main']()
            
            return None
        except Exception as e:
            logger.error(f"Ошибка выполнения скрипта {script_path}: {e}", exc_info=True)
            return None
    
    def validate_script(self, script_path: str) -> Tuple[bool, Optional[str]]:
        """Валидация скрипта.
        
        Args:
            script_path: Путь к скрипту
            
        Returns:
            Tuple[валиден, сообщение_об_ошибке]
        """
        if not os.path.exists(script_path):
            return False, "Скрипт не найден"
        
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                script_code = f.read()
            
            # Компилируем для проверки синтаксиса
            compile(script_code, script_path, 'exec')
            return True, None
        except SyntaxError as e:
            return False, f"Синтаксическая ошибка: {e}"
        except Exception as e:
            return False, f"Ошибка: {e}"

