# Project documentation

This documentation describes the standalone PDF and video transcript
chat service. It keeps the relevant ingestion, retrieval, agent, and
conversation concepts from the original implementation notes while
removing LMS-specific workflows and quiz functionality.

## Read in this order

1. [Architecture and code map](architecture.md) — end-to-end system design
   with direct links to the implementation files.
2. [PDF ingestion and retrieval](pdf-pipeline.md) — parsing, chunking,
   embeddings, vector storage, and page citations.
3. [Video transcript pipeline](video-pipeline.md) — WebVTT parsing,
   timestamp metadata, time-scoped retrieval, and whole-video context.
4. [Agent and chat lifecycle](agent-and-chat.md) — tool selection,
   LangChain AgentExecutor, memory/history, and response citations.
5. [API reference](api.md) — endpoints, request fields, and examples.
6. [Configuration and local setup](setup.md) — environment and services.
7. [Five-minute walkthrough](interview-walkthrough.md) — a code-first
   explanation sequence for a technical demo.

## Scope

Included: PDF chat, transcript-backed video chat, retrieval tools,
conversation history, vector search, organization/asset isolation,
and citations.

Not included: quizzes, LMS integrations, LMS authentication, LMS asset
identifiers, external LMS webhooks, or speech-to-text transcription.

## Source of truth

The implementation links in these pages point to files in this repository.
If a description and the code disagree, the code is authoritative.
