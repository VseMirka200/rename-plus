"""Модуль для валидации путей файлов.

Обеспечивает безопасную проверку путей для предотвращения
path traversal и других уязвимостей.
"""

import os
import sys
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from config.constants import (
        WINDOWS_MAX_PATH_LENGTH,
        WINDOWS_MAX_FILENAME_LENGTH,
        is_safe_path as constants_is_safe_path,
        check_windows_path_length as constants_check_path_length
    )
except ImportError:
    # Fallback если константы недоступны
    WINDOWS_MAX_PATH_LENGTH = 260
    WINDOWS_MAX_FILENAME_LENGTH = 255
    constants_is_safe_path = None
    constants_check_path_length = None


def is_safe_file_path(path: str, allowed_dirs: Optional[List[str]] = None) -> bool:
    """Проверка безопасности пути к файлу.
    
    Args:
        path: Путь к файлу для проверки
        allowed_dirs: Список разрешенных директорий (опционально)
        
    Returns:
        True если путь безопасен, False в противном случае
    """
    try:
        if not path or not isinstance(path, str) or not path.strip():
            return False
        
        # Проверяем на path traversal
        if '..' in path or path.startswith('~'):
            logger.warning(f"Обнаружен небезопасный путь (path traversal): {path}")
            return False
        
        # Нормализуем путь
        try:
            abs_path = os.path.abspath(path)
        except (OSError, ValueError) as e:
            logger.warning(f"Ошибка нормализации пути {path}: {e}")
            return False
        
        # Проверяем, что это файл
        try:
            if not os.path.isfile(abs_path):
                return False
        except (OSError, ValueError):
            return False
        
        # Проверяем длину пути для Windows
        if sys.platform == 'win32':
            if not check_windows_path_length(abs_path):
                logger.warning(f"Путь слишком длинный для Windows: {abs_path}")
                return False
        
        # Если указаны разрешенные директории, проверяем
        if allowed_dirs:
            for allowed_dir in allowed_dirs:
                try:
                    allowed_abs = os.path.abspath(allowed_dir)
                    if abs_path.startswith(allowed_abs):
                        return True
                except (OSError, ValueError):
                    continue
            logger.warning(f"Путь не в разрешенных директориях: {abs_path}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при проверке пути {path}: {e}", exc_info=True)
        return False


def check_windows_path_length(full_path: str) -> bool:
    """Проверка длины пути для Windows.
    
    Args:
        full_path: Полный путь к файлу
        
    Returns:
        True если длина пути допустима, False в противном случае
    """
    if constants_check_path_length:
        return constants_check_path_length(full_path)
    
    if sys.platform == 'win32':
        # Windows MAX_PATH = 260, но можно использовать длинные пути с \\?\
        return len(full_path) <= WINDOWS_MAX_PATH_LENGTH or full_path.startswith('\\\\?\\')
    return True


def validate_file_paths(paths: List[str], allowed_dirs: Optional[List[str]] = None) -> List[str]:
    """Валидация списка путей к файлам.
    
    Args:
        paths: Список путей к файлам
        allowed_dirs: Список разрешенных директорий (опционально)
        
    Returns:
        Список валидных и безопасных путей
    """
    valid_paths = []
    for path in paths:
        if is_safe_file_path(path, allowed_dirs):
            valid_paths.append(path)
        else:
            logger.warning(f"Небезопасный путь отклонен: {path}")
    return valid_paths

