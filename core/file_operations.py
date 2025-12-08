"""Модуль для операций с файлами."""

import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

# Настройка логирования
logger = logging.getLogger(__name__)

# Импорт менеджера резервных копий (опционально)
try:
    from .backup_manager import BackupManager
    HAS_BACKUP = True
except ImportError:
    HAS_BACKUP = False

# Кэш для нормализованных путей (для оптимизации проверки дубликатов)
_path_cache: Set[str] = set()

# Импортируем константы из config
try:
    from config.constants import INVALID_FILENAME_CHARS, WINDOWS_RESERVED_NAMES
    _RESERVED_NAMES = WINDOWS_RESERVED_NAMES
    _INVALID_CHARS = INVALID_FILENAME_CHARS
except ImportError:
    # Fallback если константы недоступны
    _RESERVED_NAMES = frozenset(
        ['CON', 'PRN', 'AUX', 'NUL'] +
        [f'COM{i}' for i in range(1, 10)] +
        [f'LPT{i}' for i in range(1, 10)]
    )
    _INVALID_CHARS = frozenset(['<', '>', ':', '"', '/', '\\', '|', '?', '*'])


def add_file_to_list(
    file_path: str,
    files_list: List[Dict[str, Any]],
    path_cache: Optional[Set[str]] = None
) -> Optional[Dict[str, Any]]:
    """Добавление файла в список для переименования.
    
    Args:
        file_path: Путь к файлу
        files_list: Список файлов для добавления
        path_cache: Множество нормализованных путей для быстрой проверки дубликатов (опционально)
        
    Returns:
        Словарь с данными файла или None если файл уже существует
    """
    # Используем одну проверку os.path.exists вместо двух
    try:
        if not os.path.isfile(file_path):
            return None
    except (OSError, ValueError):
        return None
    
    # Проверка на дубликаты - используем set для O(1) проверки
    normalized_path = os.path.normpath(os.path.abspath(file_path))
    
    # Используем переданный кэш или создаем из списка файлов
    if path_cache is None:
        path_cache = {os.path.normpath(os.path.abspath(f.get('full_path') or f.get('path', '')))
                     for f in files_list if f.get('full_path') or f.get('path')}
    
    if normalized_path in path_cache:
        return None
    
    # Добавляем путь в кэш
    path_cache.add(normalized_path)
    
    # Получаем имя файла и расширение
    path_obj = Path(file_path)
    name = path_obj.stem
    extension = path_obj.suffix
    
    file_data = {
        'path': file_path,
        'full_path': file_path,
        'old_name': name,
        'new_name': name,
        'extension': extension,
        'status': 'Готов'
    }
    
    files_list.append(file_data)
    return file_data


def validate_filename(name: str, extension: str, path: str, index: int) -> str:
    """Валидация имени файла.
    
    Args:
        name: Имя файла без расширения
        extension: Расширение файла
        path: Путь к файлу
        index: Индекс файла в списке
        
    Returns:
        Статус валидации
    """
    if not name or not name.strip():
        return "Ошибка: пустое имя"
    
    # Запрещенные символы в именах файлов Windows (используем кэш)
    if any(char in name for char in _INVALID_CHARS):
        # Находим первый недопустимый символ для сообщения об ошибке
        for char in _INVALID_CHARS:
            if char in name:
                return f"Ошибка: недопустимый символ '{char}'"
    
    # Проверка на зарезервированные имена Windows (используем кэш)
    if name.upper() in _RESERVED_NAMES:
        return f"Ошибка: зарезервированное имя '{name}'"
    
    # Проверка длины имени (Windows ограничение: 255 символов для полного пути)
    full_name = name + extension
    if len(full_name) > 255:
        return f"Ошибка: имя слишком длинное ({len(full_name)} > 255)"
    
    # Проверка на точки в конце имени (Windows не позволяет)
    if name.endswith('.') or name.endswith(' '):
        return "Ошибка: имя не может заканчиваться точкой или пробелом"
    
    return "Готов"


def check_conflicts(files_list: List[Dict[str, Any]]) -> None:
    """Проверка конфликтов имен файлов.
    
    Args:
        files_list: Список файлов для проверки
    """
    # Создаем словарь для подсчета одинаковых имен
    name_counts = {}
    for file_data in files_list:
        full_name = file_data['new_name'] + file_data['extension']
        if full_name not in name_counts:
            name_counts[full_name] = []
        name_counts[full_name].append(file_data)
    
    # Помечаем конфликты
    for full_name, file_list in name_counts.items():
        if len(file_list) > 1:
            # Есть конфликт
            for file_data in file_list:
                file_data['status'] = f"Конфликт: {len(file_list)} файла с именем '{full_name}'"


