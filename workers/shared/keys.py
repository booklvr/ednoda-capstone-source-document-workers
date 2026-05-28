"""Deterministic S3 key builders matching Ednoda server helpers."""


def build_extraction_text_package_prefix(
    owner_user_id: str,
    source_document_id: int,
    extraction_id: int,
) -> str:
    return (
        f"source-document-text/user/{owner_user_id}/document/"
        f"{source_document_id}/extraction/{extraction_id}"
    )


def build_extraction_text_package_keys(
    text_bucket: str,
    owner_user_id: str,
    source_document_id: int,
    extraction_id: int,
) -> dict[str, str]:
    prefix = build_extraction_text_package_prefix(
        owner_user_id,
        source_document_id,
        extraction_id,
    )
    return {
        "textBucket": text_bucket,
        "manifestKey": f"{prefix}/manifest.json",
        "plainTextKey": f"{prefix}/plain.txt",
        # preview.md is an additive, human-readable rendering (markdown tables +
        # image references). plain.txt remains the contract-canonical text body.
        "previewMarkdownKey": f"{prefix}/preview.md",
        "blocksPrefix": f"{prefix}/blocks/",
        "chunksPrefix": f"{prefix}/chunks/",
        "imagesPrefix": f"{prefix}/images/",
    }


def format_image_key(images_prefix: str, image_number: int) -> str:
    return f"{images_prefix}image-{image_number:06d}.png"


def image_filename(image_number: int) -> str:
    return f"image-{image_number:06d}.png"


def build_preview_prefix(
    owner_user_id: str,
    source_document_id: int,
    preview_id: int,
) -> str:
    return (
        f"source-document-previews/user/{owner_user_id}/document/"
        f"{source_document_id}/preview/{preview_id}/"
    )


def build_preview_page_key(preview_prefix: str, page_number: int) -> str:
    return f"{preview_prefix}pages/page-{page_number:06d}.webp"


def build_preview_pdf_key(preview_prefix: str) -> str:
    return f"{preview_prefix}preview.pdf"


def build_text_preview_key(preview_prefix: str) -> str:
    return f"{preview_prefix}text-preview.txt"


def build_csv_preview_key(preview_prefix: str) -> str:
    return f"{preview_prefix}csv-preview.json"


def format_block_key(blocks_prefix: str, block_number: int) -> str:
    return f"{blocks_prefix}block-{block_number:06d}.json"


def format_chunk_key(chunks_prefix: str, chunk_number: int) -> str:
    return f"{chunks_prefix}chunk-{chunk_number:06d}.json"


def format_block_id(block_number: int) -> str:
    return f"block-{block_number:06d}"


def format_chunk_id(chunk_number: int) -> str:
    return f"chunk-{chunk_number:06d}"


def filename_from_s3_key(key: str) -> str:
    segment = key.rsplit("/", 1)[-1]
    return segment or key
