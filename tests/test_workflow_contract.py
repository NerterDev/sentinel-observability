"""Testes contratuais e determinísticos da esteira CI/CD e Runbook (TASK-005).

Valida conformidade com:
  1. .github/workflows/sentinel_engine.yml (Sintaxe YAML, triggers, cron 30m,
     permissões restritas, prevenção de loop [skip ci] e deploy GitHub Pages)
  2. .env.example (Variáveis canónicas de ambiente e segredos de WAF)
  3. README.md (Runbook operacional completo e garantia Zero-Footprint)
"""

import unittest
from pathlib import Path
import yaml


class TestWorkflowContract(unittest.TestCase):
    """Suíte de testes da esteira de automação CI/CD e documentação operacional."""

    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).resolve().parent.parent
        cls.workflow_path = cls.root_dir / ".github" / "workflows" / "sentinel_engine.yml"
        cls.env_example_path = cls.root_dir / ".env.example"
        cls.readme_path = cls.root_dir / "README.md"

        cls.assertTrue(
            cls.workflow_path.is_file(),
            f"Ficheiro de workflow ausente: {cls.workflow_path}",
        )
        cls.assertTrue(
            cls.env_example_path.is_file(),
            f"Ficheiro .env.example ausente: {cls.env_example_path}",
        )
        cls.assertTrue(
            cls.readme_path.is_file(),
            f"Ficheiro README.md ausente: {cls.readme_path}",
        )

        cls.workflow_raw = cls.workflow_path.read_text(encoding="utf-8")
        cls.workflow_data = yaml.safe_load(cls.workflow_raw)
        cls.env_raw = cls.env_example_path.read_text(encoding="utf-8")
        cls.readme_raw = cls.readme_path.read_text(encoding="utf-8")

    def test_workflow_yaml_valid_structure(self):
        """Verifica se o YAML do GitHub Actions é sintaticamente válido."""
        self.assertIsInstance(self.workflow_data, dict, "Workflow deve ser um dicionário YAML")
        self.assertIn("name", self.workflow_data)
        self.assertIn("jobs", self.workflow_data)
        self.assertIn("observe-and-deploy", self.workflow_data["jobs"])

    def test_workflow_triggers_cron_and_dispatch(self):
        """Valida que o trigger inclui cron de 30 minutos e workflow_dispatch."""
        triggers = self.workflow_data.get("on") or self.workflow_data.get(True)
        self.assertIsNotNone(triggers, "Secção 'on' de triggers ausente no workflow")

        # 1. Cron de 30m
        self.assertIn("schedule", triggers, "Trigger 'schedule' ausente")
        schedules = triggers["schedule"]
        self.assertTrue(len(schedules) > 0)
        cron_expr = schedules[0].get("cron")
        self.assertEqual(
            cron_expr,
            "*/30 * * * *",
            f"Cron deve ser '*/30 * * * *', encontrado: {cron_expr}",
        )

        # 2. Workflow dispatch
        self.assertIn("workflow_dispatch", triggers, "Trigger 'workflow_dispatch' ausente")
        inputs = triggers["workflow_dispatch"].get("inputs", {})
        self.assertIn("site", inputs, "Input 'site' ausente no workflow_dispatch")
        self.assertIn("skip_browser", inputs, "Input 'skip_browser' ausente no workflow_dispatch")

    def test_workflow_permissions_least_privilege(self):
        """Garante que as permissões do workflow seguem o princípio de menor privilégio."""
        permissions = self.workflow_data.get("permissions", {})
        self.assertEqual(
            permissions.get("contents"),
            "write",
            "Permissão 'contents: write' mandatória para commit GitOps de telemetria",
        )
        self.assertEqual(
            permissions.get("pages"),
            "write",
            "Permissão 'pages: write' mandatória para publicação no GitHub Pages",
        )
        self.assertEqual(
            permissions.get("id-token"),
            "write",
            "Permissão 'id-token: write' mandatória para OIDC do GitHub Pages",
        )

    def test_workflow_anti_loop_ci_skip(self):
        """Garante a presença da marcação [skip ci] no commit GitOps para prevenir recursão."""
        self.assertIn(
            "[skip ci]",
            self.workflow_raw,
            "A flag '[skip ci]' deve estar presente no comando de commit do workflow",
        )

    def test_workflow_installs_playwright_chromium_with_deps(self):
        """Garante que o passo de instalação do Playwright inclui o Chromium e dependências de SO."""
        self.assertIn(
            "playwright install --with-deps chromium",
            self.workflow_raw,
            "Comando 'playwright install --with-deps chromium' ausente no workflow",
        )

    def test_workflow_deploys_dashboard_to_pages(self):
        """Valida que o workflow contém as actions canónicas de upload e deploy no GitHub Pages."""
        self.assertIn(
            "actions/upload-pages-artifact",
            self.workflow_raw,
            "Action 'actions/upload-pages-artifact' ausente no workflow",
        )
        self.assertIn(
            "actions/deploy-pages",
            self.workflow_raw,
            "Action 'actions/deploy-pages' ausente no workflow",
        )
        self.assertIn(
            "path: 'dashboard'",
            self.workflow_raw.replace('"', "'"),
            "Caminho do artefacto de pages deve ser 'dashboard'",
        )

    def test_env_example_contains_mandatory_variables(self):
        """Verifica se .env.example documenta a variável WAF_BYPASS_TOKEN e diretórios canónicos."""
        self.assertIn("WAF_BYPASS_TOKEN=", self.env_raw)
        self.assertIn("CONFIG_DIR=", self.env_raw)
        self.assertIn("OUTPUT_DIR=", self.env_raw)
        self.assertIn("SCREENSHOTS_DIR=", self.env_raw)

    def test_readme_contains_zero_footprint_and_architecture(self):
        """Garante que o README.md contém a garantia Zero-Footprint e documentação operacional."""
        self.assertIn("Zero-Footprint", self.readme_raw)
        self.assertIn("sites.json", self.readme_raw)
        self.assertIn("thresholds.json", self.readme_raw)
        self.assertIn("WAF_BYPASS_TOKEN", self.readme_raw)
        self.assertIn("orchestrator", self.readme_raw)
        self.assertIn("GitHub Pages", self.readme_raw)


if __name__ == "__main__":
    unittest.main()

