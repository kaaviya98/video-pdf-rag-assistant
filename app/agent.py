from typing import Any

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.vector_store import get_vector_store


def _format_documents(documents: list[Any]) -> str:
    return "\n\n".join(
        f"{doc.page_content}\nSOURCE: {doc.metadata}" for doc in documents
    )


def build_asset_agent(asset: Any) -> AgentExecutor:
    settings = get_settings()
    llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0)
    collection = settings.pdf_collection if asset.asset_type == "pdf" else settings.video_collection
    source_type = asset.asset_type

    @tool
    def retrieve_from_pdf(query: str, pages: list[int] | None = None, k: int = 8) -> str:
        """Search the PDF for the user's question. Pass pages only when the user explicitly names page numbers."""
        filters: dict[str, Any] = {
            "asset_id": asset.id,
            "organization_id": asset.organization_id,
        }
        if pages:
            filters["page"] = {"$in": pages}
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
        """Search the video transcript. Use timestamp for a point in time or start_timestamp/end_timestamp for a range. Set is_full_video_question for whole-video questions."""
        if timestamp is not None or start_timestamp is not None or end_timestamp is not None:
            # Exact time-window retrieval is performed against timestamp metadata.
            filters: dict[str, Any] = {
                "asset_id": asset.id,
                "organization_id": asset.organization_id,
            }
            if timestamp is not None:
                filters["start_sec"] = {"$lte": timestamp}
                filters["end_sec"] = {"$gte": timestamp}
            else:
                if start_timestamp is not None:
                    filters["end_sec"] = {"$gte": start_timestamp}
                if end_timestamp is not None:
                    filters["start_sec"] = {"$lte": end_timestamp}
            docs = get_vector_store(settings.video_collection).similarity_search(
                query or "transcript", k=max(1, min(k, 30)), filters=filters
            )
            if docs:
                return _format_documents(docs)
        retriever = get_vector_store(settings.video_collection).as_retriever(
            search_kwargs={
                "k": max(1, min(k, 30)),
                "filters": {"asset_id": asset.id, "organization_id": asset.organization_id},
            }
        )
        return _format_documents(retriever.invoke(query))

    tools = [retrieve_from_pdf] if source_type == "pdf" else [retrieve_from_transcript]
    system_prompt = (
        "You are a helpful assistant grounded in the user's source material. "
        "For factual questions, call the available retrieval tool before answering. "
        "Do not invent facts absent from the retrieved content. "
        "Cite PDF page numbers or video timestamps in the answer. "
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
    return AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=5)
