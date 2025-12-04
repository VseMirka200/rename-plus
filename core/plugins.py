"""Модуль для системы плагинов."""

import importlib
import importlib.util
import inspect
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class PluginManager:
    """Класс для управления плагинами."""
    
    def __init__(self, plugins_dir: Optional[str] = None):
        """Инициализация менеджера плагинов.
        
        Args:
            plugins_dir: Директория с плагинами
        """
        if plugins_dir is None:
            plugins_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'plugins'
            )
        self.plugins_dir = plugins_dir
        self.plugins: Dict[str, Any] = {}
        self.load_plugins()
    
    def load_plugins(self) -> None:
        """Загрузка всех плагинов из директории."""
        if not os.path.exists(self.plugins_dir):
            try:
                os.makedirs(self.plugins_dir, exist_ok=True)
            except Exception as e:
                logger.error(f"Не удалось создать директорию плагинов: {e}")
                return
        
        # Создаем __init__.py если его нет
        init_file = os.path.join(self.plugins_dir, '__init__.py')
        if not os.path.exists(init_file):
            try:
                with open(init_file, 'w') as f:
                    f.write('# Plugins directory\n')
            except Exception:
                pass
        
        # Загружаем плагины
        for file in os.listdir(self.plugins_dir):
            if file.endswith('.py') and file != '__init__.py':
                plugin_name = file[:-3]
                try:
                    self._load_plugin(plugin_name)
                except Exception as e:
                    logger.error(f"Ошибка загрузки плагина {plugin_name}: {e}")
    
    def _load_plugin(self, plugin_name: str) -> None:
        """Загрузка одного плагина.
        
        Args:
            plugin_name: Имя плагина
        """
        try:
            spec = importlib.util.spec_from_file_location(
                plugin_name,
                os.path.join(self.plugins_dir, f"{plugin_name}.py")
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.plugins[plugin_name] = module
                logger.debug(f"Плагин {plugin_name} загружен")
        except Exception as e:
            logger.error(f"Ошибка загрузки плагина {plugin_name}: {e}")
    
    def get_plugin(self, plugin_name: str):
        """Получение плагина по имени.
        
        Args:
            plugin_name: Имя плагина
            
        Returns:
            Модуль плагина или None
        """
        return self.plugins.get(plugin_name)
    
    def list_plugins(self) -> List[str]:
        """Получение списка загруженных плагинов.
        
        Returns:
            Список имен плагинов
        """
        return list(self.plugins.keys())

