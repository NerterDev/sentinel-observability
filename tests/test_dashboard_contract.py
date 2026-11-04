"""Testes contratuais e determinísticos do Painel Web SPA (TASK-004).

Valida conformidade com:
  1. .harness/invariants/ux_contract.yaml (7 Estados Existenciais, 1 CTA primário,
     escala 4/8pt, anéis de foco, zero emojis em botões, fecho por Escape)
  2. src/theme.py (Sincronização estrita dos tokens de design)
  3. src/models.py (Consumo dos esquemas canónicos de telemetria)
"""

import unittest
from pathlib import Path
import re
from src.theme import DARK_THEME, SPACING, RADIUS

MODULAR_SCALE = {0, 4, 8, 12, 16, 24, 32, 48, 64, 80, 96, 128}

EMOJI_PATTERN = re.compile(
    r"[\U0001F300-\U0001F64F\U0001F680-\U0001F6FF\U0001F700-\U0001F77F"
    r"\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF"
    r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0]"
)

CSS_SPACING_RE = re.compile(
    r"\b(margin|padding|gap)(?:-(?:top|bottom|left|right))?\s*:\s*(\d+)px\b",
    re.IGNORECASE,
)
BUTTON_HTML_RE = re.compile(r"<button[^>]*>(.*?)</button>", re.IGNORECASE | re.DOTALL)


