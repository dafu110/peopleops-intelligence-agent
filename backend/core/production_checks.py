from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

from .config import Settings, get_settings
from .connectors import connector_inventory


CheckStatus = Literal["not_configured", "configured", "verified", "failed"]


@dataclass(frozen=True)
class ProductionCheck:
    id: str
    label: str
    status: CheckStatus
    verification: str
    detail: str
    next_step: str
    latency_ms: int | None = None


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _configured(status: bool, detail: str, next_step: str) -> ProductionCheck:
    return ProductionCheck(
        id="",
        label="",
        status="configured" if status else "not_configured",
        verification="configuration",
        detail=detail,
        next_step=next_step,
    )


def _postgres_check(settings: Settings, *, live: bool) -> ProductionCheck:
    if settings.database_backend != "postgresql" or not settings.database_url:
        return ProductionCheck(
            id="postgresql",
            label="PostgreSQL 实例建库、迁移、读写回放",
            status="not_configured",
            verification="configuration",
            detail=f"DATABASE_BACKEND={settings.database_backend}; DATABASE_URL configured={bool(settings.database_url)}",
            next_step="设置 DATABASE_BACKEND=postgresql 与 DATABASE_URL，并运行迁移/读写回放。",
        )
    if not live:
        return ProductionCheck(
            id="postgresql",
            label="PostgreSQL 实例建库、迁移、读写回放",
            status="configured",
            verification="configuration",
            detail="PostgreSQL URL 已配置，但尚未执行 live=true 连通性验证。",
            next_step="调用 /production/checks?live=true 执行 SELECT 1 只读验证。",
        )
    start = time.perf_counter()
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return ProductionCheck(
            id="postgresql",
            label="PostgreSQL 实例建库、迁移、读写回放",
            status="verified",
            verification="live_select_1",
            detail="PostgreSQL 连接和只读查询通过。",
            next_step="继续执行迁移脚本和任务/审批/审计读写回放。",
            latency_ms=_elapsed_ms(start),
        )
    except Exception as exc:
        return ProductionCheck(
            id="postgresql",
            label="PostgreSQL 实例建库、迁移、读写回放",
            status="failed",
            verification="live_select_1",
            detail=f"{exc.__class__.__name__}: {exc}",
            next_step="检查 DATABASE_URL、网络、防火墙、凭证和数据库 schema 权限。",
            latency_ms=_elapsed_ms(start),
        )


def _qdrant_check(settings: Settings, *, live: bool) -> ProductionCheck:
    if settings.vector_backend != "qdrant" or not settings.vector_store_url:
        return ProductionCheck(
            id="qdrant",
            label="Qdrant 或生产向量库索引写入/检索",
            status="not_configured",
            verification="configuration",
            detail=f"VECTOR_BACKEND={settings.vector_backend}; VECTOR_STORE_URL configured={bool(settings.vector_store_url)}",
            next_step="设置 VECTOR_BACKEND=qdrant 与 VECTOR_STORE_URL，并执行索引写入/检索回放。",
        )
    if not live:
        return ProductionCheck(
            id="qdrant",
            label="Qdrant 或生产向量库索引写入/检索",
            status="configured",
            verification="configuration",
            detail="Qdrant URL 已配置，但尚未执行 live=true HTTP 验证。",
            next_step="调用 /production/checks?live=true 读取 /collections，再跑真实 RAG eval。",
        )
    start = time.perf_counter()
    try:
        url = settings.vector_store_url.rstrip("/") + "/collections"
        with urllib.request.urlopen(url, timeout=4) as response:
            ok = 200 <= response.status < 300
        return ProductionCheck(
            id="qdrant",
            label="Qdrant 或生产向量库索引写入/检索",
            status="verified" if ok else "failed",
            verification="live_http_collections",
            detail=f"Qdrant /collections HTTP status={response.status}",
            next_step="继续执行索引写入、检索召回和引用正确率 eval。",
            latency_ms=_elapsed_ms(start),
        )
    except Exception as exc:
        return ProductionCheck(
            id="qdrant",
            label="Qdrant 或生产向量库索引写入/检索",
            status="failed",
            verification="live_http_collections",
            detail=f"{exc.__class__.__name__}: {exc}",
            next_step="检查 VECTOR_STORE_URL、网络、服务健康和 collection 初始化。",
            latency_ms=_elapsed_ms(start),
        )


