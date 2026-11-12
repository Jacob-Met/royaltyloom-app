"""Lifecycle and real HTTP admission using a synthetic backend, no model download."""
import http.client, io, json, os, tempfile, threading, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import app
from local_ai_runtime import LocalAIRuntime

class FakeBackend:
    def __init__(self):
        self.preparations = self.starts = self.stops = 0
        self.release = threading.Event(); self.release.set()
        self.entered = threading.Event()
        self.fail = False
        self.process = SimpleNamespace(returncode=None)
        self.process.poll = lambda: self.process.returncode
    def prepare(self, cache, *, progress, cancelled):
        self.preparations += 1; self.entered.set()
        progress({"phase":"download","asset":"pinned-model","completed_bytes":4,"total_bytes":10})
        while not self.release.wait(.01):
            if cancelled(): raise RuntimeError("cancelled")
        if self.fail: raise RuntimeError("Simulated unavailable download")
        return Path("server"), Path("model")
    def start_model(self, server, model, cache, *, progress, cancelled):
        self.starts += 1
        progress({"phase":"starting"})
        return SimpleNamespace(process=self.process,url="http://127.0.0.1:12345/v1/chat/completions",model="royalty-local")
    def stop_model(self, handle):
        self.stops += 1; handle.process.returncode = 0

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ,{"ROYALTY_LOOM_AI_URL":"","ROYALTY_LOOM_AI_MODEL":""});self.env.start()
        self.platform = patch("local_ai_runtime.platform.system",return_value="Linux");self.platform.start()
        self.machine = patch("local_ai_runtime.platform.machine",return_value="x86_64");self.machine.start()
        self.backend = FakeBackend()
        self.manager = LocalAIRuntime(self.tmp.name,backend=self.backend)
    def tearDown(self):
        self.manager.stop(wait=True);self.machine.stop();self.platform.stop();self.env.stop();self.tmp.cleanup()
    def await_state(self,wanted):
        for _ in range(200):
            state=self.manager.snapshot()
            if state["state"]==wanted:return state
            time.sleep(.01)
        self.fail(str(self.manager.snapshot()))
    def test_read_and_unacknowledged_start_never_prepare(self):
        for _ in range(3):self.assertEqual(self.manager.snapshot()["state"],"idle")
        for value in (False,"true",None,1):
            with self.assertRaises(ValueError):self.manager.start(value)
        self.assertEqual((self.backend.preparations,self.backend.starts),(0,0))
    def test_duplicate_starts_coalesce_and_stop_owned_process(self):
        self.backend.release.clear();self.manager.start(True);self.assertTrue(self.backend.entered.wait(2))
        for _ in range(5):self.manager.start(True)
        self.assertEqual(self.backend.preparations,1)
        self.assertEqual(self.manager.snapshot()["state"],"preparing")
        self.backend.release.set();self.assertEqual(self.await_state("ready")["adapter"],"local")
        self.manager.stop(wait=True)
        self.assertEqual(self.manager.snapshot()["state"],"idle");self.assertIsNone(self.manager.adapter())
        self.assertEqual(self.backend.stops,1)
    def test_cancel_preparation_never_launches(self):
        self.backend.release.clear();self.manager.start(True);self.assertTrue(self.backend.entered.wait(2))
        self.manager.stop(wait=True)
        self.assertEqual(self.manager.snapshot()["state"],"idle");self.assertEqual(self.backend.starts,0)
    def test_failure_retry_and_unexpected_exit(self):
        self.backend.fail=True;self.manager.start(True);self.assertFalse(self.await_state("error")["configured"])
        self.backend.fail=False;self.manager.start(True);self.assertTrue(self.await_state("ready")["configured"])
        self.backend.process.returncode=2
        self.assertEqual(self.manager.snapshot()["state"],"error");self.assertIsNone(self.manager.adapter())
    def test_external_or_unsupported_never_start(self):
        for env in ({"ROYALTY_LOOM_AI_URL":"https://example.test/v1","ROYALTY_LOOM_AI_MODEL":"remote"},{"ROYALTY_LOOM_AI_URL":"https://example.test/v1"}):
            with patch.dict(os.environ,env):
                with self.assertRaises(ValueError):self.manager.start(True)
                self.assertFalse(self.manager.snapshot()["available"])
        with patch("local_ai_runtime.platform.system",return_value="Darwin"):
            with self.assertRaises(ValueError):self.manager.start(True)
        self.assertEqual(self.backend.preparations,0)
    def test_http_origin_host_acknowledgement_and_status(self):
        with patch.object(app,"LOCAL_AI",self.manager):
            server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(path,body=None,headers=None):
                c=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
                c.request("GET" if body is None else "POST",path,None if body is None else json.dumps(body),{"Content-Type":"application/json",**(headers or {})})
                r=c.getresponse();result=(r.status,json.loads(r.read()));c.close();return result
            try:
                self.assertFalse(request("/api/health")[1]["ai_configured"])
                self.assertEqual(request("/api/local-ai/start",{"acknowledge_download":True},{"Origin":"https://evil.example"})[0],403)
                self.assertEqual(request("/api/local-ai/start",{"acknowledge_download":True},{"Host":"evil.example"})[0],421)
                self.assertEqual(request("/api/local-ai/start",{"acknowledge_download":False})[0],422)
                self.assertEqual(request("/api/local-ai/start",{"acknowledge_download":True,"url":"https://evil.example"})[0],422)
                self.assertEqual(self.backend.preparations,0)
                self.assertEqual(request("/api/local-ai/start",{"acknowledge_download":True})[0],200)
                self.await_state("ready")
                health=request("/api/health")[1];self.assertTrue(health["ai_configured"]);self.assertEqual(health["ai_adapter"],"local")
                self.assertEqual(request("/api/local-ai")[1]["state"],"ready")
                self.assertEqual(request("/api/local-ai/stop",{})[0],200);self.assertFalse(request("/api/health")[1]["ai_configured"])
            finally:server.shutdown();server.server_close();thread.join()
    def test_local_adapter_source_validation_and_no_external_key(self):
        self.manager.start(True);self.await_state("ready")
        quote="Mira receives 100% of net receipts."
        response={"choices":[{"message":{"content":json.dumps({"collaborators":[{"name":"Mira","evidence":quote}]})}}]}
        with patch.object(app,"LOCAL_AI",self.manager),patch.dict(os.environ,{"ROYALTY_LOOM_AI_KEY":"external-only-test-key"}):
            with patch.object(app.urllib.request,"urlopen",return_value=io.StringIO(json.dumps(response))) as call:result=app.ai_suggest(quote)
            req=call.call_args.args[0]
            self.assertEqual(req.full_url,self.manager.adapter()[0]);self.assertIsNone(req.get_header("Authorization"))
            self.assertEqual(result["suggestions"][0]["share_bps"],10000)
            self.assertFalse(result["suggestions"][0].get("email"))


    def test_sigterm_reaps_actual_owned_child(self):
        import subprocess, socket, sys, signal
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
        pid_file=Path(self.tmp.name)/"owned-child.pid"
        script = """
import app, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
from local_ai_runtime import LocalAIRuntime
from test_local_ai_runtime import FakeBackend
class ProcessBackend(FakeBackend):
    def start_model(self,server,model,cache,**kwargs):
        child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])
        receipt=Path(sys.argv[1])
        pending=receipt.with_suffix(".pending")
        pending.write_text(str(child.pid))
        pending.replace(receipt)
        return SimpleNamespace(process=child,url="http://127.0.0.1:12345/v1/chat/completions",model="royalty-local")
    def stop_model(self,handle):
        handle.process.terminate()
        handle.process.wait(timeout=5)
app.LOCAL_AI=LocalAIRuntime(sys.argv[2],backend=ProcessBackend())
app.serve()
"""
        env={**os.environ,"PORT":str(port),"ROYALTY_LOOM_DB":str(Path(self.tmp.name)/"process.sqlite3")}
        process=subprocess.Popen([sys.executable,"-c",script,str(pid_file),self.tmp.name],cwd=Path(__file__).parent,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        child=None
        try:
            for _ in range(100):
                try:
                    c=http.client.HTTPConnection("127.0.0.1",port,timeout=1)
                    c.request("POST","/api/local-ai/start",json.dumps({"acknowledge_download":True}),{"Content-Type":"application/json"})
                    response=c.getresponse();response.read();c.close()
                    self.assertEqual(response.status,200);break
                except OSError:time.sleep(.02)
            for _ in range(100):
                if pid_file.exists():break
                time.sleep(.02)
            child=int(pid_file.read_text())
            process.terminate();self.assertEqual(process.wait(timeout=15),0)
            with self.assertRaises(ProcessLookupError):os.kill(child,0)
        finally:
            if process.poll() is None:process.kill();process.wait()
            if child is not None:
                try:os.kill(child,signal.SIGTERM)
                except ProcessLookupError:pass


    def test_start_and_repeated_stop_coalesce_during_owned_termination(self):
        self.manager.start(True);self.await_state("ready")
        stopping=threading.Event();release=threading.Event()
        original_stop=self.backend.stop_model
        def delayed_stop(handle):
            stopping.set()
            self.assertTrue(release.wait(3))
            original_stop(handle)
        self.backend.stop_model=delayed_stop
        worker=threading.Thread(target=self.manager.stop)
        worker.start()
        try:
            self.assertTrue(stopping.wait(2))
            self.assertEqual(self.manager.stop()["state"],"stopping")
            self.assertEqual(self.manager.start(True)["state"],"stopping")
            self.assertEqual(self.backend.starts,1)
            self.assertIsNone(self.manager.adapter())
        finally:
            release.set();worker.join(timeout=3)
        self.assertEqual(self.manager.snapshot()["state"],"idle")
        self.assertEqual(self.backend.stops,1)

    def test_failed_stop_retains_owned_handle_for_retry(self):
        self.manager.start(True);self.await_state("ready")
        original_stop=self.backend.stop_model
        self.backend.stop_model=lambda handle: (_ for _ in ()).throw(OSError("synthetic stop failure"))
        self.assertEqual(self.manager.stop()["state"],"error")
        self.assertTrue(self.manager.snapshot()["owned_process"])
        self.manager.start(True)
        self.assertEqual(self.backend.starts,1)
        self.backend.stop_model=original_stop
        self.assertEqual(self.manager.stop()["state"],"idle")
        self.assertFalse(self.manager.snapshot()["owned_process"])


    def test_shutdown_waits_for_an_inflight_owned_stop(self):
        self.manager.start(True);self.await_state("ready")
        stopping=threading.Event();release=threading.Event();shutdown_done=threading.Event()
        original_stop=self.backend.stop_model
        def delayed_stop(handle):
            stopping.set()
            self.assertTrue(release.wait(3))
            original_stop(handle)
        self.backend.stop_model=delayed_stop
        worker=threading.Thread(target=self.manager.stop);worker.start()
        self.assertTrue(stopping.wait(2))
        shutdown=threading.Thread(target=lambda:(self.manager.stop(wait=True),shutdown_done.set()))
        shutdown.start()
        try:self.assertFalse(shutdown_done.wait(.05))
        finally:release.set();worker.join(timeout=3);shutdown.join(timeout=3)
        self.assertTrue(shutdown_done.is_set())
        self.assertEqual(self.backend.stops,1)
        self.assertFalse(self.manager.snapshot()["owned_process"])

if __name__=="__main__":unittest.main()
