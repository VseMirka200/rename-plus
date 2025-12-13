"""Модуль для управления настройками и шаблонами.

Обеспечивает сохранение и загрузку настроек приложения и шаблонов переименования
в JSON формате. Настройки сохраняются в домашней директории пользователя.
"""

import json
import logging
import os
from typing import Dict, Any, Optional

try:
    from config.constants import get_settings_file_path, get_templates_file_path
    SETTINGS_FILE_PATH = get_settings_file_path()
    TEMPLATES_FILE_PATH = get_templates_file_path()
except ImportError:
    # Fallback если константы не доступны
    # Используем директорию текущего файла как fallback
    app_data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(app_data_dir, "data")
    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception:
            pass
    SETTINGS_FILE_PATH = os.path.join(data_dir, "rename-plus_settings.json")
    TEMPLATES_FILE_PATH = os.path.join(data_dir, "rename-plus_templates.json")

# Настройка логирования
logger = logging.getLogger(__name__)


class SettingsManager:
    """Класс для управления настройками приложения.
    
    Обеспечивает загрузку, сохранение и управление настройками приложения.
    Настройки хранятся в JSON файле в домашней директории пользователя.
    Поддерживает значения по умолчанию для всех настроек.
    """
    
    DEFAULT_SETTINGS = {
        'auto_apply': False,
        'show_warnings': True,
        'font_size': '10',
        'backup': False
    }
    
    REQUIRED_SETTINGS_KEYS = {'auto_apply', 'show_warnings', 'font_size', 'backup'}
    
    @staticmethod
    def validate_settings(settings: Dict[str, Any]) -> bool:
        """Валидация структуры настроек.
        
        Args:
            settings: Словарь с настройками
            
        Returns:
            True если настройки валидны, False в противном случае
        """
        if not isinstance(settings, dict):
            return False
        
        # Проверяем наличие обязательных ключей
        if not all(key in settings for key in SettingsManager.REQUIRED_SETTINGS_KEYS):
            return False
        
        # Проверяем типы значений
        if not isinstance(settings.get('auto_apply'), bool):
            return False
        if not isinstance(settings.get('show_warnings'), bool):
            return False
        if not isinstance(settings.get('backup'), bool):
            return False
        if not isinstance(settings.get('font_size'), (str, int)):
            return False
        
        return True
    
    def __init__(self, settings_file: Optional[str] = None):
        """Инициализация менеджера настроек.
        
        Args:
            settings_file: Путь к файлу настроек
        """
        if settings_file is None:
            try:
                settings_file = SETTINGS_FILE_PATH
            except NameError:
                # Fallback если константы не загружены
                app_data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                data_dir = os.path.join(app_data_dir, "data")
                if not os.path.exists(data_dir):
                    try:
                        os.makedirs(data_dir, exist_ok=True)
                    except (OSError, PermissionError):
                        pass
                settings_file = os.path.join(data_dir, "rename-plus_settings.json")
        self.settings_file = settings_file
        self.settings = self.load_settings()
    
    def load_settings(self) -> Dict[str, Any]:
        """Загрузка настроек из файла.
        
        Returns:
            Словарь с настройками
        """
        settings = self.DEFAULT_SETTINGS.copy()
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        # Валидируем загруженные настройки
                        if self.validate_settings(loaded):
                            settings.update(loaded)
                        else:
                            logger.warning(f"Файл настроек содержит неверный формат, используются настройки по умолчанию: {self.settings_file}")
                    else:
                        logger.warning(f"Файл настроек содержит неверный формат: {self.settings_file}")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON в настройках: {e}", exc_info=True)
        except (OSError, PermissionError, ValueError) as e:
            logger.error(f"Ошибка загрузки настроек: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Неожиданная ошибка загрузки настроек: {e}", exc_info=True)
        return settings
    
    def save_settings(self, settings_dict: Optional[Dict[str, Any]] = None) -> bool:
        """Сохранение настроек в файл.
        
        Args:
            settings_dict: Словарь с настройками (если None, используется self.settings)
        
        Returns:
            True если успешно, False в противном случае
        """
        if settings_dict is None:
            settings_dict = self.settings
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings_dict, f, ensure_ascii=False, indent=2)
            self.settings = settings_dict
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}", exc_info=True)
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Получение значения настройки.
        
        Args:
            key: Ключ настройки
            default: Значение по умолчанию
        
        Returns:
            Значение настройки или default
        """
        return self.settings.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Установка значения настройки.
        
        Args:
            key: Ключ настройки
            value: Значение
        """
        self.settings[key] = value


class TemplatesManager:
    """Класс для управления шаблонами."""
    
    def __init__(self, templates_file: Optional[str] = None):
        """Инициализация менеджера шаблонов.
        
        Args:
            templates_file: Путь к файлу шаблонов
        """
        if templates_file is None:
            try:
                templates_file = TEMPLATES_FILE_PATH
            except NameError:
                # Fallback если константы не загружены
                app_data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                data_dir = os.path.join(app_data_dir, "data")
                if not os.path.exists(data_dir):
                    try:
                        os.makedirs(data_dir, exist_ok=True)
                    except (OSError, PermissionError):
                        pass
                templates_file = os.path.join(data_dir, "rename-plus_templates.json")
        self.templates_file = templates_file
        self.templates = self.load_templates()
    
    def load_templates(self) -> Dict[str, Any]:
        """Загрузка сохраненных шаблонов из файла.
        
        Returns:
            Словарь с шаблонами
        """
        templates = {}
        try:
            if os.path.exists(self.templates_file):
                with open(self.templates_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        # Валидируем шаблоны (должны быть строками)
                        # Валидируем шаблоны (должны быть строками)
                        for key, value in loaded.items():
                            if isinstance(key, str) and isinstance(value, str):
                                templates[key] = value
                            else:
                                logger.warning(f"Неверный формат шаблона '{key}': ожидается строка")
                    else:
                        logger.warning(f"Файл шаблонов содержит неверный формат: {self.templates_file}")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON в шаблонах: {e}", exc_info=True)
        except (OSError, PermissionError, ValueError) as e:
            logger.error(f"Ошибка загрузки шаблонов: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Неожиданная ошибка загрузки шаблонов: {e}", exc_info=True)
        return templates
    
    def save_templates(self, templates: Optional[Dict[str, Any]] = None) -> bool:
        """Сохранение шаблонов в файл.
        
        Args:
            templates: Словарь с шаблонами (если None, используется self.templates)
        
        Returns:
            True если успешно, False в противном случае
        """
        if templates is None:
            templates = self.templates
        try:
            with open(self.templates_file, 'w', encoding='utf-8') as f:
                json.dump(templates, f, ensure_ascii=False, indent=2)
            self.templates = templates
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения шаблонов: {e}", exc_info=True)
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Получение шаблона.
        
        Args:
            key: Ключ шаблона
            default: Значение по умолчанию
        
        Returns:
            Шаблон или default
        """
        return self.templates.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Установка шаблона.
        
        Args:
            key: Ключ шаблона
            value: Значение шаблона
        """
        self.templates[key] = value

