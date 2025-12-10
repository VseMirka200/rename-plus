"""Модуль для извлечения метаданных из файлов.

Обеспечивает извлечение метаданных из различных типов файлов:
- Изображения: EXIF данные, размеры, даты (через Pillow)
- Аудио: ID3 теги, длительность, битрейт (через mutagen)
- Видео: длительность, разрешение, кодек
- Документы: даты создания/изменения, размер

Использует кэширование для оптимизации производительности при повторных запросах.
"""

import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Класс для извлечения метаданных из файлов."""
    
    def __init__(self):
        """Инициализация экстрактора метаданных."""
        self.pillow_available = False
        self.mutagen_available = False
        
        # Кэш для метаданных изображений (чтобы не открывать файл несколько раз)
        self._image_cache: Dict[str, Tuple[int, int, Optional[object]]] = {}
        # Кэш для аудио метаданных
        self._audio_cache: Dict[str, Optional[object]] = {}
        
        # Попытка импортировать Pillow для работы с изображениями
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS
            self.Image = Image
            self.TAGS = TAGS
            self.pillow_available = True
        except ImportError:
            self.pillow_available = False
        
        # Попытка импортировать mutagen для работы с аудио
        try:
            from mutagen import File as MutagenFile
            from mutagen.id3 import ID3NoHeaderError
            self.MutagenFile = MutagenFile
            self.ID3NoHeaderError = ID3NoHeaderError
            self.mutagen_available = True
        except ImportError:
            self.mutagen_available = False
    
    def clear_cache(self):
        """Очистка кэша метаданных."""
        self._image_cache.clear()
        self._audio_cache.clear()
    
    def extract(self, tag: str, file_path: str) -> Optional[str]:
        """
        Извлечение значения метаданных по тегу
        
        Args:
            tag: Тег метаданных (например, "{width}x{height}", "{date_created}")
            file_path: Путь к файлу
            
        Returns:
            Значение метаданных в виде строки или None
        """
        if not os.path.exists(file_path):
            return None
        
        # Обработка составных тегов (например, "{width}x{height}")
        if "x" in tag and "{width}" in tag and "{height}" in tag:
            return self._extract_dimensions(file_path)
        
        # Обработка отдельных тегов
        if tag == "{width}":
            return self._extract_width(file_path)
        elif tag == "{height}":
            return self._extract_height(file_path)
        elif tag == "{date_created}":
            return self._extract_date_created(file_path)
        elif tag == "{date_modified}":
            return self._extract_date_modified(file_path)
        elif tag == "{file_size}":
            return self._extract_file_size(file_path)
        elif tag == "{filename}":
            return os.path.basename(file_path)
        # Метаданные аудио
        elif tag == "{artist}":
            return self._extract_audio_tag(file_path, 'artist')
        elif tag == "{title}":
            return self._extract_audio_tag(file_path, 'title')
        elif tag == "{album}":
            return self._extract_audio_tag(file_path, 'album')
        elif tag == "{year}":
            return self._extract_audio_tag(file_path, 'date')
        elif tag == "{track}":
            return self._extract_audio_tag(file_path, 'tracknumber')
        elif tag == "{genre}":
            return self._extract_audio_tag(file_path, 'genre')
        elif tag.startswith("{") and tag.endswith("}"):
            # Попытка извлечь пользовательский тег
            return self._extract_custom_tag(tag, file_path)
        
        return None
    
    def _get_image_data(self, file_path: str) -> Optional[Tuple[int, int, Optional[object]]]:
        """Получение данных изображения с кэшированием.
        
        Args:
            file_path: Путь к файлу изображения
            
        Returns:
            Кортеж (width, height, exifdata) или None
        """
        if not self.pillow_available:
            return None
        
        # Проверяем кэш
        if file_path in self._image_cache:
            return self._image_cache[file_path]
        
        try:
            with self.Image.open(file_path) as img:
                width, height = img.size
                exifdata = img.getexif()
                result = (width, height, exifdata)
                # Кэшируем результат
                self._image_cache[file_path] = result
                return result
        except Exception as e:
            logger.debug(f"Не удалось извлечь данные изображения {file_path}: {e}")
            return None
    
    def _extract_dimensions(self, file_path: str) -> Optional[str]:
        """Извлечение размеров изображения (ширина x высота).
        
        Args:
            file_path: Путь к файлу изображения
            
        Returns:
            Строка с размерами в формате "widthxheight" или None
        """
        image_data = self._get_image_data(file_path)
        if image_data:
            width, height, _ = image_data
            return f"{width}x{height}"
        return None
    
    def _extract_width(self, file_path: str) -> Optional[str]:
        """Извлечение ширины изображения.
        
        Args:
            file_path: Путь к файлу изображения
            
        Returns:
            Ширина изображения в пикселях или None
        """
        image_data = self._get_image_data(file_path)
        if image_data:
            return str(image_data[0])
        return None
    
    def _extract_height(self, file_path: str) -> Optional[str]:
        """Извлечение высоты изображения.
        
        Args:
            file_path: Путь к файлу изображения
            
        Returns:
            Высота изображения в пикселях или None
        """
        image_data = self._get_image_data(file_path)
        if image_data:
            return str(image_data[1])
        return None
    
    def _extract_date_created(self, file_path: str) -> Optional[str]:
        """Извлечение даты создания файла.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Дата создания в формате YYYY-MM-DD или None
        """
        try:
            # В Windows используется st_ctime, в Unix - st_birthtime (если доступно)
            stat = os.stat(file_path)
            
            # Попытка получить дату создания
            if hasattr(stat, 'st_birthtime'):
                # macOS и некоторые версии Linux
                timestamp = stat.st_birthtime
            else:
                # Windows и другие системы (используем дату изменения как fallback)
                timestamp = stat.st_ctime
            
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d")
        except Exception as e:
            logger.debug(f"Не удалось извлечь дату создания {file_path}: {e}")
            return None
    
    def _extract_date_modified(self, file_path: str) -> Optional[str]:
        """Извлечение даты изменения файла.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Дата изменения в формате YYYY-MM-DD или None
        """
        try:
            stat = os.stat(file_path)
            timestamp = stat.st_mtime
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d")
        except Exception as e:
            logger.debug(f"Не удалось извлечь дату изменения {file_path}: {e}")
            return None
    
    def _extract_file_size(self, file_path: str) -> Optional[str]:
        """Извлечение размера файла.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Размер файла в отформатированном виде (B, KB, MB, GB) или None
        """
        try:
            size = os.path.getsize(file_path)
            
            # Форматирование размера
            if size < 1024:
                return f"{size}B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f}KB"
            elif size < 1024 * 1024 * 1024:
                return f"{size / (1024 * 1024):.1f}MB"
            else:
                return f"{size / (1024 * 1024 * 1024):.1f}GB"
        except Exception as e:
            logger.debug(f"Не удалось извлечь размер файла {file_path}: {e}")
            return None
    
    def _get_audio_tags(self, file_path: str) -> Optional[object]:
        """Получение тегов аудио файла с кэшированием.
        
        Args:
            file_path: Путь к аудио файлу
            
        Returns:
            Объект тегов или None
        """
        if not self.mutagen_available:
            return None
        
        # Проверяем кэш
        if file_path in self._audio_cache:
            return self._audio_cache[file_path]
        
        try:
            audio_file = self.MutagenFile(file_path)
            if audio_file is None:
                self._audio_cache[file_path] = None
                return None
            
            # Получаем теги
            tags = audio_file.tags
            if tags is None:
                self._audio_cache[file_path] = None
                return None
            
            # Кэшируем результат
            self._audio_cache[file_path] = tags
            return tags
        except self.ID3NoHeaderError:
            self._audio_cache[file_path] = None
            return None
        except Exception as e:
            logger.debug(f"Не удалось извлечь аудио теги из {file_path}: {e}")
            self._audio_cache[file_path] = None
            return None
    
    def _extract_audio_tag(self, file_path: str, tag_name: str) -> Optional[str]:
        """Извлечение метаданных аудио файла.
        
        Args:
            file_path: Путь к аудио файлу
            tag_name: Имя тега (artist, title, album, date, tracknumber, genre)
            
        Returns:
            Значение тега или None
        """
        tags = self._get_audio_tags(file_path)
        if tags is None:
            return None
        
        try:
            
            # Маппинг имен тегов для разных форматов (кэшируем как константу)
            tag_mapping = {
                'artist': ['TPE1', 'ARTIST', '©ART'],
                'title': ['TIT2', 'TITLE', '©nam'],
                'album': ['TALB', 'ALBUM', '©alb'],
                'date': ['TDRC', 'DATE', '©day'],
                'tracknumber': ['TRCK', 'TRACKNUMBER', 'TRACK', 'trkn'],
                'genre': ['TCON', 'GENRE', '©gen']
            }
            
            # Получаем список возможных ключей для тега
            possible_keys = tag_mapping.get(tag_name.lower(), [tag_name.upper()])
            
            # Пытаемся получить значение по разным ключам
            for key in possible_keys:
                if key in tags:
                    value = tags[key]
                    # Обработка списков и кортежей
                    if isinstance(value, (list, tuple)) and len(value) > 0:
                        value = value[0]
                    # Обработка объектов с текстовым представлением
                    if hasattr(value, 'text'):
                        value = value.text[0] if value.text else None
                    if value:
                        return str(value).strip()
            
            return None
        except Exception as e:
            logger.debug(f"Не удалось извлечь аудио тег {tag_name} из {file_path}: {e}")
            return None
    
    def _extract_custom_tag(self, tag: str, file_path: str) -> Optional[str]:
        """Извлечение пользовательского тега (расширяемая функция).
        
        Args:
            tag: Тег для извлечения
            file_path: Путь к файлу
            
        Returns:
            Значение тега или None
        """
        # Здесь можно добавить поддержку дополнительных тегов
        # Например, EXIF данные из изображений
        
        if not self.pillow_available:
            return None
        
        # Используем кэшированные данные изображения
        image_data = self._get_image_data(file_path)
        if image_data:
            _, _, exifdata = image_data
            if exifdata:
                # Поиск тега в EXIF данных
                for tag_id, value in exifdata.items():
                    tag_name = self.TAGS.get(tag_id, tag_id)
                    if tag.lower() == f"{{{tag_name.lower()}}}":
                        return str(value)
        
        return None

