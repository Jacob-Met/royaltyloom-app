import hashlib,io,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import run_local_ai as local
class Response(io.BytesIO):
 def __init__(self,data):
  super().__init__(data);self.headers={"Content-Length":str(len(data))}
class LocalSetup(unittest.TestCase):
 def test_cache(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"model";p.write_bytes(b"verified");events=[]
   with patch.object(local.urllib.request,"urlopen") as net:
    local.download("unused",p,hashlib.sha256(b"verified").hexdigest(),progress=events.append)
   net.assert_not_called();self.assertEqual(events[-1]["completed_bytes"],8)
 def test_cancel_preserves_cache(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"model";p.write_bytes(b"prior");cancel=[False]
   def report(e):
    if e["phase"]=="download" and e["completed_bytes"]:cancel[0]=True
   with patch.object(local.urllib.request,"urlopen",return_value=Response(b"x"*200000)):
    with self.assertRaises(local.LocalAICancelled):local.download("unused",p,"wrong",progress=report,cancelled=lambda:cancel[0])
   self.assertEqual(p.read_bytes(),b"prior");self.assertFalse(list(Path(d).glob("*.download")))
 def test_bad_checksum(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"model"
   with patch.object(local.urllib.request,"urlopen",return_value=Response(b"wrong")):
    with self.assertRaisesRegex(RuntimeError,"Checksum failed"):local.download("unused",p,"incorrect")
   self.assertFalse(p.exists());self.assertEqual(list(Path(d).iterdir()),[])
 def test_stream(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"model";data=b"x"*150000;events=[]
   with patch.object(local.urllib.request,"urlopen",return_value=Response(data)):local.download("unused",p,hashlib.sha256(data).hexdigest(),progress=events.append)
   self.assertEqual(p.read_bytes(),data);self.assertEqual([e for e in events if e["phase"]=="download"][-1]["completed_bytes"],len(data));self.assertTrue(all(e["asset"]=="model" for e in events))
 def test_ready_then_owned_stop(self):
  with tempfile.TemporaryDirectory() as d:
   process=Mock();process.poll.return_value=None;events=[]
   with patch.object(local.subprocess,"Popen",return_value=process),patch.object(local.urllib.request,"urlopen",return_value=Response(b'{"status":"ok"}')):
    handle=local.start_model(Path("/runtime"),Path("/model"),Path(d),progress=events.append)
   self.assertTrue(handle.url.endswith("/v1/chat/completions"));self.assertEqual(events[-1]["phase"],"ready");process.terminate.assert_not_called();local.stop_model(handle);process.terminate.assert_called_once()
 def test_cancel_start_stops_owned(self):
  with tempfile.TemporaryDirectory() as d:
   process=Mock();process.poll.return_value=None;calls=[0]
   def cancel():calls[0]+=1;return calls[0]>1
   with patch.object(local.subprocess,"Popen",return_value=process):
    with self.assertRaises(local.LocalAICancelled):local.start_model(Path("/runtime"),Path("/model"),Path(d),cancelled=cancel)
   process.terminate.assert_called_once()

 def test_cancelled_repair_cannot_leave_stale_verified_marker(self):
  import tarfile
  with tempfile.TemporaryDirectory() as d:
   cache=Path(d);dest=cache/f"runtime-{local.RUNTIME_TAG}-{local.RUNTIME_SHA[:12]}"
   dest.mkdir();marker=dest/"VERIFIED_ARCHIVE_SHA256";marker.write_text(local.RUNTIME_SHA)
   archive=cache/f"llama-{local.RUNTIME_TAG}.tar.gz"
   with tarfile.open(archive,"w:gz") as tar:
    for name in ("llama-server","library.so"):
     member=tarfile.TarInfo(f"llama-{local.RUNTIME_TAG}/"+name);member.size=1;tar.addfile(member,io.BytesIO(b"x"))
   cancel=[False]
   def progress(event):
    if event["phase"]=="extracting":cancel[0]=True
   with patch.object(local,"download"),patch.object(local.platform,"system",return_value="Linux"),patch.object(local.platform,"machine",return_value="x86_64"):
    with self.assertRaises(local.LocalAICancelled):local.prepare(cache,progress=progress,cancelled=lambda:cancel[0])
   self.assertFalse(marker.exists())
