# Video transcript ingestion and retrieval

## 1. Scope

The current service supports video chat through a WebVTT (`.vtt`)
transcript. It does not accept a raw video file, extract audio, or run
speech-to-text transcription. The client or an upstream process must
provide captions.

## 2. Ingestion workflow

```text
WebVTT upload
    |
    v
FastAPI validates .vtt
    |
    v
WebVTT parser reads caption cues
    |
    v
Sort cues chronologically
    |
    v
Normalize whitespace
    |
    v
Chunk cue text
    |
    v
Attach asset, organization, and time metadata
    |
    v
Embed and index in Weaviate video collection
```

Implementation: [ingest_vtt()](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/ingestion.py).

## 3. Timestamp metadata

Each indexed transcript chunk stores:

- `source_type`: `video`.
- `start_sec`: cue start time in seconds.
- `end_sec`: cue end time in seconds.
- `asset_id`: video asset identifier.
- `organization_id`: organization scope.

This metadata allows retrieval to be constrained to a specific video
and, where supplied, a time point or interval.

## 4. Agent retrieval behavior

The `retrieve_from_transcript` tool supports:

- Topic-based semantic retrieval.
- A single `timestamp` for a point in the video.
- `start_timestamp` and `end_timestamp` for a time range.
- `is_full_video_question` for whole-video questions.

For whole-video questions, the current implementation reads the VTT
file and returns the transcript cues with their time ranges as context.
For other questions it performs vector retrieval with asset and
organization filters, adding time filters when requested.

Implementation: [retrieve_from_transcript()](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/agent.py).

## 5. What to say in a demo

"The video is represented by its timestamped transcript. During
ingestion, every chunk keeps the cue's start and end time. At query
time, the agent can retrieve by semantic similarity or narrow the
search to a timestamp or time interval. That lets the answer point back
to a location in the source video."

Do not describe this as direct video understanding or speech
transcription: neither is implemented in this POC.
