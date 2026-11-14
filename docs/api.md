# API reference

Interactive OpenAPI docs are available at `/docs` when the service is
running locally.

## Health

`GET /health`

Returns a basic application health response. It does not currently
check Weaviate or the SQL database.

## Create an organization

`POST /api/v1/organizations`

JSON body:

```json
{ "name": "Research Team" }
```

Returns the organization ID and name.

## Upload a PDF

`POST /api/v1/assets/pdf`

Multipart form fields:

- `organization_id`: existing organization ID.
- `title`: optional display title.
- `file`: PDF file.

The API stores the file, creates an asset, indexes its chunks, and
returns the asset record. The current endpoint processes synchronously.

## Upload a video transcript

`POST /api/v1/assets/video-transcript`

Multipart form fields:

- `organization_id`: existing organization ID.
- `title`: optional display title.
- `file`: WebVTT `.vtt` transcript.

This creates a video asset and indexes the transcript. It does not
upload or transcode the actual video.

## Chat with an asset

`POST /api/v1/assets/{asset_id}/chats`

JSON body:

```json
{
  "organization_id": "organization-uuid",
  "user_id": "user-123",
  "query": "Summarize the main ideas",
  "chat_id": null
}
```

Set `chat_id` to continue an existing conversation. The response
contains `chat_id`, `answer`, and a list of citations.

## Read chat history

`GET /api/v1/chats/{chat_id}/messages?organization_id=...&user_id=...`

Returns the messages and citations for that user's conversation.

## Security note

The POC accepts organization and user IDs as request values. They are
used for data scoping but do not prove identity. Add authentication,
authorization, rate limiting, and request-size controls before exposing
the API to untrusted clients.
