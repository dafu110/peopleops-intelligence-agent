import json
import shutil
from functools import lru_cache
from typing import Dict, List, Tuple
from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document

from .audit import write_audit_event
from .config import get_chat_model, get_settings


def _source_label(doc: Document) -> str:
    settings = get_settings()
    page_num = int(doc.metadata.get("page", 0)) + 1
    return f"《{settings.policy_pdf_path.name}》第 {page_num} 页"


def _current_manifest() -> Dict[str, object]:
    settings = get_settings()
    stat = settings.policy_pdf_path.stat()
    return {
        "policy_pdf_path": str(settings.policy_pdf_path),
        "policy_pdf_size": stat.st_size,
        "policy_pdf_mtime": stat.st_mtime,
        "embedding_model": settings.embedding_model,
        "rag_chunk_size": settings.rag_chunk_size,
        "rag_chunk_overlap": settings.rag_chunk_overlap,
        "vector_backend": settings.vector_backend,
        "vector_store_url": settings.vector_store_url or "",
    }


def _read_manifest() -> Dict[str, object] | None:
    settings = get_settings()
    if not settings.rag_manifest_path.exists():
        return None
    try:
        return json.loads(settings.rag_manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_manifest(manifest: Dict[str, object]) -> None:
    settings = get_settings()
    settings.rag_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    settings.rag_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _has_persisted_index() -> bool:
    settings = get_settings()
    return settings.chroma_persist_dir.exists() and any(settings.chroma_persist_dir.iterdir())


def _index_is_current() -> bool:
    settings = get_settings()
    if not settings.policy_pdf_path.exists() or not _has_persisted_index():
        return False
    return _read_manifest() == _current_manifest()


def reset_rag_index() -> None:
    settings = get_settings()
    _build_retriever.cache_clear()
    if settings.chroma_persist_dir.exists():
        shutil.rmtree(settings.chroma_persist_dir)
    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)


def _load_policy_splits() -> list[Document]:
    try:
        from langchain_community.document_loaders import PyPDFLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ModuleNotFoundError as exc:
        raise RuntimeError("RAG indexing requires full backend dependencies. Install backend/requirements.txt.") from exc

    settings = get_settings()
    loader = PyPDFLoader(str(settings.policy_pdf_path))
    documents = loader.load()
    if not documents:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
    )
    return splitter.split_documents(documents)


def _qdrant_collection_name() -> str:
    settings = get_settings()
    return f"peopleops_policy_{uuid5(NAMESPACE_URL, str(settings.policy_pdf_path)).hex[:12]}"


class QdrantPolicyRetriever:
    def __init__(self, embeddings):
        settings = get_settings()
        if not settings.vector_store_url:
            raise RuntimeError("VECTOR_STORE_URL is required for VECTOR_BACKEND=qdrant.")

        from qdrant_client import QdrantClient
        from qdrant_client.http.exceptions import UnexpectedResponse
        from qdrant_client.http.models import Distance, PointStruct, VectorParams

        self.embeddings = embeddings
        self.collection_name = _qdrant_collection_name()
        self.client = QdrantClient(url=settings.vector_store_url)
        probe_vector = embeddings.embed_query("dimension probe")
        try:
            self.client.get_collection(self.collection_name)
        except UnexpectedResponse:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=len(probe_vector), distance=Distance.COSINE),
            )

        splits = _load_policy_splits()
        if splits:
            vectors = embeddings.embed_documents([doc.page_content for doc in splits])
            points = []
            for index, (doc, vector) in enumerate(zip(splits, vectors), start=1):
                point_key = f"{settings.policy_pdf_path}:{doc.metadata.get('page', 0)}:{index}:{doc.page_content[:80]}"
                points.append(
                    PointStruct(
                        id=uuid5(NAMESPACE_URL, point_key).hex,
                        vector=vector,
                        payload={"page_content": doc.page_content, "metadata": doc.metadata},
                    )
                )
            self.client.upsert(collection_name=self.collection_name, points=points)
        _write_manifest(_current_manifest())
        write_audit_event(
            "rag.qdrant_index_upserted",
            {
                "collection_name": self.collection_name,
                "chunk_count": len(splits),
                "vector_store_url": settings.vector_store_url,
            },
        )

    def invoke(self, question: str) -> list[Document]:
        settings = get_settings()
        query_vector = self.embeddings.embed_query(question)
        hits = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=settings.rag_top_k,
        ).points
        return [
            Document(
                page_content=str((hit.payload or {}).get("page_content", "")),
                metadata=dict((hit.payload or {}).get("metadata") or {}),
            )
            for hit in hits
        ]


