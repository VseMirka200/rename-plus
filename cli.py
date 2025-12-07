"""Командная строка для Ренейм+."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Настройка логирования
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

try:
    from core.rename_methods import (
        AddRemoveMethod,
        CaseMethod,
        MetadataMethod,
        NewNameMethod,
        NumberingMethod,
        RegexMethod,
        ReplaceMethod,
    )
    from core.metadata import MetadataExtractor
    from core.file_operations import validate_filename
    HAS_CORE = True
except ImportError:
    HAS_CORE = False
    logger.error("Не удалось импортировать основные модули")


def rename_files_cli(files: List[str], methods: List[object], dry_run: bool = False) -> Dict[str, Any]:
    """Переименование файлов через CLI.
    
    Args:
        files: Список путей к файлам
        methods: Список методов переименования
        dry_run: Только предпросмотр без переименования
        
    Returns:
        Словарь с результатами
    """
    if not HAS_CORE:
        return {'error': 'Основные модули не доступны'}
    
    results = {
        'success': 0,
        'errors': 0,
        'renamed': [],
        'errors_list': []
    }
    
    # Создаем MetadataExtractor только если он нужен (для методов, использующих метаданные)
    metadata_extractor = None
    needs_metadata = any(isinstance(m, (MetadataMethod, NewNameMethod)) for m in methods)
    if needs_metadata:
        metadata_extractor = MetadataExtractor()
    
    for file_path in files:
        # Оптимизированная проверка файла (одна операция вместо двух)
        try:
            if not os.path.isfile(file_path):
                results['errors'] += 1
                results['errors_list'].append(f"Файл не найден: {file_path}")
                continue
        except (OSError, ValueError):
            results['errors'] += 1
            results['errors_list'].append(f"Файл не найден: {file_path}")
            continue
        
        try:
            path_obj = Path(file_path)
            old_name = path_obj.stem
            extension = path_obj.suffix
            
            # Применяем методы
            new_name = old_name
            new_ext = extension
            
            for method in methods:
                new_name, new_ext = method.apply(new_name, new_ext, file_path)
            
            # Валидация
            status = validate_filename(new_name, new_ext, file_path, 0)
            if status != 'Готов':
                results['errors'] += 1
                results['errors_list'].append(f"{file_path}: {status}")
                continue
            
            if old_name == new_name and extension == new_ext:
                # Имя не изменилось
                continue
            
            new_path = os.path.join(path_obj.parent, new_name + new_ext)
            
            if not dry_run:
                # Переименовываем
                os.rename(file_path, new_path)
                results['renamed'].append({
                    'old': file_path,
                    'new': new_path
                })
            else:
                # Только предпросмотр
                results['renamed'].append({
                    'old': file_path,
                    'new': new_path,
                    'preview': True
                })
            
            results['success'] += 1
            
        except Exception as e:
            results['errors'] += 1
            results['errors_list'].append(f"{file_path}: {str(e)}")
            logger.error(f"Ошибка переименования {file_path}: {e}", exc_info=True)
    
    return results


def main():
    """Главная функция CLI."""
    parser = argparse.ArgumentParser(
        description='Ренейм+ - утилита для переименования файлов',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Переименовать файлы с добавлением префикса
  python cli.py --add-prefix "IMG_" *.jpg
  
  # Заменить текст в именах
  python cli.py --replace "old" "new" *.txt
  
  # Изменить регистр
  python cli.py --case lower *.TXT
  
  # Предпросмотр без переименования
  python cli.py --dry-run --case title *.txt
        """
    )
    
    parser.add_argument('files', nargs='+', help='Файлы для переименования')
    parser.add_argument('--dry-run', action='store_true', help='Только предпросмотр')
    parser.add_argument('--output', '-o', help='Файл для сохранения результатов (JSON)')
    
    # Методы переименования
    parser.add_argument('--add-prefix', help='Добавить префикс')
    parser.add_argument('--add-suffix', help='Добавить суффикс')
    parser.add_argument('--replace', nargs=2, metavar=('OLD', 'NEW'), help='Заменить текст')
    parser.add_argument('--case', choices=['upper', 'lower', 'title', 'capitalize'], help='Изменить регистр')
    parser.add_argument('--regex', nargs=2, metavar=('PATTERN', 'REPLACE'), help='Regex замена')
    parser.add_argument('--number', nargs='?', const='1', help='Добавить нумерацию (начало)')
    parser.add_argument('--template', help='Шаблон нового имени')
    
    args = parser.parse_args()
    
    if not HAS_CORE:
        print("Ошибка: основные модули не доступны", file=sys.stderr)
        sys.exit(1)
    
    # Создаем методы
    methods = []
    metadata_extractor = MetadataExtractor()
    
    if args.add_prefix:
        methods.append(AddRemoveMethod('add', args.add_prefix, 'start'))
    if args.add_suffix:
        methods.append(AddRemoveMethod('add', args.add_suffix, 'end'))
    if args.replace:
        methods.append(ReplaceMethod(args.replace[0], args.replace[1]))
    if args.case:
        methods.append(CaseMethod(args.case))
    if args.regex:
        methods.append(RegexMethod(args.regex[0], args.regex[1]))
    if args.number:
        start = int(args.number) if args.number.isdigit() else 1
        methods.append(NumberingMethod(start=start))
    if args.template:
        methods.append(NewNameMethod(args.template, metadata_extractor))
    
    if not methods:
        print("Ошибка: не указаны методы переименования", file=sys.stderr)
        parser.print_help()
        sys.exit(1)
    
    # Переименовываем файлы
    results = rename_files_cli(args.files, methods, args.dry_run)
    
    # Выводим результаты
    if args.dry_run:
        print("=== ПРЕДПРОСМОТР (файлы не переименованы) ===")
    else:
        print("=== РЕЗУЛЬТАТЫ ===")
    
    print(f"Успешно: {results['success']}")
    print(f"Ошибок: {results['errors']}")
    
    if results['renamed']:
        print("\nПереименованные файлы:")
        for item in results['renamed']:
            if item.get('preview'):
                print(f"  {item['old']} -> {item['new']} [ПРЕДПРОСМОТР]")
            else:
                print(f"  {item['old']} -> {item['new']}")
    
    if results['errors_list']:
        print("\nОшибки:")
        for error in results['errors_list']:
            print(f"  {error}")
    
    # Сохраняем результаты в файл, если указано
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nРезультаты сохранены в: {args.output}")
    
    sys.exit(0 if results['errors'] == 0 else 1)


if __name__ == '__main__':
    main()

