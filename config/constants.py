"""Константы приложения.

Этот модуль содержит все константы, используемые в приложении,
включая размеры окон, таймауты, форматы файлов и другие настройки.
"""

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

# Зарезервированные имена Windows
WINDOWS_RESERVED_NAMES = frozenset(
    ['CON', 'PRN', 'AUX', 'NUL'] +
    [f'COM{i}' for i in range(1, 10)] +
    [f'LPT{i}' for i in range(1, 10)]
)

# Запрещенные символы в именах файлов
INVALID_FILENAME_CHARS = frozenset(['<', '>', ':', '"', '/', '\\', '|', '?', '*'])
