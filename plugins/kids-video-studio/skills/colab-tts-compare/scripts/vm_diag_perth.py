# colab exec: why does resemble-perth expose PerthImplicitWatermarker = None in the chatterbox venv?
import subprocess

py = "/content/venv/chatterbox/bin/python"
code = r'''
import importlib, traceback
try:
    importlib.import_module("perth.perth_net.perth_net_implicit.perth_watermarker")
    print("implicit watermarker imports fine")
except Exception:
    traceback.print_exc()
import perth; print("perth version:", getattr(perth, "__version__", "?"), "| implicit:", perth.PerthImplicitWatermarker)
'''
r = subprocess.run([py, "-c", code], capture_output=True, text=True)
print(r.stdout[-3000:], r.stderr[-3000:])
# also pack what is finished so far, so it can be downloaded while Dia keeps running
r = subprocess.run("cd /content/tts && tar czf partial.tgz out/kokoro out/orpheus ref && ls -la partial.tgz",
                   shell=True, capture_output=True, text=True)
print(r.stdout, r.stderr)
