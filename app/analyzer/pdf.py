import io
import pdfplumber


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Извлекает текст из PDF. Кидает ValueError если текста нет."""
    text_parts: list[str] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)

    result = "\n\n".join(text_parts).strip()

    if len(result) < 100:
        raise ValueError("PDF не содержит читаемого текста — возможно, это скан.")

    return result
