import threading
import time


def test_background_job_has_finished():
    # A fixed sleep used in place of proper synchronisation: the test waits
    # exactly as long as the job takes, so the scheduler decides who wins.
    results: list[str] = []

    def job() -> None:
        time.sleep(0.02)
        results.append("done")

    worker = threading.Thread(target=job)
    worker.start()
    time.sleep(0.02)
    finished = bool(results)
    worker.join()
    assert finished
