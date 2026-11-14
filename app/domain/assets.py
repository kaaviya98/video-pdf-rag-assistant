from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sentry_sdk
from django.conf import settings

from app.domain.pdf.data_classes import Chunk
from app.domain.pdf.parser import PdfChunkingOptions
from app.domain.pdf.parser import parse_pdf_into_chunks
from app.domain.vector_db import get_vector_database
from app.domain.vector_db.weaviate import WeaviateClientError
from app.domain.vector_db.weaviate import WeaviateVectorDatabase
from app.domain.video.data_classes import VideoTranscriptChunk
from app.domain.video.transcript import create_transcript_lines_from_vtt
from app.domain.video.transcript_parser import parse_asset_transcript_into_vector_chunks
from app.models.asset import Asset
from app.models.asset import AssetFileType
from app.models.organization import Organization
from app.utils.file_operations import delete_file
from app.utils.file_operations import download_file
from app.utils.file_operations import is_local_file
from app.utils.file_operations import resolve_file_source_to_local_path
from app.utils.health_checks import ping_health_check
from app.utils.pdf import get_pdf_page_count


class AssetProcessingError(Exception):
    pass


async def process_asset(asset: Asset) -> None:
    from app.tasks.asset import async_process_pdf_asset
    from app.tasks.asset import async_process_video_asset

    task: Any | None = None
    if asset.file_type == AssetFileType.PDF:
        task = async_process_pdf_asset.delay(str(asset.id))
    elif asset.file_type == AssetFileType.VIDEO:
        task = async_process_video_asset.delay(str(asset.id))
    if task:
        asset.celery_task_id = task.id
        await asset.asave(update_fields=["celery_task_id"])


def process_pdf_asset(asset: Asset) -> None:
    if asset.is_processing:
        return

    local_pdf_path = None
    should_cleanup: bool = not is_local_file(asset.file_url)

    try:
        asset.mark_as_processing()

        local_pdf_path = _get_pdf_file_path(asset)

        chunks = parse_pdf_into_chunks(
            local_pdf_path,
            PdfChunkingOptions(
                max_tokens=1536,
                overlap_tokens=384,
            ),
            scope_key=asset.scope_key,
            organization=asset.organization if asset.organization_id else None,
        )
        asset.update_total_chunks(len(chunks))
        _store_asset_chunks_in_vector_db(chunks, asset)
        total_pages_count = get_pdf_page_count(local_pdf_path)
        asset.update_total_pages(total_pages_count)

        asset.mark_as_completed()

    except Exception as e:
        sentry_sdk.capture_exception(e)
        asset.mark_as_failed(str(e))

        error_message = f"Error processing PDF asset: {e}"
        ping_health_check("process_pdf", "error", str(asset.id), str(e))
        raise AssetProcessingError(error_message) from e
    finally:
        if should_cleanup and local_pdf_path:
            delete_file(local_pdf_path)


def _get_pdf_file_path(asset: Asset) -> str:
    if is_local_file(asset.file_url):
        return str(asset.file_url)
    return str(download_file(asset.file_url))


def process_video_asset(asset: Asset) -> None:
    from app.domain.video.notes import generate_notes

    if asset.is_processing:
        return

    _validate_video_asset(asset)

    local_vtt_path: str | None = None
    should_cleanup_vtt = False
    try:
        asset.mark_as_processing()

        local_vtt_path, should_cleanup_vtt = resolve_file_source_to_local_path(
            str(asset.captions_url),
            use_settings_secret=False,
        )

        create_transcript_lines_from_vtt(asset, vtt_source=local_vtt_path)

        chunks = parse_asset_transcript_into_vector_chunks(asset)
        if not chunks:
            raise AssetProcessingError("Transcript parsing produced no chunks")

        asset.update_total_chunks(len(chunks))
        store_video_transcript_chunks_in_vector_db(chunks, asset)

        generate_notes(asset, upload=False)

        asset.mark_as_completed()

    except Exception as e:
        sentry_sdk.capture_exception(e)
        asset.mark_as_failed(str(e))

        ping_health_check("process_video", "error", str(asset.id), str(e))
        raise AssetProcessingError(f"Error processing VIDEO asset: {e}") from e
    finally:
        if should_cleanup_vtt and local_vtt_path:
            delete_file(local_vtt_path)


