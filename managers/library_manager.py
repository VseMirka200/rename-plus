"""Модуль для управления установкой библиотек."""

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
    """Класс для управления установкой библиотек."""
    
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
        self.libs_check_file = os.path.join(
            os.path.expanduser("~"), ".nazovi_libs_installed.json"
        )
        # Время жизни кэша проверки библиотек (в днях)
        self.cache_ttl_days = 7
    
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
        cache_data = self._get_cache_data()
        
        # Если кэш валиден и мы хотим его использовать
        if use_cache and self._is_cache_valid(cache_data) and 'library_status' in cache_data:
            logger.debug("Используется кэш проверки библиотек")
            cached_status = cache_data['library_status']
            
            # Проверяем только те библиотеки, которые были отмечены как отсутствующие
            # Это ускоряет проверку, так как мы не проверяем все библиотеки заново
            missing_required = []
            missing_optional = []
            
            # Проверяем обязательные библиотеки из кэша
            for lib_name in cached_status.get('missing_required', []):
                import_name = self.REQUIRED_LIBRARIES.get(lib_name)
                if import_name and not self._check_library(lib_name, import_name):
                    missing_required.append(lib_name)
            
            if check_optional:
                # Проверяем опциональные библиотеки из кэша
                for lib_name in cached_status.get('missing_optional', []):
                    import_name = (self.OPTIONAL_LIBRARIES.get(lib_name) or 
                                 (self.WINDOWS_OPTIONAL_LIBRARIES.get(lib_name) if sys.platform == 'win32' else None))
                    if import_name and not self._check_library(lib_name, import_name):
                        missing_optional.append(lib_name)
            
            return {
                'required': missing_required,
                'optional': missing_optional
            }
        
        # Полная проверка всех библиотек
        missing_required = []
        missing_optional = []
        
        # Проверяем обязательные библиотеки
        for lib_name, import_name in self.REQUIRED_LIBRARIES.items():
            if not self._check_library(lib_name, import_name):
                missing_required.append(lib_name)
        
        if check_optional:
            # Проверяем опциональные библиотеки
            for lib_name, import_name in self.OPTIONAL_LIBRARIES.items():
                if not self._check_library(lib_name, import_name):
                    missing_optional.append(lib_name)
            
            # Проверяем Windows-специфичные библиотеки
            if sys.platform == 'win32':
                for lib_name, import_name in self.WINDOWS_OPTIONAL_LIBRARIES.items():
                    if not self._check_library(lib_name, import_name):
                        missing_optional.append(lib_name)
        
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
                    from pdf2docx import Converter  # type: ignore
                    return True
                except (ImportError, AttributeError):
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
            libraries: Список установленных библиотек
        """
        cache_data = self._get_cache_data()
        cache_data['installed'] = libraries
        # Инвалидируем кэш проверки, так как библиотеки изменились
        if 'last_check' in cache_data:
            del cache_data['last_check']
        if 'library_status' in cache_data:
            del cache_data['library_status']
        # Обновляем статус библиотек в кэше - помечаем установленные как найденные
        if libraries:
            # Получаем все библиотеки для проверки
            all_libs_dict = self.get_all_libraries()
            missing_required = []
            missing_optional = []
            
            # Проверяем обязательные библиотеки
            for lib_name, import_name in self.REQUIRED_LIBRARIES.items():
                if lib_name not in libraries:
                    if not self._check_library(lib_name, import_name):
                        missing_required.append(lib_name)
            
            # Проверяем опциональные библиотеки
            for lib_name, import_name in self.OPTIONAL_LIBRARIES.items():
                if lib_name not in libraries:
                    if not self._check_library(lib_name, import_name):
                        missing_optional.append(lib_name)
            
            # Проверяем Windows-специфичные библиотеки
            if sys.platform == 'win32':
                for lib_name, import_name in self.WINDOWS_OPTIONAL_LIBRARIES.items():
                    if lib_name not in libraries:
                        if not self._check_library(lib_name, import_name):
                            missing_optional.append(lib_name)
            
            # Сохраняем актуальный статус в кэш
            cache_data['library_status'] = {
                'missing_required': missing_required,
                'missing_optional': missing_optional
            }
            cache_data['last_check'] = datetime.now().isoformat()
        
        self._save_cache_data(cache_data)
    
    def invalidate_cache(self):
        """Инвалидация кэша проверки библиотек."""
        cache_data = self._get_cache_data()
        if 'last_check' in cache_data:
            del cache_data['last_check']
        if 'library_status' in cache_data:
            del cache_data['library_status']
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
            if lib_name == 'pdf2docx':
                try:
                    import numpy  # type: ignore
                    logger.debug("numpy уже установлен")
                except ImportError:
                    # Устанавливаем numpy сначала
                    logger.info("Установка numpy (зависимость для pdf2docx)...")
                    numpy_result = subprocess.run(
                        [sys.executable, '-m', 'pip', 'install', 'numpy', '--user', '--upgrade', '--no-warn-script-location'],
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
            
            logger.info(f"Установка библиотеки {lib_name}...")
            
            # Для pdf2docx используем более длинный таймаут и дополнительные опции
            install_cmd = [sys.executable, "-m", "pip", "install", lib_name, "--user", "--upgrade", "--no-warn-script-location"]
            
            # Для pdf2docx может потребоваться установка предварительно скомпилированных пакетов
            if lib_name == 'pdf2docx':
                # Добавляем опции для более надежной установки
                install_cmd.extend(['--no-cache-dir'])  # Избегаем проблем с кэшем
            
            timeout_value = 900 if lib_name == 'pdf2docx' else (600 if lib_name in ('moviepy', 'pydub') else 300)
            
            result = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_value
            )
            
            if result.returncode == 0:
                logger.info(f"{lib_name} успешно установлена")
                
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
            install_optional: Устанавливать ли опциональные библиотеки
            silent: Не показывать окна, только логировать
            force_check: Принудительная проверка без использования кэша
        """
        try:
            # Если force_check=True, инвалидируем кэш перед проверкой
            if force_check:
                self.invalidate_cache()
            
            # Сначала проверяем библиотеки, которые были помечены как установленные
            installed_libs = self.get_installed_libraries()
            
            # Если есть библиотеки в кэше как установленные, но это не первый запуск,
            # делаем полную проверку без кэша, чтобы убедиться что они действительно установлены
            if installed_libs and not self.is_first_run() and not force_check:
                logger.debug(f"Проверка ранее установленных библиотек: {', '.join(installed_libs)}")
                # Делаем полную проверку без кэша для точности
                missing = self.check_libraries(check_optional=install_optional, use_cache=False)
            else:
                # Используем кэш только если не принудительная проверка
                missing = self.check_libraries(check_optional=install_optional, use_cache=not force_check)
            
            missing_required = missing.get('required', [])
            missing_optional = missing.get('optional', [])
            
            # Всегда устанавливаем обязательные библиотеки
            all_missing = missing_required.copy()
            
            # Добавляем опциональные, если нужно
            if install_optional:
                all_missing.extend(missing_optional)
            
            # Разделяем на обязательные и опциональные для отображения
            # Теперь используем реальную проверку, а не кэш
            required_to_install = missing_required
            optional_to_install = missing_optional if install_optional else []
            
            # Если библиотеки были в кэше как установленные, но проверка их не нашла,
            # обновляем кэш - удаляем их из списка установленных
            if installed_libs:
                actually_installed = []
                all_libs_dict = self.get_all_libraries()
                for lib in installed_libs:
                    import_name = (all_libs_dict.get(lib) or 
                                 self.REQUIRED_LIBRARIES.get(lib) or
                                 self.OPTIONAL_LIBRARIES.get(lib) or
                                 (self.WINDOWS_OPTIONAL_LIBRARIES.get(lib) if sys.platform == 'win32' else None))
                    if import_name and self._check_library(lib, import_name):
                        actually_installed.append(lib)
                
                # Обновляем список установленных библиотек только реально установленными
                if set(actually_installed) != set(installed_libs):
                    logger.info(f"Обновление кэша: найдено {len(actually_installed)} из {len(installed_libs)} библиотек")
                    self.save_installed_libraries(actually_installed)
                    # Пересчитываем списки для установки
                    required_to_install = [lib for lib in missing_required if lib not in actually_installed]
                    optional_to_install = [lib for lib in missing_optional if lib not in actually_installed and install_optional]
                    all_missing = required_to_install.copy()
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
            
            if silent:
                # В тихом режиме устанавливаем автоматически в фоне
                if required_to_install or optional_to_install:
                    logger.info(f"Автоматическая установка библиотек: {', '.join(required_to_install + optional_to_install)}")
                    # Запускаем установку в отдельном потоке
                    threading.Thread(
                        target=self._install_libraries_silent,
                        args=(required_to_install + optional_to_install,),
                        daemon=True
                    ).start()
                return True
            
            # Показываем окно установки
            self._show_install_window(required_to_install, optional_to_install)
            # После установки отмечаем первый запуск как завершенный
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
                # pdf2docx требует numpy
                if lib == 'pdf2docx':
                    try:
                        import numpy  # type: ignore
                    except ImportError:
                        try:
                            logger.info("Установка numpy (зависимость для pdf2docx)...")
                            numpy_result = subprocess.run(
                                [sys.executable, '-m', 'pip', 'install', 'numpy', '--user', '--upgrade', '--quiet'],
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
                
                # pydub может работать без ffmpeg для некоторых форматов, но лучше установить базовые зависимости
                # moviepy требует несколько зависимостей, но они обычно устанавливаются автоматически
                
                # Установка библиотеки с зависимостями
                # Используем --no-warn-script-location для уменьшения предупреждений
                install_cmd = [sys.executable, '-m', 'pip', 'install', lib, '--user', '--upgrade', '--quiet', '--no-warn-script-location']
                
                # Для некоторых библиотек добавляем дополнительные опции
                if lib in ('moviepy', 'pydub'):
                    # Увеличиваем таймаут для больших библиотек
                    timeout = 600
                else:
                    timeout = 300
                
                result = subprocess.run(
                    install_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
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
                    install_cmd = [sys.executable, '-m', 'pip', 'install', lib, '--user', '--upgrade', '--no-warn-script-location']
                    
                    # Для pdf2docx может потребоваться numpy, устанавливаем его заранее
                    if lib == 'pdf2docx':
                        self.root.after(0, lambda: progress_text.insert(tk.END, f"Проверка зависимостей для {lib}...\n"))
                        self.root.after(0, lambda: progress_text.see(tk.END))
                        self.root.after(0, lambda: progress_window.update())
                        
                        # Пробуем установить numpy если его нет
                        try:
                            import numpy  # type: ignore
                        except ImportError:
                            try:
                                self.root.after(0, lambda: progress_text.insert(tk.END, f"Установка numpy (зависимость для pdf2docx)...\n"))
                                self.root.after(0, lambda: progress_text.see(tk.END))
                                self.root.after(0, lambda: progress_window.update())
                                
                                numpy_result = subprocess.run(
                                    [sys.executable, '-m', 'pip', 'install', 'numpy', '--user', '--upgrade', '--no-warn-script-location'],
                                    capture_output=True,
                                    text=True,
                                    timeout=300
                                )
                                if numpy_result.returncode == 0:
                                    self.root.after(0, lambda: progress_text.insert(tk.END, f"✓ numpy установлен как зависимость\n"))
                                else:
                                    numpy_error = numpy_result.stderr if numpy_result.stderr else numpy_result.stdout or "Неизвестная ошибка"
                                    # Извлекаем ключевые ошибки
                                    error_lines = numpy_error.split('\n')
                                    key_errors = [line.strip() for line in error_lines if any(kw in line.lower() for kw in ['error', 'failed', 'ошибка', 'exception', 'requirement', 'could not', 'building wheel'])]
                                    error_summary = '\n'.join(key_errors[:3]) if key_errors else numpy_error[:300]
                                    self.root.after(0, lambda e=error_summary: progress_text.insert(tk.END, f"⚠ Предупреждение: не удалось установить numpy:\n{e[:400]}\n"))
                            except Exception as numpy_e:
                                self.root.after(0, lambda err=str(numpy_e)[:100]: progress_text.insert(tk.END, f"⚠ Предупреждение: ошибка установки numpy: {err}\n"))
                    
                    # Увеличиваем таймаут для тяжелых библиотек
                    timeout_value = 600 if lib in ('pdf2docx', 'moviepy', 'pydub') else 300
                    
                    result = subprocess.run(
                        install_cmd,
                        capture_output=True,
                        text=True,
                        timeout=timeout_value
                    )
                    
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
                            f"  1. Сначала установите numpy:\n"
                            f"     pip install --user numpy\n\n"
                            f"  2. Затем установите pdf2docx:\n"
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


