"""
Модуль методов переименования файлов
Реализует различные стратегии переименования
"""

import re
from abc import ABC, abstractmethod
from typing import Tuple, Optional
from datetime import datetime


class RenameMethod(ABC):
    """Базовый класс для методов переименования"""
    
    @abstractmethod
    def apply(self, name: str, extension: str, file_path: str) -> Tuple[str, str]:
        """
        Применяет метод переименования к имени файла
        
        Args:
            name: Имя файла без расширения
            extension: Расширение файла (с точкой)
            file_path: Полный путь к файлу
            
        Returns:
            Tuple[str, str]: Новое имя и расширение
        """
        pass


class AddRemoveMethod(RenameMethod):
    """Метод добавления/удаления текста"""
    
    def __init__(self, operation: str, text: str = "", position: str = "before",
                 remove_type: Optional[str] = None, remove_start: Optional[str] = None,
                 remove_end: Optional[str] = None):
        """
        Args:
            operation: "add" или "remove"
            text: Текст для добавления
            position: "before", "after", "start", "end"
            remove_type: "chars" или "range" (для удаления)
            remove_start: Начальная позиция/количество для удаления
            remove_end: Конечная позиция для удаления (для диапазона)
        """
        self.operation = operation
        self.text = text
        self.position = position
        self.remove_type = remove_type
        self.remove_start = remove_start
        self.remove_end = remove_end
    
    def apply(self, name: str, extension: str, file_path: str) -> Tuple[str, str]:
        if self.operation == "add":
            return self._add_text(name, extension)
        else:
            return self._remove_text(name, extension)
    
    def _add_text(self, name: str, extension: str) -> Tuple[str, str]:
        """Добавление текста"""
        if not self.text:
            return name, extension
        
        if self.position == "before":
            # Перед именем (но после расширения не добавляем)
            new_name = self.text + name
            return new_name, extension
        elif self.position == "after":
            # После имени (перед расширением)
            new_name = name + self.text
            return new_name, extension
        elif self.position == "start":
            # В начале всего имени
            new_name = self.text + name
            return new_name, extension
        elif self.position == "end":
            # В конце всего имени (перед расширением)
            new_name = name + self.text
            return new_name, extension
        
        return name, extension
    
    def _remove_text(self, name: str, extension: str) -> Tuple[str, str]:
        """Удаление текста"""
        if self.remove_type == "chars":
            # Удаление N символов
            try:
                count = int(self.remove_start or "0")
                if self.position == "start":
                    new_name = name[count:] if count < len(name) else ""
                elif self.position == "end":
                    new_name = name[:-count] if count < len(name) else ""
                else:
                    new_name = name
                return new_name, extension
            except ValueError:
                return name, extension
        
        elif self.remove_type == "range":
            # Удаление по диапазону
            try:
                start = int(self.remove_start or "0")
                end = int(self.remove_end or str(len(name)))
                if 0 <= start < len(name) and start < end:
                    new_name = name[:start] + name[end:]
                else:
                    new_name = name
                return new_name, extension
            except ValueError:
                return name, extension
        
        # Удаление конкретного текста
        if self.text:
            new_name = name.replace(self.text, "")
            return new_name, extension
        
        return name, extension


class ReplaceMethod(RenameMethod):
    """Метод замены текста"""
    
    def __init__(self, find: str, replace: str, case_sensitive: bool = False,
                 full_match: bool = False):
        """
        Args:
            find: Текст для поиска
            replace: Текст для замены
            case_sensitive: Учитывать регистр
            full_match: Только полное совпадение
        """
        self.find = find
        self.replace = replace
        self.case_sensitive = case_sensitive
        self.full_match = full_match
    
    def apply(self, name: str, extension: str, file_path: str) -> Tuple[str, str]:
        if not self.find:
            return name, extension
        
        if self.full_match:
            # Полное совпадение
            if self.case_sensitive:
                if name == self.find:
                    new_name = self.replace
                else:
                    new_name = name
            else:
                if name.lower() == self.find.lower():
                    new_name = self.replace
                else:
                    new_name = name
        else:
            # Частичное совпадение
            if self.case_sensitive:
                new_name = name.replace(self.find, self.replace)
            else:
                # Регистронезависимая замена
                pattern = re.compile(re.escape(self.find), re.IGNORECASE)
                new_name = pattern.sub(self.replace, name)
        
        return new_name, extension


