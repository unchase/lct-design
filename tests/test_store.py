from lct_design.store import JobStore

def test_claim_durable_cancel(tmp_path):
    s=JobStore(tmp_path);j=s.create({'hello':'world'})
    assert s.claim()['id']==j['id']
    assert s.claim() is None
    s.cancel(j['id']);assert s.get(j['id'])['cancelled']
    s2=JobStore(tmp_path);s2.recover()
    assert s2.get(j['id'])['status']=='interrupted'
