"""Константы приложения."""

# Таймауты
PACKAGE_INSTALL_TIMEOUT = 300  # 5 минут для установки пакетов
COM_OPERATION_DELAY = 0.5  # Задержка после COM операций (секунды)

# Размеры окна
DEFAULT_WINDOW_WIDTH = 1000
DEFAULT_WINDOW_HEIGHT = 600
MIN_WINDOW_WIDTH = 1000
MIN_WINDOW_HEIGHT = 600

# Форматы файлов
SUPPORTED_IMAGE_FORMATS = {
    '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp', '.gif',
    '.ico', '.jfif', '.jp2', '.jpx', '.j2k', '.j2c', '.pcx', '.ppm',
    '.pgm', '.pbm', '.pnm', '.psd', '.xbm', '.xpm', '.heic', '.heif', '.avif'
}

SUPPORTED_DOCUMENT_FORMATS = {'.docx'}
SUPPORTED_AUDIO_FORMATS = {'.mp3', '.flac', '.ogg', '.wav', '.m4a', '.aac'}
SUPPORTED_VIDEO_FORMATS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv'}

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
