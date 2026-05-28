"""Source Document file-family helpers shared by preview and extraction workers."""


def normalize_extension(file_extension: str) -> str:
    return file_extension.lower().lstrip(".")


def is_txt_file(file_extension: str, mime_type: str) -> bool:
    normalized = normalize_extension(file_extension)
    normalized_mime = mime_type.lower().split(";", 1)[0].strip()
    return normalized == "txt" or normalized_mime == "text/plain"


def is_pdf_file(file_extension: str, mime_type: str) -> bool:
    normalized = normalize_extension(file_extension)
    normalized_mime = mime_type.lower().split(";", 1)[0].strip()
    return normalized == "pdf" or normalized_mime == "application/pdf"


def is_csv_file(file_extension: str, mime_type: str) -> bool:
    normalized = normalize_extension(file_extension)
    normalized_mime = mime_type.lower().split(";", 1)[0].strip()
    return normalized == "csv" or normalized_mime in {
        "text/csv",
        "application/csv",
        "text/comma-separated-values",
    }


def is_docx_file(file_extension: str, mime_type: str) -> bool:
    normalized = normalize_extension(file_extension)
    normalized_mime = mime_type.lower().split(";", 1)[0].strip()
    return normalized == "docx" or normalized_mime == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def is_pptx_file(file_extension: str, mime_type: str) -> bool:
    normalized = normalize_extension(file_extension)
    normalized_mime = mime_type.lower().split(";", 1)[0].strip()
    return normalized == "pptx" or normalized_mime == (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
