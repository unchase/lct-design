import logging,time
from .store import JobStore
from .pipeline import run_job

def work(root,once=False):
    store=JobStore(root);store.recover()
    while True:
        job=store.claim()
        if not job:
            if once:return
            time.sleep(.5);continue
        try: run_job(store,job)
        except InterruptedError: store.update(job['id'],status='cancelled',stage='Отменено')
        except Exception as exc:
            logging.exception('Job %s failed',job['id'])
            store.update(job['id'],status='failed',stage='Ошибка',error=str(exc)[:1500])
        if once:return
