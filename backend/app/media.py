from pathlib import Path
from typing import Iterator
from uuid import UUID

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse


def safe_media_path(data_dir: Path, video_id: UUID, filename: str) -> Path:
    root = data_dir.resolve()
    job_dir = (data_dir / str(video_id)).resolve()
    path = (job_dir / filename).resolve()
    if not job_dir.is_relative_to(root) or path.parent != job_dir or not path.is_relative_to(job_dir):
        raise HTTPException(status_code=404, detail="media not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="media not found")
    return path


def _read_range(path: Path, start: int, end: int, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as stream:
        stream.seek(start)
        while remaining:
            chunk = stream.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def media_response(request: Request, path: Path, media_type: str):
    size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type=media_type, headers={"Accept-Ranges": "bytes"})

    if not range_header.startswith("bytes=") or "," in range_header:
        raise HTTPException(status_code=416, detail="invalid range", headers={"Content-Range": f"bytes */{size}"})
    value = range_header[6:]
    start_text, _, end_text = value.partition("-")
    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
        else:
            suffix = int(end_text)
            start = max(0, size - suffix)
            end = size - 1
    except ValueError as exc:
        raise HTTPException(status_code=416, detail="invalid range", headers={"Content-Range": f"bytes */{size}"}) from exc
    if start < 0 or start >= size or end < start:
        raise HTTPException(status_code=416, detail="invalid range", headers={"Content-Range": f"bytes */{size}"})
    end = min(end, size - 1)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Content-Length": str(end - start + 1),
    }
    return StreamingResponse(_read_range(path, start, end), status_code=206, media_type=media_type, headers=headers)
