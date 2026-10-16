"""Incremental ACP-to-OpenAI delivery with per-call cancellation and tool buffering."""
import queue
import threading
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor, wait

from agent.memory_provider import ctx_bound

from agent.acp_openai_bridge import completion_to_stream_chunks


def stream_completion(run):
    events = queue.Queue()
    cancelled = threading.Event()
    run_in_context = ctx_bound(run)

    def consume():
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='copilot-acp-stream')
        future = executor.submit(run_in_context, lambda kind, text: events.put((kind, text)), cancelled)
        future.add_done_callback(lambda result: events.put(('complete', result)))
        text = emitted = reasoning = ''
        try:
            while True:
                kind, value = events.get()
                if kind == 'complete':
                    value = value.result()  # Propagate provider exceptions in the consumer.
                    message = value.choices[0].message
                    # The bridge parser strips tool blocks. Only the safe prose prefix
                    # was emitted; the final chunk carries remaining text and tool deltas.
                    final = message.content or ''
                    if not final.startswith(emitted):
                        raise RuntimeError('ACP final response changed its already-streamed prefix')
                    message.content = final.removeprefix(emitted)
                    message.reasoning = message.reasoning_content = (message.reasoning or '').removeprefix(reasoning)
                    yield from completion_to_stream_chunks(value)
                    return
                if kind == 'text':
                    text += value
                    # XML and bare-JSON tool envelopes may straddle chunks. Hold the
                    # first possible envelope and everything following it for the parser.
                    boundaries = [i for i in (text.find('<'), text.find('{'), text.find('`')) if i >= 0]
                    safe = text[:min(boundaries)] if boundaries else text
                    safe = safe.strip()
                    value = safe[len(emitted):]
                    emitted = safe
                    if not value:
                        continue
                else:
                    reasoning += value
                delta = SimpleNamespace(role='assistant', content=value if kind == 'text' else None,
                                        reasoning=value if kind == 'reasoning' else None,
                                        reasoning_content=value if kind == 'reasoning' else None, tool_calls=None)
                yield SimpleNamespace(choices=[SimpleNamespace(index=0, delta=delta, finish_reason=None)], usage=None)
        finally:
            cancelled.set()
            wait((future,), timeout=1)
            executor.shutdown(wait=False, cancel_futures=True)

    return consume()
