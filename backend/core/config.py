from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_name: str
    api_key: Optional[str]
    api_base: Optional[str]
    chat_model: str
    embedding_model: str
    policy_pdf_path: Path
    chroma_persist_dir: Path
    rag_manifest_path: Path
    db_path: Path
    audit_log_path: Path
    email_draft_dir: Path
    calendar_dir: Path
    ats_export_dir: Path
    access_password: Optional[str]
    enterprise_mode: bool
    require_access_password: bool
    access_password_min_length: int
    tool_execution_mode: str
    rag_chunk_size: int
    rag_chunk_overlap: int
    rag_top_k: int
    audit_log_max_bytes: int
    audit_hash_chain_enabled: bool
    api_rate_limit_per_minute: int
    smtp_host: Optional[str]
    smtp_port: int
    smtp_username: Optional[str]
    smtp_password: Optional[str]
    smtp_from: str
    smtp_use_tls: bool
    default_tenant_id: str
    default_org_id: str
    default_department_id: str
    database_backend: str
    database_url: Optional[str]
    vector_backend: str
    vector_store_url: Optional[str]
    object_storage_uri: Optional[str]
    approval_required_actions: tuple[str, ...]
    configured_connector_env: tuple[str, ...]
    tool_default_timeout_seconds: float
    tool_default_retries: int
    trusted_sso_enabled: bool
    trusted_sso_user_header: str
    trusted_sso_role_header: str
    oidc_enabled: bool
    oidc_issuer: Optional[str]
    oidc_audience: Optional[str]
    oidc_jwks_url: Optional[str]
    oidc_hs256_secret: Optional[str]
    oidc_role_claim: str
    oidc_default_role: str
    rag_min_pass_rate: float
    rag_min_keyword_coverage: float
    rag_min_citation_correctness: float

    @property
    def has_llm_config(self) -> bool:
        return bool(self.api_key and self.api_base)


def _path_env(name: str, default: str) -> Path:
    import os

    value = Path(os.getenv(name, default))
    if value.is_absolute():
        return value
    return ROOT_DIR / value


