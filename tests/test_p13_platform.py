"""Platform files for the production cluster. No staging target."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_staging_targets_are_gone() -> None:
    for path in (
        ROOT / "infra" / "terraform" / "staging",
        ROOT / "infra" / "terraform" / "envs" / "staging",
        ROOT / "deploy" / "k8s" / "staging",
    ):
        assert not path.exists(), path


def test_deploy_workflow_is_prod_only() -> None:
    text = (ROOT / ".github" / "workflows" / "deploy-k8s.yml").read_text(encoding="utf-8")
    assert "staging" not in text
    assert "KUBECONFIG_B64" not in text
    assert "environment: prod" in text
    assert "helm upgrade --install" in text
    assert "--atomic" in text


def test_chart_has_service_workers_and_migration() -> None:
    templates = ROOT / "deploy" / "k8s" / "linas" / "templates"
    names = {path.name: path.read_text(encoding="utf-8") for path in templates.glob("*.yaml")}
    combined = "\n".join(names.values())
    assert "kind: Service" in names["service.yaml"]
    assert "worker-interactive" in names["workloads.yaml"]
    assert "name: scheduler" in names["workloads.yaml"]
    assert "alembic" in names["migrate.yaml"]
    assert "kind: HorizontalPodAutoscaler" in combined


def test_render_cluster_env_does_not_print_values(tmp_path: Path, capsys) -> None:
    spec = importlib.util.spec_from_file_location(
        "render_cluster_env",
        ROOT / "scripts" / "ops" / "render_cluster_env.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pg = tmp_path / "pg.json"
    redis = tmp_path / "redis.json"
    out = tmp_path / "out.env"
    pg.write_text(json.dumps({"uri": "postgresql://db.example/app"}), encoding="utf-8")
    redis.write_text(json.dumps([{"uri": "rediss://cache.example:25061"}]), encoding="utf-8")
    argv = sys.argv
    sys.argv = ["render_cluster_env.py", str(pg), str(redis), str(out)]
    try:
        assert module.main() == 0
    finally:
        sys.argv = argv
    text = out.read_text(encoding="utf-8")
    assert "LINAS_WHATSAPP_DATABASE_URL=postgresql://db.example/app" in text
    printed = capsys.readouterr().out
    assert "postgresql://db.example/app" not in printed
    assert "env_keys" in printed
