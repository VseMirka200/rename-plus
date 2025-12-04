"""Модуль для интернационализации."""

import json
import logging
import os
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class I18nManager:
    """Класс для управления переводами."""
    
    def __init__(self, language: str = 'ru', translations_dir: Optional[str] = None):
        """Инициализация менеджера переводов.
        
        Args:
            language: Язык интерфейса
            translations_dir: Директория с переводами
        """
        if translations_dir is None:
            translations_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'translations'
            )
        self.translations_dir = translations_dir
        self.language = language
        self.translations: Dict[str, str] = {}
        self.load_translations()
    
    def load_translations(self) -> None:
        """Загрузка переводов для текущего языка."""
        translation_file = os.path.join(
            self.translations_dir,
            f"{self.language}.json"
        )
        
        try:
            if os.path.exists(translation_file):
                with open(translation_file, 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
            else:
                # Загружаем русский по умолчанию
                default_file = os.path.join(self.translations_dir, 'ru.json')
                if os.path.exists(default_file):
                    with open(default_file, 'r', encoding='utf-8') as f:
                        self.translations = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки переводов: {e}")
            self.translations = {}
    
    def translate(self, key: str, default: Optional[str] = None) -> str:
        """Перевод ключа.
        
        Args:
            key: Ключ для перевода
            default: Значение по умолчанию
            
        Returns:
            Переведенный текст или ключ/значение по умолчанию
        """
        return self.translations.get(key, default or key)
    
    def set_language(self, language: str) -> None:
        """Установка языка.
        
        Args:
            language: Код языка
        """
        self.language = language
        self.load_translations()
    
    def get_available_languages(self) -> List[str]:
        """Получение списка доступных языков.
        
        Returns:
            Список кодов языков
        """
        languages = []
        if os.path.exists(self.translations_dir):
            for file in os.listdir(self.translations_dir):
                if file.endswith('.json'):
                    languages.append(file[:-5])
        return languages

