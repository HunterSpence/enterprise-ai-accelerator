"""
core/files_api.py
=================

Wrapper around Anthropic's Files API (beta).  Provides typed upload/list/
delete/metadata helpers and a compliance-specific convenience method for
tagging documents for compliance_citations consumption.

WIRING (one-liner):
    from core.files_api import FilesClient
    fc = FilesClient(ai=get_client())
    ref = await fc.upload(Path("iso27001.pdf"), purpose="document")
    # ref.id is the file_id to pass in document source blocks

Compliance shortcut:
    ref = await fc.upload_compliance_document(
        path=Path("annex_iv_checklist.pdf"),
        title="EU AI Act Annex IV Checklist 2025",
    )

File IDs can be used in messages as:
    {
        "type": "document",
        "source": {"type": "file", "file_id": ref.id},
        "title": ref.filename,
        "citations": {"enabled": True},
    }

Note: Files API is in beta as of anthropic>=0.69.0 and requires the
``anthropic-beta: files-api-2025-04-14`` header, which the SDK injects
automatically when you call ``client.beta.files.*``.
"""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Media types the Anthropic Files API currently accepts
_SUPPORTED_MEDIA_TYPES = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/html",
        "text/markdown",
        "text/csv",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }
)

_DEFAULT_MEDIA_TYPE = "application/octet-stream"


# ---------------------------------------------------------------------------
# FileRef — returned by upload / metadata calls
# ---------------------------------------------------------------------------

@dataclass
class FileRef:
    """Reference to an uploaded file in the Anthropic Files API.

    Attributes
    ----------
    id:
        The ``file_id`` string used to reference this file in messages.
    filename:
        Original filename as stored by the API.
    bytes:
        File size in bytes (may be 0 if not returned by the API).
    created_at:
        Unix timestamp of upload (may be 0 if not returned).
    media_type:
        MIME type of the file.
    purpose:
        Purpose string passed at upload time (e.g. "document").
    """

    id: str
    filename: str
    bytes: int = 0
    created_at: int = 0
    media_type: str = ""
    purpose: str = "document"

    def as_document_block(
        self, *, title: Optional[str] = None, citations: bool = True
    ) -> dict[str, Any]:
        """Return an Anthropic content block dict for use in messages.

        Example:
            block = ref.as_document_block(title="ISO 27001", citations=True)
            # Then include in user content list
        """
        return {
            "type": "document",
            "source": {"type": "file", "file_id": self.id},
            "title": title or self.filename,
            **({"citations": {"enabled": True}} if citations else {}),
        }


# ---------------------------------------------------------------------------
# FilesClient
# ---------------------------------------------------------------------------

