"""
Модуль для извлечения метаданных из файлов
Поддерживает изображения (через Pillow) и базовые метаданные файлов
"""

import os
from datetime import datetime
from typing import Optional


class MetadataExtractor:
    """Класс для извлечения метаданных из файлов"""
    
    def __init__(self):
        """Инициализация экстрактора метаданных"""
        self.pillow_available = False
        
        # Попытка импортировать Pillow для работы с изображениями
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS
            self.Image = Image
            self.TAGS = TAGS
            self.pillow_available = True
        except ImportError:
            self.pillow_available = False
    
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
        elif tag.startswith("{") and tag.endswith("}"):
            # Попытка извлечь пользовательский тег
            return self._extract_custom_tag(tag, file_path)
        
        return None
    
    def _extract_dimensions(self, file_path: str) -> Optional[str]:
        """Извлечение размеров изображения (ширина x высота)"""
        if not self.pillow_available:
            return None
        
        try:
            with self.Image.open(file_path) as img:
                width, height = img.size
                return f"{width}x{height}"
        except Exception:
            return None
    
    def _extract_width(self, file_path: str) -> Optional[str]:
        """Извлечение ширины изображения"""
        if not self.pillow_available:
            return None
        
        try:
            with self.Image.open(file_path) as img:
                return str(img.size[0])
        except Exception:
            return None
    
    def _extract_height(self, file_path: str) -> Optional[str]:
        """Извлечение высоты изображения"""
        if not self.pillow_available:
            return None
        
        try:
            with self.Image.open(file_path) as img:
                return str(img.size[1])
        except Exception:
            return None
    
    def _extract_date_created(self, file_path: str) -> Optional[str]:
        """Извлечение даты создания файла"""
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
        except Exception:
            return None
    
    def _extract_date_modified(self, file_path: str) -> Optional[str]:
        """Извлечение даты изменения файла"""
        try:
            stat = os.stat(file_path)
            timestamp = stat.st_mtime
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None
    
    def _extract_file_size(self, file_path: str) -> Optional[str]:
        """Извлечение размера файла"""
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
        except Exception:
            return None
    
    def _extract_custom_tag(self, tag: str, file_path: str) -> Optional[str]:
        """Извлечение пользовательского тега (расширяемая функция)"""
        # Здесь можно добавить поддержку дополнительных тегов
        # Например, EXIF данные из изображений
        
        if not self.pillow_available:
            return None
        
        # Попытка извлечь EXIF данные
        try:
            with self.Image.open(file_path) as img:
                exifdata = img.getexif()
                if exifdata:
                    # Поиск тега в EXIF данных
                    for tag_id, value in exifdata.items():
                        tag_name = self.TAGS.get(tag_id, tag_id)
                        if tag.lower() == f"{{{tag_name.lower()}}}":
                            return str(value)
        except Exception:
            pass
        
        return None

