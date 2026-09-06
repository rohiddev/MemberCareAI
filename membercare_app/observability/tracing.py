from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter


SERVICE_NAME = "MemberCareAI"

_configured = False


def configure_tracing() -> None:
    global _configured

    if _configured:
        return

    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
        }
    )

    provider = TracerProvider(
        resource=resource,
    )

    exporter = CloudTraceSpanExporter(
        project_id="membercare-ai",
    )

    provider.add_span_processor(
        BatchSpanProcessor(
            exporter
        )
    )

    trace.set_tracer_provider(
        provider
    )

    _configured = True


def get_tracer():
    configure_tracing()

    return trace.get_tracer(
        SERVICE_NAME
    )