class FilesClient:
    """Async wrapper around the Anthropic beta Files API.

    Parameters
    ----------
    ai:
        An ``AIClient`` instance (core.ai_client). The underlying
        ``AsyncAnthropic`` raw client is used for all API calls.
    """

    def __init__(self, ai: Any) -> None:
        self._ai = ai

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    async def upload(
        self,
        path: Path | str,
        *,
        purpose: str = "document",
        media_type: Optional[str] = None,
    ) -> FileRef:
        """Upload a file to the Anthropic Files API.

        Parameters
        ----------
        path:
            Local filesystem path to the file.
        purpose:
            Purpose string (default "document").
        media_type:
            MIME type. If None, guessed from the file extension.

        Returns
        -------
        FileRef
            Populated with the API-returned id, filename, size, and timestamp.

        Raises
        ------
        FileNotFoundError
            If the path does not exist.
        ValueError
            If the guessed media type is not supported.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        resolved_media_type = media_type or _guess_media_type(path)
        if resolved_media_type not in _SUPPORTED_MEDIA_TYPES:
            logger.warning(
                "Media type %s may not be supported by Files API. Proceeding anyway.",
                resolved_media_type,
            )

        file_bytes = path.read_bytes()
        filename = path.name

        logger.info("Uploading %s (%d bytes, %s)", filename, len(file_bytes), resolved_media_type)

        # The SDK beta client accepts (filename, file_bytes, media_type) tuple
        response = await self._ai.raw.beta.files.upload(
            file=(filename, file_bytes, resolved_media_type),
        )

        return _parse_file_response(response, purpose=purpose, media_type=resolved_media_type)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_files(self, *, limit: int = 100) -> list[FileRef]:
        """List files stored in the Anthropic Files API.

        Parameters
        ----------
        limit:
            Maximum number of files to return (default 100).

        Returns
        -------
        list[FileRef]
        """
        response = await self._ai.raw.beta.files.list(limit=limit)
        items = getattr(response, "data", []) or []
        return [_parse_file_response(item) for item in items]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, file_id: str) -> bool:
        """Delete a file by ID.

        Returns True if the deletion was acknowledged by the API.
        """
        response = await self._ai.raw.beta.files.delete(file_id)
        # SDK returns a DeletedFile object with .deleted bool
        deleted = getattr(response, "deleted", None)
        if deleted is None:
            # Fallback for dict-like responses
            deleted = isinstance(response, dict) and response.get("deleted", False)
        logger.info("Deleted file %s: %s", file_id, deleted)
        return bool(deleted)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    async def get_metadata(self, file_id: str) -> FileRef:
        """Retrieve metadata for a single file.

        Parameters
        ----------
        file_id:
            The Files API file ID.

        Returns
        -------
        FileRef
        """
        response = await self._ai.raw.beta.files.retrieve_metadata(file_id)
        return _parse_file_response(response)

    # ------------------------------------------------------------------
    # Compliance shortcut
    # ------------------------------------------------------------------

    async def upload_compliance_document(
        self,
        path: Path | str,
        *,
        title: str,
        media_type: Optional[str] = None,
    ) -> FileRef:
        """Upload a compliance document and return a pre-configured FileRef.

        Uploads the file with purpose="document" and attaches enough metadata
        to the FileRef for compliance_citations to consume it directly:

            block = ref.as_document_block(title=title, citations=True)

        The ``title`` should include the document name + version, e.g.:
        "EU AI Act Annex IV Checklist v1.2 (2025-03)".

        Parameters
        ----------
        path:
            Local path to the PDF/text document.
        title:
            Human-readable document title (stored on the FileRef, used as
            the document block title in citations requests).
        media_type:
            Override MIME type. If None, guessed from extension.
        """
        ref = await self.upload(path, purpose="document", media_type=media_type)
        # Annotate the ref with the provided title for downstream use
        ref.filename = title  # override stored filename with the semantic title
        logger.info(
            "Compliance document uploaded: '%s' → file_id=%s", title, ref.id
        )
        return ref


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guess_media_type(path: Path) -> str:
    """Guess MIME type from file extension."""
    mt, _ = mimetypes.guess_type(str(path))
    if mt and mt in _SUPPORTED_MEDIA_TYPES:
        return mt
    # Common overrides not always in mimetypes db
    ext = path.suffix.lower()
    overrides = {
        ".md": "text/markdown",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".html": "text/html",
        ".htm": "text/html",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return overrides.get(ext, _DEFAULT_MEDIA_TYPE)


def _parse_file_response(response: Any, *, purpose: str = "document", media_type: str = "") -> FileRef:
    """Parse an API file object into a FileRef."""
    if isinstance(response, dict):
        return FileRef(
            id=response.get("id", ""),
            filename=response.get("filename", ""),
            bytes=response.get("size", response.get("bytes", 0)),
            created_at=response.get("created_at", 0),
            media_type=response.get("media_type", media_type),
            purpose=response.get("purpose", purpose),
        )
    return FileRef(
        id=getattr(response, "id", ""),
        filename=getattr(response, "filename", ""),
        bytes=getattr(response, "size", getattr(response, "bytes", 0)),
        created_at=getattr(response, "created_at", 0),
        media_type=getattr(response, "media_type", media_type),
        purpose=getattr(response, "purpose", purpose),
    )