@lru_cache(maxsize=1)
def _build_retriever():
    settings = get_settings()
    if not settings.policy_pdf_path.exists():
        return None

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ModuleNotFoundError as exc:
        raise RuntimeError("RAG embeddings require full backend dependencies. Install backend/requirements.txt.") from exc

    embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)

    if settings.vector_backend == "qdrant":
        return QdrantPolicyRetriever(embeddings)

    if _index_is_current():
        try:
            from langchain_community.vectorstores import Chroma
        except ModuleNotFoundError as exc:
            raise RuntimeError("Chroma retrieval requires full backend dependencies. Install backend/requirements.txt.") from exc
        vectorstore = Chroma(
            persist_directory=str(settings.chroma_persist_dir),
            embedding_function=embeddings,
        )
    else:
        reset_rag_index()
        splits = _load_policy_splits()
        if not splits:
            return None
        try:
            from langchain_community.vectorstores import Chroma
        except ModuleNotFoundError as exc:
            raise RuntimeError("Chroma retrieval requires full backend dependencies. Install backend/requirements.txt.") from exc
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embeddings,
            persist_directory=str(settings.chroma_persist_dir),
        )
        vectorstore.persist()
        _write_manifest(_current_manifest())
        write_audit_event(
            "rag.index_rebuilt",
            {
                "policy_pdf_path": str(settings.policy_pdf_path),
                "chunk_count": len(splits),
                "persist_directory": str(settings.chroma_persist_dir),
            },
        )

    return vectorstore.as_retriever(search_kwargs={"k": settings.rag_top_k})


def retrieve_policy_context(question: str) -> Tuple[str, List[str]]:
    retriever = _build_retriever()
    if retriever is None:
        settings = get_settings()
        raise FileNotFoundError(f"未找到企业知识库文件：{settings.policy_pdf_path}")

    docs = retriever.invoke(question)
    if not docs:
        return "", []

    context_parts = []
    sources = []
    for index, doc in enumerate(docs, start=1):
        context_parts.append(f"[片段{index} | {_source_label(doc)}]\n{doc.page_content}")
        sources.append(_source_label(doc))

    return "\n\n".join(context_parts), sorted(set(sources))


def retrieve_policy_evidence(question: str) -> List[Dict[str, str]]:
    retriever = _build_retriever()
    if retriever is None:
        return []

    docs = retriever.invoke(question)
    evidence = []
    for doc in docs:
        snippet = " ".join(doc.page_content.split())
        evidence.append(
            {
                "source": _source_label(doc),
                "snippet": snippet[:500],
            }
        )
    return evidence


def ask_rag_with_evidence(question: str) -> Dict[str, object]:
    try:
        from langchain_core.prompts import ChatPromptTemplate

        context_text, sources = retrieve_policy_context(question)
        if not context_text:
            write_audit_event("rag.no_context", {"question": question})
            return {
                "reply": "未在企业知识库中检索到相关内容，请补充制度文档后再试。",
                "sources": [],
                "evidence": [],
            }

        llm = get_chat_model(temperature=0.1)
        template = """你是一个严谨的企业 HRBP 助手。请完全基于【参考文档】回答员工问题。
如果参考文档没有相关信息，请明确说明“文档中未找到相关规定”，不要编造。

【参考文档】
{context}

【员工问题】
{question}
"""
        prompt = ChatPromptTemplate.from_template(template).format(
            context=context_text,
            question=question,
        )
        response = llm.invoke(prompt)

        write_audit_event(
            "rag.answer",
            {
                "question": question,
                "sources": sources,
                "persist_directory": str(get_settings().chroma_persist_dir),
            },
        )

        sources_markdown = "\n".join([f"- {source}" for source in sources])
        return {
            "reply": f"""{response.content}

---
#### 参考依据
{sources_markdown}
""",
            "sources": sources,
            "evidence": retrieve_policy_evidence(question),
        }
    except Exception as exc:
        write_audit_event("rag.error", {"question": question, "error": str(exc)})
        return {
            "reply": f"企业知识库检索失败：{exc}",
            "sources": [],
            "evidence": [],
        }


def ask_rag(question: str) -> str:
    return str(ask_rag_with_evidence(question)["reply"])
