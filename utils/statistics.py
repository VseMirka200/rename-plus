"""Модуль для сбора и отображения статистики."""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

try:
    from config.constants import STATS_FILE
except ImportError:
    # Fallback если константы не доступны
    STATS_FILE = ".rename_plus_stats.json"

logger = logging.getLogger(__name__)


class StatisticsManager:
    """Класс для управления статистикой приложения."""
    
    def __init__(self, stats_file: Optional[str] = None):
        """Инициализация менеджера статистики.
        
        Args:
            stats_file: Путь к файлу статистики
        """
        if stats_file is None:
            stats_file = os.path.join(
                os.path.expanduser("~"), STATS_FILE
            )
        self.stats_file = stats_file
        self.stats = self.load_stats()
    
    def load_stats(self) -> Dict:
        """Загрузка статистики из файла.
        
        Returns:
            Словарь со статистикой
        """
        default_stats = {
            'total_renamed': 0,
            'total_errors': 0,
            'total_operations': 0,
            'methods_used': {},
            'files_by_extension': {},
            'operations_history': []
        }
        
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        default_stats.update(loaded)
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики: {e}")
        
        return default_stats
    
    def save_stats(self) -> bool:
        """Сохранение статистики в файл.
        
        Returns:
            True если успешно
        """
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения статистики: {e}")
            return False
    
    def record_operation(self, operation_type: str, success_count: int, 
                        error_count: int, methods_used: List[str] = None,
                        files: List[Dict] = None) -> None:
        """Запись операции в статистику.
        
        Args:
            operation_type: Тип операции
            success_count: Количество успешных операций
            error_count: Количество ошибок
            methods_used: Список использованных методов
            files: Список файлов
        """
        self.stats['total_operations'] += 1
        self.stats['total_renamed'] += success_count
        self.stats['total_errors'] += error_count
        
        # Статистика по методам
        if methods_used:
            for method in methods_used:
                self.stats['methods_used'][method] = \
                    self.stats['methods_used'].get(method, 0) + 1
        
        # Статистика по расширениям
        if files:
            for file_data in files:
                ext = file_data.get('extension', '').lower()
                if ext:
                    self.stats['files_by_extension'][ext] = \
                        self.stats['files_by_extension'].get(ext, 0) + 1
        
        # История операций
        operation_record = {
            'timestamp': datetime.now().isoformat(),
            'type': operation_type,
            'success': success_count,
            'errors': error_count
        }
        self.stats['operations_history'].append(operation_record)
        
        # Ограничиваем размер истории
        if len(self.stats['operations_history']) > 100:
            self.stats['operations_history'] = \
                self.stats['operations_history'][-100:]
        
        self.save_stats()
    
    def get_stats_summary(self) -> Dict:
        """Получение сводки статистики.
        
        Returns:
            Словарь со сводкой
        """
        return {
            'total_renamed': self.stats.get('total_renamed', 0),
            'total_errors': self.stats.get('total_errors', 0),
            'total_operations': self.stats.get('total_operations', 0),
            'success_rate': (
                self.stats.get('total_renamed', 0) / 
                max(self.stats.get('total_operations', 1), 1) * 100
            ),
            'most_used_methods': sorted(
                self.stats.get('methods_used', {}).items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
            'most_common_extensions': sorted(
                self.stats.get('files_by_extension', {}).items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }
    
    def clear_stats(self) -> None:
        """Очистка статистики."""
        self.stats = {
            'total_renamed': 0,
            'total_errors': 0,
            'total_operations': 0,
            'methods_used': {},
            'files_by_extension': {},
            'operations_history': []
        }
        self.save_stats()

