# Video pipeline

Video ingestion consumes a WebVTT captions file; it does not transcribe raw audio/video. The VTT parser normalizes and orders cues, then persists TranscriptLine rows through Django ORM. The transcript chunker groups lines into time windows, embeds those windows, detects adjacent topic boundaries using cosine-similarity valleys, merges short tails, and applies the configured character-based rechunking. Resulting documents retain asset, segment, timestamp, and transcript-line metadata before being stored in the Weaviate video collection.
