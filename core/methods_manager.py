"""Модуль для управления методами переименования."""

from typing import Dict, List, Optional

import tkinter as tk
from tkinter import messagebox

from .rename_methods import (
    AddRemoveMethod,
    CaseMethod,
    MetadataMethod,
    NewNameMethod,
    NumberingMethod,
    RegexMethod,
    RenameMethod,
    ReplaceMethod,
)


class MethodsManager:
    """Класс для управления методами переименования."""
    
    def __init__(self, metadata_extractor=None):
        """Инициализация менеджера методов.
        
        Args:
            metadata_extractor: Экстрактор метаданных (опционально)
        """
        self.metadata_extractor = metadata_extractor
        self.methods: List[RenameMethod] = []
    
    def add_method(self, method: RenameMethod) -> None:
        """Добавление метода в список.
        
        Args:
            method: Метод переименования
        """
        self.methods.append(method)
    
    def remove_method(self, index: int) -> None:
        """Удаление метода по индексу.
        
        Args:
            index: Индекс метода для удаления
        """
        if 0 <= index < len(self.methods):
            self.methods.pop(index)
    
    def clear_methods(self) -> None:
        """Очистка всех методов."""
        self.methods.clear()
    
    def get_methods(self) -> List[RenameMethod]:
        """Получение списка методов.
        
        Returns:
            Список методов переименования
        """
        return self.methods.copy()
    
    def reset_counters(self) -> None:
        """Сброс счетчиков нумерации перед применением."""
        from .rename_methods import NumberingMethod, NewNameMethod
        for method in self.methods:
            if isinstance(method, NumberingMethod):
                method.reset()
            elif isinstance(method, NewNameMethod):
                method.reset()
    
    def create_add_remove_method(self, operation: str, text: str = "", 
                                 position: str = "before",
                                 remove_type: Optional[str] = None,
                                 remove_start: Optional[str] = None,
                                 remove_end: Optional[str] = None) -> AddRemoveMethod:
        """Создание метода добавления/удаления текста.
        
        Args:
            operation: "add" или "remove"
            text: Текст для добавления
            position: "before", "after", "start", "end"
            remove_type: "chars" или "range"
            remove_start: Начальная позиция/количество
            remove_end: Конечная позиция
            
        Returns:
            Экземпляр AddRemoveMethod
        """
        return AddRemoveMethod(operation, text, position, remove_type, remove_start, remove_end)
    
    def create_replace_method(self, find: str, replace: str, 
                             case_sensitive: bool = False,
                             full_match: bool = False) -> ReplaceMethod:
        """Создание метода замены текста.
        
        Args:
            find: Текст для поиска
            replace: Текст для замены
            case_sensitive: Учитывать регистр
            full_match: Только полное совпадение
            
        Returns:
            Экземпляр ReplaceMethod
        """
        return ReplaceMethod(find, replace, case_sensitive, full_match)
    
    def create_case_method(self, case_type: str, apply_to: str = "name") -> CaseMethod:
        """Создание метода изменения регистра.
        
        Args:
            case_type: "upper", "lower", "capitalize", "title"
            apply_to: "name", "ext", "all"
            
        Returns:
            Экземпляр CaseMethod
        """
        return CaseMethod(case_type, apply_to)
    
    def create_numbering_method(self, start: int = 1, step: int = 1, 
                               digits: int = 3, format_str: str = "({n})",
                               position: str = "end") -> NumberingMethod:
        """Создание метода нумерации.
        
        Args:
            start: Начальный индекс
            step: Шаг приращения
            digits: Количество цифр
            format_str: Формат номера
            position: "start" или "end"
            
        Returns:
            Экземпляр NumberingMethod
        """
        return NumberingMethod(start, step, digits, format_str, position)
    
    def create_metadata_method(self, tag: str, position: str = "end") -> MetadataMethod:
        """Создание метода вставки метаданных.
        
        Args:
            tag: Тег метаданных
            position: "start" или "end"
            
        Returns:
            Экземпляр MetadataMethod
        """
        return MetadataMethod(tag, position, self.metadata_extractor)
    
    def create_regex_method(self, pattern: str, replace: str) -> RegexMethod:
        """Создание метода переименования с регулярными выражениями.
        
        Args:
            pattern: Регулярное выражение
            replace: Строка замены
            
        Returns:
            Экземпляр RegexMethod
        """
        return RegexMethod(pattern, replace)
    
    def create_new_name_method(self, template: str, file_number: int = 1) -> NewNameMethod:
        """Создание метода полной замены имени по шаблону.
        
        Args:
            template: Шаблон нового имени
            file_number: Начальный номер файла
            
        Returns:
            Экземпляр NewNameMethod
        """
        return NewNameMethod(template, self.metadata_extractor, file_number)
    
    def get_method_display_name(self, method: RenameMethod) -> str:
        """Получение отображаемого имени метода.
        
        Args:
            method: Метод переименования
            
        Returns:
            Отображаемое имя метода
        """
        if isinstance(method, NewNameMethod):
            return f"Новое имя: {method.template}"
        elif isinstance(method, AddRemoveMethod):
            op = "Добавить" if method.operation == "add" else "Удалить"
            return f"{op}: {method.text}"
        elif isinstance(method, ReplaceMethod):
            return f"Заменить: '{method.find}' -> '{method.replace}'"
        elif isinstance(method, CaseMethod):
            case_names = {
                "upper": "Верхний регистр",
                "lower": "Нижний регистр",
                "capitalize": "Первая заглавная",
                "title": "Заглавные слова"
            }
            return f"Регистр: {case_names.get(method.case_type, method.case_type)}"
        elif isinstance(method, NumberingMethod):
            return f"Нумерация: {method.format_str} (нач: {method.start}, шаг: {method.step})"
        elif isinstance(method, MetadataMethod):
            return f"Метаданные: {method.tag}"
        elif isinstance(method, RegexMethod):
            return f"Regex: {method.pattern} -> {method.replace}"
        else:
            return str(type(method).__name__)

