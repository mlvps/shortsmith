"""Config loader. Reads `config.yaml` (or path passed in) and resolves paths."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Config:
    raw: dict
    project_root: Path

    def _p(self, *keys: str, default: Any = None) -> Any:
        cur: Any = self.raw
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    def path(self, key: str) -> Path:
        rel = self._p("paths", key, default=key)
        p = Path(rel)
        return p if p.is_absolute() else self.project_root / p

    @property
    def template_path(self) -> Path:
        rel = self._p("template", "path", default="template/template.mov")
        p = Path(rel)
        return p if p.is_absolute() else self.project_root / p

    @property
    def hooks_path(self) -> Path:
        return self.path("hooks_file")

    @property
    def out_dir(self) -> Path:
        return self.path("out_dir")

    @property
    def source_dir(self) -> Path:
        return self.path("source_dir")

    @property
    def final_dir(self) -> Path:
        return self.path("final_dir")

    @property
    def reports_dir(self) -> Path:
        return self.path("reports_dir")

    @property
    def uploaded_path(self) -> Path:
        return self.path("uploaded_file")

    @property
    def priority_path(self) -> Path:
        return self.path("priority_file")

    @property
    def client_secret_path(self) -> Path:
        return self.path("client_secret")

    @property
    def upload_token_path(self) -> Path:
        return self.path("upload_token")

    @property
    def analyze_token_path(self) -> Path:
        return self.path("analyze_token")

    @property
    def ntfy_topic(self) -> str:
        return self._p("ntfy", "topic", default="") or ""

    def get(self, *keys: str, default: Any = None) -> Any:
        return self._p(*keys, default=default)


DEFAULT_CONFIG_NAME = "config.yaml"


def load(path: Path | str | None = None) -> Config:
    if path is None:
        # Walk upward from cwd looking for config.yaml.
        cur = Path.cwd().resolve()
        for d in [cur, *cur.parents]:
            cand = d / DEFAULT_CONFIG_NAME
            if cand.exists():
                path = cand
                break
        if path is None:
            raise SystemExit(
                f"no {DEFAULT_CONFIG_NAME} found. copy config.example.yaml to config.yaml first."
            )
    p = Path(path).resolve()
    raw = yaml.safe_load(p.read_text())
    return Config(raw=raw, project_root=p.parent)
