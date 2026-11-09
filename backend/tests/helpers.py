from fastapi.testclient import TestClient
import main
from invariants import check_all

client = TestClient(main.app)

class Convo:
    def __init__(self, lang="mr-IN", sid=None, **seed):
        import uuid
        self.sid, self.lang = sid or f"C-{uuid.uuid4().hex[:8]}", lang
        s = main.load_session(self.sid)
        s.update(seed); main.save_session(s)

    def say(self, text) -> str:
        before = main.copy.deepcopy(main.SESSIONS[self.sid])
        r = client.post("/api/voice/process", data={"session_id": self.sid, "transcript": text, "language": self.lang})
        assert r.status_code == 200, r.text
        body = r.json(); self.sid = body["session_id"]
        check_all(self.sid, text, body["agent_text"], before)
        return body["agent_text"]

    @property
    def state(self): return main.SESSIONS[self.sid]