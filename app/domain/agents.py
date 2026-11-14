import logging
from typing import Any

from django.conf import settings
from langchain.agents import AgentExecutor
from langchain.agents import create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from app.domain.transcript_line import get_transcript_for_line_numbers
from app.domain.transcript_line import get_transcript_for_timestamp
from app.domain.vector_db.base import VectorDBClient
from app.domain.video.notes import get_full_video_notes_text
from app.models.asset import Asset
from app.utils.agents import chat_agent_tools_and_system_message


def create_agent_executor(
    asset: Asset,
    llm: Any,
    vector_db_client: VectorDBClient,
    *,
    intent: str = "CHAT",
    user_id: str | None = None,
) -> AgentExecutor:
    @tool
    def retrieve_from_transcript(
        query: str = "",
        k: int = 12,
        timestamp: float | None = None,
        start_timestamp: float | None = None,
        end_timestamp: float | None = None,
        is_full_video_question: bool = False,
    ) -> str:
        """
        Retrieve information from the VIDEO transcript based on a query.

        MUST — is_full_video_question: True when the query is about the entire video (summary,
        overview, or whole-lecture scope). False when the query targets a specific topic, time, or
        detail. Decide from the user's intent; use True so the tool can use precomputed full notes when appropriate.

        CRITICAL: It is important to choose the 'k' parameter based on the query type:
        - For summary/overview questions: use k=15-25 (more documents needed)
        - For broad overview questions: use k=8-12
        - For specific details: use k=8-10
        - For comprehensive analysis: use k=20-25
        - For document summary: use k=20-25
        - Maximum allowed is k=25

        MUST: Decide whether to pass the time arguments based on the user's query:
        - If the query refers to a specific time in the video (e.g., "what did the teacher say at 35:07?",
          "around 1:05:30", "in the thirty fifth minute"), convert that time into seconds and pass it as
          the `timestamp` argument.
        - If the query refers to a time RANGE (e.g., "between 5 and 7 minutes", "from 10:00 to 10:30"),
          convert both endpoints into seconds and pass them as `start_timestamp` and `end_timestamp`.
        - If the query is general or summary-related, leave all time arguments as None (do not filter).
        - Do not guess — only apply a timestamp filter when it is explicitly mentioned or very clearly
          implied by the user's words.

        Args:
            query (str): The search query (optional if using a timestamp-only lookup). You MAY rewrite this for clarity before retrieval.
            is_full_video_question (bool): True if the query is about the entire video; False otherwise.
            timestamp (Optional[float]): A single timestamp (seconds) to focus on, or None.
            start_timestamp (Optional[float]): Interval start in seconds, or None.
            end_timestamp (Optional[float]): Interval end in seconds, or None.
            k (int): Number of relevant documents to retrieve (1-25). ALWAYS choose based on query scope.
        """
        try:
            if (
                start_timestamp is not None
                or end_timestamp is not None
                or timestamp is not None
            ):
                content = get_transcript_for_timestamp(
                    asset,
                    timestamp=float(timestamp) if timestamp is not None else None,
                    period_start=float(start_timestamp)
                    if start_timestamp is not None
                    else None,
                    period_end=float(end_timestamp)
                    if end_timestamp is not None
                    else None,
                )
                if content.strip():
                    return content

            if is_full_video_question:
                notes_text = get_full_video_notes_text(asset)
                if notes_text:
                    return notes_text

            retriever = vector_db_client.get_retriever(
                scope_key=asset.scope_key,
                collection_name=settings.VECTOR_DB_VIDEO_COLLECTION_NAME,
                organization=asset.organization if asset.organization_id else None,
                score_threshold=0.01,
                k=k,
                filters={"asset_id": str(asset.id)},
            )
            docs = retriever.invoke(query)
            line_numbers: set[int] = set()
            for doc in docs:
                nums = doc.metadata.get("transcript_line_numbers") or []
                try:
                    line_numbers.update(int(n) for n in nums)
                except Exception:
                    pass

            if line_numbers:
                return get_transcript_for_line_numbers(asset, line_numbers)
            return "\n\n".join(doc.page_content for doc in docs)

        except Exception as e:  # pragma: no cover - defensive
            return f"Error retrieving information: {e}"

    @tool
    def retrieve_from_pdf(
        query: str,
        pages: list[int] | None = None,
        k: int = 50,
    ) -> str:
        """
        Retrieve information from the PDF document based on a query.
        CRITICAL: It is important to choose the 'k' parameter based on the query type:
        - For summary/overview questions: use k=15-25 (more documents needed)
        - For broad overview questions: use k=8-12
        - For specific details: use k=8-10
        - For comprehensive analysis: use k=20-50
        - For document summary: use k=20-50
        - Maximum allowed is k=50

        MUST: Decide whether to pass the 'pages' argument based on the user's query:
        - If the query refers to a specific page or pages, pass them as a list (e.g., pages=[9])
        - If the query is general or summary-related, leave 'pages' as None (do not filter)
        - Do not guess — only apply a page filter when it is explicitly mentioned or implied in the query
        Args:
            query (str): The search query.
            pages (Optional[list[int]]): List of page numbers to filter by, or None for no page filter.
            k (int): Number of relevant documents to retrieve (1-50). ALWAYS choose based on query scope.
        """
        try:
            filters = {"asset_id": str(asset.id)}
            if pages:
                adjusted_pages = [p - 1 for p in pages if p > 0]
                filters["pages"] = {"$containsAny": adjusted_pages}
            retriever = vector_db_client.get_multi_query_retriever(
                scope_key=asset.scope_key,
                collection_name=settings.VECTOR_DB_PDF_COLLECTION_NAME,
                llm=llm,
                organization=asset.organization if asset.organization_id else None,
                k=k,
                filters=filters,
            )
            docs = retriever.get_relevant_documents(query)
            return "\n\n".join(doc.page_content for doc in docs)

        except Exception as e:
            return f"Error retrieving information: {e}"

    tools, system_message = chat_agent_tools_and_system_message(
        asset,
        retrieve_from_pdf,
        retrieve_from_transcript,
        intent=intent,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_message),
            ("placeholder", "{chat_history}"),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ],
    )

    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    agent_executor.agent.stream_runnable = False
    return agent_executor
