"""
Modelos de Dados Canónicos (Pydantic v2) — Plataforma de Observabilidade Web (Tier-S)
Autoridade de Esquema (.harness/source_of_truth.yaml)
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class InfrastructureType(str, Enum):
    ROCKET_CLOUDFLARE = "rocket_cloudflare"
    VPS = "vps"
    BARE_METAL = "bare_metal"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class SiteSelectors(BaseModel):
    """Seletores DOM customizáveis para cada loja WooCommerce."""
    add_to_cart_btn: str = Field(
        default="button[name='add-to-cart'], .single_add_to_cart_button",
        description="Seletor CSS para o botão de adicionar ao carrinho"
    )
    cart_feedback: str = Field(
        default=".woocommerce-message, .added-to-cart, a.added_to_cart",
        description="Seletor CSS para confirmação de item adicionado ao carrinho"
    )
    checkout_url: str = Field(
        default="/checkout/",
        description="Caminho relativo ou absoluto da página de checkout"
    )
    order_review_table: str = Field(
        default="#order_review",
        description="Seletor da tabela de revisão do pedido"
    )
    shipping_blocked_notice: str = Field(
        default=".woocommerce-no-shipping-available-html",
        description="Aviso de indisponibilidade de métodos de envio"
    )
    payment_gateways_container: str = Field(
        default="#payment, .wc_payment_methods",
        description="Contentor de recipientes de métodos de pagamento"
    )


class SiteConfig(BaseModel):
    """Configuração canónica de uma loja WooCommerce a monitorizar."""
    id: str = Field(
        ...,
        min_length=2,
        max_length=64,
        pattern=r"^[a-z0-9\-_]+$",
        description="Identificador único da loja em lowercase com hífens/underscores"
    )
    name: str = Field(..., min_length=2, description="Nome legível da loja")
    store_url: str = Field(..., description="URL base da loja (deve ser https)")
    product_url: str = Field(..., description="URL completa de um produto ativo para teste")
    infrastructure_type: InfrastructureType = Field(
        default=InfrastructureType.ROCKET_CLOUDFLARE,
        description="Tipo de infraestrutura onde a loja está alojada"
    )
    selectors: SiteSelectors = Field(default_factory=SiteSelectors)
    enabled: bool = Field(default=True, description="Se a loja deve ser inspecionada nas rondas")
    waf_bypass_header_name: str = Field(
        default="X-WAF-Bypass-Token",
        description="Nome do cabeçalho HTTP para contornar bloqueios WAF autorizados"
    )
    custom_headers: Dict[str, str] = Field(
        default_factory=dict,
        description="Cabeçalhos adicionais opcionais para requisições"
    )

    @field_validator("store_url", "product_url")
    @classmethod
    def validate_https_url(cls, v: str) -> str:
        v_str = str(v).strip()
        if not v_str.startswith("https://") and not v_str.startswith("http://"):
            raise ValueError("O URL deve começar por https:// ou http://")
        return v_str


class SitesConfigFile(BaseModel):
    """Esquema do ficheiro config/sites.json."""
    version: str = Field(default="1.0")
    sites: List[SiteConfig] = Field(default_factory=list)

    @field_validator("sites")
    @classmethod
    def validate_unique_site_ids(cls, v: List[SiteConfig]) -> List[SiteConfig]:
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            duplicates = [sid for sid in ids if ids.count(sid) > 1]
            raise ValueError(f"IDs de lojas duplicados detetados: {set(duplicates)}")
        return v


class ThresholdsConfig(BaseModel):
    """Limiares canónicos de alerta e tempos de timeout (config/thresholds.json)."""
    ttfb_warning_ms: float = Field(default=800.0, ge=100.0, description="Teto para alerta de TTFB alto")
    ttfb_critical_ms: float = Field(default=2500.0, ge=200.0, description="Teto para TTFB considerado crítico")
    ssl_expiry_warning_days: int = Field(default=15, ge=1, description="Dias para alerta de renovação SSL")
    ssl_expiry_critical_days: int = Field(default=3, ge=0, description="Dias para alerta crítico de SSL")
    step_timeout_sec: int = Field(default=25, ge=5, le=120, description="Timeout máximo por etapa Playwright")
    max_js_errors_allowed: int = Field(default=0, ge=0, description="Erros JS tolerados no checkout")
    http_error_threshold: int = Field(default=400, ge=400, le=599, description="Código HTTP a partir do qual é erro")

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "ThresholdsConfig":
        if self.ttfb_warning_ms >= self.ttfb_critical_ms:
            raise ValueError("ttfb_warning_ms deve ser estritamente menor que ttfb_critical_ms")
        if self.ssl_expiry_warning_days <= self.ssl_expiry_critical_days:
            raise ValueError("ssl_expiry_warning_days deve ser estritamente maior que ssl_expiry_critical_days")
        return self


class CodeErrorDetail(BaseModel):
    """Registo estruturado de erro de código em tempo de execução."""
    error_type: str = Field(default="JavaScriptError", description="Tipo de exceção (TypeError, ReferenceError, etc.)")
    message: str = Field(..., description="Mensagem de erro")
    source_file: Optional[str] = Field(default=None, description="Ficheiro ou URL de origem do script")
    line_number: Optional[int] = Field(default=None, description="Número da linha")
    column_number: Optional[int] = Field(default=None, description="Número da coluna")
    stack_trace: Optional[str] = Field(default=None, description="Stack trace formatado")
    phase: Optional[str] = Field(default=None, description="Fase da navegação onde o erro ocorreu")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LongTaskDetail(BaseModel):
    """Registo de bloqueio de thread principal (Long Task > 50ms)."""
    duration_ms: float = Field(..., description="Duração do congelamento da thread em milissegundos")
    start_time_ms: float = Field(..., description="Momento de início relativo ao início da navegação")
    name: str = Field(default="self", description="Identificador da tarefa")
    attribution: Optional[str] = Field(default=None, description="Origem ou container associado ao bloqueio")


class SlowRequestDetail(BaseModel):
    """Registo das requisições mais lentas (gargalos de rede)."""
    url: str = Field(..., description="URL da requisição")
    method: str = Field(default="GET", description="Método HTTP")
    status: int = Field(default=200, description="Código de status HTTP")
    duration_ms: float = Field(..., description="Tempo de resposta em milissegundos")
    resource_type: str = Field(default="xhr", description="Tipo de recurso (xhr, script, stylesheet, img, etc.)")
    content_type: Optional[str] = Field(default=None, description="Tipo MIME retornado")
    size_bytes: Optional[int] = Field(default=None, description="Tamanho transferido em bytes")
    cache_status: Optional[str] = Field(default=None, description="Estado de cache (HIT, MISS, DYNAMIC, BYPASS)")


class PerformanceMetrics(BaseModel):
    """Métricas consolidadas de desempenho e Core Web Vitals."""
    total_blocking_time_ms: float = Field(default=0.0, description="Total Blocking Time (TBT)")
    long_tasks_count: int = Field(default=0, description="Total de tarefas que bloquearam a thread >50ms")
    fcp_ms: Optional[float] = Field(default=None, description="First Contentful Paint (FCP)")
    dom_content_loaded_ms: Optional[float] = Field(default=None, description="DOMContentLoaded timing")
    load_event_ms: Optional[float] = Field(default=None, description="Window Load timing")
    total_transferred_bytes: int = Field(default=0, description="Bytes totais transferidos na sessão")
    js_bytes: int = Field(default=0, description="Bytes de scripts JavaScript")
    css_bytes: int = Field(default=0, description="Bytes de folhas de estilo CSS")
    img_bytes: int = Field(default=0, description="Bytes de imagens")
    font_bytes: int = Field(default=0, description="Bytes de fontes")
    requests_count: int = Field(default=0, description="Total de requisições HTTP efetuadas")


class EdgeInspectionResult(BaseModel):
    """Resultado da sonda de rede, DNS e handshake TLS/SSL."""
    site_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dns_resolved_ip: Optional[str] = None
    dns_lookup_time_ms: Optional[float] = None
    ssl_valid: bool = False
    ssl_issuer: Optional[str] = None
    ssl_expiry_date: Optional[datetime] = None
    ssl_days_remaining: Optional[int] = None
    ttfb_ms: Optional[float] = None
    total_latency_ms: Optional[float] = None
    http_status_code: Optional[int] = None
    status: HealthStatus = HealthStatus.HEALTHY
    waf_bypass_applied: bool = False
    error_message: Optional[str] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class ForensicIncident(BaseModel):
    """Registo individual detalhado de falha técnica detetada."""
    incident_id: str
    site_id: str
    site_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    failure_phase: str = Field(..., description="Fase onde ocorreu a quebra (edge, cart, checkout, payment)")
    verdict_pt: str = Field(..., description="Causa-raiz em português claro")
    screenshot_path: Optional[str] = None
    js_errors: List[Dict[str, Any]] = Field(default_factory=list)
    failed_ajax_calls: List[Dict[str, Any]] = Field(default_factory=list)
    dom_extract: Optional[str] = None
    http_status: Optional[int] = None
    error_details: Optional[str] = None
    code_errors: List[CodeErrorDetail] = Field(default_factory=list)
    long_tasks: List[LongTaskDetail] = Field(default_factory=list)
    slowest_requests: List[SlowRequestDetail] = Field(default_factory=list)


class StoreStatus(BaseModel):
    """Estado consolidado instantâneo de uma loja para o painel web."""
    site_id: str
    name: str
    infrastructure_type: InfrastructureType
    status: HealthStatus = HealthStatus.HEALTHY
    ssl_days_remaining: Optional[int] = None
    latest_ttfb_ms: Optional[float] = None
    average_ttfb_ms: Optional[float] = None
    uptime_pct_30d: float = 100.0
    checkout_success_rate_pct: float = 100.0
    last_checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_incident: Optional[ForensicIncident] = None
    diagnostics_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Resumo de diagnósticos rápidos (erros JS, TBT, cache Cloudflare, peso)"
    )


class DiagnosticsDossier(BaseModel):
    """Dossiê forense aprofundado persistido por loja (dashboard/data/dossiers/{site_id}.json)."""
    site_id: str
    site_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: HealthStatus = HealthStatus.HEALTHY
    verdict_pt: str = Field(default="Inspeção de observabilidade concluída", description="Veredito executivo e causa-raiz")
    failure_phase: Optional[str] = None
    cf_cache_status: Optional[str] = None
    content_encoding: Optional[str] = None
    http_version: Optional[str] = None
    ttfb_ms: Optional[float] = None
    code_errors: List[CodeErrorDetail] = Field(default_factory=list)
    console_errors: List[str] = Field(default_factory=list)
    long_tasks: List[LongTaskDetail] = Field(default_factory=list)
    performance: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    slowest_requests: List[SlowRequestDetail] = Field(default_factory=list)
    failed_requests: List[Dict[str, Any]] = Field(default_factory=list)
    screenshot_path: Optional[str] = None
    dom_extract: Optional[str] = None


class ProbeResult(BaseModel):
    """Resultado da sonda de browser Playwright para uma loja."""
    site_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    success: bool = False
    completed_step: str = Field(default="init", description="Última etapa concluída com sucesso")
    step_latencies_ms: Dict[str, float] = Field(default_factory=dict)
    total_duration_ms: float = 0.0
    js_errors: List[Dict[str, Any]] = Field(default_factory=list)
    console_errors: List[str] = Field(default_factory=list)
    failed_ajax_calls: List[Dict[str, Any]] = Field(default_factory=list)
    screenshot_path: Optional[str] = None
    dom_extract: Optional[str] = None
    verdict_pt: Optional[str] = None
    incident: Optional[ForensicIncident] = None
    code_errors: List[CodeErrorDetail] = Field(default_factory=list)
    long_tasks: List[LongTaskDetail] = Field(default_factory=list)
    performance: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    slowest_requests: List[SlowRequestDetail] = Field(default_factory=list)



class HistoryPoint(BaseModel):
    """Ponto individual da série temporal de telemetria."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    site_id: str
    status: HealthStatus = HealthStatus.HEALTHY
    ttfb_ms: Optional[float] = None
    checkout_success: bool = False
    total_duration_ms: Optional[float] = None
    incident_id: Optional[str] = None


class CurrentStatusPayload(BaseModel):
    """Payload completo gravado em dashboard/data/current_status.json."""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stores: List[StoreStatus] = Field(default_factory=list)


class HistoryPayload(BaseModel):
    """Payload completo gravado em dashboard/data/history.json (30 dias)."""
    retention_days: int = 30
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    points: List[HistoryPoint] = Field(default_factory=list)



