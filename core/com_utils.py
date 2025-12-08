"""Утилиты для работы с COM объектами (Word, Excel и т.д.)."""

import logging
import os
from typing import Optional, Tuple, Any

logger = logging.getLogger(__name__)


def cleanup_word_application(word_app: Optional[Any]) -> None:
    """Безопасное закрытие Word приложения.
    
    Args:
        word_app: Объект Word.Application или None
    """
    if word_app:
        try:
            word_app.Quit(SaveChanges=False)
        except Exception as e:
            logger.warning(f"Ошибка при закрытии Word: {e}")


def cleanup_word_document(doc: Optional[Any]) -> None:
    """Безопасное закрытие Word документа.
    
    Args:
        doc: Объект Word.Document или None
    """
    if doc:
        try:
            doc.Close(SaveChanges=False)
        except Exception as e:
            logger.warning(f"Ошибка при закрытии документа: {e}")


def create_word_application(com_client: Any) -> Tuple[Optional[Any], Optional[str]]:
    """Создание объекта Word.Application с несколькими попытками.
    
    Args:
        com_client: Клиент COM (win32com.client или comtypes.client)
        
    Returns:
        Tuple[word_app, error_message] - объект Word или None и сообщение об ошибке
    """
    # Пробуем разные способы создания Word объекта
    try:
        word = com_client.Dispatch('Word.Application')
        return word, None
    except Exception as e1:
        logger.warning(f"Первый способ создания Word.Application не удался: {e1}")
        # Пробуем альтернативный способ через DispatchEx
        try:
            word = com_client.DispatchEx('Word.Application')
            logger.debug("Word.Application создан через DispatchEx")
            return word, None
        except Exception as e2:
            logger.warning(f"Второй способ создания Word.Application не удался: {e2}")
            # Пробуем через GetActiveObject (если Word уже запущен)
            try:
                word = com_client.GetActiveObject('Word.Application')
                logger.debug("Word.Application получен через GetActiveObject (Word уже запущен)")
                return word, None
            except Exception as e3:
                error_msg = str(e1)
                logger.error(f"Все способы создания Word.Application не удались. Первая ошибка: {error_msg}")
                if "Invalid class string" in error_msg or "CLSID" in error_msg or "Class not registered" in error_msg:
                    return None, "Microsoft Word не установлен или недоступен. Убедитесь, что Word установлен и зарегистрирован в системе."
                return None, f"Не удалось создать объект Word.Application: {error_msg}"


def convert_docx_with_word(
    word_app: Any,
    file_path: str,
    output_path: str,
    com_client_type: str = "win32com"
) -> Tuple[bool, Optional[str]]:
    """Конвертация DOCX в PDF через Word приложение.
    
    Args:
        word_app: Объект Word.Application
        file_path: Путь к исходному DOCX файлу
        output_path: Путь для сохранения PDF
        com_client_type: Тип COM клиента ("win32com" или "comtypes")
        
    Returns:
        Tuple[success, error_message]
    """
    doc = None
    try:
        # Проверяем, что файл существует
        if not os.path.exists(file_path):
            return False, f"Исходный файл не найден: {file_path}"
        
        # Проверяем, что директория для выходного файла существует
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Настраиваем Word
        word_app.Visible = False
        word_app.DisplayAlerts = 0  # Отключаем предупреждения
        
        # Открываем документ
        doc_path = os.path.abspath(file_path)
        logger.debug(f"Открываем документ Word: {doc_path}")
        try:
            doc = word_app.Documents.Open(
                FileName=doc_path,
                ReadOnly=True,
                ConfirmConversions=False,
                AddToRecentFiles=False
            )
            logger.debug("Документ открыт успешно")
        except Exception as open_error:
            error_msg = str(open_error)
            logger.error(f"Ошибка при открытии документа: {error_msg}")
            if "не найден" in error_msg.lower() or "not found" in error_msg.lower():
                return False, f"Не удалось открыть документ: {file_path}"
            return False, f"Ошибка при открытии документа: {error_msg}"
        
        # Сохраняем как PDF
        pdf_path = os.path.abspath(output_path)
        logger.debug(f"Сохраняем как PDF: {pdf_path}")
        try:
            doc.SaveAs(FileName=pdf_path, FileFormat=17)  # 17 = PDF format
            logger.debug("Документ сохранен как PDF")
        except Exception as save_error:
            error_msg = str(save_error)
            logger.error(f"Ошибка при сохранении PDF: {error_msg}")
            # Проверяем, может быть файл уже существует и заблокирован
            if os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                    doc.SaveAs(FileName=pdf_path, FileFormat=17)
                except Exception as retry_error:
                    return False, f"Не удалось сохранить PDF: {retry_error}"
            else:
                return False, f"Ошибка при сохранении PDF: {error_msg}"
        
        return True, None
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка при конвертации через {com_client_type}: {error_msg}")
        return False, error_msg
    finally:
        cleanup_word_document(doc)

