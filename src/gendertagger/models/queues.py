"""Operational queue-routing vocabulary shared across the API and workers."""

DEFAULT_QUEUE = "default"
CPU_QUEUE = "cpu"
GPU_QUEUE = "gpu"
LLM_QUEUE = "llm"
EXTERNAL_QUEUE = "external"
EXPORT_QUEUE = "export"

# Operational routing classes; methods are routed to one of these, never a
# per-method queue. See docs/06-task-queue.md.
CLASSIFICATION_QUEUES: tuple[str, ...] = (
    DEFAULT_QUEUE,
    CPU_QUEUE,
    GPU_QUEUE,
    LLM_QUEUE,
    EXTERNAL_QUEUE,
    EXPORT_QUEUE,
)