class TestDashboardContract(unittest.TestCase):
    """Suíte de verificação contratual do Frontend SPA estático."""

    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).resolve().parent.parent
        cls.dashboard_dir = cls.root_dir / "dashboard"
        cls.html_path = cls.dashboard_dir / "index.html"
        cls.css_path = cls.dashboard_dir / "styles.css"
        cls.js_path = cls.dashboard_dir / "app.js"

        cls.html_content = cls.html_path.read_text(encoding="utf-8")
        cls.css_content = cls.css_path.read_text(encoding="utf-8")
        cls.js_content = cls.js_path.read_text(encoding="utf-8")

    def test_dashboard_files_exist(self):
        """Verifica a existência física dos três ficheiros canónicos da SPA."""
        self.assertTrue(self.html_path.is_file(), "index.html deve existir em dashboard/")
        self.assertTrue(self.css_path.is_file(), "styles.css deve existir em dashboard/")
        self.assertTrue(self.js_path.is_file(), "app.js deve existir em dashboard/")

    def test_all_seven_existential_states_present_in_html(self):
        """Verifica se os 7 estados existenciais estão declarados no DOM de index.html."""
        # 1. EMPTY
        self.assertIn('id="state-empty"', self.html_content, "Estado EMPTY ausente no HTML")
        # 2. LOADING
        self.assertIn('id="state-loading"', self.html_content, "Estado LOADING ausente no HTML")
        # 3. POPULATED
        self.assertIn('id="state-populated"', self.html_content, "Estado POPULATED ausente no HTML")
        # 4. ZERO_RESULTS
        self.assertIn('id="state-zero-results"', self.html_content, "Estado ZERO_RESULTS ausente no HTML")
        # 5. PARTIAL_DEGRADED
        self.assertIn('id="state-partial-degraded"', self.html_content, "Estado PARTIAL_DEGRADED ausente no HTML")
        # 6. ERROR
        self.assertIn('id="state-error"', self.html_content, "Estado ERROR ausente no HTML")
        # 7. SUCCESS_FEEDBACK
        self.assertIn('id="toast-container"', self.html_content, "Container SUCCESS_FEEDBACK ausente no HTML")

    def test_action_hierarchy_single_primary_cta_in_header(self):
        """Garante estritamente 1 botão de ação primária (.btn-primary) no cabeçalho."""
        header_match = re.search(r"<header[^>]*>(.*?)</header>", self.html_content, re.DOTALL)
        self.assertIsNotNone(header_match, "Elemento <header> ausente no HTML")
        header_html = header_match.group(1)

        primary_buttons = re.findall(r'<button[^>]*class="[^"]*btn-primary[^"]*"[^>]*>', header_html)
        self.assertEqual(
            len(primary_buttons),
            1,
            f"O cabeçalho deve conter estritamente 1 ação primária, encontrados: {len(primary_buttons)}",
        )
        self.assertIn('id="btn-refresh"', primary_buttons[0])

    def test_zero_emojis_in_buttons(self):
        """Garante a ausência absoluta de emojis em botões funcionais do HTML."""
        for match in BUTTON_HTML_RE.finditer(self.html_content):
            btn_body = match.group(1)
            emoji_found = EMOJI_PATTERN.findall(btn_body)
            self.assertEqual(
                emoji_found,
                [],
                f"Botão funcional contém emojis proibidos ({emoji_found}): {btn_body.strip()[:60]}",
            )

    def test_accessibility_wai_aria_attributes(self):
        """Garante conformidade com padrões de acessibilidade WAI-ARIA."""
        # Skip-link para salto de navegação
        self.assertIn('class="skip-link"', self.html_content)
        # Modal com role="dialog" e aria-modal="true"
        self.assertIn('role="dialog"', self.html_content)
        self.assertIn('aria-modal="true"', self.html_content)
        # Tabs e painéis acessíveis
        self.assertIn('role="tablist"', self.html_content)
        self.assertIn('role="tab"', self.html_content)
        self.assertIn('role="tabpanel"', self.html_content)
        # Toasts com aria-live
        self.assertIn('aria-live="polite"', self.html_content)

    def test_css_design_tokens_aligned_with_theme_py(self):
        """Valida que as variáveis CSS mapeiam fielmente os tokens de src/theme.py."""
        self.assertIn(f"--surface: {DARK_THEME.SURFACE}", self.css_content)
        self.assertIn(f"--surface-card: {DARK_THEME.SURFACE_CARD}", self.css_content)
        self.assertIn(f"--surface-elevated: {DARK_THEME.SURFACE_ELEVATED}", self.css_content)
        self.assertIn(f"--border: {DARK_THEME.BORDER}", self.css_content)
        self.assertIn(f"--text-primary: {DARK_THEME.TEXT_PRIMARY}", self.css_content)
        self.assertIn(f"--text-secondary: {DARK_THEME.TEXT_SECONDARY}", self.css_content)
        self.assertIn(f"--action-primary: {DARK_THEME.ACTION_PRIMARY}", self.css_content)
        self.assertIn(f"--action-danger: {DARK_THEME.ACTION_DANGER}", self.css_content)
        self.assertIn(f"--status-success: {DARK_THEME.STATUS_SUCCESS}", self.css_content)
        self.assertIn(f"--status-warning: {DARK_THEME.STATUS_WARNING}", self.css_content)
        self.assertIn(f"--status-error: {DARK_THEME.STATUS_ERROR}", self.css_content)
        self.assertIn(f"--status-info: {DARK_THEME.STATUS_INFO}", self.css_content)

    def test_css_modular_scale_spacing_4_8pt(self):
        """Garante que todos os espaçamentos no CSS cumprem a escala modular 4/8pt."""
        violations = []
        for line_no, line in enumerate(self.css_content.splitlines(), start=1):
            for match in CSS_SPACING_RE.finditer(line):
                prop, val_str = match.group(1), match.group(2)
                val = int(val_str)
                if val not in MODULAR_SCALE and val % 8 != 0:
                    violations.append((line_no, prop, val))

        self.assertEqual(
            violations,
            [],
            f"Espaçamentos não-modulares detetados em styles.css: {violations}",
        )

    def test_css_focus_visible_ring_present(self):
        """Garante que a navegação por teclado tem anel de foco visível (:focus-visible)."""
        self.assertIn(":focus-visible", self.css_content)
        self.assertIn("outline:", self.css_content)

    def test_js_escape_key_listener_present(self):
        """Garante que o JavaScript escuta o evento Escape para fecho determinístico do modal."""
        self.assertTrue(
            "Escape" in self.js_content,
            "Listener da tecla Escape ausente no app.js",
        )
        self.assertTrue(
            "closeForensicModal" in self.js_content,
            "Função closeForensicModal() ausente no app.js",
        )

    def test_js_handles_async_fetch_with_states(self):
        """Garante que app.js efetua carregamento assíncrono com tratamento para todos os estados."""
        self.assertIn("fetch(", self.js_content)
        self.assertIn("Promise.allSettled", self.js_content)
        self.assertIn("current_status.json", self.js_content)
        self.assertIn("history.json", self.js_content)
        self.assertIn("LOADING", self.js_content)
        self.assertIn("EMPTY", self.js_content)
        self.assertIn("ZERO_RESULTS", self.js_content)
        self.assertIn("PARTIAL_DEGRADED", self.js_content)
        self.assertIn("ERROR", self.js_content)
        self.assertIn("POPULATED", self.js_content)

    def test_js_exports_sentinel_app_object(self):
        """Garante que app.js expõe o namespace global para testabilidade."""
        self.assertIn("window.SentinelApp", self.js_content)
        self.assertIn("initDashboard", self.js_content)
        self.assertIn("applyFilters", self.js_content)
        self.assertIn("showToast", self.js_content)


if __name__ == "__main__":
    unittest.main()

