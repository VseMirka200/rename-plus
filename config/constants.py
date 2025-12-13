"""Константы приложения.

Этот модуль содержит все константы, используемые в приложении,
включая размеры окон, таймауты, форматы файлов и другие настройки.
"""

import os
import logging
from typing import Optional, List

# Инициализация логгера для функций в этом модуле
logger = logging.getLogger(__name__)

# Версия приложения
APP_VERSION = "1.0.0"

# Таймауты
PACKAGE_INSTALL_TIMEOUT = 300  # 5 минут для установки пакетов
COM_OPERATION_DELAY = 0.5  # Задержка после COM операций (секунды)

# Размеры окна
DEFAULT_WINDOW_WIDTH = 1000
DEFAULT_WINDOW_HEIGHT = 600
MIN_WINDOW_WIDTH = 1000
MIN_WINDOW_HEIGHT = 600

# Форматы файлов (только популярные)
SUPPORTED_IMAGE_FORMATS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif',
    '.ico', '.svg', '.heic', '.heif', '.avif', '.dng', '.cr2', '.nef', '.raw'
}

SUPPORTED_DOCUMENT_FORMATS = {
    '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt',
    '.txt', '.rtf', '.csv', '.html', '.htm', '.odt', '.ods', '.odp'
}

SUPPORTED_AUDIO_FORMATS = {
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus'
}

SUPPORTED_VIDEO_FORMATS = {
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
    '.mpg', '.mpeg', '.3gp'
}

# Качество по умолчанию
DEFAULT_JPEG_QUALITY = 95

# Лимиты
MAX_OPERATIONS_HISTORY = 100
MAX_UNDO_STACK_SIZE = 50
MAX_PATH_CACHE_SIZE = 10000  # Максимальный размер кеша путей
WINDOWS_MAX_FILENAME_LENGTH = 255  # Максимальная длина имени файла в Windows
WINDOWS_MAX_PATH_LENGTH = 260  # Максимальная длина пути в Windows (MAX_PATH)
CONTEXT_MENU_DELAY = 0.8  # Задержка для сбора файлов из контекстного меню (секунды)
FILE_OPERATION_DELAY = 0.5  # Задержка для операций с файлами (секунды)
MIN_PYTHON_VERSION = (3, 7)  # Минимальная версия Python

# Зарезервированные имена Windows
WINDOWS_RESERVED_NAMES = frozenset(
    ['CON', 'PRN', 'AUX', 'NUL'] +
    [f'COM{i}' for i in range(1, 10)] +
    [f'LPT{i}' for i in range(1, 10)]
)

# Запрещенные символы в именах файлов
INVALID_FILENAME_CHARS = frozenset(['<', '>', ':', '"', '/', '\\', '|', '?', '*'])

# Имена файлов конфигурации и логов
LOG_FILE = "rename-plus.log"
CONTEXT_MENU_WRAPPER_LOG = "context_menu_wrapper.log"
SETTINGS_FILE = "rename-plus_settings.json"
TEMPLATES_FILE = "rename-plus_templates.json"
LIBS_INSTALLED_FILE = "rename-plus_libs_installed.json"

# Функция для получения базовой директории программы
def get_app_data_dir():
    """Получение директории программы для хранения конфигурационных файлов.
    
    Returns:
        Путь к директории программы
    """
    import os
    # Определяем директорию, где находится этот файл (config/constants.py)
    # и возвращаем родительскую директорию (корень проекта)
    current_file = os.path.abspath(__file__)
    config_dir = os.path.dirname(current_file)
    app_dir = os.path.dirname(config_dir)  # Родительская директория (корень проекта)
    return app_dir

# Функция для получения директории логов
def get_logs_dir():
    """Получение директории для хранения логов.
    
    Returns:
        Путь к директории логов
    """
    import os
    logs_dir = os.path.join(get_app_data_dir(), "logs")
    # Создаём директорию, если её нет
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir, exist_ok=True)
        except Exception:
            pass
    return logs_dir

# Функция для получения директории данных (конфигурация и кеш)
def get_data_dir():
    """Получение директории для хранения конфигурационных файлов и кеша.
    
    Returns:
        Путь к директории данных
    """
    import os
    data_dir = os.path.join(get_app_data_dir(), "data")
    # Создаём директорию, если её нет
    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception:
            pass
    return data_dir

# Полные пути к файлам
def get_log_file_path():
    """Получение полного пути к файлу основного лога."""
    return os.path.join(get_logs_dir(), LOG_FILE)

def get_context_menu_wrapper_log_path():
    """Получение полного пути к файлу лога обёртки контекстного меню."""
    return os.path.join(get_logs_dir(), CONTEXT_MENU_WRAPPER_LOG)

def get_settings_file_path():
    """Получение полного пути к файлу настроек."""
    return os.path.join(get_data_dir(), SETTINGS_FILE)

def get_templates_file_path():
    """Получение полного пути к файлу шаблонов."""
    return os.path.join(get_data_dir(), TEMPLATES_FILE)

def get_libs_installed_file_path():
    """Получение полного пути к файлу установленных библиотек."""
    return os.path.join(get_data_dir(), LIBS_INSTALLED_FILE)

# Утилита для создания директорий
def ensure_directory_exists(path: str) -> bool:
    """Создание директории если не существует.
    
    Args:
        path: Путь к директории
        
    Returns:
        True если директория существует или была создана, False в противном случае
    """
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except (OSError, PermissionError) as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Не удалось создать директорию {path}: {e}")
        return False

# Функция валидации путей для безопасности
def is_safe_path(path: str, allowed_dirs: Optional[List[str]] = None) -> bool:
    """Проверка безопасности пути.
    
    Args:
        path: Путь к файлу для проверки
        allowed_dirs: Список разрешенных директорий (опционально)
        
    Returns:
        True если путь безопасен, False в противном случае
    """
    try:
        if not path or not path.strip():
            return False
        
        # Проверяем на path traversal
        if '..' in path or path.startswith('~'):
            return False
        
        # Нормализуем путь
        abs_path = os.path.abspath(path)
        
        # Проверяем, что это файл
        if not os.path.isfile(abs_path):
            return False
        
        # Если указаны разрешенные директории, проверяем
        if allowed_dirs:
            for allowed_dir in allowed_dirs:
                allowed_abs = os.path.abspath(allowed_dir)
                if abs_path.startswith(allowed_abs):
                    return True
            return False
        
        return True
    except (OSError, ValueError, TypeError):
        return False

# Функция проверки длины пути для Windows
def check_windows_path_length(full_path: str) -> bool:
    """Проверка длины пути для Windows.
    
    Args:
        full_path: Полный путь к файлу
        
    Returns:
        True если длина пути допустима, False в противном случае
    """
    import sys
    if sys.platform == 'win32':
        # Windows MAX_PATH = 260, но можно использовать длинные пути с \\?\
        return len(full_path) <= WINDOWS_MAX_PATH_LENGTH or full_path.startswith('\\\\?\\')
    return True