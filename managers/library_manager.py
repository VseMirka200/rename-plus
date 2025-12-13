"""Модуль для управления установкой библиотек.

Обеспечивает автоматическую проверку, установку и управление зависимостями приложения.
Поддерживает кэширование результатов проверки для оптимизации производительности.
"""

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, Dict, Callable, Optional, Tuple

logger = logging.getLogger(__name__)


class LibraryManager:
    """Класс для управления установкой библиотек.
    
    Отвечает за:
    - Проверку наличия обязательных и опциональных библиотек
    - Автоматическую установку недостающих библиотек
    - Кэширование результатов проверки
    - Управление зависимостями Windows-специфичных библиотек
    
    Attributes:
        REQUIRED_LIBRARIES: Словарь обязательных библиотек {имя_пакета: имя_импорта}
        OPTIONAL_LIBRARIES: Словарь опциональных библиотек
        WINDOWS_OPTIONAL_LIBRARIES: Словарь Windows-специфичных библиотек
    """
    
    # Обязательные библиотеки (нужны для базовой функциональности)
    REQUIRED_LIBRARIES = {
        'Pillow': 'PIL',
        'tkinterdnd2': 'tkinterdnd2',
    }
    
    # Опциональные библиотеки (улучшают функциональность)
    OPTIONAL_LIBRARIES = {
        'pystray': 'pystray',  # Для системного трея
        'python-docx': 'docx',  # Для работы с Word документами
        'mutagen': 'mutagen',  # Для работы с метаданными аудио
        'openpyxl': 'openpyxl',  # Для работы с Excel
        'python-pptx': 'pptx',  # Для работы с PowerPoint
        'pypdf': 'pypdf',  # Для работы с PDF (предпочтительно)
        'PyPDF2': 'PyPDF2',  # Альтернатива для работы с PDF
        'pydub': 'pydub',  # Для конвертации аудио
        'moviepy': 'moviepy',  # Для конвертации видео
    }
    
    # Опциональные библиотеки для Windows (конвертация документов)
    WINDOWS_OPTIONAL_LIBRARIES = {
        'pywin32': 'win32com',  # Для COM объектов (Windows)
        'comtypes': 'comtypes',  # Альтернатива для COM (Windows)
        'docx2pdf': 'docx2pdf',  # Для конвертации DOCX в PDF (если нет COM)
        'pdf2docx': 'pdf2docx',  # Для конвертации PDF в DOCX
    }
    
    def __init__(self, root: tk.Tk, log_callback: Optional[Callable[[str], None]] = None):
        """Инициализация менеджера библиотек.
        
        Args:
            root: Корневое окно Tkinter
            log_callback: Функция для логирования сообщений
        """
        self.root = root
        self.log = log_callback or (lambda msg: print(msg))
        try:
            from config.constants import get_libs_installed_file_path
            self.libs_check_file = get_libs_installed_file_path()
        except ImportError:
            # Fallback если константы не загружены
            app_data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(app_data_dir, "data")
            if not os.path.exists(data_dir):
                try:
                    os.makedirs(data_dir, exist_ok=True)
                except Exception:
                    pass
            self.libs_check_file = os.path.join(data_dir, "rename-plus_libs_installed.json")
        # Время жизни кэша проверки библиотек (в днях)
        self.cache_ttl_days = 7
        # Определяем, запущена ли программа в виртуальном окружении
        self.in_venv = self._is_in_venv()
    
    def _is_in_venv(self) -> bool:
        """Проверка, запущена ли программа в виртуальном окружении.
        
        Returns:
            True если в виртуальном окружении, False иначе
        """
        # Проверяем через sys.prefix (в venv он отличается от base_prefix)
        if hasattr(sys, 'base_prefix'):
            return sys.prefix != sys.base_prefix
        # Альтернативная проверка через переменную окружения
        return bool(os.environ.get('VIRTUAL_ENV'))
    
    def _get_pip_install_args(self, package: str, upgrade: bool = True) -> List[str]:
        """Получение аргументов для команды pip install.
        
        Args:
            package: Имя пакета для установки
            upgrade: Обновлять ли пакет если уже установлен
            
        Returns:
            Список аргументов для pip install
        """
        args = [sys.executable, "-m", "pip", "install", package]
        if upgrade:
            args.append("--upgrade")
        # Используем --user только если НЕ в виртуальном окружении
        if not self.in_venv:
            args.append("--user")
        args.append("--no-warn-script-location")
        return args
    
    def get_all_libraries(self) -> Dict[str, str]:
        """Получение всех библиотек для проверки.
        
        Returns:
            Словарь {имя_пакета: имя_импорта}
        """
        all_libs = {}
        all_libs.update(self.REQUIRED_LIBRARIES)
        all_libs.update(self.OPTIONAL_LIBRARIES)
        
        # Добавляем Windows-специфичные библиотеки только на Windows
        if sys.platform == 'win32':
            all_libs.update(self.WINDOWS_OPTIONAL_LIBRARIES)
        
        return all_libs
    
    def _get_cache_data(self) -> Dict:
        """Получение данных кэша.
        
        Returns:
            Словарь с данными кэша
        """
        try:
            if os.path.exists(self.libs_check_file):
                with open(self.libs_check_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def _save_cache_data(self, data: Dict):
        """Сохранение данных кэша.
        
        Args:
            data: Словарь с данными для сохранения
        """
        try:
            with open(self.libs_check_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def _is_cache_valid(self, cache_data: Dict) -> bool:
        """Проверка валидности кэша.
        
        Args:
            cache_data: Данные кэша
            
        Returns:
            True если кэш валиден, False иначе
        """
        if 'last_check' not in cache_data:
            return False
        
        try:
            last_check_str = cache_data['last_check']
            last_check = datetime.fromisoformat(last_check_str)
            cache_age = datetime.now() - last_check
            
            # Кэш действителен если прошло меньше дней, чем TTL
            return cache_age < timedelta(days=self.cache_ttl_days)
        except (ValueError, KeyError):
            return False
    
    def check_libraries(self, check_optional: bool = True, use_cache: bool = True) -> Dict[str, List[str]]:
        """Проверка наличия библиотек.
        
        Args:
            check_optional: Проверять ли опциональные библиотеки
            use_cache: Использовать ли кэш для ускорения проверки
            
        Returns:
            Словарь с ключами 'required' и 'optional', содержащий списки отсутствующих библиотек
        """
        # Обновляем sys.path для обнаружения установленных библиотек
        try:
            import site
            user_site = site.getusersitepackages()
            if user_site and user_site not in sys.path:
                sys.path.insert(0, user_site)
                site.addsitedir(user_site)
        except Exception:
            pass
        
        cache_data = self._get_cache_data()
        
        # Получаем список установленных библиотек из кэша
        installed_libs = set(cache_data.get('installed', []))
        
        # Если кэш валиден и мы хотим его использовать
        if use_cache and self._is_cache_valid(cache_data) and 'library_status' in cache_data:
            logger.debug("Используется кэш проверки библиотек")
            cached_status = cache_data['library_status']
            
            # Проверяем только те библиотеки, которые были отмечены как отсутствующие
            # Но исключаем те, которые уже помечены как установленные
            missing_required = []
            missing_optional = []
            
            # Проверяем обязательные библиотеки из кэша
            for lib_name in cached_status.get('missing_required', []):
                # Пропускаем библиотеки, которые уже помечены как установленные
                if lib_name in installed_libs:
                    # Но проверяем, действительно ли они установлены
                    import_name = self.REQUIRED_LIBRARIES.get(lib_name)
                    if import_name and self._check_library(lib_name, import_name):
                        # Библиотека действительно установлена, оставляем в списке установленных
                        continue
                    else:
                        # Библиотека помечена как установленная, но не найдена - удаляем из списка
                        installed_libs.discard(lib_name)
                        missing_required.append(lib_name)
                        continue
                import_name = self.REQUIRED_LIBRARIES.get(lib_name)
                if import_name and not self._check_library(lib_name, import_name):
                    missing_required.append(lib_name)
            
            if check_optional:
                # Проверяем опциональные библиотеки из кэша
                for lib_name in cached_status.get('missing_optional', []):
                    # Пропускаем библиотеки, которые уже помечены как установленные
                    if lib_name in installed_libs:
                        # Но проверяем, действительно ли они установлены
                        import_name = (self.OPTIONAL_LIBRARIES.get(lib_name) or 
                                     (self.WINDOWS_OPTIONAL_LIBRARIES.get(lib_name) if sys.platform == 'win32' else None))
                        if import_name and self._check_library(lib_name, import_name):
                            # Библиотека действительно установлена, оставляем в списке установленных
                            continue
                        else:
                            # Библиотека помечена как установленная, но не найдена - удаляем из списка
                            installed_libs.discard(lib_name)
                            missing_optional.append(lib_name)
                            continue
                    import_name = (self.OPTIONAL_LIBRARIES.get(lib_name) or 
                                 (self.WINDOWS_OPTIONAL_LIBRARIES.get(lib_name) if sys.platform == 'win32' else None))
                    if import_name and not self._check_library(lib_name, import_name):
                        missing_optional.append(lib_name)
            
            # Обновляем список установленных библиотек, если что-то изменилось
            if installed_libs != set(cache_data.get('installed', [])):
                cache_data['installed'] = list(installed_libs)
                self._save_cache_data(cache_data)
            
            return {
                'required': missing_required,
                'optional': missing_optional
            }
        
        # Полная проверка всех библиотек
        missing_required = []
        missing_optional = []
        
        # Проверяем обязательные библиотеки
        for lib_name, import_name in self.REQUIRED_LIBRARIES.items():
            # Пропускаем библиотеки, которые уже помечены как установленные
            if lib_name in installed_libs:
                # Но все равно проверяем, действительно ли они установлены
                if not self._check_library(lib_name, import_name):
                    # Если библиотека помечена как установленная, но не найдена, удаляем из списка
                    installed_libs.discard(lib_name)
                    missing_required.append(lib_name)
            elif not self._check_library(lib_name, import_name):
                missing_required.append(lib_name)
        
        if check_optional:
            # Проверяем опциональные библиотеки
            for lib_name, import_name in self.OPTIONAL_LIBRARIES.items():
                # Пропускаем библиотеки, которые уже помечены как установленные
                if lib_name in installed_libs:
                    # Но все равно проверяем, действительно ли они установлены
                    if not self._check_library(lib_name, import_name):
                        # Если библиотека помечена как установленная, но не найдена, удаляем из списка
                        installed_libs.discard(lib_name)
                        missing_optional.append(lib_name)
                elif not self._check_library(lib_name, import_name):
                    missing_optional.append(lib_name)
            
            # Проверяем Windows-специфичные библиотеки
            if sys.platform == 'win32':
                for lib_name, import_name in self.WINDOWS_OPTIONAL_LIBRARIES.items():
                    # Пропускаем библиотеки, которые уже помечены как установленные
                    if lib_name in installed_libs:
                        # Но все равно проверяем, действительно ли они установлены
                        if not self._check_library(lib_name, import_name):
                            # Если библиотека помечена как установленная, но не найдена, удаляем из списка
                            installed_libs.discard(lib_name)
                            missing_optional.append(lib_name)
                    elif not self._check_library(lib_name, import_name):
                        missing_optional.append(lib_name)
        
        # Обновляем список установленных библиотек, если что-то изменилось
        if installed_libs != set(cache_data.get('installed', [])):
            cache_data['installed'] = list(installed_libs)
        
        # Сохраняем результаты в кэш
        cache_data['last_check'] = datetime.now().isoformat()
        cache_data['library_status'] = {
            'missing_required': missing_required,
            'missing_optional': missing_optional
        }
        self._save_cache_data(cache_data)
        
        return {
            'required': missing_required,
            'optional': missing_optional
        }
    
    def _check_library(self, lib_name: str, import_name: str) -> bool:
        """Проверка наличия одной библиотеки.
        
        Args:
            lib_name: Имя пакета для установки
            import_name: Имя для импорта
            
        Returns:
            True если библиотека доступна, False иначе
        """
        try:
            # Обновляем sys.path перед проверкой
            try:
                import site
                user_site = site.getusersitepackages()
                if user_site and user_site not in sys.path:
                    sys.path.insert(0, user_site)
                    site.addsitedir(user_site)
            except Exception:
                pass  # Игнорируем ошибки обновления пути
            
            # Очищаем кэш импортов для этой библиотеки перед проверкой
            # Это помогает найти библиотеки, которые были только что установлены
            modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith(import_name)]
            for m in modules_to_remove:
                try:
                    del sys.modules[m]
                except KeyError:
                    pass
            
            # Специальная обработка для win32com
            if import_name == 'win32com':
                try:
                    import win32com.client  # type: ignore
                    return True
                except (ImportError, AttributeError):
                    return False
            
            # Специальная обработка для comtypes
            if import_name == 'comtypes':
                try:
                    import comtypes.client  # type: ignore
                    return True
                except (ImportError, AttributeError):
                    return False
            
            # Специальная обработка для moviepy
            if import_name == 'moviepy':
                try:
                    from moviepy.editor import VideoFileClip  # type: ignore
                    return True
                except (ImportError, AttributeError):
                    return False
            
            # Специальная обработка для pdf2docx
            if import_name == 'pdf2docx':
                try:
                    # pdf2docx требует PyMuPDF (модуль fitz)
                    try:
                        import fitz  # type: ignore
                    except ImportError:
                        # PyMuPDF не установлен, но pdf2docx может быть установлен
                        logger.debug("pdf2docx требует PyMuPDF (fitz), но он не установлен")
                        return False
                    from pdf2docx import Converter  # type: ignore
                    return True
                except (ImportError, AttributeError) as e:
                    logger.debug(f"Ошибка импорта pdf2docx: {e}")
                    return False
            
            # Специальная обработка для PIL (Pillow)
            if import_name == 'PIL':
                try:
                    from PIL import Image  # type: ignore
                    return True
                except (ImportError, AttributeError):
                    return False
            
            # Специальная обработка для pydub
            if import_name == 'pydub':
                try:
                    import pydub  # type: ignore
                    # Проверяем что модуль действительно загружен
                    if hasattr(pydub, 'AudioSegment'):
                        return True
                    return False
                except (ImportError, AttributeError):
                    return False
            
            # Обычная проверка для остальных библиотек
            module = __import__(import_name)
            # Дополнительная проверка: убеждаемся что модуль действительно загружен
            if module is None:
                return False
            return True
        except ImportError:
            return False
        except ModuleNotFoundError:
            return False
        except Exception as e:
            # Для некоторых библиотек могут быть другие исключения
            if "ImportError" in str(type(e)) or "ModuleNotFoundError" in str(type(e)):
                return False
            # Логируем неожиданные ошибки, но считаем библиотеку недоступной
            logger.debug(f"Неожиданная ошибка при проверке {lib_name} ({import_name}): {e}")
            return False
    
    def get_installed_libraries(self) -> List[str]:
        """Получение списка ранее установленных библиотек.
        
        Returns:
            Список установленных библиотек
        """
        cache_data = self._get_cache_data()
        return cache_data.get('installed', [])
    
    def is_first_run(self) -> bool:
        """Проверка, является ли это первым запуском программы.
        
        Returns:
            True если это первый запуск, False иначе
        """
        cache_data = self._get_cache_data()
        return not cache_data.get('first_run_completed', False)
    
    def mark_first_run_completed(self):
        """Отметить, что первый запуск завершен."""
        cache_data = self._get_cache_data()
        cache_data['first_run_completed'] = True
        self._save_cache_data(cache_data)
    
    def save_installed_libraries(self, libraries: List[str]):
        """Сохранение списка установленных библиотек.
        
        Args:
            libraries: Список только что установленных библиотек (добавляются к существующим)
        """
        # Обновляем sys.path для обнаружения новых модулей
        try:
            import site
            user_site = site.getusersitepackages()
            if user_site and user_site not in sys.path:
                sys.path.insert(0, user_site)
                site.addsitedir(user_site)
        except Exception:
            pass
        
        cache_data = self._get_cache_data()
        # Получаем уже установленные библиотеки из кэша
        existing_installed = cache_data.get('installed', [])
        logger.debug(f"save_installed_libraries: новые библиотеки={libraries}, существующие={existing_installed}")
        
        # Объединяем старые и новые установленные библиотеки
        all_installed = list(set(existing_installed + libraries))
        logger.debug(f"save_installed_libraries: объединенный список={all_installed}")
        
        # Проверяем все библиотеки реально и обновляем список
        all_libs_dict = self.get_all_libraries()
        actually_installed = []
        
        # Очищаем кэш импортов для только что установленных библиотек
        for lib_name in libraries:
            import_name = (all_libs_dict.get(lib_name) or 
                         self.REQUIRED_LIBRARIES.get(lib_name) or
                         self.OPTIONAL_LIBRARIES.get(lib_name) or
                         (self.WINDOWS_OPTIONAL_LIBRARIES.get(lib_name) if sys.platform == 'win32' else None))
            if import_name:
                # Очищаем кэш импортов для этой библиотеки
                modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith(import_name)]
                for m in modules_to_remove:
                    try:
                        del sys.modules[m]
                    except KeyError:
                        pass
        
        # Небольшая задержка для обновления путей Python
        time.sleep(0.1)
        
        # Проверяем все библиотеки из объединенного списка
        for lib_name in all_installed:
            import_name = (all_libs_dict.get(lib_name) or 
                         self.REQUIRED_LIBRARIES.get(lib_name) or
                         self.OPTIONAL_LIBRARIES.get(lib_name) or
                         (self.WINDOWS_OPTIONAL_LIBRARIES.get(lib_name) if sys.platform == 'win32' else None))
            if import_name and self._check_library(lib_name, import_name):
                actually_installed.append(lib_name)
        
        # Также проверяем все остальные библиотеки, которые могут быть установлены
        for lib_name, import_name in self.REQUIRED_LIBRARIES.items():
            if lib_name not in actually_installed and self._check_library(lib_name, import_name):
                actually_installed.append(lib_name)
        
        for lib_name, import_name in self.OPTIONAL_LIBRARIES.items():
            if lib_name not in actually_installed and self._check_library(lib_name, import_name):
                actually_installed.append(lib_name)
        
        if sys.platform == 'win32':
            for lib_name, import_name in self.WINDOWS_OPTIONAL_LIBRARIES.items():
                if lib_name not in actually_installed and self._check_library(lib_name, import_name):
                    actually_installed.append(lib_name)
        
        # Сохраняем проверенный список установленных библиотек
        cache_data['installed'] = actually_installed
        
        # Инвалидируем кэш проверки, так как библиотеки изменились
        if 'last_check' in cache_data:
            del cache_data['last_check']
        if 'library_status' in cache_data:
            del cache_data['library_status']
        
        # Обновляем статус библиотек в кэше
        missing_required = []
        missing_optional = []
        
        # Проверяем обязательные библиотеки
        for lib_name, import_name in self.REQUIRED_LIBRARIES.items():
            if lib_name not in actually_installed:
                if not self._check_library(lib_name, import_name):
                    missing_required.append(lib_name)
        
        # Проверяем опциональные библиотеки
        for lib_name, import_name in self.OPTIONAL_LIBRARIES.items():
            if lib_name not in actually_installed:
                if not self._check_library(lib_name, import_name):
                    missing_optional.append(lib_name)
        
        # Проверяем Windows-специфичные библиотеки
        if sys.platform == 'win32':
            for lib_name, import_name in self.WINDOWS_OPTIONAL_LIBRARIES.items():
                if lib_name not in actually_installed:
                    if not self._check_library(lib_name, import_name):
                        missing_optional.append(lib_name)
        
        # Сохраняем актуальный статус в кэш
        cache_data['library_status'] = {
            'missing_required': missing_required,
            'missing_optional': missing_optional
        }
        cache_data['last_check'] = datetime.now().isoformat()
        
        self._save_cache_data(cache_data)
        logger.info(f"Сохранен список установленных библиотек: {len(actually_installed)} библиотек: {actually_installed}")
    
    def invalidate_cache(self):
        """Инвалидация кэша проверки библиотек."""
        cache_data = self._get_cache_data()
        if 'last_check' in cache_data:
            del cache_data['last_check']
        if 'library_status' in cache_data:
            del cache_data['library_status']
        # Очищаем список установленных библиотек, чтобы принудительно проверить все заново
        if 'installed' in cache_data:
            del cache_data['installed']
        self._save_cache_data(cache_data)
    
    def uninstall_library(self, lib_name: str) -> Tuple[bool, str]:
        """Удаление библиотеки.
        
        Args:
            lib_name: Имя библиотеки для удаления
            
        Returns:
            Кортеж (успех, сообщение)
        """
        try:
            # Валидация имени библиотеки для безопасности
            if not re.match(r'^[a-zA-Z0-9_-]+$', lib_name):
                return False, "Недопустимое имя библиотеки"
            
            logger.info(f"Удаление библиотеки {lib_name}...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "uninstall", lib_name, "-y", "--no-warn-script-location"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                logger.info(f"{lib_name} успешно удалена")
                # Инвалидируем кэш после удаления
                self.invalidate_cache()
                return True, f"Библиотека {lib_name} успешно удалена"
            else:
                error_msg = result.stderr if result.stderr else result.stdout or "Неизвестная ошибка"
                logger.warning(f"Не удалось удалить {lib_name}: {error_msg[:500]}")
                return False, f"Ошибка удаления: {error_msg[:200]}"
        except subprocess.TimeoutExpired:
            logger.error(f"Таймаут при удалении {lib_name}")
            return False, "Таймаут при удалении библиотеки"
        except Exception as e:
            logger.error(f"Ошибка при удалении {lib_name}: {e}")
            return False, f"Ошибка: {str(e)}"
    
    def install_single_library(self, lib_name: str, install_window: Optional[tk.Toplevel] = None) -> Tuple[bool, str]:
        """Установка одной библиотеки.
        
        Args:
            lib_name: Имя библиотеки для установки
            install_window: Окно для отображения прогресса (опционально)
            
        Returns:
            Кортеж (успех, сообщение)
        """
        try:
            # Валидация имени библиотеки для безопасности
            if not re.match(r'^[a-zA-Z0-9_-]+$', lib_name):
                return False, "Недопустимое имя библиотеки"
            
            # Специальная обработка для pdf2docx
            numpy_installed = False
            pymupdf_installed = False
            if lib_name == 'pdf2docx':
                # Проверяем и устанавливаем numpy
                try:
                    import numpy  # type: ignore
                    numpy_installed = True
                    logger.debug("numpy уже установлен")
                except ImportError:
                    # Устанавливаем numpy сначала, используя только предкомпилированные пакеты
                    logger.info("Установка numpy (зависимость для pdf2docx)...")
                    numpy_cmd = self._get_pip_install_args('numpy')
                    # Добавляем --only-binary :all: чтобы использовать только wheels
                    numpy_cmd.insert(-1, '--only-binary')
                    numpy_cmd.insert(-1, ':all:')
                    numpy_result = subprocess.run(
                        numpy_cmd,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    if numpy_result.returncode != 0:
                        numpy_error = numpy_result.stderr if numpy_result.stderr else numpy_result.stdout or "Неизвестная ошибка"
                        logger.error(f"Не удалось установить numpy: {numpy_error[:500]}")
                        # Извлекаем ключевые части ошибки
                        error_lines = numpy_error.split('\n')
                        key_errors = []
                        for line in error_lines:
                            line_lower = line.lower()
                            if any(keyword in line_lower for keyword in ['error', 'failed', 'не удалось', 'ошибка', 'exception', 'requirement', 'could not', 'no matching', 'building wheel', 'failed building', 'cmake', 'visual studio', 'compiler']):
                                key_errors.append(line.strip())
                        detailed_error = '\n'.join(key_errors[:5]) if key_errors else numpy_error[:400]
                        return False, f"Не удалось установить зависимость numpy:\n{detailed_error}\n\nПопробуйте установить вручную:\npip install --user numpy\n\nЕсли ошибка связана с компиляцией, используйте предварительно скомпилированные пакеты или установите Visual Studio Build Tools."
                    numpy_installed = True
                
                # Проверяем и устанавливаем PyMuPDF (требуется для pdf2docx)
                try:
                    import fitz  # type: ignore
                    pymupdf_installed = True
                    logger.debug("PyMuPDF (fitz) уже установлен")
                except ImportError:
                    # Устанавливаем PyMuPDF
                    logger.info("Установка PyMuPDF (зависимость для pdf2docx)...")
                    pymupdf_cmd = self._get_pip_install_args('PyMuPDF')
                    pymupdf_result = subprocess.run(
                        pymupdf_cmd,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    if pymupdf_result.returncode != 0:
                        pymupdf_error = pymupdf_result.stderr if pymupdf_result.stderr else pymupdf_result.stdout or "Неизвестная ошибка"
                        logger.warning(f"Не удалось установить PyMuPDF: {pymupdf_error[:500]}")
                        # Не критично, продолжаем установку pdf2docx
                    else:
                        pymupdf_installed = True
                        logger.info("PyMuPDF успешно установлен")
            
            logger.info(f"Установка библиотеки {lib_name}...")
            
            # Для pdf2docx используем более длинный таймаут и дополнительные опции
            install_cmd = self._get_pip_install_args(lib_name)
            
            # Для pdf2docx может потребоваться установка предварительно скомпилированных пакетов
            if lib_name == 'pdf2docx':
                # Пробуем установить только из wheels, но если это не удастся, пропускаем установку
                # pdf2docx не критичен для работы программы
                install_cmd.insert(-1, '--only-binary')
                install_cmd.insert(-1, ':all:')
                if numpy_installed:
                    # Если numpy уже установлен, также используем --no-deps
                    install_cmd.insert(-1, '--no-deps')
                    logger.info("Установка pdf2docx только из wheels без зависимостей (numpy уже установлен)")
                else:
                    logger.info("Установка pdf2docx только из wheels (предкомпилированные пакеты)")
                install_cmd.extend(['--no-cache-dir'])  # Избегаем проблем с кэшем
            
            timeout_value = 900 if lib_name == 'pdf2docx' else (600 if lib_name in ('moviepy', 'pydub') else 300)
            
            result = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_value
            )
            
            # Специальная обработка для pdf2docx - если установка не удалась из-за компиляции,
            # пропускаем её с предупреждением (библиотека не критична)
            if lib_name == 'pdf2docx' and result.returncode != 0:
                error_msg = result.stderr if result.stderr else result.stdout or ""
                if 'compiler' in error_msg.lower() or 'building wheel' in error_msg.lower() or 'meson' in error_msg.lower() or 'numpy' in error_msg.lower():
                    logger.warning(f"Не удалось установить {lib_name} из-за проблем с компиляцией зависимостей. "
                                 f"Библиотека не критична для работы программы. "
                                 f"Вы можете установить её вручную позже.")
                    return True, f"pdf2docx не установлен (требует компилятор для зависимостей). " \
                               f"Библиотека не критична. Вы можете установить её вручную: pip install pdf2docx"
            
            if result.returncode == 0:
                logger.info(f"{lib_name} успешно установлена")
                
                # Специальная обработка для pywin32 - запускаем post-install скрипт
                if lib_name == 'pywin32':
                    try:
                        logger.info("Запуск post-install скрипта для pywin32...")
                        post_install_script = os.path.join(
                            sys.prefix, 'Scripts', 'pywin32_postinstall.py'
                        )
                        if os.path.exists(post_install_script):
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
                        else:
                            logger.debug("pywin32_postinstall.py не найден, пропускаем")
                    except Exception as e:
                        logger.warning(f"Не удалось запустить post-install скрипт для pywin32: {e}")
                
                # Обновляем sys.path для обнаружения новых модулей
                try:
                    import site
                    import importlib
                    # Добавляем пользовательский site-packages в sys.path если еще не добавлен
                    user_site = site.getusersitepackages()
                    if user_site and user_site not in sys.path:
                        sys.path.insert(0, user_site)
                        site.addsitedir(user_site)
                    
                    # Очищаем кэш модулей для установленной библиотеки (если она была загружена ранее)
                    all_libs = self.get_all_libraries()
                    import_name = all_libs.get(lib_name)
                    if import_name:
                        # Очищаем все модули, начинающиеся с имени импорта
                        modules_to_remove = [m for m in sys.modules.keys() if m.startswith(import_name)]
                        for m in modules_to_remove:
                            del sys.modules[m]
                except Exception as path_e:
                    logger.debug(f"Не удалось обновить sys.path после установки {lib_name}: {path_e}")
                
                # Инвалидируем кэш после установки
                self.invalidate_cache()
                
                # Проверяем, что библиотека действительно доступна
                all_libs = self.get_all_libraries()
                import_name = all_libs.get(lib_name)
                if import_name:
                    # Даем немного времени на завершение установки
                    import time
                    time.sleep(0.5)
                    
                    # Пробуем импортировать библиотеку для проверки
                    if not self._check_library(lib_name, import_name):
                        return True, f"Библиотека {lib_name} установлена, но может потребоваться перезапуск программы для полной загрузки"
                
                return True, f"Библиотека {lib_name} успешно установлена"
            else:
                error_msg = result.stderr if result.stderr else result.stdout or "Неизвестная ошибка"
                logger.warning(f"Не удалось установить {lib_name}: {error_msg[:500]}")
                
                # Более детальный анализ ошибки
                error_lines = error_msg.split('\n')
                key_errors = []
                for line in error_lines:
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in ['error', 'failed', 'не удалось', 'ошибка', 'exception', 'requirement', 'could not', 'no matching', 'building wheel', 'failed building', 'cmake', 'visual studio', 'compiler', 'microsoft visual c++', 'unable to find vcvarsall']):
                        key_errors.append(line.strip())
                
                if key_errors:
                    detailed_error = '\n'.join(key_errors[:8])
                    
                    # Специальные рекомендации для pdf2docx
                    recommendations = ""
                    if lib_name == 'pdf2docx':
                        if any('compiler' in err.lower() or 'visual' in err.lower() or 'vcvarsall' in err.lower() or 'cmake' in err.lower() for err in key_errors):
                            recommendations = "\n\nВозможные решения:\n" \
                                            "1. Установите Visual Studio Build Tools: https://visualstudio.microsoft.com/downloads/\n" \
                                            "2. Или используйте предварительно скомпилированные пакеты:\n" \
                                            "   pip install --user --only-binary :all: pdf2docx\n" \
                                            "3. Или установите через conda (если доступен)"
                        elif any('requirement' in err.lower() or 'dependency' in err.lower() or 'no matching' in err.lower() for err in key_errors):
                            recommendations = "\n\nПопробуйте:\n" \
                                            "1. Обновить pip: python -m pip install --upgrade pip\n" \
                                            "2. Установить зависимости вручную:\n" \
                                            "   pip install --user numpy pillow python-docx"
                    
                    return False, f"Ошибка установки {lib_name}:\n{detailed_error}\n\nПолный вывод:\n{error_msg[:500]}{recommendations}"
                else:
                    # Общие рекомендации для любых ошибок
                    recommendations = ""
                    if lib_name == 'pdf2docx':
                        recommendations = "\n\nРекомендации:\n" \
                                        "1. Обновите pip: python -m pip install --upgrade pip\n" \
                                        "2. Установите зависимости: pip install --user numpy\n" \
                                        "3. Попробуйте установить через: pip install --user pdf2docx"
                    
                    return False, f"Ошибка установки {lib_name}:\n{error_msg[:500]}{recommendations}"
        except subprocess.TimeoutExpired:
            logger.error(f"Таймаут при установке {lib_name}")
            return False, "Таймаут при установке библиотеки"
        except Exception as e:
            logger.error(f"Ошибка при установке {lib_name}: {e}")
            return False, f"Ошибка: {str(e)}"
    
    def is_library_installed(self, lib_name: str) -> bool:
        """Проверка установлена ли библиотека.
        
        Args:
            lib_name: Имя библиотеки для проверки
            
        Returns:
            True если установлена, False иначе
        """
        all_libs = self.get_all_libraries()
        import_name = all_libs.get(lib_name)
        if not import_name:
            return False
        return self._check_library(lib_name, import_name)
    
    def check_and_install(self, install_optional: bool = True, silent: bool = False, force_check: bool = False):
        """Проверка и автоматическая установка необходимых библиотек.
        
        Args:
            install_optional: Устанавливать ли опциональные библиотеки (всегда True - все библиотеки устанавливаются автоматически)
            silent: Не показывать окна, только логировать
            force_check: Принудительная проверка без использования кэша
        """
        # Всегда устанавливаем все опциональные библиотеки автоматически
        install_optional = True
        
        try:
            # Если force_check=True, инвалидируем кэш перед проверкой
            if force_check:
                self.invalidate_cache()
            
            # Сначала проверяем библиотеки, которые были помечены как установленные
            installed_libs = self.get_installed_libraries()
            
            # Проверяем библиотеки из списка установленных, чтобы убедиться что они действительно установлены
            actually_installed = []
            if installed_libs:
                logger.debug(f"Проверка ранее установленных библиотек: {', '.join(installed_libs)}")
                all_libs_dict = self.get_all_libraries()
                for lib in installed_libs:
                    import_name = (all_libs_dict.get(lib) or 
                                 self.REQUIRED_LIBRARIES.get(lib) or
                                 self.OPTIONAL_LIBRARIES.get(lib) or
                                 (self.WINDOWS_OPTIONAL_LIBRARIES.get(lib) if sys.platform == 'win32' else None))
                    if import_name and self._check_library(lib, import_name):
                        actually_installed.append(lib)
                    else:
                        logger.debug(f"Библиотека {lib} помечена как установленная, но не найдена при проверке")
                
                # Обновляем список установленных библиотек, если что-то изменилось
                if set(actually_installed) != set(installed_libs):
                    logger.info(f"Обновление кэша: найдено {len(actually_installed)} из {len(installed_libs)} библиотек")
                    self.save_installed_libraries(actually_installed)
            
            # Делаем проверку всех библиотек
            # Используем кэш только если не принудительная проверка и это не первый запуск
            # и есть установленные библиотеки в кэше
            use_cache = not force_check and not self.is_first_run() and len(installed_libs) > 0
            logger.debug(f"Проверка библиотек: use_cache={use_cache}, installed_libs={len(installed_libs)}, actually_installed={len(actually_installed)}")
            missing = self.check_libraries(check_optional=install_optional, use_cache=use_cache)
            
            missing_required = missing.get('required', [])
            missing_optional = missing.get('optional', [])
            
            # Исключаем из списка отсутствующих библиотеки, которые действительно установлены
            required_to_install = [lib for lib in missing_required if lib not in actually_installed]
            optional_to_install = [lib for lib in missing_optional if lib not in actually_installed] if install_optional else []
            
            # Всегда устанавливаем обязательные библиотеки
            all_missing = required_to_install.copy()
            
            # Добавляем опциональные, если нужно
            if install_optional:
                all_missing.extend(optional_to_install)
            
            if not all_missing:
                # Если это первый запуск, показываем окно статуса
                if not silent and self.is_first_run():
                    self._show_status_window(required_to_install, optional_to_install, "✓ Все необходимые библиотеки установлены")
                    self.mark_first_run_completed()
                elif not silent:
                    logger.info("Все необходимые библиотеки установлены")
                else:
                    logger.info("Все необходимые библиотеки установлены")
                return True
            
            # Всегда устанавливаем все библиотеки автоматически
            # Если это не первый запуск, используем тихий режим (установка в фоне)
            if not self.is_first_run():
                silent = True
                logger.info("Не первый запуск - установка библиотек в фоновом режиме")
            
            # Устанавливаем все недостающие библиотеки (обязательные и опциональные)
            if required_to_install or optional_to_install:
                all_to_install = required_to_install + optional_to_install
                logger.info(f"Автоматическая установка библиотек: {', '.join(all_to_install)}")
                
                if silent:
                    # В тихом режиме устанавливаем автоматически в фоне
                    threading.Thread(
                        target=self._install_libraries_silent,
                        args=(all_to_install,),
                        daemon=True
                    ).start()
                else:
                    # Показываем окно установки только при первом запуске
                    self._show_install_window(required_to_install, optional_to_install)
                    # После установки отмечаем первый запуск как завершенный
                    self.mark_first_run_completed()
                return True
            
            # Если дошли сюда, значит все библиотеки уже установлены
            # Отмечаем первый запуск как завершенный
            if self.is_first_run():
                self.mark_first_run_completed()
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при проверке библиотек: {str(e)}", exc_info=True)
            return False
    
    def _install_libraries_silent(self, libraries: List[str]):
        """Автоматическая установка библиотек в фоновом режиме без окон.
        
        Args:
            libraries: Список библиотек для установки
        """
        installed_libs = []
        success_count = 0
        error_count = 0
        
        logger.info(f"Начало автоматической установки {len(libraries)} библиотек...")
        
        for lib in libraries:
            try:
                # Валидация имени библиотеки для безопасности
                if not re.match(r'^[a-zA-Z0-9_-]+$', lib):
                    logger.warning(f"Недопустимое имя библиотеки: {lib}")
                    error_count += 1
                    continue
                
                logger.info(f"Установка {lib}...")
                
                # Специальная обработка для библиотек с зависимостями
                # pdf2docx требует numpy и PyMuPDF
                if lib == 'pdf2docx':
                    # Устанавливаем numpy
                    try:
                        import numpy  # type: ignore
                    except ImportError:
                        try:
                            logger.info("Установка numpy (зависимость для pdf2docx)...")
                            numpy_result = subprocess.run(
                                self._get_pip_install_args('numpy')[:-1] + ['--quiet', '--no-warn-script-location'],
                                capture_output=True,
                                text=True,
                                timeout=300
                            )
                            if numpy_result.returncode == 0:
                                logger.info("✓ numpy установлен как зависимость")
                            else:
                                logger.warning(f"Не удалось установить numpy: {numpy_result.stderr[:200] if numpy_result.stderr else 'Неизвестная ошибка'}")
                        except Exception as numpy_e:
                            logger.warning(f"Ошибка установки numpy: {numpy_e}")
                    
                    # Устанавливаем PyMuPDF
                    try:
                        import fitz  # type: ignore
                    except ImportError:
                        try:
                            logger.info("Установка PyMuPDF (зависимость для pdf2docx)...")
                            pymupdf_result = subprocess.run(
                                self._get_pip_install_args('PyMuPDF')[:-1] + ['--quiet', '--no-warn-script-location'],
                                capture_output=True,
                                text=True,
                                timeout=300
                            )
                            if pymupdf_result.returncode == 0:
                                logger.info("✓ PyMuPDF установлен как зависимость")
                            else:
                                logger.warning(f"Не удалось установить PyMuPDF: {pymupdf_result.stderr[:200] if pymupdf_result.stderr else 'Неизвестная ошибка'}")
                        except Exception as pymupdf_e:
                            logger.warning(f"Ошибка установки PyMuPDF: {pymupdf_e}")
                
                # pydub может работать без ffmpeg для некоторых форматов, но лучше установить базовые зависимости
                # moviepy требует несколько зависимостей, но они обычно устанавливаются автоматически
                
                # Установка библиотеки с зависимостями
                # Используем --no-warn-script-location для уменьшения предупреждений
                install_cmd = self._get_pip_install_args(lib)
                install_cmd.insert(-1, '--quiet')  # Добавляем --quiet перед --no-warn-script-location
                
                # Специальная обработка для pdf2docx
                if lib == 'pdf2docx':
                    install_cmd.insert(-1, '--only-binary')
                    install_cmd.insert(-1, ':all:')
                    try:
                        import numpy  # type: ignore
                        install_cmd.insert(-1, '--no-deps')
                    except ImportError:
                        pass
                
                # Для некоторых библиотек добавляем дополнительные опции
                if lib in ('moviepy', 'pydub'):
                    # Увеличиваем таймаут для больших библиотек
                    timeout = 600
                elif lib == 'pdf2docx':
                    timeout = 900
                else:
                    timeout = 300
                
                result = subprocess.run(
                    install_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                # Специальная обработка для pdf2docx - если установка не удалась из-за компиляции,
                # пропускаем её с предупреждением (библиотека не критична)
                if lib == 'pdf2docx' and result.returncode != 0:
                    error_msg = result.stderr if result.stderr else result.stdout or ""
                    if 'compiler' in error_msg.lower() or 'building wheel' in error_msg.lower() or 'meson' in error_msg.lower() or 'numpy' in error_msg.lower():
                        logger.warning(f"Не удалось установить {lib} из-за проблем с компиляцией зависимостей. "
                                     f"Библиотека не критична для работы программы. Пропускаем установку.")
                        # Не считаем это ошибкой, просто пропускаем
                        continue
                
                if result.returncode == 0:
                    logger.info(f"✓ {lib} установлен успешно")
                    success_count += 1
                    installed_libs.append(lib)
                    
                    # Пробуем перезагрузить модуль для некоторых библиотек, чтобы они были доступны сразу
                    # (для некоторых библиотек может потребоваться перезапуск Python)
                    try:
                        if lib == 'pydub':
                            import importlib
                            importlib.reload(sys.modules.get('pydub', None))
                        elif lib == 'moviepy':
                            import importlib
                            importlib.reload(sys.modules.get('moviepy', None))
                    except Exception:
                        pass  # Не критично, библиотека все равно будет доступна после перезапуска
                else:
                    error_msg = result.stderr if result.stderr else result.stdout or f"Код возврата: {result.returncode}"
                    logger.error(f"✗ Ошибка установки {lib}: {error_msg[:500]}")
                    error_count += 1
                    
            except subprocess.TimeoutExpired:
                logger.error(f"✗ Таймаут при установке {lib}")
                error_count += 1
            except Exception as e:
                logger.error(f"✗ Ошибка {lib}: {e}")
                error_count += 1
        
        # Сохраняем информацию об установленных библиотеках
        if installed_libs:
            self.save_installed_libraries(installed_libs)
        
        # Финальное сообщение
        if error_count == 0:
            logger.info(f"Все библиотеки установлены успешно! ({success_count} библиотек)")
            logger.info("Некоторые библиотеки могут потребовать перезапуска программы для загрузки.")
        else:
            logger.warning(f"Установка завершена: успешно {success_count}, ошибок {error_count}")
            failed_libs = [lib for lib in libraries if lib not in installed_libs]
            if failed_libs:
                logger.warning(f"Неустановленные библиотеки: {', '.join(failed_libs)}")
                logger.info("Попробуйте установить их вручную или перезапустите программу для повторной попытки.")
    
    def _show_status_window(self, required_libs: List[str], optional_libs: List[str], status_message: str = ""):
        """Показ окна статуса библиотек (без установки).
        
        Args:
            required_libs: Список обязательных библиотек
            optional_libs: Список опциональных библиотек
            status_message: Сообщение о статусе
        """
        all_libs = required_libs + optional_libs
        
        status_window = tk.Toplevel(self.root)
        status_window.title("Проверка библиотек")
        status_window.geometry("600x350")
        status_window.transient(self.root)
        status_window.grab_set()
        
        # Центрируем окно
        status_window.update_idletasks()
        x = (status_window.winfo_screenwidth() // 2) - (600 // 2)
        y = (status_window.winfo_screenheight() // 2) - (350 // 2)
        status_window.geometry(f"600x350+{x}+{y}")
        
        # Заголовок
        title_label = tk.Label(
            status_window,
            text="Проверка библиотек",
            font=('Segoe UI', 12, 'bold'),
            pady=10
        )
        title_label.pack()
        
        # Статус
        if status_message:
            status_label = tk.Label(
                status_window,
                text=status_message,
                font=('Segoe UI', 10),
                fg='green',
                pady=10
            )
            status_label.pack()
        
        # Список библиотек
        installed_libs = self.get_installed_libraries()
        all_libs_dict = self.get_all_libraries()
        
        text_frame = tk.Frame(status_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        status_text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=('Consolas', 9),
            yscrollcommand=scrollbar.set,
            bg='#f0f0f0'
        )
        status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=status_text.yview)
        
        status_text.insert(tk.END, "Обязательные библиотеки:\n")
        for lib in self.REQUIRED_LIBRARIES:
            status = "✓ установлена" if lib in installed_libs else "✗ отсутствует"
            color = "green" if lib in installed_libs else "red"
            status_text.insert(tk.END, f"  {lib}: {status}\n")
            last_line = status_text.index(tk.END + "-1l")
            status_text.tag_add(lib, last_line.split('.')[0] + ".0", tk.END + "-1c")
            status_text.tag_config(lib, foreground=color)
        
        status_text.insert(tk.END, "\nОпциональные библиотеки:\n")
        for lib in self.OPTIONAL_LIBRARIES:
            status = "✓ установлена" if lib in installed_libs else "○ не установлена"
            color = "green" if lib in installed_libs else "gray"
            status_text.insert(tk.END, f"  {lib}: {status}\n")
            last_line = status_text.index(tk.END + "-1l")
            status_text.tag_add(lib, last_line.split('.')[0] + ".0", tk.END + "-1c")
            status_text.tag_config(lib, foreground=color)
        
        if sys.platform == 'win32':
            status_text.insert(tk.END, "\nWindows-специфичные библиотеки:\n")
            for lib in self.WINDOWS_OPTIONAL_LIBRARIES:
                status = "✓ установлена" if lib in installed_libs else "○ не установлена"
                color = "green" if lib in installed_libs else "gray"
                status_text.insert(tk.END, f"  {lib}: {status}\n")
                last_line = status_text.index(tk.END + "-1l")
                status_text.tag_add(lib, last_line.split('.')[0] + ".0", tk.END + "-1c")
                status_text.tag_config(lib, foreground=color)
        
        status_text.config(state=tk.DISABLED)
        
        # Кнопка закрытия
        close_btn = tk.Button(
            status_window,
            text="Закрыть",
            command=status_window.destroy,
            font=('Segoe UI', 10),
            width=15
        )
        close_btn.pack(pady=15)
    
    def _show_install_window(self, required_libs: List[str], optional_libs: List[str]):
        """Показ окна установки библиотек.
        
        Args:
            required_libs: Список обязательных библиотек для установки
            optional_libs: Список опциональных библиотек для установки
        """
        all_libs = required_libs + optional_libs
        
        install_window = tk.Toplevel(self.root)
        install_window.title("Установка библиотек")
        install_window.geometry("600x250")
        install_window.transient(self.root)
        install_window.grab_set()
        
        # Центрируем окно
        install_window.update_idletasks()
        x = (install_window.winfo_screenwidth() // 2) - (600 // 2)
        y = (install_window.winfo_screenheight() // 2) - (250 // 2)
        install_window.geometry(f"600x250+{x}+{y}")
        
        # Формируем текст сообщения
        message_text = "Установка необходимых библиотек:\n\n"
        if required_libs:
            message_text += f"Обязательные:\n{', '.join(required_libs)}\n\n"
        if optional_libs:
            message_text += f"Опциональные:\n{', '.join(optional_libs)}\n\n"
        message_text += "Это займет некоторое время..."
        
        info_label = tk.Label(
            install_window,
            text=message_text,
            font=('Segoe UI', 10),
            justify=tk.LEFT,
            pady=20,
            padx=20
        )
        info_label.pack(pady=20)
        
        install_window.update()
        
        self.install_libraries_auto(all_libs, install_window)
    
    def install_libraries_auto(self, libraries: List[str], parent_window: tk.Toplevel):
        """Автоматическая установка библиотек.
        
        Args:
            libraries: Список библиотек для установки
            parent_window: Родительское окно
        """
        progress_window = tk.Toplevel(parent_window)
        progress_window.title("Установка библиотек")
        progress_window.geometry("600x300")
        progress_window.transient(parent_window)
        progress_window.grab_set()
        
        # Центрируем окно
        progress_window.update_idletasks()
        x = (progress_window.winfo_screenwidth() // 2) - (600 // 2)
        y = (progress_window.winfo_screenheight() // 2) - (300 // 2)
        progress_window.geometry(f"600x300+{x}+{y}")
        
        status_label = tk.Label(
            progress_window,
            text="Проверка и установка библиотек...",
            font=('Segoe UI', 11, 'bold'),
            pady=15
        )
        status_label.pack()
        
        # Счетчик установленных библиотек
        counter_label = tk.Label(
            progress_window,
            text="",
            font=('Segoe UI', 9),
            pady=5
        )
        counter_label.pack()
        
        progress_text = tk.Text(
            progress_window,
            height=12,
            wrap=tk.WORD,
            font=('Consolas', 9),
            bg='#f0f0f0',
            state=tk.NORMAL
        )
        progress_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        progress_bar = ttk.Progressbar(
            progress_window,
            mode='indeterminate',
            length=550
        )
        progress_bar.pack(pady=10)
        progress_bar.start()
        
        installed_libs = []
        
        def install_thread():
            """Установка библиотек в отдельном потоке."""
            nonlocal installed_libs
            success_count = 0
            error_count = 0
            
            total_libs = len(libraries)
            self.root.after(0, lambda t=total_libs: counter_label.config(text=f"Библиотек для установки: {t}"))
            
            # Проверяем доступность pip
            try:
                self.root.after(0, lambda: progress_text.insert(tk.END, "🔍 Проверка доступности pip...\n"))
                self.root.after(0, lambda: progress_text.see(tk.END))
                self.root.after(0, lambda: progress_window.update())
                check_pip = subprocess.run(
                    [sys.executable, '-m', 'pip', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if check_pip.returncode != 0:
                    self.root.after(0, lambda: progress_text.insert(tk.END, "✗ pip не доступен. Установите pip вручную.\n"))
                    self.root.after(0, lambda: progress_bar.stop())
                    self.root.after(0, lambda: close_btn.config(state=tk.NORMAL))
                    return
                else:
                    pip_version = check_pip.stdout.strip() if check_pip.stdout else "доступен"
                    self.root.after(0, lambda v=pip_version: progress_text.insert(tk.END, f"✓ pip {v}\n"))
                    self.root.after(0, lambda: progress_text.see(tk.END))
            except Exception as e:
                self.root.after(0, lambda: progress_text.insert(tk.END, f"✗ Ошибка проверки pip: {str(e)}\n"))
                self.root.after(0, lambda: progress_bar.stop())
                self.root.after(0, lambda: close_btn.config(state=tk.NORMAL))
                return
            
            for idx, lib in enumerate(libraries, 1):
                try:
                    # Валидация имени библиотеки для безопасности
                    if not re.match(r'^[a-zA-Z0-9_-]+$', lib):
                        error_msg = f"Недопустимое имя библиотеки: {lib}"
                        self.root.after(0, lambda l=lib, e=error_msg: progress_text.insert(tk.END, f"✗ Ошибка валидации {l}: {e}\n"))
                        error_count += 1
                        continue
                    
                    current_num = idx
                    self.root.after(0, lambda l=lib, n=current_num, t=total_libs: status_label.config(
                        text=f"Установка {l}... ({n}/{t})"
                    ))
                    self.root.after(0, lambda l=lib, n=current_num, t=total_libs: counter_label.config(
                        text=f"Установка: {n} из {t}"
                    ))
                    self.root.after(0, lambda l=lib, n=current_num, t=total_libs: progress_text.insert(tk.END, f"\n[{n}/{t}] Установка {l}...\n"))
                    self.root.after(0, lambda: progress_text.see(tk.END))
                    self.root.after(0, lambda: progress_window.update())
                    
                    # Специальная обработка для библиотек, которые могут требовать дополнительные зависимости
                    install_cmd = self._get_pip_install_args(lib)
                    
                    # Для pdf2docx может потребоваться numpy, устанавливаем его заранее
                    numpy_installed = False
                    if lib == 'pdf2docx':
                        self.root.after(0, lambda: progress_text.insert(tk.END, f"Проверка зависимостей для {lib}...\n"))
                        self.root.after(0, lambda: progress_text.see(tk.END))
                        self.root.after(0, lambda: progress_window.update())
                        
                        # Пробуем установить numpy если его нет
                        try:
                            import numpy  # type: ignore
                            numpy_installed = True
                        except ImportError:
                            try:
                                self.root.after(0, lambda: progress_text.insert(tk.END, f"Установка numpy (зависимость для pdf2docx)...\n"))
                                self.root.after(0, lambda: progress_text.see(tk.END))
                                self.root.after(0, lambda: progress_window.update())
                                
                                # Используем --only-binary для numpy чтобы избежать компиляции
                                numpy_cmd = self._get_pip_install_args('numpy')
                                numpy_cmd.insert(-1, '--only-binary')
                                numpy_cmd.insert(-1, ':all:')
                                numpy_result = subprocess.run(
                                    numpy_cmd,
                                    capture_output=True,
                                    text=True,
                                    timeout=300
                                )
                                if numpy_result.returncode == 0:
                                    self.root.after(0, lambda: progress_text.insert(tk.END, f"✓ numpy установлен как зависимость\n"))
                                    numpy_installed = True
                                else:
                                    numpy_error = numpy_result.stderr if numpy_result.stderr else numpy_result.stdout or "Неизвестная ошибка"
                                    # Извлекаем ключевые ошибки
                                    error_lines = numpy_error.split('\n')
                                    key_errors = [line.strip() for line in error_lines if any(kw in line.lower() for kw in ['error', 'failed', 'ошибка', 'exception', 'requirement', 'could not', 'building wheel'])]
                                    error_summary = '\n'.join(key_errors[:3]) if key_errors else numpy_error[:300]
                                    self.root.after(0, lambda e=error_summary: progress_text.insert(tk.END, f"⚠ Предупреждение: не удалось установить numpy:\n{e[:400]}\n"))
                            except Exception as numpy_e:
                                self.root.after(0, lambda err=str(numpy_e)[:100]: progress_text.insert(tk.END, f"⚠ Предупреждение: ошибка установки numpy: {err}\n"))
                        
                        # Пробуем установить PyMuPDF если его нет
                        pymupdf_installed = False
                        try:
                            import fitz  # type: ignore
                            pymupdf_installed = True
                        except ImportError:
                            try:
                                self.root.after(0, lambda: progress_text.insert(tk.END, f"Установка PyMuPDF (зависимость для pdf2docx)...\n"))
                                self.root.after(0, lambda: progress_text.see(tk.END))
                                self.root.after(0, lambda: progress_window.update())
                                
                                pymupdf_cmd = self._get_pip_install_args('PyMuPDF')
                                pymupdf_result = subprocess.run(
                                    pymupdf_cmd,
                                    capture_output=True,
                                    text=True,
                                    timeout=300
                                )
                                if pymupdf_result.returncode == 0:
                                    self.root.after(0, lambda: progress_text.insert(tk.END, f"✓ PyMuPDF установлен как зависимость\n"))
                                    pymupdf_installed = True
                                else:
                                    pymupdf_error = pymupdf_result.stderr if pymupdf_result.stderr else pymupdf_result.stdout or "Неизвестная ошибка"
                                    self.root.after(0, lambda e=pymupdf_error[:300]: progress_text.insert(tk.END, f"⚠ Предупреждение: не удалось установить PyMuPDF:\n{e[:400]}\n"))
                            except Exception as pymupdf_e:
                                self.root.after(0, lambda err=str(pymupdf_e)[:100]: progress_text.insert(tk.END, f"⚠ Предупреждение: ошибка установки PyMuPDF: {err}\n"))
                    
                    # Для pdf2docx: всегда используем --only-binary :all: чтобы использовать только wheels
                    if lib == 'pdf2docx':
                        install_cmd.insert(-1, '--only-binary')
                        install_cmd.insert(-1, ':all:')
                        if numpy_installed:
                            # Если numpy уже установлен, также используем --no-deps
                            install_cmd.insert(-1, '--no-deps')
                            self.root.after(0, lambda: progress_text.insert(tk.END, f"Установка pdf2docx только из wheels без зависимостей (numpy уже установлен)...\n"))
                        else:
                            self.root.after(0, lambda: progress_text.insert(tk.END, f"Установка pdf2docx только из wheels...\n"))
                        install_cmd.extend(['--no-cache-dir'])
                    
                    # Увеличиваем таймаут для тяжелых библиотек
                    timeout_value = 600 if lib in ('pdf2docx', 'moviepy', 'pydub') else 300
                    
                    result = subprocess.run(
                        install_cmd,
                        capture_output=True,
                        text=True,
                        timeout=timeout_value
                    )
                    
                    # Специальная обработка для pdf2docx - если установка не удалась из-за компиляции,
                    # пропускаем её с предупреждением (библиотека не критична)
                    if lib == 'pdf2docx' and result.returncode != 0:
                        error_msg = result.stderr if result.stderr else result.stdout or ""
                        if 'compiler' in error_msg.lower() or 'building wheel' in error_msg.lower() or 'meson' in error_msg.lower() or 'numpy' in error_msg.lower():
                            self.root.after(0, lambda: progress_text.insert(tk.END, f"  ⚠ pdf2docx не установлен (требует компилятор). Библиотека не критична.\n"))
                            self.root.after(0, lambda: progress_text.insert(tk.END, f"  Вы можете установить её вручную позже: pip install pdf2docx\n"))
                            self.root.after(0, lambda: progress_text.see(tk.END))
                            # Не считаем это ошибкой, просто пропускаем
                            continue
                    
                    if result.returncode == 0:
                        # Обновляем sys.path для обнаружения новых модулей
                        try:
                            import site
                            user_site = site.getusersitepackages()
                            if user_site and user_site not in sys.path:
                                sys.path.insert(0, user_site)
                                site.addsitedir(user_site)
                            
                            # Очищаем кэш модулей
                            all_libs_dict = self.get_all_libraries()
                            import_name = all_libs_dict.get(lib)
                            if import_name:
                                modules_to_remove = [m for m in sys.modules.keys() if m.startswith(import_name)]
                                for m in modules_to_remove:
                                    del sys.modules[m]
                        except Exception:
                            pass
                        
                        # Специальная обработка для pywin32 - запускаем post-install скрипт
                        if lib == 'pywin32':
                            try:
                                self.root.after(0, lambda: progress_text.insert(tk.END, f"  Запуск post-install скрипта для {lib}...\n"))
                                self.root.after(0, lambda: progress_text.see(tk.END))
                                self.root.after(0, lambda: progress_window.update())
                                
                                post_install_script = os.path.join(
                                    sys.prefix, 'Scripts', 'pywin32_postinstall.py'
                                )
                                if os.path.exists(post_install_script):
                                    post_result = subprocess.run(
                                        [sys.executable, post_install_script, '-install'],
                                        capture_output=True,
                                        text=True,
                                        timeout=60
                                    )
                                    if post_result.returncode == 0:
                                        self.root.after(0, lambda: progress_text.insert(tk.END, f"  ✓ pywin32 post-install выполнен\n"))
                                    else:
                                        self.root.after(0, lambda: progress_text.insert(tk.END, f"  ⚠ pywin32 post-install завершился с предупреждением\n"))
                                else:
                                    self.root.after(0, lambda: progress_text.insert(tk.END, f"  ⚠ pywin32_postinstall.py не найден\n"))
                            except Exception as e:
                                self.root.after(0, lambda err=str(e)[:100]: progress_text.insert(tk.END, f"  ⚠ Ошибка post-install для pywin32: {err}\n"))
                        
                        # Проверяем, что библиотека действительно установлена
                        all_libs_dict = self.get_all_libraries()
                        import_name = all_libs_dict.get(lib)
                        if import_name:
                            # Даем немного времени на завершение установки
                            time.sleep(0.2)
                            # Проверяем библиотеку
                            if self._check_library(lib, import_name):
                                self.root.after(0, lambda l=lib: progress_text.insert(tk.END, f"  ✓ {l} установлен успешно\n"))
                                success_count += 1
                                installed_libs.append(lib)
                            else:
                                # Библиотека установлена, но не может быть импортирована сразу
                                # Это нормально для некоторых библиотек, требующих перезапуска
                                self.root.after(0, lambda l=lib: progress_text.insert(tk.END, f"  ✓ {l} установлен (может потребоваться перезапуск)\n"))
                                success_count += 1
                                installed_libs.append(lib)
                        else:
                            self.root.after(0, lambda l=lib: progress_text.insert(tk.END, f"  ✓ {l} установлен успешно\n"))
                            success_count += 1
                            installed_libs.append(lib)
                        self.root.after(0, lambda s=success_count, t=total_libs: counter_label.config(
                            text=f"Успешно установлено: {s} из {t}"
                        ))
                    else:
                        # Более подробный вывод ошибки
                        error_msg = result.stderr if result.stderr else result.stdout or f"Код возврата: {result.returncode}"
                        
                        # Показываем больше информации об ошибке (до 500 символов)
                        error_display = error_msg[:500] if len(error_msg) > 500 else error_msg
                        
                        # Извлекаем ключевые части ошибки для лучшего понимания
                        error_lines = error_msg.split('\n')
                        key_errors = []
                        for line in error_lines:
                            line_lower = line.lower()
                            if any(keyword in line_lower for keyword in ['error', 'failed', 'не удалось', 'ошибка', 'exception', 'requirement', 'could not', 'no matching', 'building wheel', 'failed building', 'cmake']):
                                key_errors.append(line.strip())
                        
                        if key_errors:
                            error_summary = '\n'.join(key_errors[:8])  # Первые 8 важных строк
                            error_display = f"{error_summary}\n\nПолный вывод:\n{error_display}"
                        
                        self.root.after(0, lambda l=lib, e=error_display: progress_text.insert(tk.END, f"  ✗ Ошибка установки {l}:\n{e}\n\n"))
                        error_count += 1
                        self.root.after(0, lambda ec=error_count, t=total_libs: counter_label.config(
                            text=f"Ошибок: {ec} из {t}"
                        ))
                        try:
                            # Логируем полную ошибку
                            logger.error(f"Ошибка установки {lib}: {error_msg}")
                            self.log(f"Ошибка установки {lib}: {error_msg[:1000]}")
                        except Exception as e:
                            logger.debug(f"Не удалось залогировать ошибку установки {lib}: {e}")
                    
                    self.root.after(0, lambda: progress_text.see(tk.END))
                    self.root.after(0, lambda: progress_window.update())
                    
                except subprocess.TimeoutExpired:
                    self.root.after(0, lambda l=lib: progress_text.insert(tk.END, f"✗ Таймаут при установке {l}\n"))
                    error_count += 1
                except Exception as e:
                    self.root.after(0, lambda l=lib, err=str(e): progress_text.insert(tk.END, f"✗ Ошибка {l}: {err[:100]}\n"))
                    error_count += 1
                    self.root.after(0, lambda: progress_text.see(tk.END))
                    self.root.after(0, lambda: progress_window.update())
            
            # Останавливаем прогресс-бар
            self.root.after(0, lambda: progress_bar.stop())
            
            # Сохраняем информацию об установленных библиотеках
            self.save_installed_libraries(installed_libs)
            
            # Финальное сообщение
            failed_libs = [lib for lib in libraries if lib not in installed_libs]
            
            if error_count == 0:
                self.root.after(0, lambda: status_label.config(text="✓ Все библиотеки установлены успешно!"))
                self.root.after(0, lambda s=success_count, t=total_libs: counter_label.config(
                    text=f"✓ Успешно установлено: {s} из {t}"
                ))
                self.root.after(0, lambda: progress_text.insert(tk.END, "\n✓ Установка завершена успешно!\n"))
            else:
                self.root.after(0, lambda sc=success_count, ec=error_count: status_label.config(
                    text=f"⚠ Установлено: {sc}, Ошибок: {ec}"
                ))
                self.root.after(0, lambda sc=success_count, ec=error_count, t=total_libs: counter_label.config(
                    text=f"Установлено: {sc}, Ошибок: {ec} из {t}"
                ))
                self.root.after(0, lambda: progress_text.insert(tk.END, f"\n⚠ Некоторые библиотеки не установлены.\n"))
                
                if failed_libs:
                    self.root.after(0, lambda: progress_text.insert(tk.END, f"\nНеустановленные библиотеки: {', '.join(failed_libs)}\n"))
                    self.root.after(0, lambda: progress_text.insert(tk.END, f"\nПопробуйте установить вручную через командную строку:\n\n"))
                    
                    # Для pdf2docx добавляем специальную рекомендацию с зависимостями
                    if 'pdf2docx' in failed_libs:
                        self.root.after(0, lambda: progress_text.insert(tk.END, 
                            f"Для pdf2docx может потребоваться:\n"
                            f"  1. Сначала установите зависимости:\n"
                            f"     pip install --user numpy PyMuPDF\n\n"
                            f"  2. Затем установите pdf2docx:\n"
                            f"     pip install --user pdf2docx\n\n"
                            f"  Или установите все сразу:\n"
                            f"     pip install --user pdf2docx\n\n"
                            f"  Если возникает ошибка компиляции, установите Visual Studio Build Tools\n"
                            f"  или используйте предварительно скомпилированные пакеты:\n"
                            f"     pip install --user --only-binary :all: pdf2docx\n\n"))
                        
                        # Если есть другие библиотеки, показываем их отдельно
                        other_libs = [lib for lib in failed_libs if lib != 'pdf2docx']
                        if other_libs:
                            self.root.after(0, lambda: progress_text.insert(tk.END, 
                                f"Другие библиотеки:\n"
                                f"  pip install --user {' '.join(other_libs)}\n\n"))
                        
                        # Общая команда для всех
                        self.root.after(0, lambda: progress_text.insert(tk.END, 
                            f"Или установите все сразу:\n"
                            f"  pip install --user {' '.join(failed_libs)}\n"))
                    else:
                        # Для остальных библиотек показываем простую команду
                        self.root.after(0, lambda: progress_text.insert(tk.END, 
                            f"  pip install --user {' '.join(failed_libs)}\n"))
            
            self.root.after(0, lambda: progress_text.see(tk.END))
            self.root.after(0, lambda: progress_window.update())
            
            # Активируем кнопку закрытия
            self.root.after(0, lambda: close_btn.config(state=tk.NORMAL))
        
        def close_window():
            parent_window.destroy()
            progress_window.destroy()
            if installed_libs:
                messagebox.showinfo(
                    "Установка завершена",
                    "Библиотеки установлены успешно.\n"
                    "Перезапустите программу для применения изменений."
                )
        
        close_btn = tk.Button(
            progress_window,
            text="Закрыть",
            command=close_window,
            font=('Segoe UI', 10),
            padx=20,
            pady=5,
            state=tk.DISABLED
        )
        close_btn.pack(pady=10)
        
        threading.Thread(target=install_thread, daemon=True).start()


