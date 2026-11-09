#!/usr/bin/env python3
"""Regression tests for the skill's helper scripts. No pytest needed:

    python3 tests/test_skill_scripts.py

Static tests need only the standard library. Runner tests need nbformat, nbclient and
ipykernel, and are skipped with a note when those are missing.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "paper-to-prototype" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import lint  # noqa: E402

FAILURES: list[str] = []


def check(ok: bool, label: str) -> None:
    if not ok:
        FAILURES.append(label)
        print(f"FAIL  {label}")


def blocked(src: str) -> bool:
    return bool(lint.check_security([(0, src)]))


# Each of these must be BLOCKED. Most came from adversarial review rounds.
MUST_BLOCK = {
    "getattr string-built os.system": "import os\ngetattr(os, 'sys'+'tem')('id')",
    "vars(os)": "import os\nvars(os)['system']('id')",
    "import os as o": "import os as o\nprint(o.environ)",
    "from os import environ": "from os import environ\nprint(environ)",
    "sys.modules": "import sys\nsys.modules['os'].environ",
    "import posix": "import posix\nposix.environ",
    "__import__": "__import__('os').environ",
    "__import__ via variable": "f = __import__\nf('os')",
    "get_ipython": "get_ipython().system('id')",
    "IPython import": "from IPython import get_ipython\nget_ipython().system('id')",
    "os.execvp": "import os\nos.execvp('sh', ['sh'])",
    "os.posix_spawn": "import os\nos.posix_spawn('/bin/sh', ['sh'], {})",
    "builtins.open": "import builtins\nbuiltins.open('/etc/passwd').read()",
    "io.open": "import io\nio.open('/etc/passwd').read()",
    "aliased open": "f = open\nf('/etc/passwd')",
    "open": "open('/etc/passwd').read()",
    "np.loadtxt": "import numpy as np\nnp.loadtxt('/etc/hostname', dtype=str)",
    "np.fromfile": "import numpy as np\nnp.fromfile('/etc/hostname')",
    "np.genfromtxt": "import numpy as np\nnp.genfromtxt('/etc/hostname', dtype=str)",
    "np.load": "import numpy as np\nnp.load('x.npy', allow_pickle=True)",
    "np.save": "import numpy as np\nnp.save('x', np.zeros(2))",
    "from numpy import loadtxt as lt": "from numpy import loadtxt as lt\nlt('x')",
    "star import": "from numpy import *\nloadtxt('x')",
    "np.os": "import numpy as np\nnp.os.system('id')",
    "matplotlib.os": "import matplotlib\nmatplotlib.os.environ",
    "np.DataSource": "import numpy as np\nnp.DataSource().open('http://x')",
    "np.lib.npyio": "import numpy as np\nnp.lib.npyio.open",
    "np.ctypeslib": "import numpy as np\nnp.ctypeslib.load_library('a', '.')",
    "np __dict__": "import numpy as np\nnp.__dict__['loadtxt']('x')",
    "getattr np load": "import numpy as np\ngetattr(np, 'lo'+'ad')('x')",
    "dunder subclasses": "().__class__.__bases__[0].__subclasses__()",
    "fetch_20newsgroups": "from sklearn.datasets import fetch_20newsgroups\nfetch_20newsgroups()",
    "datasets.fetch_openml": "from sklearn import datasets\ndatasets.fetch_openml('mnist_784')",
    "get_data_home": "from sklearn.datasets import get_data_home\nget_data_home()",
    "load_files": "from sklearn.datasets import load_files\nload_files('/etc')",
    "torchvision.datasets": "import torchvision\ntorchvision.datasets.MNIST('d', download=True)",
    "from torchvision import datasets": "from torchvision import datasets\ndatasets.MNIST('d')",
    "download kwarg": "import numpy as np\nfoo(download=True)",
    "torch.load": "import torch\ntorch.load('x.pt')",
    "torch.hub": "import torch.hub\ntorch.hub.load('a', 'b')",
    "pd.read_csv url": "import pandas as pd\npd.read_csv('http://x/y.csv')",
    "df.to_csv": "import pandas as pd\npd.DataFrame().to_csv('/tmp/x')",
    "plt.imread": "import matplotlib.pyplot as plt\nplt.imread('/etc/passwd')",
    "plt.savefig": "import matplotlib.pyplot as plt\nplt.savefig('/tmp/x.png')",
    "get_sample_data": "import matplotlib.cbook as c\nc.get_sample_data('x')",
    "scipy.io": "import scipy.io\nscipy.io.loadmat('x')",
    "scipy.io attr": "import scipy\nscipy.io.loadmat('x')",
    "PIL": "from PIL import Image\nImage.open('/etc/passwd')",
    "pickle": "import pickle\npickle.loads(b'x')",
    "subprocess": "import subprocess\nsubprocess.run(['id'])",
    "socket": "import socket\nsocket.socket()",
    "requests": "import requests\nrequests.get('http://x')",
    "urllib": "import urllib.request\nurllib.request.urlopen('http://x')",
    "importlib": "import importlib\nimportlib.import_module('os')",
    "pathlib": "import pathlib\npathlib.Path('/etc/passwd').read_text()",
    "shutil": "import shutil\nshutil.rmtree('x')",
    "ctypes": "import ctypes",
    "eval": "eval('1+1')",
    "exec": "exec('x=1')",
    "compile": "compile('1', 'x', 'eval')",
    "setattr": "setattr(object, 'x', 1)",
    "globals": "globals()['__builtins__']",
    "shell escape": "!curl http://x.y",
    "cell magic": "%%bash\nid",
    "pip magic": "%pip install requests",
    "run magic": "%run other.py",
    "relative import": "from . import x",
    "private module alias": "import collections\ncollections._sys.modules",
    "private name import": "from collections import _sys",
    "private attr of module": "import numpy as np\nnp._globals",
    "banned module as attribute": "import matplotlib\nmatplotlib.shutil.rmtree('x')",
    "pathlib as attribute": "import numpy as np\nnp.testing.extbuild.pathlib.Path('/etc/hostname').read_text()",
    "pickle as attribute": "import pandas as pd\npd.core.generic.pickle.loads(b'')",
    "warnings.formatwarning": "import warnings\nwarnings.formatwarning('m', UserWarning, '/etc/hostname', 1, None)",
    "warnings.showwarning": "import warnings\nwarnings.showwarning('m', UserWarning, 'f', 1)",
    "unanalysable huge expression": "x = " + "1+" * 200000 + "1",
    "syntax error": "def f(:\n  pass",
}

# Each of these must NOT be blocked: ordinary reproduction code.
MUST_PASS = {
    "digits + matplotlib": "%matplotlib inline\nimport numpy as np\nimport matplotlib.pyplot as plt\n"
                           "from sklearn.datasets import load_digits\nX, y = load_digits(return_X_y=True)\n"
                           "np.random.seed(0)\nplt.plot(X[0]); plt.show()",
    "blobs + sklearn": "from sklearn.datasets import make_blobs\nfrom sklearn.model_selection import train_test_split\n"
                       "from sklearn.linear_model import LogisticRegression\nX, y = make_blobs(200)\n"
                       "LogisticRegression().fit(*train_test_split(X, y)[::2])",
    "torch module": "import torch\nimport torch.nn as nn\nimport torch.nn.functional as F\n"
                    "from torch import optim\nclass M(nn.Module):\n    def forward(self, x):\n        return F.relu(x)",
    "stdlib data structures": "from collections import deque, defaultdict\nimport heapq, itertools, math, random, time\n"
                              "from dataclasses import dataclass\nfrom typing import List\n"
                              "w = deque(maxlen=5)\nw.append(1)\nitems = [1, 2]\nitems.remove(1)\ns = 'a'.replace('a', 'b')",
    "variables named like APIs": "load = 1\nsave = 2\nlink = 3\nwalk = 4\nsystem = 5\nprint(load + save)",
    "docstring URL": 'def f():\n    """See https://arxiv.org/abs/cs/0610 for the method."""\n    return 1',
    "scipy stats": "import scipy.stats as st\nfrom scipy.special import expit\nfrom scipy.spatial.distance import cdist\n"
                   "import scipy.sparse as sp\nst.norm.cdf(0)",
    "pca/tsne": "from sklearn.decomposition import PCA\nfrom sklearn.manifold import TSNE\nPCA(2)",
    "default_rng": "import numpy as np\nrng = np.random.default_rng(0)\nrng.normal(size=3)",
    "subplots": "import matplotlib.pyplot as plt\nfig, ax = plt.subplots(1, 2)\nax[0].set_xlabel('x')\nplt.show()",
    "self private attrs": "class A:\n    def __init__(self):\n        self._items = []\n"
                          "    def add(self, x):\n        self._items.append(x)\n        return self._items",
    "warnings filter": "import warnings\nwarnings.filterwarnings('ignore')\nwarnings.warn('x')",
    "re and statistics": "import re, statistics\nre.compile('a')\nstatistics.mean([1, 2])",
}

