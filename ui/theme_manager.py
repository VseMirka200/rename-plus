"""Модуль для управления темами интерфейса."""

import tkinter as tk
from typing import Dict


class ThemeManager:
    """Класс для управления темами."""
    
    LIGHT_THEME = {
        'primary': '#667EEA',
        'primary_hover': '#5568D3',
        'primary_light': '#818CF8',
        'primary_dark': '#4C51BF',
        'success': '#10B981',
        'success_hover': '#059669',
        'danger': '#EF4444',
        'danger_hover': '#DC2626',
        'warning': '#F59E0B',
        'warning_hover': '#D97706',
        'info': '#3B82F6',
        'info_hover': '#2563EB',
        'bg_main': '#F5F7FA',
        'bg_card': '#FFFFFF',
        'bg_secondary': '#EDF2F7',
        'bg_hover': '#F7FAFC',
        'bg_input': '#FFFFFF',
        'bg_elevated': '#FFFFFF',
        'border': '#E2E8F0',
        'border_focus': '#667EEA',
        'border_light': '#F1F5F9',
        'text_primary': '#1A202C',
        'text_secondary': '#4A5568',
        'text_muted': '#718096',
        'header_bg': '#FFFFFF',
        'header_text': '#1A202C',
        'accent': '#9F7AEA',
        'shadow': 'rgba(0,0,0,0.08)',
        'shadow_lg': 'rgba(0,0,0,0.12)',
        'shadow_xl': 'rgba(0,0,0,0.16)',
        'glow': 'rgba(102, 126, 234, 0.4)',
        'gradient_start': '#667EEA',
        'gradient_end': '#764BA2'
    }
    
    DARK_THEME = {
        'primary': '#667EEA',
        'primary_hover': '#5568D3',
        'primary_light': '#818CF8',
        'primary_dark': '#4C51BF',
        'success': '#10B981',
        'success_hover': '#059669',
        'danger': '#EF4444',
        'danger_hover': '#DC2626',
        'warning': '#F59E0B',
        'warning_hover': '#D97706',
        'info': '#3B82F6',
        'info_hover': '#2563EB',
        'bg_main': '#1A202C',
        'bg_card': '#2D3748',
        'bg_secondary': '#4A5568',
        'bg_hover': '#374151',
        'bg_input': '#4A5568',
        'bg_elevated': '#2D3748',
        'border': '#4A5568',
        'border_focus': '#667EEA',
        'border_light': '#718096',
        'text_primary': '#F7FAFC',
        'text_secondary': '#CBD5E0',
        'text_muted': '#A0AEC0',
        'header_bg': '#2D3748',
        'header_text': '#F7FAFC',
        'accent': '#9F7AEA',
        'shadow': 'rgba(0,0,0,0.3)',
        'shadow_lg': 'rgba(0,0,0,0.4)',
        'shadow_xl': 'rgba(0,0,0,0.5)',
        'glow': 'rgba(102, 126, 234, 0.4)',
        'gradient_start': '#667EEA',
        'gradient_end': '#764BA2'
    }
    
    def __init__(self, theme: str = 'light'):
        """Инициализация менеджера тем.
        
        Args:
            theme: Название темы ('light' или 'dark')
        """
        self.current_theme = theme
        self.colors = self.get_theme_colors(theme)
    
    def get_theme_colors(self, theme: str) -> Dict[str, str]:
        """Получение цветов темы.
        
        Args:
            theme: Название темы
            
        Returns:
            Словарь с цветами
        """
        if theme == 'dark':
            return self.DARK_THEME.copy()
        return self.LIGHT_THEME.copy()
    
    def set_theme(self, theme: str) -> None:
        """Установка темы.
        
        Args:
            theme: Название темы ('light' или 'dark')
        """
        self.current_theme = theme
        self.colors = self.get_theme_colors(theme)
    
    def toggle_theme(self) -> str:
        """Переключение темы.
        
        Returns:
            Название новой темы
        """
        if self.current_theme == 'light':
            self.set_theme('dark')
            return 'dark'
        else:
            self.set_theme('light')
            return 'light'

