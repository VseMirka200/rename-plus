"""Модуль для конвертации файлов.

Поддерживает конвертацию изображений (через Pillow) и базовую конвертацию файлов.
"""

import logging
import os
import shutil
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FileConverter:
    """Класс для конвертации файлов."""
    
    def __init__(self):
        """Инициализация конвертера файлов."""
        self.pillow_available = False
        
        # Попытка импортировать Pillow для работы с изображениями
        try:
            from PIL import Image
            self.Image = Image
            self.pillow_available = True
        except ImportError:
            self.pillow_available = False
        
        # Поддерживаемые форматы изображений для конвертации
        self.supported_image_formats = {
            '.jpg': 'JPEG',
            '.jpeg': 'JPEG',
            '.png': 'PNG',
            '.bmp': 'BMP',
            '.tiff': 'TIFF',
            '.tif': 'TIFF',
            '.webp': 'WEBP',
            '.gif': 'GIF',
            '.ico': 'ICO',
            '.jfif': 'JPEG',
            '.jp2': 'JPEG2000',
            '.jpx': 'JPEG2000',
            '.j2k': 'JPEG2000',
            '.j2c': 'JPEG2000',
            '.pcx': 'PCX',
            '.ppm': 'PPM',
            '.pgm': 'PGM',
            '.pbm': 'PBM',
            '.pnm': 'PNM',
            '.psd': 'PSD',
            '.xbm': 'XBM',
            '.xpm': 'XPM',
            '.heic': 'HEIC',
            '.heif': 'HEIF',
            '.avif': 'AVIF'
        }
        
        # Попытка импортировать python-docx для работы с Word документами
        self.docx_available = False
        try:
            import docx
            self.docx_module = docx
            self.docx_available = True
        except ImportError:
            self.docx_available = False
        
        # Поддерживаемые форматы документов
        # Примечание: python-docx не поддерживает конвертацию в старый формат .doc
        self.supported_document_formats = {
            '.docx': 'DOCX'
        }
    
    def can_convert(self, file_path: str, target_format: str) -> bool:
        """Проверка возможности конвертации файла.
        
        Args:
            file_path: Путь к исходному файлу
            target_format: Целевой формат (расширение с точкой, например '.png')
            
        Returns:
            True если можно конвертировать, False иначе
        """
        if not os.path.exists(file_path):
            return False
        
        source_ext = os.path.splitext(file_path)[1].lower()
        target_ext = target_format.lower()
        
        # Не конвертируем в тот же формат
        if source_ext == target_ext:
            return False
        
        # Проверяем конвертацию изображений
        if source_ext in self.supported_image_formats and target_ext in self.supported_image_formats:
            if self.pillow_available:
                return True
        
        # Проверяем конвертацию документов Word
        if source_ext in self.supported_document_formats and target_ext in self.supported_document_formats:
            if self.docx_available:
                return True
        
        return False
    
    def get_supported_formats(self) -> List[str]:
        """Получение списка поддерживаемых форматов.
        
        Returns:
            Список расширений форматов (с точкой)
        """
        formats = list(self.supported_image_formats.keys())
        if self.docx_available:
            formats.extend(list(self.supported_document_formats.keys()))
        return formats
    
    def convert(self, file_path: str, target_format: str, output_path: Optional[str] = None, 
                quality: int = 95, create_backup: bool = True) -> Tuple[bool, str, Optional[str]]:
        """Конвертация файла.
        
        Args:
            file_path: Путь к исходному файлу
            target_format: Целевой формат (расширение с точкой, например '.png')
            output_path: Путь для сохранения (если None, заменяет исходный файл)
            quality: Качество для JPEG (1-100)
            create_backup: Создавать ли резервную копию исходного файла
            
        Returns:
            Кортеж (успех, сообщение, путь к выходному файлу)
        """
        if not os.path.exists(file_path):
            return False, "Файл не найден", None
        
        if not self.can_convert(file_path, target_format):
            return False, "Конвертация в этот формат не поддерживается", None
        
        source_ext = os.path.splitext(file_path)[1].lower()
        target_ext = target_format.lower()
        
        # Определяем путь для выходного файла
        if output_path is None:
            # Заменяем расширение исходного файла
            base_name = os.path.splitext(file_path)[0]
            output_path = base_name + target_ext
        else:
            # Убеждаемся, что выходной файл имеет правильное расширение
            if not output_path.lower().endswith(target_ext):
                output_path = os.path.splitext(output_path)[0] + target_ext
        
        # Создаем резервную копию если нужно
        backup_path = None
        if create_backup and output_path == file_path.replace(source_ext, target_ext):
            try:
                backup_path = file_path + '.backup'
                shutil.copy2(file_path, backup_path)
            except Exception as e:
                logger.warning(f"Не удалось создать резервную копию: {e}")
        
        try:
            # Проверяем тип файла и конвертируем соответственно
            if source_ext in self.supported_document_formats:
                # Конвертация документов Word
                return self._convert_document(file_path, target_ext, output_path, create_backup)
            elif source_ext in self.supported_image_formats:
                # Конвертация изображений
                if not self.pillow_available:
                    return False, "Pillow не установлен", None
                
                # Открываем изображение
                with self.Image.open(file_path) as img:
                    # Конвертируем в RGB для форматов, которые не поддерживают прозрачность
                    if target_ext in ('.jpg', '.jpeg', '.bmp') and img.mode in ('RGBA', 'LA', 'P'):
                        # Создаем белый фон
                        background = self.Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        if img.mode == 'RGBA':
                            background.paste(img, mask=img.split()[-1])
                        else:
                            background.paste(img)
                        img = background
                    elif img.mode == 'P' and target_ext not in ('.png', '.gif', '.webp'):
                        # Конвертируем палитровые изображения
                        img = img.convert('RGB')
                    
                    # Параметры сохранения
                    save_kwargs = {}
                    format_name = self.supported_image_formats.get(target_ext, 'PNG')
                    
                    # Обработка специальных форматов
                    if format_name == 'JPEG2000':
                        format_name = 'JPEG2000'
                    elif format_name == 'HEIC' or format_name == 'HEIF':
                        # Pillow может не поддерживать HEIC/HEIF напрямую
                        # Конвертируем в PNG как fallback
                        format_name = 'PNG'
                        if not output_path.endswith('.png'):
                            output_path = os.path.splitext(output_path)[0] + '.png'
                    elif format_name == 'AVIF':
                        # Pillow может не поддерживать AVIF напрямую
                        # Конвертируем в PNG как fallback
                        format_name = 'PNG'
                        if not output_path.endswith('.png'):
                            output_path = os.path.splitext(output_path)[0] + '.png'
                    
                    if format_name == 'JPEG':
                        save_kwargs['quality'] = quality
                        save_kwargs['optimize'] = True
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                    elif format_name == 'PNG':
                        save_kwargs['optimize'] = True
                    elif format_name == 'WEBP':
                        save_kwargs['quality'] = quality
                        save_kwargs['method'] = 6
                    elif format_name == 'JPEG2000':
                        save_kwargs['quality'] = quality
                    
                    # Сохраняем в новом формате
                    try:
                        img.save(output_path, format=format_name, **save_kwargs)
                    except Exception as e:
                        # Если формат не поддерживается, пробуем PNG
                        if format_name not in ('PNG', 'JPEG'):
                            format_name = 'PNG'
                            output_path = os.path.splitext(output_path)[0] + '.png'
                            img.save(output_path, format='PNG', optimize=True)
                            logger.warning(f"Формат {target_ext} не поддерживается, сохранено как PNG")
                        else:
                            raise
                
                # Удаляем резервную копию если операция успешна
                if backup_path and os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception:
                        pass
                
                return True, "Файл успешно конвертирован", output_path
            else:
                return False, "Неподдерживаемый формат файла", None
            
        except Exception as e:
            logger.error(f"Ошибка при конвертации файла {file_path}: {e}", exc_info=True)
            # Восстанавливаем из резервной копии при ошибке
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, file_path)
                    os.remove(backup_path)
                except Exception:
                    pass
            return False, f"Ошибка: {str(e)}", None
    
    def convert_batch(self, file_paths: List[str], target_format: str, 
                     output_dir: Optional[str] = None, quality: int = 95,
                     create_backup: bool = True) -> List[Tuple[str, bool, str, Optional[str]]]:
        """Конвертация нескольких файлов.
        
        Args:
            file_paths: Список путей к файлам
            target_format: Целевой формат (расширение с точкой)
            output_dir: Директория для сохранения (если None, сохраняет рядом с исходными)
            quality: Качество для JPEG (1-100)
            create_backup: Создавать ли резервные копии
            
        Returns:
            Список кортежей (путь, успех, сообщение, путь к выходному файлу)
        """
        results = []
        for file_path in file_paths:
            output_path = None
            if output_dir:
                base_name = os.path.basename(os.path.splitext(file_path)[0])
                output_path = os.path.join(output_dir, base_name + target_format.lower())
            
            success, message, converted_path = self.convert(
                file_path, target_format, output_path, quality, create_backup
            )
            results.append((file_path, success, message, converted_path))
        return results
    
    def _convert_document(self, file_path: str, target_ext: str, output_path: str, 
                         create_backup: bool) -> Tuple[bool, str, Optional[str]]:
        """Конвертация документов Word.
        
        Args:
            file_path: Путь к исходному файлу
            target_ext: Целевое расширение (с точкой)
            output_path: Путь для сохранения
            create_backup: Создавать ли резервную копию
            
        Returns:
            Кортеж (успех, сообщение, путь к выходному файлу)
        """
        if not self.docx_available:
            return False, "python-docx не установлен", None
        
        try:
            # Открываем документ
            doc = self.docx_module.Document(file_path)
            
            # Сохраняем в новом формате
            if target_ext == '.docx':
                doc.save(output_path)
                return True, "Документ успешно конвертирован", output_path
            else:
                return False, f"Неподдерживаемый целевой формат: {target_ext}", None
            
        except Exception as e:
            logger.error(f"Ошибка при конвертации документа {file_path}: {e}", exc_info=True)
            return False, f"Ошибка: {str(e)}", None

