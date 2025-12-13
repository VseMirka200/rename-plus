"""Модуль для конвертации файлов.

Обеспечивает конвертацию файлов между различными форматами:
- Изображения: JPG, PNG, BMP, TIFF, WEBP и др. (через Pillow)
- Документы: DOCX в PDF, PDF в DOCX (через COM или специализированные библиотеки)
- Аудио: MP3, WAV, FLAC и др. (через pydub)
- Видео: MP4, AVI, MKV и др. (через moviepy)

Поддерживает автоматическую установку необходимых библиотек.
"""

import io
import importlib
import importlib.util
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


def _is_in_venv() -> bool:
    """Проверка, запущена ли программа в виртуальном окружении.
    
    Returns:
        True если в виртуальном окружении, False иначе
    """
    # Проверяем через sys.prefix (в venv он отличается от base_prefix)
    if hasattr(sys, 'base_prefix'):
        return sys.prefix != sys.base_prefix
    # Альтернативная проверка через переменную окружения
    return bool(os.environ.get('VIRTUAL_ENV'))


def _install_package(package_name: str) -> bool:
    """Установка пакета через pip.
    
    Args:
        package_name: Имя пакета для установки
        
    Returns:
        True если установка успешна, False иначе
    """
    try:
        logger.info(f"Попытка установки {package_name}...")
        # Формируем команду установки
        install_cmd = [sys.executable, "-m", "pip", "install", package_name, "--upgrade"]
        # Используем --user только если НЕ в виртуальном окружении
        if not _is_in_venv():
            install_cmd.append("--user")
        install_cmd.append("--no-warn-script-location")
        
        result = subprocess.run(
            install_cmd,
            capture_output=True,
            text=True,
            timeout=PACKAGE_INSTALL_TIMEOUT,
            check=False,
        )
        if result.returncode == 0:
            logger.info(f"{package_name} успешно установлен")
            return True
        error_msg = result.stderr if result.stderr else result.stdout or "Неизвестная ошибка"
        logger.warning(f"Не удалось установить {package_name}: {error_msg[:500]}")
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
                    # Запускаем post-install скрипт для pywin32
                    try:
                        post_install_script = os.path.join(
                            sys.prefix, 'Scripts', 'pywin32_postinstall.py'
                        )
                        if os.path.exists(post_install_script):
                            logger.info("Запуск post-install скрипта для pywin32...")
                            post_result = subprocess.run(
                                [sys.executable, post_install_script, '-install'],
                                capture_output=True,
                                text=True,
                                timeout=60
                            )
                            if post_result.returncode == 0:
                                logger.info("pywin32 post-install скрипт выполнен успешно")
                            else:
                                logger.warning(f"pywin32 post-install скрипт завершился с ошибкой: {post_result.stderr[:200]}")
                    except Exception as e:
                        logger.warning(f"Не удалось запустить post-install скрипт для pywin32: {e}")
                    
                    try:
                        import win32com.client
                        self.win32com = win32com.client
                        self.docx2pdf_available = True
                        logger.info("win32com успешно установлен и доступен для конвертации DOCX в PDF")
                    except ImportError:
                        logger.warning("pywin32 установлен, но win32com.client все еще недоступен. Может потребоваться перезапуск программы.")
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
        
        # Пробуем загрузить docx2pdf как fallback метод (даже если COM методы доступны)
        # docx2pdf будет использоваться если COM методы не работают
        try:
            from docx2pdf import convert as docx2pdf_convert
            self.docx2pdf_convert = docx2pdf_convert
            self.docx2pdf_available = True
            if not self.win32com and not self.comtypes:
                self.use_docx2pdf = True
                logger.info("docx2pdf доступен для конвертации DOCX в PDF (COM методы недоступны)")
            else:
                self.use_docx2pdf = False
                logger.info("docx2pdf доступен как fallback метод для конвертации DOCX в PDF")
        except ImportError:
            pass
        
        # Поддерживаемые форматы документов
        # Примечание: python-docx не поддерживает конвертацию в старый формат .doc
        # Но через COM (win32com/comtypes) можно конвертировать и .doc файлы
        self.supported_document_formats = {
            '.docx': 'DOCX',
            '.doc': 'DOC',  # Старый формат Word, поддерживается через COM
            '.pdf': 'PDF'
        }
        
        # Поддерживаемые целевые форматы для документов
        self.supported_document_target_formats = {
            '.docx': 'DOCX',
            '.pdf': 'PDF'
        }
        
        # Попытка импортировать pydub для конвертации аудио
        self.pydub_available = False
        self.AudioSegment = None
        try:
            from pydub import AudioSegment
            self.AudioSegment = AudioSegment
            self.pydub_available = True
            logger.info("pydub доступен для конвертации аудио")
        except ImportError:
            logger.debug("pydub не найден. Будет установлен автоматически при первом запуске или при попытке конвертации.")
            self.pydub_available = False
        
        # Поддерживаемые форматы аудио для конвертации
        self.supported_audio_formats = {
            '.mp3': 'mp3',
            '.wav': 'wav',
            '.flac': 'flac',
            '.aac': 'aac',
            '.ogg': 'ogg',
            '.m4a': 'm4a',
            '.wma': 'wma',
            '.opus': 'opus',
            '.aiff': 'aiff',
            '.au': 'au',
            '.mp2': 'mp2',
            '.ac3': 'ac3',
            '.3gp': '3gp',
            '.amr': 'amr',
            '.ra': 'ra',
            '.ape': 'ape',
            '.mpc': 'mpc',
            '.tta': 'tta',
            '.wv': 'wv'
        }
        
        # Попытка импортировать moviepy для конвертации видео
        self.moviepy_available = False
        self.VideoFileClip = None
        try:
            from moviepy.editor import VideoFileClip
            self.VideoFileClip = VideoFileClip
            self.moviepy_available = True
            logger.info("moviepy доступен для конвертации видео")
        except ImportError:
            logger.debug("moviepy не найден. Будет установлен автоматически при первом запуске или при попытке конвертации.")
            self.moviepy_available = False
        
        # Поддерживаемые форматы видео для конвертации
        self.supported_video_formats = {
            '.mp4': 'mp4',
            '.avi': 'avi',
            '.mkv': 'mkv',
            '.mov': 'mov',
            '.wmv': 'wmv',
            '.flv': 'flv',
            '.webm': 'webm',
            '.m4v': 'm4v',
            '.mpg': 'mpg',
            '.mpeg': 'mpeg',
            '.3gp': '3gp',
            '.ogv': 'ogv',
            '.ts': 'ts',
            '.mts': 'mts',
            '.m2ts': 'm2ts',
            '.f4v': 'f4v',
            '.asf': 'asf',
            '.rm': 'rm',
            '.rmvb': 'rmvb',
            '.vob': 'vob',
            '.divx': 'divx',
            '.xvid': 'xvid'
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
                # DOC в DOC не поддерживается (тот же формат)
                if source_ext == '.doc' and target_ext == '.doc':
                    return False
                # PDF в PDF не поддерживается (тот же формат)
                if source_ext == '.pdf' and target_ext == '.pdf':
                    return False
                # DOCX в PDF
                if source_ext == '.docx' and target_ext == '.pdf':
                    return self.docx2pdf_available
                # DOC в PDF (через COM)
                if source_ext == '.doc' and target_ext == '.pdf':
                    return self.docx2pdf_available
                # PDF в DOCX
                if source_ext == '.pdf' and target_ext == '.docx':
                    # Динамическая проверка доступности pdf2docx (на случай если библиотека была установлена после инициализации)
                    if not self.pdf2docx_available or self.Converter is None:
                        try:
                            # Обновляем sys.path для обнаружения новых модулей
                            try:
                                import site
                                user_site = site.getusersitepackages()
                                if user_site and user_site not in sys.path:
                                    sys.path.insert(0, user_site)
                                    site.addsitedir(user_site)
                            except Exception:
                                pass
                            
                            # Очищаем кэш импортов для pdf2docx
                            modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith('pdf2docx')]
                            for m in modules_to_remove:
                                try:
                                    del sys.modules[m]
                                except KeyError:
                                    pass
                            
                            # Пробуем импортировать pdf2docx
                            from pdf2docx import Converter
                            self.Converter = Converter
                            self.pdf2docx_available = True
                            logger.info("pdf2docx успешно импортирован (обнаружен в can_convert)")
                        except ImportError:
                            return False
                    return self.pdf2docx_available
                # Для других форматов документов
                if self.docx_available:
                    return True
        
        # Проверяем конвертацию аудио
        # Показываем как поддерживаемый формат, даже если библиотека не установлена
        # (пользователь увидит сообщение при попытке конвертации)
        if source_ext in self.supported_audio_formats and target_ext in self.supported_audio_formats:
            return True
        
        # Проверяем конвертацию видео
        # Показываем как поддерживаемый формат, даже если библиотека не установлена
        # (пользователь увидит сообщение при попытке конвертации)
        if source_ext in self.supported_video_formats and target_ext in self.supported_video_formats:
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
        # Всегда включаем аудио и видео форматы (библиотеки могут быть установлены позже)
        formats.extend(list(self.supported_audio_formats.keys()))
        formats.extend(list(self.supported_video_formats.keys()))
        # Удаляем дубликаты и сортируем
        formats = sorted(list(set(formats)))
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
        
        # Аудио (расширенный список)
        audio_extensions = set(self.supported_audio_formats.keys())
        if ext in audio_extensions:
            return 'audio'
        
        # Видео (расширенный список)
        video_extensions = set(self.supported_video_formats.keys())
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
                # Конвертация документов Word в PDF
                if (source_ext == '.docx' or source_ext == '.doc') and target_ext == '.pdf':
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
            elif source_ext in self.supported_audio_formats:
                # Конвертация аудио
                return self._convert_audio(file_path, output_path, source_ext, target_ext, quality)
            elif source_ext in self.supported_video_formats:
                # Конвертация видео
                return self._convert_video(file_path, output_path, source_ext, target_ext, quality)
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
        """Конвертация DOCX/DOC в PDF.
        
        Args:
            file_path: Путь к исходному DOCX или DOC файлу
            output_path: Путь для сохранения PDF
            compress_pdf: Сжимать ли PDF после конвертации
            
        Returns:
            Кортеж (успех, сообщение, путь к выходному файлу)
        """
        if not self.docx2pdf_available:
            source_ext = os.path.splitext(file_path)[1].lower()
            format_name = "DOCX" if source_ext == '.docx' else "DOC"
            return False, f"Библиотека для конвертации {format_name} в PDF не установлена. Установите docx2pdf или используйте Windows с установленным Microsoft Word", None
        
        try:
            # Нормализуем пути
            file_path = os.path.abspath(file_path)
            output_path = os.path.abspath(output_path)
            
            # Определяем расширение исходного файла
            source_ext = os.path.splitext(file_path)[1].lower()
            
            # Пробуем разные методы конвертации по порядку
            conversion_method = None
            conversion_success = False
            tried_methods = []  # Список методов, которые были попробованы
            
            # Метод 1: Пробуем использовать docx2pdf (только если COM методы недоступны)
            # Пропускаем docx2pdf если доступны COM методы, так как они более надежны
            # ВАЖНО: docx2pdf может не поддерживать старые .doc файлы, поэтому для .doc лучше использовать COM
            if self.use_docx2pdf and self.docx2pdf_convert is not None and not self.win32com and not self.comtypes and source_ext == '.docx':
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
            elif source_ext == '.doc':
                # Для старых .doc файлов сразу используем COM методы
                logger.info(f"Файл .doc обнаружен, используем COM методы для конвертации")
                conversion_success = False
            
            # Метод 2: Пробуем win32com (более надежный метод для Windows)
            if not conversion_success and self.win32com is not None and sys.platform == 'win32':
                tried_methods.append("win32com")
                logger.info(f"Пробуем конвертировать через win32com: {file_path} -> {output_path}")
                word = None
                com_initialized = False
                pythoncom_module = None
                try:
                    # Инициализируем COM в текущем потоке для win32com
                    try:
                        import pythoncom
                        pythoncom_module = pythoncom
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
                            logger.warning(f"Ошибка инициализации COM для win32com: {init_error}")
                    com_initialized = True
                    
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
                    # Освобождаем COM для win32com
                    if com_initialized and pythoncom_module:
                        try:
                            pythoncom_module.CoUninitialize()
                        except Exception:
                            pass
            
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
                    error_msg = str(e)
                    # Специальная обработка ошибки генерации кода в comtypes
                    if "CodeGenerator" in error_msg and "NoneType" in error_msg:
                        logger.error(f"Ошибка генерации кода в comtypes (известная проблема библиотеки): {error_msg}")
                        logger.warning("comtypes не может сгенерировать код для Word интерфейсов. Пропускаем comtypes.")
                    elif "CoInitialize" in error_msg:
                        logger.error(f"Ошибка инициализации COM в comtypes: {error_msg}")
                    else:
                        logger.error(f"Ошибка при конвертации через comtypes: {error_msg}", exc_info=True)
                    
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
                    
                    conversion_success = False
            
            # Если ни один метод не сработал, пробуем docx2pdf как последний fallback
            if not conversion_success and self.docx2pdf_convert is not None and source_ext == '.docx':
                logger.info("Все COM методы не сработали, пробуем docx2pdf как fallback...")
                tried_methods.append("docx2pdf")
                docx2pdf_com_initialized = False
                docx2pdf_pythoncom = None
                try:
                    # docx2pdf использует COM внутри, поэтому нужно инициализировать COM
                    try:
                        import pythoncom
                        docx2pdf_pythoncom = pythoncom
                        # Пробуем использовать CoInitializeEx (более надежный метод)
                        if hasattr(pythoncom, 'CoInitializeEx'):
                            try:
                                # COINIT_APARTMENTTHREADED = 2
                                pythoncom.CoInitializeEx(2)
                            except (AttributeError, ValueError):
                                pythoncom.CoInitialize()
                        else:
                            pythoncom.CoInitialize()
                    except Exception as init_error:
                        # Если уже инициализирован, это нормально
                        if "already initialized" not in str(init_error).lower() and "RPC_E_CHANGED_MODE" not in str(init_error):
                            logger.warning(f"Ошибка инициализации COM для docx2pdf: {init_error}")
                    docx2pdf_com_initialized = True
                    
                    output_dir = os.path.dirname(output_path)
                    if not output_dir:
                        output_dir = os.path.dirname(file_path)
                    os.makedirs(output_dir, exist_ok=True)
                    
                    old_stdout = sys.stdout
                    old_stderr = sys.stderr
                    sys.stdout = io.StringIO()
                    sys.stderr = io.StringIO()
                    
                    try:
                        self.docx2pdf_convert(file_path, output_path)
                    except (TypeError, ValueError):
                        self.docx2pdf_convert(file_path)
                    finally:
                        sys.stdout = old_stdout
                        sys.stderr = old_stderr
                        # Освобождаем COM после docx2pdf
                        if docx2pdf_com_initialized and docx2pdf_pythoncom:
                            try:
                                docx2pdf_pythoncom.CoUninitialize()
                            except Exception:
                                pass
                    
                    if os.path.exists(output_path):
                        logger.info("docx2pdf успешно конвертировал файл")
                        return True, "Документ успешно конвертирован в PDF через docx2pdf", output_path
                    
                    possible_path = self._find_pdf_in_source_directory(file_path)
                    if possible_path and os.path.exists(possible_path):
                        if possible_path != output_path:
                            try:
                                shutil.move(possible_path, output_path)
                            except Exception:
                                pass
                        logger.info("docx2pdf успешно конвертировал файл (найден в другой директории)")
                        return True, "Документ успешно конвертирован в PDF через docx2pdf", output_path
                except Exception as e:
                    error_msg = str(e)
                    logger.warning(f"docx2pdf также не сработал: {error_msg}")
                    # Освобождаем COM при ошибке
                    if docx2pdf_com_initialized and docx2pdf_pythoncom:
                        try:
                            docx2pdf_pythoncom.CoUninitialize()
                        except Exception:
                            pass
            
            # Если все методы не сработали, формируем сообщение об ошибке
            if not conversion_success:
                format_name = "DOCX" if source_ext == '.docx' else "DOC"
                error_msg = f"Не удалось конвертировать {format_name} в PDF. "
                
                if tried_methods:
                    error_msg += f"Пробовались методы: {', '.join(tried_methods)}. "
                    
                    # Проверяем наличие Word для более информативного сообщения
                    if HAS_COM_UTILS:
                        try:
                            from core.com_utils import check_word_installed
                            word_installed, install_msg = check_word_installed()
                            if not word_installed:
                                error_msg += install_msg
                                if self.docx2pdf_convert and source_ext == '.docx':
                                    error_msg += " Или установите docx2pdf: pip install docx2pdf"
                            else:
                                error_msg += "Возможно, Word заблокирован или недоступен. Попробуйте закрыть все окна Word и перезапустить программу."
                                if self.docx2pdf_convert and source_ext == '.docx':
                                    error_msg += " Или установите docx2pdf для альтернативного метода: pip install docx2pdf"
                        except Exception:
                            error_msg += "Убедитесь, что Microsoft Word установлен и доступен."
                            if self.docx2pdf_convert and source_ext == '.docx':
                                error_msg += " Или используйте docx2pdf: pip install docx2pdf"
                    else:
                        error_msg += "Убедитесь, что Microsoft Word установлен и доступен."
                        if self.docx2pdf_convert and source_ext == '.docx':
                            error_msg += " Или используйте docx2pdf: pip install docx2pdf"
                else:
                    # Если ни один метод не был попробован
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
                        error_msg += "Установите docx2pdf (pip install docx2pdf) или используйте Windows с установленным Microsoft Word."
                
                logger.error(error_msg)
                return False, error_msg, None
                
        except Exception as e:
            logger.error(f"Ошибка при конвертации Word документа в PDF {file_path}: {e}", exc_info=True)
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
        # Динамическая проверка и импорт pdf2docx (на случай если библиотека была установлена после инициализации)
        if not self.pdf2docx_available or self.Converter is None:
            try:
                # Обновляем sys.path для обнаружения новых модулей
                try:
                    import site
                    user_site = site.getusersitepackages()
                    if user_site and user_site not in sys.path:
                        sys.path.insert(0, user_site)
                        site.addsitedir(user_site)
                except Exception:
                    pass
                
                # Очищаем кэш импортов для pdf2docx
                modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith('pdf2docx')]
                for m in modules_to_remove:
                    try:
                        del sys.modules[m]
                    except KeyError:
                        pass
                
                # Пробуем импортировать pdf2docx
                from pdf2docx import Converter
                self.Converter = Converter
                self.pdf2docx_available = True
                logger.info("pdf2docx успешно импортирован для конвертации PDF в DOCX")
            except ImportError:
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
    
    def _convert_audio(self, file_path: str, output_path: str, source_ext: str, 
                       target_ext: str, bitrate: int = 192) -> Tuple[bool, str, Optional[str]]:
        """Конвертация аудио файлов.
        
        Args:
            file_path: Путь к исходному аудио файлу
            output_path: Путь для сохранения
            source_ext: Исходное расширение
            target_ext: Целевое расширение
            bitrate: Битрейт для выходного файла (кбит/с)
            
        Returns:
            Кортеж (успех, сообщение, путь к выходному файлу)
        """
        if not self.pydub_available:
            # Пробуем установить pydub автоматически
            logger.info("pydub не найден, пытаемся установить...")
            if _install_package("pydub"):
                # После установки нужно обновить sys.path и попробовать импортировать
                # Python не всегда может загрузить только что установленный модуль в текущем процессе
                # После установки пытаемся загрузить модуль
                # Python не всегда может загрузить только что установленный модуль в текущем процессе
                try:
                    import site
                    import importlib
                    import importlib.util
                    
                    # Добавляем пользовательский site-packages в путь
                    user_site = site.getusersitepackages()
                    if user_site and os.path.exists(user_site):
                        if user_site not in sys.path:
                            sys.path.insert(0, user_site)
                        # Также добавляем через addsitedir для обработки .pth файлов
                        site.addsitedir(user_site)
                    
                    # Очищаем кэш импортов для pydub и его подмодулей
                    modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith('pydub')]
                    for m in modules_to_remove:
                        try:
                            del sys.modules[m]
                        except KeyError:
                            pass
                    
                    # Небольшая задержка для завершения установки
                    time.sleep(0.5)
                    
                    # Пробуем импортировать через importlib для более надежной загрузки
                    try:
                        spec = importlib.util.find_spec("pydub")
                        if spec is None or spec.loader is None:
                            raise ImportError("pydub не найден в sys.path")
                        
                        pydub_module = importlib.import_module("pydub")
                        AudioSegment = pydub_module.AudioSegment
                        self.AudioSegment = AudioSegment
                        self.pydub_available = True
                        logger.info("pydub успешно установлен и загружен")
                    except (ImportError, AttributeError):
                        # Пробуем обычный импорт
                        from pydub import AudioSegment
                        self.AudioSegment = AudioSegment
                        self.pydub_available = True
                        logger.info("pydub успешно установлен и загружен")
                        
                except Exception as e:
                    # Если не удалось загрузить, проверяем, что библиотека установлена
                    logger.warning(f"Не удалось загрузить pydub сразу после установки: {e}")
                    # Проверяем, что библиотека действительно установлена
                    check_result = subprocess.run(
                        [sys.executable, "-m", "pip", "show", "pydub"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if check_result.returncode == 0:
                        # Библиотека установлена, но нужен перезапуск для загрузки
                        logger.info("pydub установлен, но требуется перезапуск программы для загрузки модуля")
                        return False, "pydub установлен успешно. Перезапустите программу для применения изменений, затем попробуйте конвертировать снова.", None
                    else:
                        return False, "Не удалось установить pydub. Установите вручную: pip install pydub", None
            else:
                return False, "Не удалось установить pydub автоматически. Установите вручную: pip install pydub", None
        
        try:
            # Нормализуем пути
            file_path = os.path.abspath(file_path)
            output_path = os.path.abspath(output_path)
            
            # Убеждаемся, что директория существует
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            logger.info(f"Конвертируем аудио: {file_path} -> {output_path}")
            
            # Загружаем аудио файл
            audio = self.AudioSegment.from_file(file_path, format=source_ext[1:])
            
            # Определяем параметры экспорта
            format_name = target_ext[1:].lower()
            export_params = {}
            
            # Настройки битрейта для разных форматов
            if format_name in ('mp3', 'aac', 'ogg', 'opus'):
                export_params['bitrate'] = f"{bitrate}k"
            elif format_name == 'wav':
                export_params['format'] = 'wav'
            
            # Экспортируем в новый формат
            audio.export(output_path, format=format_name, **export_params)
            
            # Проверяем, что файл создан
            if os.path.exists(output_path):
                logger.info(f"Аудио успешно конвертировано: {output_path}")
                return True, "Аудио файл успешно конвертирован", output_path
            else:
                return False, "Файл не был создан", None
                
        except Exception as e:
            logger.error(f"Ошибка при конвертации аудио {file_path}: {e}", exc_info=True)
            error_msg = str(e)
            # Проверяем, требуется ли ffmpeg
            if "ffmpeg" in error_msg.lower() or "ffprobe" in error_msg.lower():
                return False, "Требуется FFmpeg. Установите FFmpeg: https://ffmpeg.org/download.html", None
            return False, f"Ошибка конвертации: {error_msg}", None
    
    def _convert_video_via_subprocess(self, file_path: str, output_path: str, source_ext: str, 
                                      target_ext: str, quality: int = 95) -> Tuple[bool, str, Optional[str]]:
        """Конвертация видео через отдельный процесс Python (когда moviepy не может быть импортирован в текущем процессе).
        
        Args:
            file_path: Путь к исходному видео файлу
            output_path: Путь для сохранения
            source_ext: Исходное расширение
            target_ext: Целевое расширение
            quality: Качество видео (1-100)
            
        Returns:
            Кортеж (успех, сообщение, путь к выходному файлу)
        """
        try:
            # Нормализуем пути
            file_path = os.path.abspath(file_path)
            output_path = os.path.abspath(output_path)
            
            # Убеждаемся, что директория существует
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            logger.info(f"Конвертируем видео через subprocess: {file_path} -> {output_path}")
            
            # Определяем параметры экспорта
            format_name = target_ext[1:].lower()
            codec = 'libx264'  # По умолчанию H.264
            audio_codec = 'aac'  # По умолчанию AAC
            
            # Настройки для разных форматов
            if format_name in ('mp4', 'm4v'):
                codec = 'libx264'
                audio_codec = 'aac'
            elif format_name == 'avi':
                codec = 'libx264'
                audio_codec = 'mp3'
            elif format_name in ('webm', 'ogv'):
                codec = 'libvpx-vp9'
                audio_codec = 'libopus'
            elif format_name == 'mkv':
                codec = 'libx264'
                audio_codec = 'libmp3lame'
            
            # Преобразуем качество (1-100) в битрейт
            if quality >= 90:
                bitrate = '5000k'
            elif quality >= 70:
                bitrate = '3000k'
            elif quality >= 50:
                bitrate = '2000k'
            else:
                bitrate = '1000k'
            
            # Создаем Python скрипт для конвертации
            convert_script = f"""
import sys
import os
from moviepy.editor import VideoFileClip

file_path = r"{file_path}"
output_path = r"{output_path}"
codec = "{codec}"
audio_codec = "{audio_codec}"
bitrate = "{bitrate}"

try:
    video = VideoFileClip(file_path)
    video.write_videofile(
        output_path,
        codec=codec,
        audio_codec=audio_codec,
        bitrate=bitrate,
        logger=None
    )
    video.close()
    if os.path.exists(output_path):
        print("SUCCESS")
    else:
        print("ERROR: File not created")
        sys.exit(1)
except Exception as e:
    print(f"ERROR: {{str(e)}}")
    sys.exit(1)
"""
            
            # Запускаем конвертацию в отдельном процессе
            result = subprocess.run(
                [sys.executable, "-c", convert_script],
                capture_output=True,
                text=True,
                timeout=600  # Таймаут 10 минут для больших видео
            )
            
            if result.returncode == 0 and 'SUCCESS' in result.stdout:
                if os.path.exists(output_path):
                    logger.info(f"Видео успешно конвертировано через subprocess: {output_path}")
                    return True, "Видео файл успешно конвертирован", output_path
                else:
                    return False, "Файл не был создан", None
            else:
                error_msg = result.stderr if result.stderr else result.stdout or "Неизвестная ошибка"
                logger.error(f"Ошибка конвертации через subprocess: {error_msg}")
                if "ffmpeg" in error_msg.lower() or "ffprobe" in error_msg.lower():
                    return False, "Требуется FFmpeg. Установите FFmpeg: https://ffmpeg.org/download.html", None
                return False, f"Ошибка конвертации: {error_msg[:200]}", None
                
        except subprocess.TimeoutExpired:
            logger.error("Таймаут при конвертации видео через subprocess")
            return False, "Таймаут при конвертации видео", None
        except Exception as e:
            logger.error(f"Ошибка при конвертации видео через subprocess {file_path}: {e}", exc_info=True)
            return False, f"Ошибка конвертации: {str(e)[:200]}", None
    
    def _convert_video(self, file_path: str, output_path: str, source_ext: str, 
                       target_ext: str, quality: int = 95) -> Tuple[bool, str, Optional[str]]:
        """Конвертация видео файлов.
        
        Args:
            file_path: Путь к исходному видео файлу
            output_path: Путь для сохранения
            source_ext: Исходное расширение
            target_ext: Целевое расширение
            quality: Качество видео (1-100)
            
        Returns:
            Кортеж (успех, сообщение, путь к выходному файлу)
        """
        if not self.moviepy_available:
            # Пробуем установить moviepy автоматически
            logger.info("moviepy не найден, пытаемся установить...")
            # moviepy может быть большой библиотекой, увеличиваем таймаут
            try:
                logger.info("Установка moviepy (это может занять несколько минут)...")
                # Формируем команду установки
                install_cmd = [sys.executable, "-m", "pip", "install", "moviepy", "--upgrade"]
                # Используем --user только если НЕ в виртуальном окружении
                if not _is_in_venv():
                    install_cmd.append("--user")
                
                result = subprocess.run(
                    install_cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,  # Увеличенный таймаут для moviepy
                    check=False,
                )
                if result.returncode == 0:
                    try:
                        # Обновляем sys.path для поиска только что установленных модулей
                        import site
                        import importlib
                        import importlib.util
                        
                        # Обновляем site-packages
                        try:
                            site.main()  # Перезагружает site-packages
                        except Exception:
                            pass
                        
                        # Получаем пути к site-packages
                        try:
                            user_site = site.getusersitepackages()
                            if user_site and os.path.exists(user_site) and user_site not in sys.path:
                                sys.path.insert(0, user_site)
                                site.addsitedir(user_site)
                        except Exception:
                            pass
                        
                        # Также добавляем стандартные пути site-packages
                        try:
                            for site_dir in site.getsitepackages():
                                if site_dir not in sys.path:
                                    sys.path.insert(0, site_dir)
                                    site.addsitedir(site_dir)
                        except Exception:
                            pass
                        
                        # Получаем путь к установленному пакету через pip show
                        try:
                            show_result = subprocess.run(
                                [sys.executable, "-m", "pip", "show", "moviepy"],
                                capture_output=True,
                                text=True,
                                timeout=10
                            )
                            if show_result.returncode == 0:
                                # Ищем Location в выводе pip show
                                for line in show_result.stdout.split('\n'):
                                    if line.startswith('Location:'):
                                        location = line.split(':', 1)[1].strip()
                                        if location and os.path.exists(location) and location not in sys.path:
                                            sys.path.insert(0, location)
                                            site.addsitedir(location)
                                            logger.debug(f"Добавлен путь в sys.path: {location}")
                                        break
                        except (OSError, subprocess.SubprocessError, AttributeError) as e:
                            logger.debug(f"Не удалось обновить sys.path через pip show: {e}")
                        
                        # Очищаем кэш импортов для moviepy и его подмодулей
                        modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith('moviepy')]
                        for m in modules_to_remove:
                            try:
                                del sys.modules[m]
                            except KeyError:
                                pass
                        
                        # Небольшая задержка для завершения установки и обновления sys.path
                        time.sleep(2.0)  # Увеличиваем задержку для надежности
                        
                        # Пробуем проверить импорт через отдельный процесс Python
                        # Это более надежный способ, так как новый процесс увидит установленный пакет
                        try:
                            check_import_cmd = [
                                sys.executable, "-c",
                                "import moviepy.editor; print('OK')"
                            ]
                            check_result = subprocess.run(
                                check_import_cmd,
                                capture_output=True,
                                text=True,
                                timeout=10
                            )
                            if check_result.returncode == 0 and 'OK' in check_result.stdout:
                                # Модуль доступен в новом процессе, обновляем sys.path еще раз
                                try:
                                    site.main()
                                    # Получаем путь еще раз
                                    show_result = subprocess.run(
                                        [sys.executable, "-m", "pip", "show", "moviepy"],
                                        capture_output=True,
                                        text=True,
                                        timeout=10
                                    )
                                    if show_result.returncode == 0:
                                        for line in show_result.stdout.split('\n'):
                                            if line.startswith('Location:'):
                                                location = line.split(':', 1)[1].strip()
                                                if location and os.path.exists(location):
                                                    if location not in sys.path:
                                                        sys.path.insert(0, location)
                                                        site.addsitedir(location)
                                                    # Также добавляем moviepy подпапку если есть
                                                    moviepy_path = os.path.join(location, 'moviepy')
                                                    if os.path.exists(moviepy_path) and moviepy_path not in sys.path:
                                                        sys.path.insert(0, moviepy_path)
                                                break
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        
                        # Удаляем все модули moviepy из кеша перед импортом
                        modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith('moviepy')]
                        for m in modules_to_remove:
                            try:
                                del sys.modules[m]
                            except KeyError:
                                pass
                        
                        # Дополнительная задержка после очистки кеша
                        time.sleep(0.5)
                        
                        # Пробуем импортировать через importlib для более надежной загрузки
                        try:
                            # Сначала пробуем найти спецификацию модуля moviepy (не moviepy.editor)
                            spec = importlib.util.find_spec("moviepy")
                            if spec is None:
                                # Пробуем еще раз с задержкой
                                time.sleep(0.5)
                                spec = importlib.util.find_spec("moviepy")
                            
                            if spec is not None and spec.origin:
                                # Загружаем модуль через importlib
                                try:
                                    # Сначала импортируем базовый модуль
                                    importlib.import_module("moviepy")
                                    # Затем импортируем editor
                                    moviepy_module = importlib.import_module("moviepy.editor")
                                    VideoFileClip = moviepy_module.VideoFileClip
                                    self.VideoFileClip = VideoFileClip
                                    self.moviepy_available = True
                                    logger.info("moviepy успешно установлен и загружен")
                                except (ImportError, AttributeError) as import_err:
                                    # Пробуем обычный импорт
                                    from moviepy.editor import VideoFileClip  # type: ignore
                                    self.VideoFileClip = VideoFileClip
                                    self.moviepy_available = True
                                    logger.info("moviepy успешно установлен и загружен (обычный импорт)")
                            else:
                                # Пробуем обычный импорт даже если spec не найден
                                try:
                                    from moviepy.editor import VideoFileClip  # type: ignore
                                    self.VideoFileClip = VideoFileClip
                                    self.moviepy_available = True
                                    logger.info("moviepy успешно установлен и загружен (fallback импорт)")
                                except ImportError:
                                    raise ImportError("moviepy.editor не найден в sys.path после установки")
                        except (ImportError, AttributeError) as e:
                            # Последняя попытка с дополнительной задержкой и обновлением sys.path
                            time.sleep(1)
                            try:
                                # Обновляем sys.path еще раз
                                site.main()
                                
                                # Очищаем кеш еще раз
                                modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith('moviepy')]
                                for m in modules_to_remove:
                                    try:
                                        del sys.modules[m]
                                    except KeyError:
                                        pass
                                
                                from moviepy.editor import VideoFileClip  # type: ignore
                                self.VideoFileClip = VideoFileClip
                                self.moviepy_available = True
                                logger.info("moviepy успешно установлен и загружен (последняя попытка)")
                            except ImportError:
                                raise e  # Пробрасываем исходную ошибку
                            
                    except Exception as e:
                        # Если не удалось загрузить, проверяем, что библиотека установлена
                        logger.warning(f"Не удалось загрузить moviepy сразу после установки: {e}")
                        
                        # Проверяем через отдельный процесс Python, доступен ли moviepy
                        try:
                            check_import_cmd = [
                                sys.executable, "-c",
                                "import moviepy.editor; print('IMPORT_OK')"
                            ]
                            check_import_result = subprocess.run(
                                check_import_cmd,
                                capture_output=True,
                                text=True,
                                timeout=10
                            )
                            if check_import_result.returncode == 0 and 'IMPORT_OK' in check_import_result.stdout:
                                # Модуль доступен в новом процессе, но не в текущем
                                # Запускаем конвертацию в отдельном процессе Python
                                logger.info("moviepy установлен и доступен в новом процессе, запускаем конвертацию через subprocess")
                                return self._convert_video_via_subprocess(file_path, output_path, source_ext, target_ext, quality)
                        except Exception:
                            pass
                        
                        # Проверяем через pip show
                        check_result = subprocess.run(
                            [sys.executable, "-m", "pip", "show", "moviepy"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if check_result.returncode == 0:
                            # moviepy установлен, но не может быть импортирован в текущем процессе
                            # Пробуем запустить конвертацию через subprocess
                            logger.info("moviepy установлен, но не может быть импортирован. Пробуем конвертацию через subprocess")
                            try:
                                # Проверяем, доступен ли moviepy в новом процессе
                                check_import_cmd = [
                                    sys.executable, "-c",
                                    "import moviepy.editor; print('IMPORT_OK')"
                                ]
                                check_import_result = subprocess.run(
                                    check_import_cmd,
                                    capture_output=True,
                                    text=True,
                                    timeout=10
                                )
                                if check_import_result.returncode == 0 and 'IMPORT_OK' in check_import_result.stdout:
                                    return self._convert_video_via_subprocess(file_path, output_path, source_ext, target_ext, quality)
                            except Exception:
                                pass
                            logger.info("moviepy установлен, но требуется перезапуск программы для загрузки модуля")
                            return False, "moviepy установлен. Перезапустите программу.", None
                        else:
                            return False, "Не удалось установить moviepy. Установите вручную: pip install moviepy", None
                else:
                    error_msg = result.stderr if result.stderr else result.stdout or "Неизвестная ошибка"
                    logger.warning(f"Не удалось установить moviepy: {error_msg[:300]}")
                    return False, f"Не удалось установить moviepy автоматически. Установите вручную: pip install moviepy", None
            except subprocess.TimeoutExpired:
                logger.error("Таймаут при установке moviepy")
                return False, "Таймаут при установке moviepy. Установите вручную: pip install moviepy", None
            except Exception as e:
                logger.error(f"Ошибка при установке moviepy: {e}")
                return False, f"Ошибка установки moviepy: {str(e)[:200]}. Установите вручную: pip install moviepy", None
        
        try:
            # Нормализуем пути
            file_path = os.path.abspath(file_path)
            output_path = os.path.abspath(output_path)
            
            # Убеждаемся, что директория существует
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            logger.info(f"Конвертируем видео: {file_path} -> {output_path}")
            
            # Загружаем видео файл
            video = self.VideoFileClip(file_path)
            
            try:
                # Определяем параметры экспорта
                format_name = target_ext[1:].lower()
                codec = 'libx264'  # По умолчанию H.264
                audio_codec = 'aac'  # По умолчанию AAC
                
                # Настройки для разных форматов
                if format_name in ('mp4', 'm4v'):
                    codec = 'libx264'
                    audio_codec = 'aac'
                elif format_name == 'avi':
                    codec = 'libx264'
                    audio_codec = 'mp3'
                elif format_name in ('webm', 'ogv'):
                    codec = 'libvpx-vp9'
                    audio_codec = 'libopus'
                elif format_name == 'mkv':
                    codec = 'libx264'
                    audio_codec = 'libmp3lame'
                
                # Преобразуем качество (1-100) в битрейт
                # Качество 95 -> высокий битрейт, 50 -> средний
                if quality >= 90:
                    bitrate = '5000k'
                elif quality >= 70:
                    bitrate = '3000k'
                elif quality >= 50:
                    bitrate = '2000k'
                else:
                    bitrate = '1000k'
                
                # Экспортируем видео
                video.write_videofile(
                    output_path,
                    codec=codec,
                    audio_codec=audio_codec,
                    bitrate=bitrate,
                    logger=None  # Отключаем логирование moviepy
                )
                
                # Проверяем, что файл создан
                if os.path.exists(output_path):
                    logger.info(f"Видео успешно конвертировано: {output_path}")
                    return True, "Видео файл успешно конвертирован", output_path
                else:
                    return False, "Файл не был создан", None
                    
            finally:
                # Освобождаем ресурсы
                video.close()
                
        except Exception as e:
            logger.error(f"Ошибка при конвертации видео {file_path}: {e}", exc_info=True)
            error_msg = str(e)
            # Проверяем, требуется ли ffmpeg
            if "ffmpeg" in error_msg.lower() or "ffprobe" in error_msg.lower():
                return False, "Требуется FFmpeg. Установите FFmpeg: https://ffmpeg.org/download.html", None
            return False, f"Ошибка конвертации: {error_msg}", None

