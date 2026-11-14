import fitz
import sentry_sdk


def get_pdf_page_count(pdf_path: str) -> int:
    try:
        with fitz.open(pdf_path) as doc:
            return doc.page_count
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return 0
