import os
from dotenv import load_dotenv

load_dotenv()

_tracer = None

def get_tracer():
    global _tracer
    if _tracer is None:
        try:
            from arize.otel import register, Endpoint
            from opentelemetry import trace

            register(
                space_id=os.getenv("ARIZE_SPACE_ID"),
                api_key=os.getenv("ARIZE_API_KEY"),
                project_name=os.getenv(
                    "ARIZE_MODEL_ID",
                    "supply-chain-risk-agent"
                ),
                endpoint=Endpoint.ARIZE,
                batch=True,
                verbose=True
            )
            _tracer = trace.get_tracer(__name__)
            print("✅ Arize tracing initialized")

        except Exception as e:
            print(f"⚠️ Arize init failed: {e}")
            _tracer = None
    return _tracer

def trace_step(step_name: str, attributes: dict = {}):
    tracer = get_tracer()
    if tracer:
        try:
            span = tracer.start_span(step_name)
            for k, v in attributes.items():
                span.set_attribute(k, str(v))
            span.end()
        except Exception:
            pass

if __name__ == "__main__":
    tracer = get_tracer()
    if tracer:
        trace_step("test_connection",
                   {"status": "connected"})
        print("✅ Test trace sent to Arize")