def _int_env(name: str, default: int) -> int:
    import os

    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    import os

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def enterprise_warnings(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    warnings: list[str] = []
    if settings.require_access_password and not settings.access_password:
        warnings.append("ACCESS_PASSWORD is required when REQUIRE_ACCESS_PASSWORD is enabled.")
    if settings.access_password and settings.access_password.startswith("sha256:"):
        warnings.append("ACCESS_PASSWORD uses legacy sha256 hashing; prefer pbkdf2_sha256.")
    if settings.access_password and not settings.access_password.startswith(("pbkdf2_sha256$", "sha256:")):
        if len(settings.access_password) < settings.access_password_min_length:
            warnings.append("ACCESS_PASSWORD is shorter than ACCESS_PASSWORD_MIN_LENGTH.")
        warnings.append("ACCESS_PASSWORD is configured as plain text; prefer pbkdf2_sha256.")
    if settings.enterprise_mode and settings.tool_execution_mode == "live" and not settings.smtp_host:
        warnings.append("SMTP_HOST should be configured before enabling live tool execution.")
    if settings.enterprise_mode and not settings.audit_hash_chain_enabled:
        warnings.append("AUDIT_HASH_CHAIN_ENABLED should stay enabled in enterprise mode.")
    if settings.enterprise_mode and settings.api_rate_limit_per_minute <= 0:
        warnings.append("API_RATE_LIMIT_PER_MINUTE should be enabled in enterprise mode.")
    if settings.enterprise_mode and settings.default_tenant_id == "default":
        warnings.append("DEFAULT_TENANT_ID should be set to a real tenant slug in enterprise mode.")
    if settings.enterprise_mode and not settings.trusted_sso_enabled:
        if not settings.oidc_enabled:
            warnings.append("TRUSTED_SSO_ENABLED or OIDC_ENABLED should be enabled for production identity.")
    if settings.enterprise_mode and settings.database_backend == "sqlite":
        warnings.append("DATABASE_BACKEND=sqlite is for reference deployments; use PostgreSQL for production.")
    if settings.database_backend not in {"sqlite", "postgresql"}:
        warnings.append("DATABASE_BACKEND must be sqlite or postgresql in this build.")
    if settings.enterprise_mode and settings.database_backend != "sqlite" and not settings.database_url:
        warnings.append("DATABASE_URL is required when DATABASE_BACKEND is not sqlite.")
    if settings.enterprise_mode and settings.vector_backend == "chroma":
        warnings.append("VECTOR_BACKEND=chroma is local-only; use pgvector, Qdrant, Milvus, or managed search for production.")
    if settings.vector_backend not in {"chroma", "qdrant"}:
        warnings.append("VECTOR_BACKEND must be chroma or qdrant in this build.")
    if settings.enterprise_mode and settings.vector_backend != "chroma" and not settings.vector_store_url:
        warnings.append("VECTOR_STORE_URL is required when VECTOR_BACKEND is not chroma.")
    if settings.enterprise_mode and not settings.object_storage_uri:
        warnings.append("OBJECT_STORAGE_URI should point to S3, MinIO, OSS, or another managed object store in enterprise mode.")
    return warnings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    import os

    load_dotenv(ROOT_DIR / ".env")
    enterprise_mode = _bool_env("ENTERPRISE_MODE", False)

    return Settings(
        app_name=os.getenv("APP_NAME", "PeopleOps Intelligence Agent"),
        api_key=os.getenv("OPENAI_API_KEY"),
        api_base=os.getenv("OPENAI_API_BASE"),
        chat_model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
        policy_pdf_path=_path_env("HR_POLICY_PDF", "data/\u5458\u5de5\u624b\u518c\u6d4b\u8bd5\u7248.pdf"),
        chroma_persist_dir=_path_env("CHROMA_PERSIST_DIR", "var/chroma/policy"),
        rag_manifest_path=_path_env("RAG_MANIFEST_PATH", "var/chroma/policy/manifest.json"),
        db_path=_path_env("APP_DB_PATH", "var/runtime/peopleops.sqlite3"),
        audit_log_path=_path_env("AUDIT_LOG_PATH", "var/runtime/audit/events.jsonl"),
        email_draft_dir=_path_env("EMAIL_DRAFT_DIR", "var/runtime/email_drafts"),
        calendar_dir=_path_env("CALENDAR_DIR", "var/runtime/calendar"),
        ats_export_dir=_path_env("ATS_EXPORT_DIR", "var/runtime/ats_exports"),
        access_password=os.getenv("ACCESS_PASSWORD"),
        enterprise_mode=enterprise_mode,
        require_access_password=_bool_env("REQUIRE_ACCESS_PASSWORD", enterprise_mode),
        access_password_min_length=_int_env("ACCESS_PASSWORD_MIN_LENGTH", 12),
        tool_execution_mode=os.getenv("TOOL_EXECUTION_MODE", "local").strip().lower(),
        rag_chunk_size=_int_env("RAG_CHUNK_SIZE", 400),
        rag_chunk_overlap=_int_env("RAG_CHUNK_OVERLAP", 40),
        rag_top_k=_int_env("RAG_TOP_K", 3),
        audit_log_max_bytes=_int_env("AUDIT_LOG_MAX_BYTES", 5_000_000),
        audit_hash_chain_enabled=_bool_env("AUDIT_HASH_CHAIN_ENABLED", True),
        api_rate_limit_per_minute=_int_env("API_RATE_LIMIT_PER_MINUTE", 120),
        smtp_host=os.getenv("SMTP_HOST"),
        smtp_port=_int_env("SMTP_PORT", 587),
        smtp_username=os.getenv("SMTP_USERNAME"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        smtp_from=os.getenv("SMTP_FROM", "hr@example.com"),
        smtp_use_tls=_bool_env("SMTP_USE_TLS", True),
        default_tenant_id=os.getenv("DEFAULT_TENANT_ID", "default").strip() or "default",
        default_org_id=os.getenv("DEFAULT_ORG_ID", "default-org").strip() or "default-org",
        default_department_id=os.getenv("DEFAULT_DEPARTMENT_ID", "peopleops").strip() or "peopleops",
        database_backend=os.getenv("DATABASE_BACKEND", "sqlite").strip().lower(),
        database_url=os.getenv("DATABASE_URL"),
        vector_backend=os.getenv("VECTOR_BACKEND", "chroma").strip().lower(),
        vector_store_url=os.getenv("VECTOR_STORE_URL"),
        object_storage_uri=os.getenv("OBJECT_STORAGE_URI"),
        approval_required_actions=tuple(
            item.strip()
            for item in os.getenv("APPROVAL_REQUIRED_ACTIONS", "send_email,calendar_invite,ats_stage_change,offer_draft,rejection_draft").split(",")
            if item.strip()
        ),
        configured_connector_env=tuple(
            item.strip()
            for item in os.getenv("CONFIGURED_CONNECTOR_ENV", "").split(",")
            if item.strip()
        ),
        tool_default_timeout_seconds=float(os.getenv("TOOL_DEFAULT_TIMEOUT_SECONDS", "20")),
        tool_default_retries=_int_env("TOOL_DEFAULT_RETRIES", 1),
        trusted_sso_enabled=_bool_env("TRUSTED_SSO_ENABLED", False),
        trusted_sso_user_header=os.getenv("TRUSTED_SSO_USER_HEADER", "X-Authenticated-User"),
        trusted_sso_role_header=os.getenv("TRUSTED_SSO_ROLE_HEADER", "X-Authenticated-Role"),
        oidc_enabled=_bool_env("OIDC_ENABLED", False),
        oidc_issuer=os.getenv("OIDC_ISSUER"),
        oidc_audience=os.getenv("OIDC_AUDIENCE"),
        oidc_jwks_url=os.getenv("OIDC_JWKS_URL"),
        oidc_hs256_secret=os.getenv("OIDC_HS256_SECRET"),
        oidc_role_claim=os.getenv("OIDC_ROLE_CLAIM", "role"),
        oidc_default_role=os.getenv("OIDC_DEFAULT_ROLE", "viewer").strip().lower(),
        rag_min_pass_rate=float(os.getenv("RAG_MIN_PASS_RATE", "1.0")),
        rag_min_keyword_coverage=float(os.getenv("RAG_MIN_KEYWORD_COVERAGE", "0.5")),
        rag_min_citation_correctness=float(os.getenv("RAG_MIN_CITATION_CORRECTNESS", "0.8")),
    )


def get_chat_model(*, temperature: float = 0.0):
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.has_llm_config:
        raise RuntimeError("Missing OPENAI_API_KEY or OPENAI_API_BASE. Configure .env first.")

    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.api_key,
        base_url=settings.api_base,
        temperature=temperature,
    )
