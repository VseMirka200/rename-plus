"""Модуль для улучшенной обработки ошибок."""

import logging
import traceback
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Класс для улучшенной обработки ошибок."""
    
    @staticmethod
    def get_error_details(exception: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Получение детальной информации об ошибке.
        
        Args:
            exception: Исключение
            context: Дополнительный контекст
            
        Returns:
            Словарь с деталями ошибки
        """
        error_type = type(exception).__name__
        error_message = str(exception)
        error_traceback = traceback.format_exc()
        
        details = {
            'type': error_type,
            'message': error_message,
            'traceback': error_traceback,
            'context': context or {}
        }
        
        # Предложения по исправлению
        suggestions = ErrorHandler._get_suggestions(exception, context)
        if suggestions:
            details['suggestions'] = suggestions
        
        return details
    
    @staticmethod
    def _get_suggestions(exception: Exception, context: Optional[Dict[str, Any]] = None) -> list:
        """Получение предложений по исправлению ошибки.
        
        Args:
            exception: Исключение
            context: Контекст ошибки
            
        Returns:
            Список предложений
        """
        suggestions = []
        error_type = type(exception).__name__
        error_message = str(exception).lower()
        
        if 'permission' in error_message or 'PermissionError' in error_type:
            suggestions.append("Проверьте права доступа к файлу")
            suggestions.append("Убедитесь, что файл не открыт в другой программе")
            suggestions.append("Попробуйте запустить программу от имени администратора")
        
        elif 'not found' in error_message or 'FileNotFoundError' in error_type:
            suggestions.append("Проверьте, что файл существует")
            suggestions.append("Убедитесь, что путь указан правильно")
        
        elif 'invalid' in error_message or 'ValueError' in error_type:
            suggestions.append("Проверьте корректность введенных данных")
            suggestions.append("Убедитесь, что имя файла не содержит недопустимых символов")
        
        elif 'disk' in error_message or 'space' in error_message:
            suggestions.append("Проверьте свободное место на диске")
            suggestions.append("Освободите место и попробуйте снова")
        
        elif 'name too long' in error_message or 'path too long' in error_message:
            suggestions.append("Имя файла слишком длинное")
            suggestions.append("Сократите имя файла или путь")
        
        return suggestions
    
    @staticmethod
    def format_error_message(error_details: Dict[str, Any], include_traceback: bool = False) -> str:
        """Форматирование сообщения об ошибке для пользователя.
        
        Args:
            error_details: Детали ошибки
            include_traceback: Включать ли traceback
            
        Returns:
            Отформатированное сообщение
        """
        message = f"Ошибка: {error_details['message']}\n"
        message += f"Тип: {error_details['type']}\n"
        
        if error_details.get('suggestions'):
            message += "\nПредложения по исправлению:\n"
            for i, suggestion in enumerate(error_details['suggestions'], 1):
                message += f"{i}. {suggestion}\n"
        
        if include_traceback and error_details.get('traceback'):
            message += f"\nДетали:\n{error_details['traceback']}"
        
        return message

