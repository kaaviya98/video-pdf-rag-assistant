# Chat API

`POST /api/v1/chat`

Request JSON fields: `asset_id` (UUID), `query` (string), `conversation_id` (string). The endpoint loads the Asset with Django ORM, invokes the original LangChain tool-calling agent, and uses Redis-backed chat history. Response fields: `asset_id`, `conversation_id`, `answer`.