for name, src in MUST_BLOCK.items():
    check(blocked(src), f"should be BLOCKED: {name}")
for name, src in MUST_PASS.items():
    problems = lint.check_security([(0, src)])
    check(not problems, f"should PASS: {name}  -> {problems}")

# v3 notebooks must be seen by lint exactly as the runner will see them
try:
    import nbformat
    v3 = {"nbformat": 3, "nbformat_minor": 0, "metadata": {}, "worksheets": [{"cells": [
        {"cell_type": "code", "language": "python", "input": "import subprocess\nsubprocess.check_output(['id'])",
         "outputs": [], "collapsed": False}]}]}
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "v3.ipynb"
        p.write_text(json.dumps(v3))
        check(bool(lint.check_security(lint.cells_from_notebook(p))), "v3 notebook with subprocess is BLOCKED")
except ImportError:
    print("note: nbformat missing, skipped the v3 notebook test")

# spec checks
with tempfile.TemporaryDirectory() as d:
    sp = Path(d) / "spec.json"
    sp.write_text(json.dumps({"title": "x"}))
    b, _ = lint.check_spec(sp)
    check(any("pass_condition" in m for m in b) and any("conventions" in m for m in b),
          "spec without conventions/pass_condition is blocking")

# contract warnings: comments must not satisfy them, docstring URLs must not warn
w = lint.check_contract([(0, "# np.random.seed(0)\nx = 1")])
check(any("seed" in m for m in w), "a seed in a comment does not count")
w = lint.check_contract([(0, 'def f():\n    """https://x.y"""\n    return 1')])
check(not any("URL" in m for m in w), "docstring URL does not warn")

