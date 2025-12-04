"""Константы приложения."""

# Размеры окна
DEFAULT_WINDOW_WIDTH = 1000
DEFAULT_WINDOW_HEIGHT = 600
MIN_WINDOW_WIDTH = 1000
MIN_WINDOW_HEIGHT = 600

# Пути к файлам
SETTINGS_FILE = ".nazovi_settings.json"
TEMPLATES_FILE = ".nazovi_templates.json"
STATS_FILE = ".rename_plus_stats.json"
HISTORY_FILE = ".rename_plus_history.json"

# Лимиты
MAX_HISTORY_ITEMS = 100
MAX_FILES_PREVIEW = 1000

# Интервалы
UPDATE_CHECK_DELAY = 5000  # мс
CANCEL_CHECK_INTERVAL = 100  # мс

# Цвета (fallback, если тема не загружена)
DEFAULT_COLORS = {
    'primary': '#667EEA',
    'primary_hover': '#5568D3',
    'success': '#10B981',
    'success_hover': '#059669',
    'danger': '#EF4444',
    'danger_hover': '#DC2626',
    'bg_main': '#F5F7FA',
    'bg_card': '#FFFFFF',
    'text_primary': '#1A202C',
    'text_secondary': '#4A5568',
}

# Сообщения
MESSAGES = {
    'rename_complete': 'Переименование завершено.\nУспешно: {success}\nОшибок: {error}',
    'no_files': 'Нет файлов для переименования',
    'no_ready_files': 'Нет файлов готовых к переименованию',
    'confirm_rename': 'Вы собираетесь переименовать {count} файлов. Выполнить?',
}

