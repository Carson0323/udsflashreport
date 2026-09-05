"""Include the canonical executable specs in wheels without duplicating sources."""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithSpecs(build_py):
    def run(self):
        super().run()
        destination = Path(self.build_lib) / "flashreport_core" / "resources" / "spec"
        destination.mkdir(parents=True, exist_ok=True)
        for name in ("findings.yaml", "report.schema.json", "config.schema.json"):
            self.copy_file(str(Path(__file__).parent / "spec" / name), str(destination / name))


setup(cmdclass={"build_py": BuildWithSpecs})
