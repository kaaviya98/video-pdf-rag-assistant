# Agent and chat flow

The FastAPI chat endpoint loads an Asset through Django ORM and delegates to the chat service. The service initializes the asset-specific chat model, creates the original LangChain tool-calling agent, and invokes it through RunnableWithMessageHistory backed by Redis.

For PDF assets, the agent receives the PDF retrieval tool, which uses the Weaviate PDF collection and asset/page filters. For video/audio transcript assets, it receives the transcript retrieval tool, which supports timestamp lookup, full-video notes, and Weaviate retrieval. The agent selects the tool and determines retrieval scope from the user question. Quiz tools and quiz prompts are excluded.
