"""Модуль для управления историей операций переименования."""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

try:
    from config.constants import HISTORY_FILE, MAX_HISTORY_ITEMS
except ImportError:
    # Fallback если константы не доступны
    HISTORY_FILE = ".rename_plus_history.json"
    MAX_HISTORY_ITEMS = 100

logger = logging.getLogger(__name__)


class HistoryManager:
    """Класс для управления историей операций."""
    
    def __init__(self, history_file: Optional[str] = None):
        """Инициализация менеджера истории.
        
        Args:
            history_file: Путь к файлу истории
        """
        if history_file is None:
            history_file = os.path.join(
                os.path.expanduser("~"), HISTORY_FILE
            )
        self.history_file = history_file
        self.history: List[Dict] = []
        self.load_history()
    
    def load_history(self) -> None:
        """Загрузка истории из файла."""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
                if not isinstance(self.history, list):
                    self.history = []
        except Exception as e:
            logger.error(f"Ошибка загрузки истории: {e}")
            self.history = []
    
    def save_history(self) -> bool:
        """Сохранение истории в файл.
        
        Returns:
            True если успешно, False в противном случае
        """
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения истории: {e}")
            return False
    
    def add_operation(self, operation_type: str, files: List[Dict], 
                     success_count: int, error_count: int) -> None:
        """Добавление операции в историю.
        
        Args:
            operation_type: Тип операции (rename, undo, redo и т.д.)
            files: Список файлов
            success_count: Количество успешных операций
            error_count: Количество ошибок
        """
        operation = {
            'timestamp': datetime.now().isoformat(),
            'type': operation_type,
            'files_count': len(files),
            'success_count': success_count,
            'error_count': error_count,
            'files': files[:100]  # Ограничиваем количество файлов для экономии места
        }
        
        self.history.append(operation)
        
        # Ограничиваем размер истории
        if len(self.history) > MAX_HISTORY_ITEMS:
            self.history = self.history[-MAX_HISTORY_ITEMS:]
        
        self.save_history()
    
    def get_history(self, limit: Optional[int] = None) -> List[Dict]:
        """Получение истории операций.
        
        Args:
            limit: Максимальное количество операций для возврата
            
        Returns:
            Список операций
        """
        if limit:
            return self.history[-limit:]
        return self.history.copy()
    
    def clear_history(self) -> None:
        """Очистка истории."""
        self.history = []
        self.save_history()
    
    def export_history(self, file_path: str) -> bool:
        """Экспорт истории в файл.
        
        Args:
            file_path: Путь к файлу для экспорта
            
        Returns:
            True если успешно, False в противном случае
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Ошибка экспорта истории: {e}")
            return False

