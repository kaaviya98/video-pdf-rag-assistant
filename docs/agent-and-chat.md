# Agent execution and chat lifecycle

## 1. Why an agent

A conventional RAG chain has a fixed sequence: retrieve, then generate.
Here, a tool-calling agent is used so the model can select a retrieval
tool and provide tool arguments based on the user's question.

The current agent is deliberately constrained: one asset is selected
for the request, and only the retrieval tool for that asset type is
registered.

## 2. Tool registration

[build_asset_agent()](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/agent.py)
creates a ChatOpenAI model and defines two tools:

### PDF tool — retrieve_from_pdf

- Input: query, optional page numbers, and result count.
- Searches the PDF collection.
- Filters by asset ID and organization ID.
- Optionally narrows retrieval to requested pages.

### Video tool — retrieve_from_transcript

- Input: query, optional timestamp/range, result count, and
  whole-video intent.
- Searches the video collection.
- Filters by asset ID and organization ID.
- Can return the full timestamped transcript for whole-video questions.

The agent registers only one tool for a given asset type. Quiz tools
and quiz prompts are intentionally excluded.

## 3. Prompt and executor

The system prompt tells the assistant to retrieve evidence before
answering factual questions, avoid inventing facts, cite the source
metadata, and respond naturally to greetings.

The code builds a ChatPromptTemplate with:

- System message: behavior and grounding rules.
- Chat history: recent user and assistant turns.
- Human message: current input.
- Agent scratchpad: intermediate tool reasoning/results managed by
  LangChain.

Then `create_tool_calling_agent()` combines the LLM, tools, and prompt.
`AgentExecutor` runs the tool-calling loop with a maximum of five
iterations.

Code: [app/agent.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/agent.py).

## 4. End-to-end chat lifecycle

1. The client sends the asset ID, organization ID, user ID, query, and
   optional chat ID.
2. The API confirms the asset is ready and belongs to the organization.
3. It finds or creates the conversation for that user and asset.
4. It loads the latest 12 messages.
5. The messages are converted into LangChain HumanMessage and AIMessage
   objects.
6. The agent is invoked with the current query and chat history.
7. Tool observations are used to derive structured citations.
8. User and assistant messages are persisted in SQL.
9. The API returns the answer, chat ID, and citations.

Code: [chat_with_asset()](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/main.py).

## 5. Conversation memory

Conversation history is persisted in the relational database, not held
only in process memory. On each request, the API fetches up to 12
previous messages for that conversation and passes them to the agent.
This provides multi-turn context across requests and application
restarts.

The current POC does not yet implement token-budget-aware summarization,
Redis-backed short-term memory, or streaming generation.

## 6. Citation flow

The retrieval tools return source metadata with each chunk. The agent
receives that tool output and produces a final answer. The API inspects
the agent's intermediate tool observations and extracts page or
timestamp metadata into the response's citations array.

This separates citation extraction from free-form prose. Integration
tests should verify the metadata format returned by the configured
Weaviate/LangChain versions.
