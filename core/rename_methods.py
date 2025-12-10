"""Модуль методов переименования файлов.

Реализует различные стратегии переименования файлов через паттерн Strategy.
Каждый метод переименования наследуется от базового класса RenameMethod
и реализует метод apply() для преобразования имени файла.
"""

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class RenameMethod(ABC):
    """Базовый абстрактный класс для методов переименования.
    
    Все методы переименования должны наследоваться от этого класса
    и реализовывать метод apply() для преобразования имени файла.
    
    Методы переименования применяются последовательно к каждому файлу
    в порядке их добавления в MethodsManager.
    """
    
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
    
    def __init__(
        self,
        operation: str,
        text: str = "",
        position: str = "before",
        remove_type: Optional[str] = None,
        remove_start: Optional[str] = None,
        remove_end: Optional[str] = None
    ):
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
        # Кэшируем скомпилированный regex для регистронезависимой замены
        self._compiled_pattern = None
        if find and not case_sensitive and not full_match:
            try:
                self._compiled_pattern = re.compile(re.escape(find), re.IGNORECASE)
            except re.error:
                self._compiled_pattern = None
    
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
                # Регистронезависимая замена - используем кэшированный паттерн
                if self._compiled_pattern:
                    new_name = self._compiled_pattern.sub(self.replace, name)
                else:
                    # Fallback, если компиляция не удалась
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
    
    def __init__(
        self,
        start: int = 1,
        step: int = 1,
        digits: int = 3,
        format_str: str = "({n})",
        position: str = "end"
    ):
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
    
    def reset(self) -> None:
        """Сброс счетчика (вызывается перед применением к новому списку)."""
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
        except Exception as e:
            logger.warning(f"Ошибка применения regex паттерна '{self.pattern}': {e}")
            return name, extension


class NewNameMethod(RenameMethod):
    """Метод полной замены имени по шаблону"""
    
    def __init__(self, template: str, metadata_extractor=None, file_number: int = 1):
        """
        Args:
            template: Шаблон нового имени (может содержать {name}, {ext}, {n}, {n:03d}, 
                     {width}x{height}, {date_created} и т.д.)
            metadata_extractor: Экстрактор метаданных
            file_number: Начальный номер файла (для {n})
        """
        self.template = template
        self.metadata_extractor = metadata_extractor
        self.start_number = file_number
        self.file_number = file_number
        # Определение формата нумерации из шаблона
        self.number_format = self._detect_number_format(template)
        # Предварительно определяем, какие метаданные теги используются в шаблоне
        self.required_metadata_tags = self._detect_metadata_tags(template)
    
    def _detect_number_format(self, template: str) -> dict:
        """Определение формата нумерации из шаблона"""
        # Поиск паттернов типа {n:03d}, {n:02d} и т.д.
        match = re.search(r'\{n:0?(\d+)d\}', template)
        if match:
            digits = int(match.group(1))
            return {'format': f'{{:0{digits}d}}', 'digits': digits}
        return {'format': '{}', 'digits': 0}
    
    def _detect_metadata_tags(self, template: str) -> set:
        """Определение используемых тегов метаданных в шаблоне"""
        metadata_tags = {
            "{width}x{height}", "{width}", "{height}", "{date_created}", 
            "{date_modified}", "{file_size}", "{artist}", "{title}", 
            "{album}", "{year}", "{track}", "{genre}"
        }
        found_tags = set()
        for tag in metadata_tags:
            if tag in template:
                found_tags.add(tag)
        return found_tags
    
    def apply(self, name: str, extension: str, file_path: str) -> Tuple[str, str]:
        """Применение шаблона для создания нового имени"""
        if not self.template:
            return name, extension
        
        # Начинаем с шаблона - он полностью заменяет имя, если нет {name}
        new_name = self.template
        
        # Заменяем переменные в фигурных скобках
        # {ext} - расширение (без точки)
        ext_without_dot = extension.lstrip('.') if extension else ""
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
        
        # Метаданные (если доступны) - используем предварительно определенные теги
        if self.metadata_extractor and self.required_metadata_tags:
            # Извлекаем все необходимые метаданные за один проход
            metadata_values = {}
            for tag in self.required_metadata_tags:
                value = self.metadata_extractor.extract(tag, file_path)
                metadata_values[tag] = value or ""
            
            # Заменяем все теги одним проходом
            for tag, value in metadata_values.items():
                new_name = new_name.replace(tag, value)
        
        # Условная логика в шаблонах: {if:condition:then:else}
        # Пример: {if:{ext}==jpg:IMG_{n}:FILE_{n}}
        import re as regex_module
        conditional_pattern = r'\{if:([^:]+):([^:]+):([^}]+)\}'
        matches = regex_module.finditer(conditional_pattern, new_name)
        for match in reversed(list(matches)):  # Обратный порядок для корректной замены
            condition = match.group(1)
            then_part = match.group(2)
            else_part = match.group(3)
            
            # Вычисляем условие (простая проверка равенства)
            result = False
            if '==' in condition:
                parts = condition.split('==', 1)
                left = parts[0].strip().strip('"\'')
                right = parts[1].strip().strip('"\'')
                # Подставляем переменные
                left = self._substitute_variables(left, name, extension, file_path)
                result = left == right
            elif '!=' in condition:
                parts = condition.split('!=', 1)
                left = parts[0].strip().strip('"\'')
                right = parts[1].strip().strip('"\'')
                left = self._substitute_variables(left, name, extension, file_path)
                result = left != right
            elif 'in' in condition:
                parts = condition.split(' in ', 1)
                left = parts[0].strip().strip('"\'')
                right = parts[1].strip().strip('"\'')
                left = self._substitute_variables(left, name, extension, file_path)
                right = self._substitute_variables(right, name, extension, file_path)
                result = left in right
            else:
                # Простая проверка на существование/непустоту
                var = self._substitute_variables(condition, name, extension, file_path)
                result = bool(var and str(var).strip())
            
            # Подставляем результат
            if result:
                replacement = then_part
            else:
                replacement = else_part
            
            # Подставляем переменные в результат
            replacement = self._substitute_variables(replacement, name, extension, file_path)
            new_name = new_name[:match.start()] + replacement + new_name[match.end():]
        
        # Замена {name} в самом конце (если есть в шаблоне)
        # Если {name} нет в шаблоне, то шаблон полностью заменяет имя
        if "{name}" in new_name:
            new_name = new_name.replace("{name}", name)
        
        # Увеличение номера для следующего файла
        self.file_number += 1
        
        return new_name, extension
    
    def _substitute_variables(self, text: str, name: str, extension: str, file_path: str) -> str:
        """Подстановка переменных в текст.
        
        Args:
            text: Текст с переменными
            name: Имя файла
            extension: Расширение
            file_path: Путь к файлу
            
        Returns:
            Текст с подставленными переменными
        """
        result = text
        ext_without_dot = extension.lstrip('.') if extension else ""
        result = result.replace("{ext}", ext_without_dot)
        result = result.replace("{name}", name)
        
        if self.metadata_extractor:
            # Подставляем метаданные
            for tag in ["{width}", "{height}", "{date_created}", "{date_modified}", "{file_size}",
                       "{artist}", "{title}", "{album}", "{year}", "{track}", "{genre}"]:
                if tag in result:
                    value = self.metadata_extractor.extract(tag, file_path)
                    result = result.replace(tag, value or "")
        
        return result
    
    def reset(self) -> None:
        """Сброс счетчика (вызывается перед применением к новому списку)."""
        self.file_number = self.start_number

