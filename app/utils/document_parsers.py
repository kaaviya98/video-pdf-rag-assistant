from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marker.config.parser import ConfigParser
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.renderers.json import JSONOutput

from app.utils.logger import get_logger

logger = get_logger()


class DocumentParsingError(Exception):
    EMPTY_FILE_PATH = "File path cannot be empty"
    FILE_NOT_FOUND = "File `{file_path}` not found"
    INVALID_FILE_TYPE = "File `{file_path}` is not a {expected_extension}"
    PDF_PARSING_ERROR = "Error parsing PDF file: {error}"


@dataclass
class DocumentParserConfig:
    output_format: str = "json"
    page_range: str | None = None
    use_llm: bool = False
    disable_image_extraction: bool = False
    llm_service: str | None = None
    extra_kwargs: dict[str, Any] | None = None
    disable_multiprocessing: bool = True

    def to_dict(self) -> dict[str, Any]:
        config_dict = {
            "output_format": self.output_format,
            "page_range": self.page_range,
            "use_llm": self.use_llm,
            "disable_image_extraction": self.disable_image_extraction,
            "llm_service": self.llm_service,
            "disable_multiprocessing": self.disable_multiprocessing,
        }
        if self.extra_kwargs:
            config_dict.update(self.extra_kwargs)
        return config_dict


def parse_pdf(file_path: str, config: DocumentParserConfig | None = None) -> JSONOutput:
    validate_file_path(file_path, ".pdf")

    if config is None:
        config = DocumentParserConfig()

    try:
        config_parser = ConfigParser(config.to_dict())

        logger.info(f"[DOC_PARSER] Creating model dictionary")
        model_dict = create_model_dict()

        logger.info(f"[DOC_PARSER] Initializing PdfConverter")
        converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=model_dict,
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
            llm_service=config_parser.get_llm_service(),
        )

        logger.info(f"[DOC_PARSER] Running Marker converter")
        result = converter(file_path)
        logger.info(f"[DOC_PARSER] Marker conversion completed")
    except Exception as e:
        error_msg = DocumentParsingError.PDF_PARSING_ERROR.format(error=str(e))
        logger.exception(error_msg)
        raise DocumentParsingError(error_msg) from e
    else:
        return result


def validate_file_path(file_path: str, expected_extension: str) -> None:
    if not file_path:
        raise DocumentParsingError(DocumentParsingError.EMPTY_FILE_PATH)

    path = Path(file_path)
    if not path.exists():
        error_msg = DocumentParsingError.FILE_NOT_FOUND.format(file_path=file_path)
        raise DocumentParsingError(error_msg)

    if not path.is_file() or path.suffix != expected_extension:
        error_msg = DocumentParsingError.INVALID_FILE_TYPE.format(
            file_path=file_path,
            expected_extension=expected_extension,
        )
        raise DocumentParsingError(error_msg)