def _object_storage_check(settings: Settings, *, live: bool) -> ProductionCheck:
    if not settings.object_storage_uri:
        return ProductionCheck(
            id="object_storage",
            label="S3/MinIO 对象上传、下载、权限、生命周期",
            status="not_configured",
            verification="configuration",
            detail="OBJECT_STORAGE_URI is not configured.",
            next_step="配置 S3/MinIO/OSS URI、凭证、bucket 权限和生命周期策略。",
        )
    parsed = urlparse(settings.object_storage_uri)
    return ProductionCheck(
        id="object_storage",
        label="S3/MinIO 对象上传、下载、权限、生命周期",
        status="configured",
        verification="configuration" if not live else "configuration_only",
        detail=f"{parsed.scheme or 'storage'}://{parsed.netloc or parsed.path.split('/')[0]} 已配置；当前构建未内置对象存储 SDK 写读探针。",
        next_step="用部署环境的 S3/MinIO SDK 执行 put/get/delete 和权限/生命周期验证。",
    )


def _oidc_check(settings: Settings, *, live: bool) -> ProductionCheck:
    if not settings.oidc_enabled:
        return ProductionCheck(
            id="oidc",
            label="OIDC provider 真实 token 校验和角色映射",
            status="not_configured",
            verification="configuration",
            detail="OIDC_ENABLED=false.",
            next_step="配置 OIDC_ISSUER、OIDC_AUDIENCE、OIDC_JWKS_URL 和角色 claim。",
        )
    required = [settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url or settings.oidc_hs256_secret]
    if not all(required):
        return ProductionCheck(
            id="oidc",
            label="OIDC provider 真实 token 校验和角色映射",
            status="failed",
            verification="configuration",
            detail="OIDC 已启用，但 issuer/audience/JWKS 或 HS256 secret 不完整。",
            next_step="补齐 OIDC 配置，并用真实 bearer token 调用 /me 验证角色映射。",
        )
    if not live:
        return ProductionCheck(
            id="oidc",
            label="OIDC provider 真实 token 校验和角色映射",
            status="configured",
            verification="configuration",
            detail="OIDC 参数已配置；后端不能自行生成真实用户 token。",
            next_step="使用真实 provider token 调用 /me，验证 username、role、tenant scope。",
        )
    if settings.oidc_jwks_url:
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(settings.oidc_jwks_url, timeout=4) as response:
                ok = 200 <= response.status < 300
            return ProductionCheck(
                id="oidc",
                label="OIDC provider 真实 token 校验和角色映射",
                status="configured" if ok else "failed",
                verification="live_jwks_fetch",
                detail=f"JWKS endpoint HTTP status={response.status}; token 校验仍需真实 bearer token。",
                next_step="使用真实 token 调用 /me 验证角色映射和租户隔离。",
                latency_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            return ProductionCheck(
                id="oidc",
                label="OIDC provider 真实 token 校验和角色映射",
                status="failed",
                verification="live_jwks_fetch",
                detail=f"{exc.__class__.__name__}: {exc}",
                next_step="检查 OIDC_JWKS_URL、网络和 provider 配置。",
                latency_ms=_elapsed_ms(start),
            )
    return ProductionCheck(
        id="oidc",
        label="OIDC provider 真实 token 校验和角色映射",
        status="configured",
        verification="configuration_only",
        detail="HS256 secret 已配置；仍需真实 bearer token 调用 /me 验证。",
        next_step="使用真实 token 调用 /me 验证角色映射。",
    )


def _smtp_socket_check(settings: Settings, *, live: bool) -> ProductionCheck:
    if not settings.smtp_host:
        return ProductionCheck(
            id="smtp",
            label="邮件真实 API/SMTP 凭证、失败重试、幂等、补偿",
            status="not_configured",
            verification="configuration",
            detail="SMTP_HOST is not configured.",
            next_step="配置 SMTP_HOST/PORT/USERNAME/PASSWORD，并以 approval 模式验证邮件草稿与发送链路。",
        )
    if not live:
        return ProductionCheck(
            id="smtp",
            label="邮件真实 API/SMTP 凭证、失败重试、幂等、补偿",
            status="configured",
            verification="configuration",
            detail=f"SMTP_HOST={settings.smtp_host}; SMTP_PORT={settings.smtp_port}",
            next_step="调用 /production/checks?live=true 执行 socket 连通性验证，再跑审批后发送演示。",
        )
    start = time.perf_counter()
    try:
        with socket.create_connection((settings.smtp_host, settings.smtp_port), timeout=4):
            pass
        return ProductionCheck(
            id="smtp",
            label="邮件真实 API/SMTP 凭证、失败重试、幂等、补偿",
            status="verified",
            verification="live_socket",
            detail="SMTP host:port socket reachable.",
            next_step="继续验证认证、发送沙箱邮件、重试、幂等键和补偿记录。",
            latency_ms=_elapsed_ms(start),
        )
    except Exception as exc:
        return ProductionCheck(
            id="smtp",
            label="邮件真实 API/SMTP 凭证、失败重试、幂等、补偿",
            status="failed",
            verification="live_socket",
            detail=f"{exc.__class__.__name__}: {exc}",
            next_step="检查 SMTP 网络、端口、防火墙、TLS 和凭证。",
            latency_ms=_elapsed_ms(start),
        )


def _ats_calendar_check(settings: Settings) -> ProductionCheck:
    inventory = connector_inventory()
    configured = [item["name"] for item in inventory if item["status"] == "configured" and item["category"] in {"ats", "calendar", "collaboration"}]
    required = ["Greenhouse", "Lever", "Outlook", "Google Calendar"]
    if not configured:
        return ProductionCheck(
            id="external_tools",
            label="ATS/日历真实 API 凭证、失败重试、幂等、补偿",
            status="not_configured",
            verification="configuration",
            detail="No ATS/calendar connector is marked configured.",
            next_step=f"配置至少一个生产连接器：{', '.join(required)}，再执行审批后真实 API 沙箱演示。",
        )
    return ProductionCheck(
        id="external_tools",
        label="ATS/日历真实 API 凭证、失败重试、幂等、补偿",
        status="configured",
        verification="configuration",
        detail=f"Configured connectors: {', '.join(configured)}",
        next_step="执行沙箱 ATS 阶段变更、日历邀请、失败重试和补偿记录验证。",
    )


def _network_ops_check(settings: Settings) -> ProductionCheck:
    configured = [
        settings.enterprise_mode,
        settings.api_rate_limit_per_minute > 0,
        settings.trusted_sso_enabled or settings.oidc_enabled,
    ]
    status: CheckStatus = "configured" if all(configured) else "not_configured"
    return ProductionCheck(
        id="network_ops",
        label="生产网络、TLS、CORS、网关、日志/告警链路",
        status=status,
        verification="configuration",
        detail=(
            f"enterprise_mode={settings.enterprise_mode}; "
            f"rate_limit={settings.api_rate_limit_per_minute}/min; "
            f"identity={settings.trusted_sso_enabled or settings.oidc_enabled}"
        ),
        next_step="在网关层验证 TLS、生产域名 CORS、访问日志、告警路由和错误预算监控。",
    )


def _e2e_check() -> ProductionCheck:
    return ProductionCheck(
        id="e2e_demo",
        label="全链路端到端演示和回滚演练",
        status="configured",
        verification="runbook",
        detail="Runbook exists; completion requires an operator-run demo with real integrations.",
        next_step="按 docs/production-readiness.md 跑上传、问答、审批、执行、审计链，并记录回滚演练证据。",
    )


def production_checks(*, live: bool = False) -> dict[str, object]:
    settings = get_settings()
    checks = [
        _postgres_check(settings, live=live),
        _qdrant_check(settings, live=live),
        _object_storage_check(settings, live=live),
        _oidc_check(settings, live=live),
        _ats_calendar_check(settings),
        _smtp_socket_check(settings, live=live),
        _network_ops_check(settings),
        _e2e_check(),
    ]
    counts: dict[str, int] = {"not_configured": 0, "configured": 0, "verified": 0, "failed": 0}
    for check in checks:
        counts[check.status] += 1
    return {
        "live": live,
        "summary": counts,
        "checks": [asdict(check) for check in checks],
    }