def rename_files_thread(
    files_to_rename: List[Dict],
    callback: Callable[[int, int, List[Dict]], None],
    log_callback: Optional[Callable[[str], None]] = None,
    backup_manager: Optional[BackupManager] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_var: Optional[threading.Event] = None
) -> None:
    """Переименование файлов в отдельном потоке.
    
    Args:
        files_to_rename: Список файлов для переименования
        callback: Функция обратного вызова после завершения
        log_callback: Функция для логирования (опционально)
        backup_manager: Менеджер резервных копий (опционально)
        progress_callback: Функция для обновления прогресса (current, total, filename)
        cancel_var: Событие для отмены операции (опционально)
    """
    def rename_worker():
        success_count = 0
        error_count = 0
        renamed_files = []
        total = len(files_to_rename)
        
        # Создаем резервные копии, если включено
        backups = {}
        if backup_manager and HAS_BACKUP:
            try:
                backups = backup_manager.create_backups(files_to_rename)
                if backups and log_callback:
                    log_callback(f"Создано резервных копий: {len(backups)}")
            except Exception as e:
                logger.error(f"Ошибка при создании резервных копий: {e}")
                if log_callback:
                    log_callback(f"Предупреждение: не удалось создать резервные копии")
        
        for i, file_data in enumerate(files_to_rename):
            # Проверка отмены
            if cancel_var and cancel_var.is_set():
                if log_callback:
                    log_callback("Операция переименования отменена пользователем")
                break
            old_path = None
            new_path = None
            try:
                # Используем full_path если доступен, иначе path
                old_path = file_data.get('full_path') or file_data.get('path')
                if not old_path:
                    error_msg = "Не указан путь к файлу"
                    if log_callback:
                        log_callback(f"Ошибка: {error_msg}")
                    file_data['status'] = f"Ошибка: {error_msg}"
                    error_count += 1
                    continue
                
                # Нормализуем путь
                old_path = os.path.normpath(old_path)
                
                # Проверяем существование исходного файла (объединяем проверки)
                try:
                    if not os.path.isfile(old_path):
                        error_msg = f"Исходный файл не найден или не является файлом: {os.path.basename(old_path)}"
                        if log_callback:
                            log_callback(f"Ошибка: {error_msg}")
                        file_data['status'] = f"Ошибка: {error_msg}"
                        error_count += 1
                        continue
                except (OSError, ValueError):
                    error_msg = f"Исходный файл не найден: {os.path.basename(old_path)}"
                    if log_callback:
                        log_callback(f"Ошибка: {error_msg}")
                    file_data['status'] = f"Ошибка: {error_msg}"
                    error_count += 1
                    continue
                
                new_name = file_data.get('new_name', '')
                extension = file_data.get('extension', '')
                
                # Валидация нового имени
                if not new_name or not new_name.strip():
                    error_msg = "Пустое имя файла"
                    if log_callback:
                        log_callback(f"Ошибка: {error_msg}")
                    file_data['status'] = f"Ошибка: {error_msg}"
                    error_count += 1
                    continue
                
                # Получаем директорию и создаем новый путь
                directory = os.path.dirname(old_path)
                new_path = os.path.join(directory, new_name + extension)
                new_path = os.path.normpath(new_path)
                
                # Проверяем, что новый путь отличается от старого
                if old_path == new_path:
                    if log_callback:
                        log_callback(f"Без изменений: '{os.path.basename(old_path)}'")
                    success_count += 1
                    continue
                
                # Проверяем, существует ли файл с таким именем (os.path.exists уже проверяет и файлы, и директории)
                try:
                    if os.path.exists(new_path):
                        error_msg = f"Файл '{new_name + extension}' уже существует"
                        if log_callback:
                            log_callback(f"Ошибка: {error_msg}")
                        file_data['status'] = f"Ошибка: {error_msg}"
                        error_count += 1
                        continue
                except (OSError, ValueError):
                    pass  # Продолжаем, если проверка не удалась
                
                # Переименовываем файл
                try:
                    os.rename(old_path, new_path)
                    # Если переименование успешно, os.rename гарантирует, что файл существует по новому пути
                    # Проверка os.path.exists(new_path) не нужна
                except OSError as rename_error:
                    # Проверяем, что исходный файл все еще существует
                    try:
                        if not os.path.exists(old_path):
                            error_msg = f"Исходный файл был удален при переименовании: {os.path.basename(old_path)}"
                        else:
                            error_msg = f"Ошибка переименования: {str(rename_error)}"
                    except (OSError, ValueError):
                        error_msg = f"Ошибка переименования: {str(rename_error)}"
                    if log_callback:
                        log_callback(f"Ошибка: {error_msg}")
                    file_data['status'] = f"Ошибка: {error_msg}"
                    error_count += 1
                    continue
                
                # Обновляем путь в данных файла
                file_data['path'] = new_path
                file_data['full_path'] = new_path
                file_data['old_name'] = new_name
                
                renamed_files.append(file_data)
                success_count += 1
                
                if log_callback:
                    log_callback(f"Переименован: '{os.path.basename(old_path)}' -> '{new_name + extension}'")
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Ошибка при переименовании '{file_data.get('old_name', 'unknown')}': {error_msg}", exc_info=True)
                if log_callback:
                    log_callback(f"Ошибка при переименовании '{file_data.get('old_name', 'unknown')}': {error_msg}")
                file_data['status'] = f"Ошибка: {error_msg}"
                error_count += 1
                # Проверяем, что исходный файл все еще существует (опционально, только для логирования)
                if old_path:
                    try:
                        if os.path.exists(old_path) and log_callback:
                            log_callback(f"Исходный файл сохранен: {os.path.basename(old_path)}")
                    except (OSError, ValueError):
                        pass
            
            # Обновление прогресса даже при ошибке
            if progress_callback:
                try:
                    progress_callback(i + 1, total, file_data.get('old_name', 'unknown'))
                except Exception:
                    pass
        
        # Вызываем callback в главном потоке
        if callback:
            callback(success_count, error_count, renamed_files)
    
    thread = threading.Thread(target=rename_worker, daemon=True)
    thread.start()


