import sentry_sdk
from celery import shared_task
from django.conf import settings
from app.domain.assets import process_pdf_asset
from app.domain.assets import process_video_asset
from app.models.asset import Asset, AssetFileType
from app.utils.health_checks import ping_health_check


@shared_task(queue=settings.CELERY_PDF_QUEUE)
def async_process_pdf_asset(asset_id: str) -> None:
    try:
        asset = Asset.objects.get(id=asset_id)

        if asset.is_processed:
            return

        if asset.is_processing:
            return

        ping_health_check("process_pdf", "start", str(asset_id))
        process_pdf_asset(asset)

        ping_health_check("process_pdf", "completed", str(asset_id))
    except Asset.DoesNotExist:
        sentry_sdk.capture_message(f"Asset not found during PDF processing: {asset_id}")
    except Exception as e:
        sentry_sdk.capture_exception(e)
        raise


@shared_task(queue=settings.CELERY_VIDEO_QUEUE)
def async_process_video_asset(asset_id: str) -> None:
    asset: Asset | None = None
    try:
        asset = Asset.objects.get(id=asset_id)
        if asset.file_type != AssetFileType.VIDEO:
            return
        if not (asset.captions_url or "").strip():
            asset.mark_as_failed("VIDEO asset requires captions_url")
            return
        if asset.is_processed:
            return
        if asset.is_processing:
            return

        ping_health_check("process_video", "start", str(asset_id))
        process_video_asset(asset)
        ping_health_check("process_video", "completed", str(asset_id))
    except Asset.DoesNotExist:
        sentry_sdk.capture_message(
            f"Asset not found during VIDEO processing: {asset_id}"
        )
    except Exception as e:
        sentry_sdk.capture_exception(e)
        if asset is not None and asset.processing_status != Asset.STATUS_CHOICES.FAILED:
            asset.mark_as_failed(str(e))

        ping_health_check("process_video", "error", str(asset_id), str(e))
        raise

