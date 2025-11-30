"""Модуль для управления настройками и шаблонами."""

import json
import os
from typing import Dict, Any, Optional


class SettingsManager:
    """Класс для управления настройками приложения."""
    
    DEFAULT_SETTINGS = {
        'auto_apply': False,
        'show_warnings': True,
        'font_size': '10',
        'backup': False
    }
    
    def __init__(self, settings_file: Optional[str] = None):
        """Инициализация менеджера настроек.
        
        Args:
            settings_file: Путь к файлу настроек
        """
        if settings_file is None:
            settings_file = os.path.join(
                os.path.expanduser("~"), ".nazovi_settings.json"
            )
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
                    settings.update(loaded)
        except Exception as e:
            print(f"Ошибка загрузки настроек: {e}")
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
            print(f"Ошибка сохранения настроек: {e}")
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
    
    def set(self, key: str, value: Any):
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
            templates_file = os.path.join(
                os.path.expanduser("~"), ".nazovi_templates.json"
            )
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
                        templates = loaded
        except Exception as e:
            print(f"Ошибка загрузки шаблонов: {e}")
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
            print(f"Ошибка сохранения шаблонов: {e}")
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
    
    def set(self, key: str, value: Any):
        """Установка шаблона.
        
        Args:
            key: Ключ шаблона
            value: Значение шаблона
        """
        self.templates[key] = value