# runner tests
def have(n: str) -> bool:
    return importlib.util.find_spec(n) is not None

if all(have(n) for n in ("nbformat", "nbclient", "ipykernel", "numpy", "matplotlib")):
    def run_cells(cells, *extra, env=None):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            nb = nbformat.v4.new_notebook()
            nb.cells = [nbformat.v4.new_code_cell(c) for c in cells]
            p = d / "t.ipynb"
            nbformat.write(nb, str(p))
            e = dict(os.environ, **(env or {}))
            r = subprocess.run([sys.executable, str(SCRIPTS / "run_notebook.py"), str(p), "--figures-dir",
                                str(d / "figs"), *extra], capture_output=True, text=True, env=e, timeout=300)
            out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
            return r.returncode, out, nbformat.read(str(p), as_version=4)

    good = ("import numpy as np, matplotlib.pyplot as plt\nnp.random.seed(0)\nx = np.linspace(0, 6, 20)\n"
            "print('m', float(np.sin(x).mean()))\nprint('PASS')",
            "plt.plot(x, np.sin(x)); plt.xlabel('x'); plt.ylabel('y'); plt.show()")
    rc, out, _ = run_cells(good)
    check(rc == 0 and out.get("success") and len(out.get("figures", [])) == 1 and not out.get("warnings"),
          f"clean notebook runs with one figure and no warnings: {out}")

    rc, out, _ = run_cells(["import subprocess"])
    check(rc == 1 and out.get("error_name") == "BlockedBySecurityCheck", "runner refuses a blocked notebook")

    rc, out, _ = run_cells(["print(undefined_name)"])
    check(rc == 1 and out.get("error_cell_index") == 0 and out.get("error_name") == "NameError",
          "runner reports the failing cell")

    rc, out, _ = run_cells(["while True: pass"], "--timeout", "3")
    check(rc == 1 and out.get("error_name") == "Timeout" and "per-cell" in out.get("error_value", ""),
          f"per-cell timeout is reported as such: {out.get('error_value')}")

    rc, out, _ = run_cells(["import time; time.sleep(2)", "import time; time.sleep(2)"], "--total-timeout", "3")
    check(rc == 1 and out.get("error_name") == "Timeout" and "total budget" in out.get("error_value", ""),
          "total budget is enforced")

    # secrets: allow-listed env only. --allow-unsafe because reading os.environ is blocked by design.
    leak_cells = ["import os\nprint(sorted(k for k in os.environ if k.startswith('P2P_TEST_')))\nprint(os.environ.get('PATH') is not None)"]
    rc, out, nb = run_cells(leak_cells, "--allow-unsafe", env={
        "P2P_TEST_GITHUB_PAT": "x", "P2P_TEST_DATABASE_URL": "x", "P2P_TEST_KEY": "x", "P2P_TEST_ANY": "x"})
    text = "".join(nb.cells[0].outputs[0].get("text", "")) if rc == 0 else ""
    check(rc == 0 and text.splitlines()[0] == "[]" and text.splitlines()[1] == "True",
          f"kernel sees none of the extra env vars but still has PATH: {text!r}")

    rc, out, _ = run_cells(["x = 1"])
    check(rc == 0 and len(out.get("warnings", [])) == 2, "no-figure / no-output warnings fire")

    # the kernel runs on the same interpreter as the script
    rc, out, nb = run_cells(["import sys\nprint(sys.executable)"], "--allow-unsafe")  # sys is blocked by design
    got = "".join(nb.cells[0].outputs[0].get("text", "")).strip() if rc == 0 else ""
    check(rc == 0 and os.path.realpath(got) == os.path.realpath(sys.executable), f"kernel uses sys.executable: {got}")
else:
    print("note: runner dependencies missing, skipped runner tests")

# build_notebook
if have("nbformat"):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "c.json").write_text(json.dumps([{"type": "Code", "source": ["a = 1", "b = 2"]}]))
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_notebook.py"), str(d / "c.json"), str(d / "o.ipynb")],
                           capture_output=True, text=True)
        nb = json.loads((d / "o.ipynb").read_text())
        check(r.returncode == 0 and "".join(nb["cells"][0]["source"]) == "a = 1\nb = 2",
              "line lists are joined with newlines and Code is accepted")
        (d / "bad.json").write_text(json.dumps([{"type": "code", "source": "  "}]))
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_notebook.py"), str(d / "bad.json"), str(d / "o2.ipynb")],
                           capture_output=True, text=True)
        check(r.returncode == 2 and "empty" in r.stderr, "empty code cell is rejected cleanly")

print(f"\n{len(MUST_BLOCK)} must-block and {len(MUST_PASS)} must-pass static cases checked.")
if FAILURES:
    print(f"{len(FAILURES)} FAILED")
    sys.exit(1)
print("all tests passed")
