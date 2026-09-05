"""Verify an extracted wheel in isolation from the source checkout.

Run with the project's dependency environment. Python -I plus an asserted
import path prevents an editable source install from hiding missing resources.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def check(wheel: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="flashreport-wheel-") as temporary:
        target = Path(temporary)
        with zipfile.ZipFile(wheel) as archive:
            required = {
                "flashreport_core/resources/spec/findings.yaml",
                "flashreport_core/resources/spec/report.schema.json",
                "flashreport_core/resources/spec/config.schema.json",
                "flashreport_gui/assets/icons/flashreport.svg",
            }
            assert required <= set(archive.namelist()), "wheel is missing runtime resources"
            for name in archive.namelist():
                assert not {"private_corpus", "corpus", "artifacts"} & set(Path(name).parts)
                assert (target / name).resolve().is_relative_to(target.resolve())
            archive.extractall(target)
        script = '''
import json
import sys
from pathlib import Path
package_root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(package_root))
import flashreport_core
from flashreport_core.api import load_trace, analyze_trace, default_config, export_report
from flashreport_core.spec_utils import resolve_runtime_resource
assert Path(flashreport_core.__file__).resolve().is_relative_to(package_root)
assert resolve_runtime_resource("spec/findings.yaml").resolve().is_relative_to(package_root)
cfg = default_config()
samples = sorted(Path(sys.argv[2]).glob("*.asc"))
assert samples
for sample in samples:
    result = analyze_trace(load_trace(str(sample), cfg), cfg)
    exported = export_report(result, sample.stem + ".md", sample.stem + ".json")
    assert exported["validated"]
    assert json.loads(Path(sample.stem + ".json").read_text(encoding="utf-8"))["version"] == flashreport_core.__version__
print(f"Wheel {flashreport_core.__version__}: {len(samples)} public samples analyzed and exported outside the checkout")
'''
        subprocess.run(
            [sys.executable, "-I", "-c", script, str(target), str(root / "samples")],
            cwd=target, check=True, timeout=120,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    check(parser.parse_args().wheel.resolve())
