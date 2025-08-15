
import logging


def parse_pdf_content(pdf_bytes: bytes, paper_id: str = None, logger: logging.Logger = None) -> str:
        try:
            import fitz
            full_text = []
            with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf_document:
                if pdf_document.page_count == 0:
                    logger.warning(f"PDF-документ {paper_id} не содержит страниц.")
                    return None
                
                for page_num, page in enumerate(pdf_document, start=1):
                    try:
                        page_text = page.get_text()
                        if page_text.strip():
                            full_text.append(page_text)
                    except Exception as page_error:
                        logger.error(f"Ошибка извлечения текста со страницы {page_num} для {paper_id}: {page_error}")
            
            if not full_text:
                logger.warning(f"Не удалось извлечь текст из PDF {paper_id}, хотя файл валиден.")
                return None

            result = "\n".join(full_text)
            logger.info(f"Успешно извлечен текст из {len(full_text)} страниц для {paper_id}. "
                        f"Общая длина: {len(result)} символов.")
            return result
        except Exception as e:
            logger.error(f"Критическая ошибка PyMuPDF при обработке {paper_id}: {e}")
            return None