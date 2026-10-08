"""UDP reception isolated from Open3D's GIL-holding render calls.

Only the input process binds sockets and decodes packets. Its one-slot mailbox
and a pipe keep display buffering bounded even when the renderer is blocked.
Use spawn: forking after Open3D has initialized threads/GL is unsafe.
"""
import multiprocessing
import threading

from .live import receive
from .mailbox import LatestFrame
from .pipeline import Pipeline


def _receive_process(options, stop, connection):
    mailbox = LatestFrame()
    finished = threading.Event()
    result = {}
    error = None
    pipeline = Pipeline(mailbox.put)

    def forward():
        try:
            while True:
                # Snapshot completion before taking the last (flushed) frame.
                done = finished.is_set()
                frame = mailbox.take()
                if frame is not None:
                    connection.send(("frame", frame))
                if done:
                    result["input_skipped_frames"] = mailbox.skipped
                    connection.send(("result", (result, error)))
                    return
                finished.wait(0.005)
        except (BrokenPipeError, EOFError, OSError):
            stop.set()

    sender = threading.Thread(target=forward, daemon=True)
    sender.start()
    try:
        receive(pipeline, **options, stop_event=stop,
                on_ready=lambda: connection.send(("ready", None)))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        result.update(pipeline.finish())
        finished.set()
        sender.join()
        connection.close()


def receive_isolated(options, on_frame, *, stop_event, on_ready=lambda: None):
    """Bridge child messages; always stop/reap the child on exit or errors."""
    context = multiprocessing.get_context("spawn")
    stop = context.Event()
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_receive_process,
                              args=(options, stop, writer), name="e1r-udp",
                              daemon=True)
    started = False
    try:
        process.start()
        started = True
        writer.close()
        while True:
            if stop_event.is_set():
                stop.set()
            if not reader.poll(0.1):
                if not process.is_alive():
                    raise RuntimeError(f"UDP input process exited with code {process.exitcode}")
                continue
            try:
                kind, value = reader.recv()
            except EOFError as exc:
                raise RuntimeError("UDP input process closed without a result") from exc
            if kind == "ready":
                on_ready()
            elif kind == "frame":
                on_frame(value)
            elif kind == "result":
                stats, error = value
                if error:
                    raise RuntimeError(error)
                return stats
            else:
                raise RuntimeError(f"Unexpected input message: {kind}")
    finally:
        stop.set()
        reader.close()
        writer.close()
        if started:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            process.close()
