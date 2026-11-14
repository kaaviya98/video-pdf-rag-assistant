# Chat API

`POST /api/v1/chat`

Request JSON fields: `asset_id` (UUID), `query` (string), `conversation_id` (string). The endpoint loads the Asset with Django ORM, invokes the original LangChain tool-calling agent, and uses Redis-backed chat history. Response fields: `asset_id`, `conversation_id`, `answer`.

Conversation history is isolated by both asset UUID and conversation ID, so reusing a conversation ID for another asset does not mix contexts. Requests for assets that are not yet marked completed return HTTP 409.
