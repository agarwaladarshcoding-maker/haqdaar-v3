import tempfile, os, types
from dotenv import load_dotenv; load_dotenv(".env")
from haqdaar.model.client import GroqModelClient
from tools import talk_questions as tq
from haqdaar.data.corpus import Corpus
corpus=Corpus.load("CURRENT")
cap={}
class C:
    def call(self,messages,task="",timeout=None,model=None):
        cap['m']=messages; return types.SimpleNamespace(success=False,data=None,is_429=False)
t,audio,log=tq._talk(corpus,C(),"hi",tempfile.mkdtemp(),"probe")
t._turn("मेरे को फार्मर स्कीम्स के बारे में जानना है।")
m=cap['m']
first=GroqModelClient(); first.backup_key=""
second=GroqModelClient(api_key=os.environ["GROQ_API_KEY_2"]); second.backup_key=""
for model in ("openai/gpt-oss-120b","qwen/qwen3.8-27b"):
    for name,c in (("first key",first),("second key",second)):
        r=c.call(m,task="talk",timeout=10,model=model)
        print(model,name,'ok' if r.success else r.error, round(r.latency_s,2),'s', (r.data or {}).get('say','')[:150])
