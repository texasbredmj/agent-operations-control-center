from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, set_span_in_context


class Collector(SpanExporter):
    def __init__(self):
        self.rows = []

    def export(self, spans):
        for span in spans:
            self.rows.append(
                {
                    "span_id": format(span.context.span_id, "016x"),
                    "trace_id": format(span.context.trace_id, "032x"),
                    "parent_span_id": format(span.parent.span_id, "016x") if span.parent else None,
                    "name": span.name,
                    "duration_ms": (span.end_time - span.start_time) / 1_000_000,
                    "attributes": dict(span.attributes or {}),
                }
            )
        return SpanExportResult.SUCCESS


def telemetry(task):
    collector = Collector()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(collector))
    parent = NonRecordingSpan(
        SpanContext(
            trace_id=int(task["trace_id"], 16),
            span_id=int(task["id"].hex[:16], 16),
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
    )
    return provider, collector, set_span_in_context(parent)
