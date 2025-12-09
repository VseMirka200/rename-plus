"""Модуль для конвертации файлов.

Поддерживает конвертацию изображений (через Pillow) и базовую конвертацию файлов.
"""

import io
import logging
import os
import shutil
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from typing import Dict, List, Optional, Tuple

try:
    from config.constants import (
        COM_OPERATION_DELAY,
        DEFAULT_JPEG_QUALITY,
        PACKAGE_INSTALL_TIMEOUT,
    )
except ImportError:
    # Fallback если константы недоступны
    PACKAGE_INSTALL_TIMEOUT = 300
    COM_OPERATION_DELAY = 0.5
    DEFAULT_JPEG_QUALITY = 95

try:
    from core.com_utils import (
        cleanup_word_application,
        cleanup_word_document,
        convert_docx_with_word,
        create_word_application,
    )
    HAS_COM_UTILS = True
except ImportError:
    HAS_COM_UTILS = False

logger = logging.getLogger(__name__)


def _install_package(package_name: str) -> bool:
    """Установка пакета через pip.
    
    Args:
        package_name: Имя пакета для установки
        
    Returns:
        True если установка успешна, False иначе
    """
    try:
        logger.info(f"Попытка установки {package_name}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name],
            capture_output=True,
            text=True,
            timeout=PACKAGE_INSTALL_TIMEOUT,
            check=False,
        )
        if result.returncode == 0:
            logger.info(f"{package_name} успешно установлен")
            return True
        logger.warning(f"Не удалось установить {package_name}: {result.stderr}")
        return False
    except subprocess.TimeoutExpired:
        logger.error(f"Таймаут при установке {package_name}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при установке {package_name}: {e}")
        return False


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
        
        # Попытка импортировать docx2pdf для конвертации DOCX в PDF
        self.docx2pdf_available = False
        self.docx2pdf_convert = None
        self.comtypes = None
        self.win32com = None
        self.use_docx2pdf = False  # Флаг для отключения docx2pdf если доступны COM методы
        
        # Попытка импортировать pdf2docx для конвертации PDF в DOCX
        self.pdf2docx_available = False
        self.pdf2docx_convert = None
        self.Converter = None
        try:
            from pdf2docx import Converter
            self.Converter = Converter
            self.pdf2docx_available = True
            logger.info("pdf2docx доступен для конвертации PDF в DOCX")
        except ImportError:
            # Не устанавливаем автоматически при инициализации, чтобы не блокировать запуск
            # Пользователь может установить pdf2docx вручную при необходимости
            logger.debug("pdf2docx не найден. Для конвертации PDF в DOCX установите: pip install pdf2docx")
            self.pdf2docx_available = False
        
        # Пробуем альтернативный способ через comtypes или win32com (Windows)
        # Приоритет: win32com > comtypes > docx2pdf
        # ВАЖНО: Импортируем оба метода, чтобы использовать comtypes как fallback
        if sys.platform == 'win32':
            # Сначала пробуем win32com (более надежный)
            try:
                import win32com.client
                self.win32com = win32com.client
                self.docx2pdf_available = True
                logger.info("win32com доступен для конвертации DOCX в PDF")
            except ImportError:
                # Пробуем установить pywin32
                logger.info("win32com не найден, пытаемся установить pywin32...")
                if _install_package("pywin32"):
                    try:
                        import win32com.client
                        self.win32com = win32com.client
                        self.docx2pdf_available = True
                        logger.info("win32com успешно установлен и доступен для конвертации DOCX в PDF")
                    except ImportError:
                        logger.warning("pywin32 установлен, но win32com.client все еще недоступен")
                        # Пробуем comtypes
                        try:
                            import comtypes.client
                            self.comtypes = comtypes.client
                            # Пробуем импортировать pythoncom для инициализации COM
                            try:
                                import pythoncom
                                self.pythoncom = pythoncom
                            except ImportError:
                                pass
                            self.docx2pdf_available = True
                            logger.info("comtypes доступен для конвертации DOCX в PDF")
                        except ImportError:
                            # Пробуем установить comtypes
                            logger.info("comtypes не найден, пытаемся установить comtypes...")
                            if _install_package("comtypes"):
                                try:
                                    import comtypes.client
                                    self.comtypes = comtypes.client
                                    try:
                                        import pythoncom
                                        self.pythoncom = pythoncom
                                    except ImportError:
                                        pass
                                    self.docx2pdf_available = True
                                    logger.info("comtypes успешно установлен и доступен для конвертации DOCX в PDF")
                                except ImportError:
                                    logger.warning("comtypes установлен, но все еще недоступен")
                else:
                    # Если pywin32 не установился, пробуем comtypes
                    try:
                        import comtypes.client
                        self.comtypes = comtypes.client
                        # Пробуем импортировать pythoncom для инициализации COM
                        try:
                            import pythoncom
                            self.pythoncom = pythoncom
                        except ImportError:
                            pass
                        self.docx2pdf_available = True
                        logger.info("comtypes доступен для конвертации DOCX в PDF")
                    except ImportError:
                        # Пробуем установить comtypes
                        logger.info("comtypes не найден, пытаемся установить comtypes...")
                        if _install_package("comtypes"):
                            try:
                                import comtypes.client
                                self.comtypes = comtypes.client
                                try:
                                    import pythoncom
                                    self.pythoncom = pythoncom
                                except ImportError:
                                    pass
                                self.docx2pdf_available = True
                                logger.info("comtypes успешно установлен и доступен для конвертации DOCX в PDF")
                            except ImportError:
                                logger.warning("comtypes установлен, но все еще недоступен")
            
            # ВАЖНО: Пробуем импортировать comtypes даже если win32com доступен (для fallback)
            if self.win32com is not None and self.comtypes is None:
                try:
                    import comtypes.client
                    self.comtypes = comtypes.client
                    # Пробуем импортировать pythoncom для инициализации COM
                    try:
                        import pythoncom
                        self.pythoncom = pythoncom
                    except ImportError:
                        pass
                    logger.info("comtypes также доступен для конвертации DOCX в PDF (как fallback)")
                except ImportError:
                    # Пробуем установить comtypes
                    logger.info("comtypes не найден, пытаемся установить comtypes...")
                    if _install_package("comtypes"):
                        try:
                            import comtypes.client
                            self.comtypes = comtypes.client
                            try:
                                import pythoncom
                                self.pythoncom = pythoncom
                            except ImportError:
                                pass
                            logger.info("comtypes успешно установлен и доступен для конвертации DOCX в PDF (как fallback)")
                        except ImportError:
                            logger.warning("comtypes установлен, но все еще недоступен")
        
        # Пробуем docx2pdf только если COM методы недоступны
        if not self.win32com and not self.comtypes:
            try:
                from docx2pdf import convert as docx2pdf_convert
                self.docx2pdf_convert = docx2pdf_convert
                self.docx2pdf_available = True
                self.use_docx2pdf = True
                logger.info("docx2pdf доступен для конвертации DOCX в PDF (COM методы недоступны)")
            except ImportError:
                pass
        
        # Поддерживаемые форматы документов
        # Примечание: python-docx не поддерживает конвертацию в старый формат .doc
        self.supported_document_formats = {
            '.docx': 'DOCX',
            '.pdf': 'PDF'
        }
        
        # Поддерживаемые целевые форматы для документов
        self.supported_document_target_formats = {
            '.docx': 'DOCX',
            '.pdf': 'PDF'
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
        if source_ext in self.supported_document_formats:
            if target_ext in self.supported_document_target_formats:
                # DOCX в DOCX не поддерживается (тот же формат)
                if source_ext == '.docx' and target_ext == '.docx':
                    return False
                # PDF в PDF не поддерживается (тот же формат)
                if source_ext == '.pdf' and target_ext == '.pdf':
                    return False
                # DOCX в PDF
                if source_ext == '.docx' and target_ext == '.pdf':
                    return self.docx2pdf_available
                # PDF в DOCX
                if source_ext == '.pdf' and target_ext == '.docx':
                    return self.pdf2docx_available
                # Для других форматов документов
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
        if self.docx2pdf_available:
            if '.pdf' not in formats:
                formats.append('.pdf')
        return formats
    
    def get_file_type_category(self, file_path: str) -> Optional[str]:
        """Определение категории типа файла.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Категория файла: 'image', 'document', 'audio', 'video' или None
        """
        if not os.path.exists(file_path):
            return None
        
        ext = os.path.splitext(file_path)[1].lower()
        
        # Изображения (только популярные)
        image_extensions = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif',
            '.ico', '.svg', '.heic', '.heif', '.avif', '.dng', '.cr2', '.nef', '.raw'
        }
        if ext in image_extensions:
            return 'image'
        
        # Документы (только популярные)
        document_extensions = {
            '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt',
            '.txt', '.rtf', '.csv', '.html', '.htm', '.odt', '.ods', '.odp'
        }
        if ext in document_extensions:
            return 'document'
        
        # Аудио (только популярные)
        audio_extensions = {
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus'
        }
        if ext in audio_extensions:
            return 'audio'
        
        # Видео (только популярные)
        video_extensions = {
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
            '.mpg', '.mpeg', '.3gp'
        }
        if ext in video_extensions:
            return 'video'
        
        return None
    
    def convert(self, file_path: str, target_format: str, output_path: Optional[str] = None, 
                quality: int = 95, compress_pdf: bool = False) -> Tuple[bool, str, Optional[str]]:
        """Конвертация файла.
        
        Args:
            file_path: Путь к исходному файлу
            target_format: Целевой формат (расширение с точкой, например '.png')
            output_path: Путь для сохранения (если None, заменяет исходный файл)
            quality: Качество для JPEG (1-100)
            compress_pdf: Сжимать ли PDF после конвертации
            
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
        
        try:
            # Проверяем тип файла и конвертируем соответственно
            if source_ext in self.supported_document_formats:
                # Конвертация документов Word
                if source_ext == '.docx' and target_ext == '.pdf':
                    result = self._convert_docx_to_pdf(file_path, output_path, compress_pdf)
                    # Если конвертация успешна и нужно сжать PDF
                    if result[0] and compress_pdf and os.path.exists(result[2]):
                        compress_result = self._compress_pdf(result[2])
                        if compress_result[0]:
                            return True, f"{result[1]} (PDF сжат)", result[2]
                    return result
                elif source_ext == '.pdf' and target_ext == '.docx':
                    return self._convert_pdf_to_docx(file_path, output_path)
                else:
                    return self._convert_document(file_path, target_ext, output_path)
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
                
                return True, "Файл успешно конвертирован", output_path
            else:
                return False, "Неподдерживаемый формат файла", None
            
        except Exception as e:
            logger.error(f"Ошибка при конвертации файла {file_path}: {e}", exc_info=True)
            return False, f"Ошибка: {str(e)}", None
    
    def convert_batch(self, file_paths: List[str], target_format: str, 
                     output_dir: Optional[str] = None, quality: int = 95,
                     compress_pdf: bool = False) -> List[Tuple[str, bool, str, Optional[str]]]:
        """Конвертация нескольких файлов.
        
        Args:
            file_paths: Список путей к файлам
            target_format: Целевой формат (расширение с точкой)
            output_dir: Директория для сохранения (если None, сохраняет рядом с исходными)
            quality: Качество для JPEG (1-100)
            compress_pdf: Сжимать ли PDF после конвертации
            
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
                file_path, target_format, output_path, quality, compress_pdf
            )
            results.append((file_path, success, message, converted_path))
        return results
    
    def _convert_document(self, file_path: str, target_ext: str, output_path: str) -> Tuple[bool, str, Optional[str]]:
        """Конвертация документов Word.
        
        Args:
            file_path: Путь к исходному файлу
            target_ext: Целевое расширение (с точкой)
            output_path: Путь для сохранения
            
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
    
    def _find_pdf_in_source_directory(self, file_path: str) -> Optional[str]:
        """Поиск PDF файла в директории исходного файла.
        
        Args:
            file_path: Путь к исходному файлу
            
        Returns:
            Путь к найденному PDF или None
        """
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        return os.path.join(os.path.dirname(file_path), base_name + '.pdf')
    
    def _get_pdf_library(self) -> Tuple[Optional[type], Optional[type], bool]:
        """Получение библиотеки для работы с PDF.
        
        Returns:
            Tuple[PdfReader, PdfWriter, available] - классы и доступность
        """
        try:
            import PyPDF2
            return PyPDF2.PdfReader, PyPDF2.PdfWriter, True
        except ImportError:
            try:
                import pypdf
                return pypdf.PdfReader, pypdf.PdfWriter, True
            except ImportError:
                return None, None, False
    
    def _compress_pdf(self, pdf_path: str) -> Tuple[bool, str]:
        """Сжатие PDF файла.
        
        Args:
            pdf_path: Путь к PDF файлу
            
        Returns:
            Кортеж (успех, сообщение)
        """
        try:
            PdfReader, PdfWriter, pdf_available = self._get_pdf_library()
            
            if not pdf_available:
                return False, "Библиотека для работы с PDF не установлена (PyPDF2/pypdf)"
            
            # Читаем PDF
            with open(pdf_path, 'rb') as input_file:
                pdf_reader = PdfReader(input_file)
                pdf_writer = PdfWriter()
                
                # Копируем страницы с оптимизацией
                for page in pdf_reader.pages:
                    # Сжимаем страницу
                    page.compress_content_streams()
                    pdf_writer.add_page(page)
                
                # Удаляем метаданные для уменьшения размера
                pdf_writer.add_metadata({})
            
            # Сохраняем сжатый PDF во временный файл
            temp_path = pdf_path + '.temp'
            with open(temp_path, 'wb') as output_file:
                pdf_writer.write(output_file)
            
            # Заменяем оригинальный файл
            if os.path.exists(temp_path):
                original_size = os.path.getsize(pdf_path)
                shutil.move(temp_path, pdf_path)
                new_size = os.path.getsize(pdf_path)
                compression_ratio = (1 - new_size / original_size) * 100 if original_size > 0 else 0
                return True, f"PDF сжат (размер уменьшен на {compression_ratio:.1f}%)"
            
            return False, "Не удалось создать сжатый PDF"
            
        except Exception as e:
            logger.error(f"Ошибка при сжатии PDF {pdf_path}: {e}", exc_info=True)
            return False, f"Ошибка сжатия: {str(e)}"
    
    def _convert_docx_to_pdf(self, file_path: str, output_path: str, 
                              compress_pdf: bool = False) -> Tuple[bool, str, Optional[str]]:
        """Конвертация DOCX в PDF.
        
        Args:
            file_path: Путь к исходному DOCX файлу
            output_path: Путь для сохранения PDF
            compress_pdf: Сжимать ли PDF после конвертации
            
        Returns:
            Кортеж (успех, сообщение, путь к выходному файлу)
        """
        if not self.docx2pdf_available:
            return False, "Библиотека для конвертации DOCX в PDF не установлена. Установите docx2pdf или используйте Windows с установленным Microsoft Word", None
        
        try:
            # Нормализуем пути
            file_path = os.path.abspath(file_path)
            output_path = os.path.abspath(output_path)
            
            # Пробуем разные методы конвертации по порядку
            conversion_method = None
            conversion_success = False
            tried_methods = []  # Список методов, которые были попробованы
            
            # Метод 1: Пробуем использовать docx2pdf (только если COM методы недоступны)
            # Пропускаем docx2pdf если доступны COM методы, так как они более надежны
            if self.use_docx2pdf and self.docx2pdf_convert is not None and not self.win32com and not self.comtypes:
                logger.info(f"Пробуем конвертировать через docx2pdf: {file_path} -> {output_path}")
                try:
                    # docx2pdf может принимать путь к файлу или путь к папке
                    output_dir = os.path.dirname(output_path)
                    if not output_dir:
                        output_dir = os.path.dirname(file_path)
                    
                    # Убеждаемся, что директория существует
                    os.makedirs(output_dir, exist_ok=True)
                    
                    # ВАЖНО: docx2pdf может пытаться писать в stdout, который может быть None
                    # Поэтому перенаправляем stdout перед вызовом
                    # Перенаправляем stdout/stderr чтобы избежать ошибки 'NoneType' object has no attribute 'write'
                    # Также перехватываем sys.stdout и sys.stderr напрямую
                    sys_module = sys
                    old_stdout = sys_module.stdout
                    old_stderr = sys_module.stderr
                    fake_stdout = io.StringIO()
                    fake_stderr = io.StringIO()
                    
                    try:
                        # Устанавливаем фиктивные потоки напрямую в sys
                        # Это более надежно, чем contextlib.redirect_stdout
                        sys_module.stdout = fake_stdout
                        sys_module.stderr = fake_stderr
                        
                        try:
                            # Метод 1: передаем оба пути (исходный и выходной)
                            self.docx2pdf_convert(file_path, output_path)
                            conversion_method = "docx2pdf (2 params)"
                        except (TypeError, ValueError) as e1:
                            # Метод 2: передаем только исходный файл, выходной будет рядом
                            logger.debug(f"Попытка конвертации с двумя параметрами не удалась: {e1}, пробуем один параметр")
                            self.docx2pdf_convert(file_path)
                            conversion_method = "docx2pdf (1 param)"
                    finally:
                        # Восстанавливаем оригинальные потоки
                        sys_module.stdout = old_stdout
                        sys_module.stderr = old_stderr
                    
                    # Проверяем, создан ли файл
                    if os.path.exists(output_path):
                        logger.info(f"docx2pdf успешно создал файл: {output_path}")
                        conversion_success = True
                        return True, "Документ успешно конвертирован в PDF", output_path
                    
                    # Если файл не найден по указанному пути, ищем в директории исходного файла
                    possible_path = self._find_pdf_in_source_directory(file_path)
                    
                    if possible_path and os.path.exists(possible_path):
                        logger.info(f"docx2pdf создал файл в другой директории: {possible_path}")
                        if possible_path != output_path:
                            # Перемещаем файл в нужное место
                            try:
                                shutil.move(possible_path, output_path)
                                conversion_success = True
                                return True, "Документ успешно конвертирован в PDF", output_path
                            except Exception as move_e:
                                logger.warning(f"Не удалось переместить файл: {move_e}")
                                conversion_success = True
                                return True, "Документ успешно конвертирован в PDF", possible_path
                        conversion_success = True
                        return True, "Документ успешно конвертирован в PDF", output_path
                    
                    # Если файл не создан, пробуем следующий метод
                    logger.warning(f"docx2pdf не создал файл, пробуем COM методы")
                    conversion_success = False
                except Exception as e:
                    logger.error(f"Ошибка при вызове docx2pdf: {e}", exc_info=True)
                    conversion_success = False
            
            # Метод 2: Пробуем win32com (более надежный метод для Windows)
            if not conversion_success and self.win32com is not None and sys.platform == 'win32':
                tried_methods.append("win32com")
                logger.info(f"Пробуем конвертировать через win32com: {file_path} -> {output_path}")
                word = None
                try:
                    if HAS_COM_UTILS:
                        # Используем утилиты для создания Word объекта
                        word, error_msg = create_word_application(self.win32com)
                        if word is None:
                            logger.warning(f"{error_msg}. Пробуем comtypes...")
                            conversion_success = False
                        else:
                            # Используем утилиту для конвертации
                            success, error_msg = convert_docx_with_word(
                                word, file_path, output_path, "win32com"
                            )
                            if success:
                                time.sleep(COM_OPERATION_DELAY)
                                if os.path.exists(output_path):
                                    logger.info(f"win32com успешно создал файл: {output_path}")
                                    conversion_success = True
                                    return True, "Документ успешно конвертирован в PDF", output_path
                                # Проверяем альтернативное расположение
                                possible_path = self._find_pdf_in_source_directory(file_path)
                                if possible_path and os.path.exists(possible_path):
                                    logger.info(f"PDF найден в директории исходного файла: {possible_path}")
                                    try:
                                        shutil.move(possible_path, output_path)
                                        return True, "Документ успешно конвертирован в PDF", output_path
                                    except Exception as move_e:
                                        logger.warning(f"Не удалось переместить файл: {move_e}")
                                        return True, "Документ успешно конвертирован в PDF", possible_path
                            else:
                                logger.warning(f"Ошибка конвертации через win32com: {error_msg}. Пробуем comtypes...")
                                conversion_success = False
                    else:
                        # Fallback на старый код если утилиты недоступны
                        raise ImportError("COM утилиты недоступны")
                except Exception as e:
                    if HAS_COM_UTILS and word:
                        cleanup_word_application(word)
                    error_msg = str(e)
                    logger.error(f"Ошибка при конвертации через win32com: {error_msg}", exc_info=True)
                    if "Word.Application" in error_msg or "CLSID" in error_msg:
                        logger.warning("Microsoft Word не установлен через win32com. Пробуем comtypes...")
                    conversion_success = False
                finally:
                    if HAS_COM_UTILS and word:
                        cleanup_word_application(word)
            
            # Метод 3: Пробуем comtypes (fallback для Windows)
            if not conversion_success and self.comtypes is not None and sys.platform == 'win32':
                tried_methods.append("comtypes")
                logger.info(f"Пробуем конвертировать через comtypes: {file_path} -> {output_path}")
                # Используем COM для Windows (требует установленный Microsoft Word)
                # ВАЖНО: COM должен инициализироваться в том же потоке, где используется
                word = None
                com_initialized = False
                pythoncom_module = None
                
                try:
                    # Инициализируем COM в текущем потоке
                    if hasattr(self, 'pythoncom'):
                        pythoncom_module = self.pythoncom
                    else:
                        import pythoncom
                        pythoncom_module = pythoncom
                        self.pythoncom = pythoncom
                    
                    # Инициализируем COM для текущего потока
                    # ВАЖНО: COM должен быть инициализирован в каждом потоке отдельно
                    try:
                        # Пробуем использовать CoInitializeEx (более надежный метод)
                        if hasattr(pythoncom_module, 'CoInitializeEx'):
                            try:
                                # COINIT_APARTMENTTHREADED = 2
                                pythoncom_module.CoInitializeEx(2)
                            except (AttributeError, ValueError):
                                pythoncom_module.CoInitialize()
                        else:
                            pythoncom_module.CoInitialize()
                    except Exception as init_error:
                        # Если уже инициализирован, это нормально
                        if "already initialized" not in str(init_error).lower() and "RPC_E_CHANGED_MODE" not in str(init_error):
                            raise
                    com_initialized = True
                    
                    # Создаем объект Word
                    word = self.comtypes.CreateObject('Word.Application')
                    word.Visible = False
                    word.DisplayAlerts = 0  # Отключаем предупреждения
                    
                    # Открываем документ (используем полный путь)
                    doc_path = os.path.abspath(file_path)
                    doc = word.Documents.Open(doc_path, ReadOnly=True, ConfirmConversions=False)
                    
                    try:
                        # Сохраняем как PDF (используем полный путь)
                        pdf_path = os.path.abspath(output_path)
                        doc.SaveAs(pdf_path, FileFormat=17)  # 17 = PDF format
                    finally:
                        doc.Close(SaveChanges=False)
                    
                    word.Quit(SaveChanges=False)
                    word = None
                    
                    # Освобождаем COM
                    if com_initialized and pythoncom_module:
                        pythoncom_module.CoUninitialize()
                        com_initialized = False
                    
                    if os.path.exists(output_path):
                        return True, "Документ успешно конвертирован в PDF", output_path
                    else:
                        return False, "Файл PDF не был создан", None
                        
                except Exception as e:
                    # Очистка при ошибке
                    if word:
                        try:
                            word.Quit(SaveChanges=False)
                        except:
                            pass
                        word = None
                    
                    if com_initialized:
                        try:
                            if pythoncom_module:
                                pythoncom_module.CoUninitialize()
                        except:
                            pass
                        com_initialized = False
                    
                    logger.error(f"Ошибка при конвертации через comtypes: {e}", exc_info=True)
                    conversion_success = False
            
            # Если ни один метод не сработал
            if not conversion_success:
                error_msg = "Не удалось конвертировать DOCX в PDF. "
                
                if tried_methods:
                    error_msg += f"Пробовались методы: {', '.join(tried_methods)}. "
                    error_msg += "Убедитесь, что Microsoft Word установлен и доступен."
                else:
                    # Если ни один метод не был попробован, значит они недоступны
                    available_methods = []
                    if self.docx2pdf_convert:
                        available_methods.append("docx2pdf")
                    if self.win32com:
                        available_methods.append("win32com")
                    if self.comtypes:
                        available_methods.append("comtypes")
                    
                    if available_methods:
                        error_msg += f"Доступны методы: {', '.join(available_methods)}, но они не были использованы. "
                    else:
                        error_msg += "Установите docx2pdf или используйте Windows с установленным Microsoft Word."
                
                logger.error(error_msg)
                return False, error_msg, None
                
        except Exception as e:
            logger.error(f"Ошибка при конвертации DOCX в PDF {file_path}: {e}", exc_info=True)
            error_msg = str(e)
            if "Word.Application" in error_msg or "COM" in error_msg:
                return False, "Не удалось использовать Microsoft Word. Убедитесь, что Word установлен и доступен.", None
            return False, f"Ошибка: {error_msg}", None
    
    def _convert_pdf_to_docx(self, file_path: str, output_path: str) -> Tuple[bool, str, Optional[str]]:
        """Конвертация PDF в DOCX.
        
        Args:
            file_path: Путь к исходному PDF файлу
            output_path: Путь для сохранения DOCX
            
        Returns:
            Кортеж (успех, сообщение, путь к выходному файлу)
        """
        if not self.pdf2docx_available:
            return False, "Библиотека для конвертации PDF в DOCX не установлена. Установите pdf2docx", None
        
        try:
            # Нормализуем пути
            file_path = os.path.abspath(file_path)
            output_path = os.path.abspath(output_path)
            
            # Убеждаемся, что директория существует
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            logger.info(f"Конвертируем PDF в DOCX: {file_path} -> {output_path}")
            
            # Создаем конвертер
            converter = self.Converter(file_path)
            
            try:
                # Конвертируем PDF в DOCX
                converter.convert(output_path)
                
                # Проверяем, что файл создан
                if os.path.exists(output_path):
                    logger.info(f"PDF успешно конвертирован в DOCX: {output_path}")
                    return True, "PDF успешно конвертирован в DOCX", output_path
                else:
                    return False, "Файл DOCX не был создан", None
            finally:
                # Закрываем конвертер
                try:
                    converter.close()
                except Exception:
                    pass
                
        except Exception as e:
            logger.error(f"Ошибка при конвертации PDF в DOCX {file_path}: {e}", exc_info=True)
            error_msg = str(e)
            return False, f"Ошибка конвертации: {error_msg}", None