def _validate_video_asset(asset: Asset) -> None:
    if asset.file_type != AssetFileType.VIDEO:
        raise AssetProcessingError(
            f"Asset {asset.id} is not a VIDEO asset (file_type={asset.file_type})"
        )
    if not (asset.captions_url or "").strip():
        raise AssetProcessingError(
            f"Asset {asset.id} has no captions_url; VIDEO pipeline requires a VTT transcript URL"
        )



def _store_asset_chunks_in_vector_db(chunks: list[Chunk], asset: Asset) -> None:
    vector_db = None
    try:
        vector_db = get_vector_database()
        client = vector_db.get_client()
        vector_store = client.get_vector_store(
            settings.VECTOR_DB_PDF_COLLECTION_NAME,
            scope_key=asset.scope_key,
            organization=asset.organization if asset.organization_id else None,
        )
        additional_metadata = {"asset_id": str(asset.id)}
        documents = [
            chunk.to_langchain_document(additional_metadata=additional_metadata)
            for chunk in chunks
            if chunk.content.text
        ]

        client.add_documents(vector_store, documents, tenant=asset.scope_key)
    except WeaviateClientError as e:
        raise AssetProcessingError(str(e)) from e
    except Exception as e:
        error_message = f"Error storing asset chunks in vector database: {e}"
        raise AssetProcessingError(error_message) from e
    finally:
        if vector_db:
            vector_db.close()


def store_video_transcript_chunks_in_vector_db(
    chunks: list[VideoTranscriptChunk],
    asset: Asset,
) -> None:
    vector_db = None
    try:
        vector_db = get_vector_database()
        client = vector_db.get_client()
        vector_store = client.get_vector_store(
            settings.VECTOR_DB_VIDEO_COLLECTION_NAME,
            scope_key=asset.scope_key,
            organization=asset.organization if asset.organization_id else None,
        )
        asset_id = str(asset.id)
        topic_title = asset.title or ""
        documents = [
            chunk.to_langchain_document(asset_id=asset_id, topic_title=topic_title)
            for chunk in chunks
        ]
        client.add_documents(vector_store, documents, tenant=asset.scope_key)
    except WeaviateClientError as e:
        raise AssetProcessingError(str(e)) from e
    except Exception as e:
        error_message = f"Error storing video transcript chunks in vector database: {e}"
        raise AssetProcessingError(error_message) from e
    finally:
        if vector_db:
            vector_db.close()


def get_video_asset_docs_from_vector_db(asset: Asset) -> list[dict[str, Any]]:
    if not asset.scope_key:
        raise AssetProcessingError(
            "Asset must have scope_key to fetch video segment docs"
        )

    vector_db = WeaviateVectorDatabase()
    client = vector_db.get_client()
    try:
        docs = client.get_documents(
            scope_key=asset.scope_key,
            collection_name=settings.VECTOR_DB_VIDEO_COLLECTION_NAME,
            filters={"asset_id": str(asset.id)},
            limit=500,
        )
    except Exception as e:
        error_message = f"Error getting video asset docs from vector database: {e}"
        raise AssetProcessingError(error_message) from e
    finally:
        if vector_db:
            vector_db.close()

    return sorted(docs, key=lambda d: d.get("segment_order", 0))


def assign_organization_to_assets(
    asset_pks: UUID | Sequence[UUID],
    organization: Organization,
) -> None:
    from django_multitenant.utils import unset_current_tenant

    if isinstance(asset_pks, UUID):
        pks: tuple[UUID, ...] = (asset_pks,)
    else:
        pks = tuple(asset_pks)
    if not pks:
        msg = "At least one asset id is required"
        raise ValueError(msg)
    unique_pks = tuple(dict.fromkeys(pks))

    unset_current_tenant()
    qs = Asset.all_objects.filter(pk__in=unique_pks)
    found = qs.count()
    if found != len(unique_pks):
        raise Asset.DoesNotExist
    updated = qs.update(organization_id=organization.pk)
    if updated != len(unique_pks):
        msg = f"Expected to update {len(unique_pks)} asset rows, updated {updated}"
        raise RuntimeError(msg)