class CaseMethod(RenameMethod):
    """Метод изменения регистра"""
    
    def __init__(self, case_type: str, apply_to: str = "name"):
        """
        Args:
            case_type: "upper", "lower", "capitalize", "title"
            apply_to: "name", "ext", "all"
        """
        self.case_type = case_type
        self.apply_to = apply_to
    
    def apply(self, name: str, extension: str, file_path: str) -> Tuple[str, str]:
        new_name = name
        new_ext = extension
        
        if self.apply_to == "name" or self.apply_to == "all":
            if self.case_type == "upper":
                new_name = name.upper()
            elif self.case_type == "lower":
                new_name = name.lower()
            elif self.case_type == "capitalize":
                new_name = name.capitalize()
            elif self.case_type == "title":
                new_name = name.title()
        
        if self.apply_to == "ext" or self.apply_to == "all":
            if extension:
                if self.case_type == "upper":
                    new_ext = extension.upper()
                elif self.case_type == "lower":
                    new_ext = extension.lower()
                elif self.case_type == "capitalize":
                    new_ext = extension.capitalize()
                elif self.case_type == "title":
                    new_ext = extension.title()
        
        return new_name, new_ext


class NumberingMethod(RenameMethod):
    """Метод нумерации файлов"""
    
    def __init__(self, start: int = 1, step: int = 1, digits: int = 3,
                 format_str: str = "({n})", position: str = "end"):
        """
        Args:
            start: Начальный индекс
            step: Шаг приращения
            digits: Количество цифр (с ведущими нулями)
            format_str: Формат номера (используйте {n} для номера)
            position: "start" или "end"
        """
        self.start = start
        self.step = step
        self.digits = digits
        self.format_str = format_str
        self.position = position
        self.current_number = start
    
    def apply(self, name: str, extension: str, file_path: str) -> Tuple[str, str]:
        # Форматирование номера с ведущими нулями
        number_str = str(self.current_number).zfill(self.digits)
        formatted_number = self.format_str.replace("{n}", number_str)
        
        # Добавление номера
        if self.position == "start":
            new_name = formatted_number + name
        else:  # end
            new_name = name + formatted_number
        
        # Увеличение номера для следующего файла
        self.current_number += self.step
        
        return new_name, extension
    
    def reset(self):
        """Сброс счетчика (вызывается перед применением к новому списку)"""
        self.current_number = self.start


class MetadataMethod(RenameMethod):
    """Метод вставки метаданных"""
    
    def __init__(self, tag: str, position: str = "end", extractor=None):
        """
        Args:
            tag: Тег метаданных (например, "{width}x{height}")
            position: "start" или "end"
            extractor: Экземпляр MetadataExtractor
        """
        self.tag = tag
        self.position = position
        self.extractor = extractor
    
    def apply(self, name: str, extension: str, file_path: str) -> Tuple[str, str]:
        if not self.extractor:
            return name, extension
        
        # Извлечение метаданных
        metadata_value = self.extractor.extract(self.tag, file_path)
        
        if metadata_value:
            if self.position == "start":
                new_name = metadata_value + name
            else:  # end
                new_name = name + metadata_value
        else:
            new_name = name
        
        return new_name, extension


class RegexMethod(RenameMethod):
    """Метод переименования с использованием регулярных выражений"""
    
    def __init__(self, pattern: str, replace: str):
        """
        Args:
            pattern: Регулярное выражение
            replace: Строка замены (может содержать группы \1, \2 и т.д.)
        """
        self.pattern = pattern
        self.replace = replace
        self.compiled_pattern = None
        
        if pattern:
            try:
                self.compiled_pattern = re.compile(pattern)
            except re.error:
                self.compiled_pattern = None
    
    def apply(self, name: str, extension: str, file_path: str) -> Tuple[str, str]:
        if not self.compiled_pattern:
            return name, extension
        
        try:
            new_name = self.compiled_pattern.sub(self.replace, name)
            return new_name, extension
        except Exception:
            return name, extension


