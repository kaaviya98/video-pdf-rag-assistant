from typing import Any

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from weaviate.classes.query import Filter

from app.config import get_settings
from app.vector_store import get_vector_store


def _format_documents(documents: list[Any]) -> str:
    return "\n\n".join(
        f"{doc.page_content}\nSOURCE: {doc.metadata}" for doc in documents
    )


def _asset_filter(asset: Any):
    return (
        Filter.by_property("asset_id").equal(asset.id)
        & Filter.by_property("organization_id").equal(asset.organization_id)
    )


def build_asset_agent(asset: Any) -> AgentExecutor:
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )

    @tool
    def retrieve_from_pdf(
        query: str,
        pages: list[int] | None = None,
        k: int = 8,
    ) -> str:
        """Search this PDF. Use pages only when the user explicitly names page numbers."""
        filters = _asset_filter(asset)
        if pages:
            filters = filters & Filter.by_property("page").contains_any(pages)
        retriever = get_vector_store(settings.pdf_collection).as_retriever(
            search_kwargs={"k": max(1, min(k, 30)), "filters": filters}
        )
        return _format_documents(retriever.invoke(query))

    @tool
    def retrieve_from_transcript(
        query: str,
        timestamp: float | None = None,
        start_timestamp: float | None = None,
        end_timestamp: float | None = None,
        k: int = 10,
        is_full_video_question: bool = False,
    ) -> str:
        """Search this video's transcript by topic or time. Use timestamp for a point in time, start_timestamp/end_timestamp for a range, and is_full_video_question for a whole-video question."""
        vector_store = get_vector_store(settings.video_collection)
        filters = _asset_filter(asset)

        if is_full_video_question:
            from pathlib import Path
            import webvtt

            captions = webvtt.read(str(Path(asset.source_path)))
            transcript = [
                f"[{cue.start} - {cue.end}] {' '.join((cue.text or '').split())}"
                for cue in captions
                if (cue.text or '').strip()
            ]
            if transcript:
                return "\n".join(transcript)

        if timestamp is not None:
            filters = (
                filters
                & Filter.by_property("start_sec").less_or_equal(timestamp)
                & Filter.by_property("end_sec").greater_or_equal(timestamp)
            )
        else:
            if start_timestamp is not None:
                filters = filters & Filter.by_property("end_sec").greater_or_equal(start_timestamp)
            if end_timestamp is not None:
                filters = filters & Filter.by_property("start_sec").less_or_equal(end_timestamp)

        retriever = vector_store.as_retriever(
            search_kwargs={"k": max(1, min(k, 30)), "filters": filters}
        )
        return _format_documents(retriever.invoke(query or "video transcript"))

    tools = [retrieve_from_pdf] if asset.asset_type == "pdf" else [retrieve_from_transcript]
    system_prompt = (
        "You are a helpful assistant grounded in the user's source material. "
        "For factual questions, call the available retrieval tool before answering. "
        "Do not invent facts absent from the retrieved content. Cite PDF page "
        "numbers or video timestamps from the retrieved SOURCE metadata. "
        "For greetings, respond naturally without retrieval. If retrieval returns "
        "no relevant content, say you could not find the answer in this source."
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        max_iterations=5,
        return_intermediate_steps=True,
    )
