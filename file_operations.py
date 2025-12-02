"""Модуль для операций с файлами."""

import os
import threading
from pathlib import Path
from typing import Dict, List, Optional


def add_file_to_list(file_path: str, files_list: List[Dict]) -> Optional[Dict]:
    """Добавление файла в список для переименования.
    
    Args:
        file_path: Путь к файлу
        files_list: Список файлов для добавления
        
    Returns:
        Словарь с данными файла или None если файл уже существует
    """
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return None
    
    # Проверка на дубликаты
    for existing_file in files_list:
        if existing_file['path'] == file_path:
            return None
    
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
    
    # Запрещенные символы в именах файлов Windows
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in invalid_chars:
        if char in name:
            return f"Ошибка: недопустимый символ '{char}'"
    
    # Проверка на зарезервированные имена Windows
    reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + \
                     [f'COM{i}' for i in range(1, 10)] + \
                     [f'LPT{i}' for i in range(1, 10)]
    if name.upper() in reserved_names:
        return f"Ошибка: зарезервированное имя '{name}'"
    
    # Проверка длины имени (Windows ограничение: 255 символов для полного пути)
    full_name = name + extension
    if len(full_name) > 255:
        return f"Ошибка: имя слишком длинное ({len(full_name)} > 255)"
    
    # Проверка на точки в конце имени (Windows не позволяет)
    if name.endswith('.') or name.endswith(' '):
        return "Ошибка: имя не может заканчиваться точкой или пробелом"
    
    return "Готов"


def check_conflicts(files_list: List[Dict]) -> None:
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


def rename_files_thread(files_to_rename: List[Dict], 
                        callback: callable,
                        log_callback: Optional[callable] = None) -> None:
    """Переименование файлов в отдельном потоке.
    
    Args:
        files_to_rename: Список файлов для переименования
        callback: Функция обратного вызова после завершения
        log_callback: Функция для логирования (опционально)
    """
    def rename_worker():
        success_count = 0
        error_count = 0
        renamed_files = []
        
        for file_data in files_to_rename:
            try:
                old_path = file_data['path']
                new_name = file_data['new_name']
                extension = file_data['extension']
                
                # Получаем директорию и создаем новый путь
                directory = os.path.dirname(old_path)
                new_path = os.path.join(directory, new_name + extension)
                
                # Проверяем, что новый путь отличается от старого
                if old_path == new_path:
                    continue
                
                # Проверяем, существует ли файл с таким именем
                if os.path.exists(new_path):
                    error_msg = f"Файл '{new_name + extension}' уже существует"
                    if log_callback:
                        log_callback(f"Ошибка: {error_msg}")
                    file_data['status'] = f"Ошибка: {error_msg}"
                    error_count += 1
                    continue
                
                # Переименовываем файл
                os.rename(old_path, new_path)
                
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
                if log_callback:
                    log_callback(f"Ошибка при переименовании '{file_data.get('old_name', 'unknown')}': {error_msg}")
                file_data['status'] = f"Ошибка: {error_msg}"
                error_count += 1
        
        # Вызываем callback в главном потоке
        if callback:
            callback(success_count, error_count, renamed_files)
    
    thread = threading.Thread(target=rename_worker, daemon=True)
    thread.start()