class NewNameMethod(RenameMethod):
    """Метод полной замены имени по шаблону"""
    
    def __init__(self, template: str, metadata_extractor=None, file_number: int = 1):
        """
        Args:
            template: Шаблон нового имени (может содержать {name}, {ext}, {n}, {n:03d}, {width}x{height} и т.д.)
            metadata_extractor: Экстрактор метаданных
            file_number: Начальный номер файла (для {n})
        """
        self.template = template
        self.metadata_extractor = metadata_extractor
        self.file_number = file_number
        # Определение формата нумерации из шаблона
        self.number_format = self._detect_number_format(template)
    
    def _detect_number_format(self, template: str) -> dict:
        """Определение формата нумерации из шаблона"""
        # Поиск паттернов типа {n:03d}, {n:02d} и т.д.
        match = re.search(r'\{n:0?(\d+)d\}', template)
        if match:
            digits = int(match.group(1))
            return {'format': f'{{:0{digits}d}}', 'digits': digits}
        return {'format': '{}', 'digits': 0}
    
    def apply(self, name: str, extension: str, file_path: str) -> Tuple[str, str]:
        """Применение шаблона для создания нового имени"""
        if not self.template:
            return name, extension
        
        # Начинаем с шаблона - он полностью заменяет имя, если нет {name}
        new_name = self.template
        
        # Сначала заменяем все переменные, кроме {name}
        # {ext} - расширение (без точки)
        ext_without_dot = extension.lstrip('.')
        new_name = new_name.replace("{ext}", ext_without_dot)
        
        # {n} - номер файла (с поддержкой формата {n:03d}, {n:02d} и т.д.)
        if self.number_format['digits'] > 0:
            # Форматирование с ведущими нулями
            formatted_number = self.number_format['format'].format(self.file_number)
            # Заменяем все варианты {n:XXd} на отформатированный номер
            new_name = re.sub(r'\{n:0?\d+d\}', formatted_number, new_name)
        else:
            # Простая замена {n}
            new_name = new_name.replace("{n}", str(self.file_number))
        
        # Метаданные (если доступны)
        if self.metadata_extractor:
            # {width}x{height}
            if "{width}x{height}" in new_name:
                dims = self.metadata_extractor.extract("{width}x{height}", file_path)
                if dims:
                    new_name = new_name.replace("{width}x{height}", dims)
                else:
                    new_name = new_name.replace("{width}x{height}", "")
            
            # {width}
            if "{width}" in new_name:
                width = self.metadata_extractor.extract("{width}", file_path)
                if width:
                    new_name = new_name.replace("{width}", width)
                else:
                    new_name = new_name.replace("{width}", "")
            
            # {height}
            if "{height}" in new_name:
                height = self.metadata_extractor.extract("{height}", file_path)
                if height:
                    new_name = new_name.replace("{height}", height)
                else:
                    new_name = new_name.replace("{height}", "")
            
            # {date_created}
            if "{date_created}" in new_name:
                date = self.metadata_extractor.extract("{date_created}", file_path)
                if date:
                    new_name = new_name.replace("{date_created}", date)
                else:
                    new_name = new_name.replace("{date_created}", "")
            
            # {date_modified}
            if "{date_modified}" in new_name:
                date = self.metadata_extractor.extract("{date_modified}", file_path)
                if date:
                    new_name = new_name.replace("{date_modified}", date)
                else:
                    new_name = new_name.replace("{date_modified}", "")
            
            # {file_size}
            if "{file_size}" in new_name:
                size = self.metadata_extractor.extract("{file_size}", file_path)
                if size:
                    new_name = new_name.replace("{file_size}", size)
                else:
                    new_name = new_name.replace("{file_size}", "")
        
        # Замена {name} в самом конце (если есть в шаблоне)
        # Если {name} нет в шаблоне, то шаблон полностью заменяет имя
        if "{name}" in new_name:
            new_name = new_name.replace("{name}", name)
        
        # Увеличение номера для следующего файла
        self.file_number += 1
        
        return new_name, extension
    
    def reset(self):
        """Сброс счетчика (вызывается перед применением к новому списку)"""
        self.file_number = 1

