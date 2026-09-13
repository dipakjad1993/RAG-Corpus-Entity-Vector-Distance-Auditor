"""Shared Material 3 design system for every RAG-EVDA surface.

Single source of truth for the visual language used across the self-contained
HTML report, the narrative pages and the Flask web app:

* **Pixel-first typography**: `'Google Sans','Product Sans'` lead the stack so
  Pixel phones and Android devices render the genuine Pixel typeface; everywhere
  else it falls back to locally-bundled **Roboto Flex** (Material 3's official
  Pixel-fallback typeface), base64-embedded as a ``data:`` URI so every surface
  is *fully offline and self-contained* — no CDN ``@import`` calls, no external
  font files (a dashboard can even be emailed and opened standalone).
* Authentic **Material 3 / M3 Expressive color tokens** (primary / secondary /
  tertiary / surfaces / outline) with dark & light tonal palettes, expressive
  shapes (20–28px cards, pill buttons), spring easing, and a working runtime
  light/dark toggle (`body.light` scope + `color-scheme`). Component styles
  reference token *variables* only — no mood is ever baked in, so toggling the
  theme re-renders every color correctly.
* M3 elevation, shape (roundness) and type-scale tokens, plus shared
  component styles (top app bar, navigation, cards, chips, tables, buttons,
  progress) so dashboard, narrative and web pages stay visually consistent.

The font file lives at project-root ``assets/fonts/RobotoFlex-Variable.woff2``.
If it is missing, the design system degrades gracefully to a system font stack
rather than erroring — the tool must never hard-fail on a cosmetic asset.
"""

from __future__ import annotations

import base64
import os
from typing import Dict, Optional

# Project root = parent of the ragevda package.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FONT_REL = os.path.join("assets", "fonts", "RobotoFlex-Variable.woff2")

FONT_FAMILY = "Roboto Flex"
# Pixel-first stack: Google Sans / Product Sans ship on Pixel phones and many
# Android devices, so the UI renders the genuine Pixel typeface there; every-
# where else it falls back to the locally-bundled Roboto Flex (Material 3's
# official Pixel-fallback typeface, embedded as a data URI — fully offline).
# Google Sans itself is proprietary and cannot be redistributed, hence the
# prefer-but-fallback stack rather than a download.
_FONT_FALLBACK = (
    "'Google Sans','Product Sans','Google Sans Text',"
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
)

# 2026 Enterprise "Midnight Aurora" — vivid indigo + cyan + emerald on deep navy.
# Replaces the flat grey-purple M3 baseline that looked dated. Dark surfaces
# carry a blue tint, primary is electric indigo, secondary is cyan,
# tertiary is emerald. Light mode is an icy indigo-tinted paper, not beige-grey.
# Both expose identical token names so dark<->light toggle still re-renders.
_M3_DARK = {
    "primary": "#818CF8", "on-primary": "#101130",
    "primary-container": "#2E33A6", "on-primary-container": "#E7E7FF",
    "secondary": "#22D3EE", "on-secondary": "#062A33",
    "secondary-container": "#0E3A45", "on-secondary-container": "#C9F6FF",
    "tertiary": "#34D399", "on-tertiary": "#052E22",
    "tertiary-container": "#064E3B", "on-tertiary-container": "#D1FAE5",
    "error": "#FDA4AF", "on-error": "#450A0A",
    "error-container": "#7F1D1D", "on-error-container": "#FFE4E6",
    "surface": "#070C1D", "surface-dim": "#070C1D", "surface-bright": "#22304F",
    "surface-container-lowest": "#04070F", "surface-container-low": "#0B1226",
    "surface-container": "#111A33", "surface-container-high": "#182544",
    "surface-container-highest": "#1F2F56",
    "on-surface": "#EDF1FF", "on-surface-variant": "#A8B3CF",
    "outline": "#5B6B8C", "outline-variant": "#26314F", "scrim": "#000000",
}

_M3_LIGHT = {
    "primary": "#4F46E5", "on-primary": "#FFFFFF",
    "primary-container": "#E0E7FF", "on-primary-container": "#1E1B4B",
    "secondary": "#0891B2", "on-secondary": "#FFFFFF",
    "secondary-container": "#CFFAFE", "on-secondary-container": "#164E63",
    "tertiary": "#059669", "on-tertiary": "#FFFFFF",
    "tertiary-container": "#D1FAE5", "on-tertiary-container": "#064E3B",
    "error": "#DC2626", "on-error": "#FFFFFF",
    "error-container": "#FECACA", "on-error-container": "#7F1D1D",
    "surface": "#F5F7FF", "surface-dim": "#DDE3F5", "surface-bright": "#FFFFFF",
    "surface-container-lowest": "#FFFFFF", "surface-container-low": "#EFF3FF",
    "surface-container": "#E8EDFF", "surface-container-high": "#DDE5FA",
    "surface-container-highest": "#D2DCF5",
    "on-surface": "#0B1226", "on-surface-variant": "#4A5878",
    "outline": "#7C8AA8", "outline-variant": "#C4CDE3", "scrim": "#000000",
}

# Elevation tints follow the new navy / icy surfaces.
_DARK_ELEVATION = ["#070C1D", "#111A33", "#182544", "#1F2F56", "#22304F"]
_LIGHT_ELEVATION = ["#FFFFFF", "#E8EDFF", "#DDE5FA", "#D2DCF5", "#C6D4F2"]


def _font_face() -> str:
    """@font-face for the locally bundled Roboto Flex variable font (data URI)."""
    path = os.path.join(_PROJECT_ROOT, _FONT_REL)
    if os.path.exists(path):
        try:
            with open(path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            return (
                "@font-face{font-family:'%s';font-style:normal;font-weight:100 1000;"
                "font-stretch:100%%;font-display:swap;"
                "src:url(data:font/woff2;base64,%s) format('woff2');}" % (FONT_FAMILY, b64)
            )
        except OSError:
            pass
    return ""


# Loading the 34 KB font once at import keeps repeated renders cheap.
_FONT_FACE_CSS = _font_face()


def font_css() -> str:
    """Return the @font-face CSS (empty string if font unavailable)."""
    return _FONT_FACE_CSS


def _palette(mood: str) -> Dict[str, str]:
    return (_M3_LIGHT if mood == "light" else _M3_DARK)





def material_css(mood: str, selector: str = ":root") -> str:
    """Material 3 color/type/shape tokens under ``selector`` (no component rules).

    For the webapp the light palette is scoped under ``body.light`` (plus
    ``body[data-theme="light"]`` alias) so the dark ``:root`` tokens stay intact
    for runtime theme toggling. Component styles are emitted separately once via
    :func:`components_css`. Token names intentionally match every
    ``var(--m3-*)`` reference used by components/history/dashboard/narrative so
    toggling the theme re-renders every color correctly in both modes.
    """
    p = _palette(mood)
    elev = _LIGHT_ELEVATION if mood == "light" else _DARK_ELEVATION

    def v(name: str) -> str:
        return str(p.get(name, ""))

    # Type scale — 2026 Pixel stack: Google Sans / Product Sans on Pixel phones,
    # Roboto Flex fallback everywhere else (embedded offline as data URI).
    type_scale = f"""
  --type-display:400 57px/normal '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-display-l:400 45px/normal '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-headline-l:400 36px/normal '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-headline-m:400 28px/normal '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-headline-s:400 24px/normal '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-title-l:400 22px/normal '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-title-m:500 16px/normal '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-title-s:500 14px/normal '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-body-l:400 16px/1.6 '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-body-m:400 14px/1.6 '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-body-s:400 12px/1.55 '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-label-l:500 14px/1.4 '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-label-m:500 12px/1.4 '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-label-s:500 11px/1.4 '{FONT_FAMILY}',{_FONT_FALLBACK};
  --type-mono:500 12px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
"""
    shadow_1 = ("0 1px 2px rgba(28,27,31,.08),0 1px 3px rgba(28,27,31,.10)"
                if mood == "light" else
                "0 1px 3px rgba(0,0,0,.3),0 1px 2px rgba(0,0,0,.24)")
    shadow_2 = ("0 2px 6px rgba(28,27,31,.10),0 1px 4px rgba(28,27,31,.08)"
                if mood == "light" else
                "0 2px 6px rgba(0,0,0,.24),0 1px 4px rgba(0,0,0,.22)")
    shadow_3 = ("0 8px 20px rgba(79,70,229,.22),0 2px 8px rgba(28,27,31,.10)"
                if mood == "light" else
                "0 6px 18px rgba(34,211,238,.18),0 2px 8px rgba(0,0,0,.30)")
    color_block = f"""
  color-scheme:{'light' if mood == 'light' else 'dark'};
  --m3-primary:{v('primary')};
  --m3-on-primary:{v('on-primary')};
  --m3-primary-container:{v('primary-container')};
  --m3-on-primary-container:{v('on-primary-container')};
  --m3-secondary:{v('secondary')};
  --m3-on-secondary:{v('on-secondary')};
  --m3-secondary-container:{v('secondary-container')};
  --m3-on-secondary-container:{v('on-secondary-container')};
  --m3-tertiary:{v('tertiary')};
  --m3-on-tertiary:{v('on-tertiary')};
  --m3-tertiary-container:{v('tertiary-container')};
  --m3-on-tertiary-container:{v('on-tertiary-container')};
  --m3-error:{v('error')};
  --m3-on-error:{v('on-error')};
  --m3-error-container:{v('error-container')};
  --m3-on-error-container:{v('on-error-container')};
  --m3-surface:{v('surface')};
  --m3-surface-dim:{v('surface-dim')};
  --m3-surface-bright:{v('surface-bright')};
  --m3-surface-container-lowest:{v('surface-container-lowest')};
  --m3-surface-container-low:{v('surface-container-low')};
  --m3-surface-container:{v('surface-container')};
  --m3-surface-container-high:{v('surface-container-high')};
  --m3-surface-container-highest:{v('surface-container-highest')};
  --m3-surface-lowest:{v('surface-container-lowest')};
  --m3-surface-low:{v('surface-container-low')};
  --m3-surface-c:{v('surface-container')};
  --m3-surface-high:{v('surface-container-high')};
  --m3-surface-highest:{v('surface-container-highest')};
  --m3-on-surface:{v('on-surface')};
  --m3-on-surface-variant:{v('on-surface-variant')};
  --m3-outline:{v('outline')};
  --m3-outline-variant:{v('outline-variant')};
  --m3-scrim:{v('scrim')};
  --m3-elev-0:{elev[0]}; --m3-elev-1:{elev[1]};
  --m3-elev-2:{elev[2]}; --m3-elev-3:{elev[3]};
  --m3-shape-xs:10px; --m3-shape-s:14px; --m3-shape-m:20px;
  --m3-shape-l:28px; --m3-shape-full:999px;
  --m3-ease:cubic-bezier(.2,0,0,1);
  --m3-ease-spring:cubic-bezier(.34,1.4,.4,1);
  --m3-font:'{FONT_FAMILY}',{_FONT_FALLBACK};
  --m3-shadow-1:{shadow_1};
  --m3-shadow-2:{shadow_2};
  --m3-shadow-3:{shadow_3};
"""

    return selector + "{\n" + color_block + type_scale + "}\n"


def components_css(mood: str) -> str:
    """Component styles (emitted once) building on the M3 tokens."""
    return _COMPONENTS(mood, _palette(mood).get)


def _COMPONENTS(mood: str, v) -> str:
    """Shared component styles built on the M3 tokens above.

    All rules reference token *variables* only — never a hard-coded mood — so
    runtime dark<->light switching re-renders every color. The 2026 Pixel
    typeface (Google Sans / Product Sans with Roboto Flex fallback) is applied
    to every textual element via ``--m3-font``.
    """
    return """
* {box-sizing:border-box}
html,body{height:100%}
html{scroll-behavior:smooth}
body{
  margin:0; color:var(--m3-on-surface); font-family:var(--m3-font);
  font-size:14px; line-height:1.65; letter-spacing:.1px;
  -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
  background:var(--m3-surface);
  transition:background-color .35s var(--m3-ease), color .35s var(--m3-ease);
}
body *, body *::before, body *::after{font-family:var(--m3-font)}
body.theme-anim, body.theme-anim *, body.theme-anim *::before, body.theme-anim *::after{
  transition:background-color .35s var(--m3-ease), color .35s var(--m3-ease),
  border-color .35s var(--m3-ease), box-shadow .35s var(--m3-ease) !important;
}
a{color:var(--m3-primary); text-decoration:none}
a:hover{text-decoration:underline}
::selection{background:var(--m3-primary-container); color:var(--m3-on-primary-container)}
:focus-visible{outline:2px solid var(--m3-primary); outline-offset:2px; border-radius:8px}
.m3-app-bar{
  position:sticky; top:0; z-index:20; backdrop-filter:blur(16px) saturate(1.3);
  -webkit-backdrop-filter:blur(16px) saturate(1.3);
  background:color-mix(in srgb,var(--m3-surface-container) 86%, transparent);
  border-bottom:1px solid var(--m3-outline-variant);
}
.m3-app-inner{max-width:1280px; margin:0 auto; padding:12px 22px; display:flex;
  align-items:center; gap:16px}
.m3-logo{width:42px; height:42px; border-radius:14px; flex:0 0 auto;
  background:linear-gradient(135deg,var(--m3-primary) 0%,var(--m3-secondary) 55%,var(--m3-tertiary) 100%);
  color:var(--m3-on-primary); font-weight:800; font-size:15px; letter-spacing:-.3px;
  display:flex; align-items:center; justify-content:center;
  box-shadow:var(--m3-shadow-2)}
.m3-title{font-weight:700; font-size:17px; letter-spacing:-.2px; line-height:1.1}
.m3-title small{display:block; color:var(--m3-on-surface-variant); font-weight:500; font-size:11.5px}
.m3-nav{display:flex; gap:6px; margin-left:auto; flex-wrap:wrap}
.m3-nav a{color:var(--m3-on-surface-variant); padding:9px 14px; border-radius:var(--m3-shape-full);
  font-weight:600; font-size:13.5px; transition:.18s var(--m3-ease); white-space:nowrap}
.m3-nav a:hover{background:color-mix(in srgb,var(--m3-primary) 10%, transparent); color:var(--m3-on-surface); text-decoration:none}
.m3-nav a.on{background:var(--m3-secondary-container); color:var(--m3-on-secondary-container)}
.m3-container{max-width:1280px; margin:0 auto; padding:22px 22px 64px}
.m3-h1{font-size:clamp(26px,3.4vw,34px); line-height:1.12; font-weight:750; letter-spacing:-.6px; margin:4px 0 6px}
.m3-h2{font-size:20px; font-weight:700; letter-spacing:-.2px; margin:30px 0 10px;
  display:flex; align-items:center; gap:10px}
.m3-h2::before{content:""; width:4px; height:20px; border-radius:99px;
  background:linear-gradient(180deg,var(--m3-primary),var(--m3-secondary),var(--m3-tertiary)); flex:0 0 auto}
.m3-h3{font-size:15px; font-weight:600; margin:18px 0 6px}
.m3-lead{color:var(--m3-on-surface-variant); font-size:15px; max-width:880px;
  line-height:1.7; margin:6px 0 18px}
.m3-sub{color:var(--m3-on-surface-variant); font-size:13px}
.muted{color:var(--m3-on-surface-variant)}
.m3-card{
  background:var(--m3-surface-container-low); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-l); padding:22px 24px; box-shadow:var(--m3-shadow-1);
  transition:transform .3s var(--m3-ease), box-shadow .3s var(--m3-ease), background-color .35s var(--m3-ease), border-color .35s}
.m3-card:hover{transform:translateY(-2px); box-shadow:var(--m3-shadow-2)}
.m3-grid{display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); margin:16px 0}
.m3-kpi{background:var(--m3-surface-container-low); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m); padding:18px 20px; box-shadow:var(--m3-shadow-1);
  position:relative; overflow:hidden}
.m3-kpi::after{content:""; position:absolute; inset:0 0 auto 0; height:3px;
  background:linear-gradient(90deg,var(--m3-primary),var(--m3-secondary),var(--m3-tertiary)); opacity:.9}
.m3-kpi .v{font-size:30px; font-weight:780; line-height:1.05; letter-spacing:-.5px}
.m3-kpi .l{color:var(--m3-on-surface-variant); font-size:11px; text-transform:uppercase;
  letter-spacing:.8px; margin-top:6px; font-weight:600}
.m3-table{
  width:100%; border-collapse:separate; border-spacing:0; margin:10px 0 4px;
  background:var(--m3-surface-container-low); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m); overflow:hidden; font-size:13px; color:var(--m3-on-surface)}
.m3-table th,.m3-table td{text-align:left; padding:12px 14px;
  border-bottom:1px solid var(--m3-outline-variant); vertical-align:top; color:var(--m3-on-surface)}
.m3-table th{color:var(--m3-on-surface-variant); text-transform:uppercase;
  font-size:11px; letter-spacing:.7px; background:var(--m3-surface-container); font-weight:700}
.m3-table tbody tr:last-child td{border-bottom:none}
.m3-table tbody tr:hover{background:color-mix(in srgb,var(--m3-primary) 8%, transparent)}
.m3-chip{display:inline-flex; align-items:center; gap:6px; background:var(--m3-surface-container-high);
  border:1px solid var(--m3-outline-variant); color:var(--m3-on-surface);
  border-radius:var(--m3-shape-full); padding:6px 14px; font-size:12.5px; font-weight:600}
.m3-chip b{color:var(--m3-primary); margin-right:3px}
.m3-chip-row{display:flex; gap:8px; flex-wrap:wrap; margin:6px 0}
.m3-badge{background:var(--m3-primary-container); color:var(--m3-on-primary-container);
  border-radius:var(--m3-shape-xs); padding:3px 10px; font-size:11px; font-weight:800;
  letter-spacing:.5px; display:inline-block}
.m3-badge.on-primary{background:var(--m3-primary); color:var(--m3-on-primary)}
.m3-badge.error{background:var(--m3-error-container); color:var(--m3-on-error-container)}
.m3-btn{background:var(--m3-primary); color:var(--m3-on-primary); border:none;
  border-radius:20px; padding:14px 26px; font-weight:700; font-size:14px;
  cursor:pointer; box-shadow:var(--m3-shadow-1); transition:.25s var(--m3-ease); font-family:var(--m3-font)}
.m3-btn:hover{box-shadow:var(--m3-shadow-3); filter:brightness(1.05); transform:translateY(-1px); text-decoration:none; color:var(--m3-on-primary)}
.m3-btn:active{transform:translateY(0) scale(.98)}
.m3-btn:disabled{opacity:.55; cursor:wait; transform:none}
.m3-btn.tonal{background:var(--m3-secondary-container); color:var(--m3-on-secondary-container)}
.m3-btn.tonal:hover{color:var(--m3-on-secondary-container)}
.m3-btn.outlined{background:transparent; color:var(--m3-primary);
  border:1px solid var(--m3-outline)}
.m3-btn.outlined:hover{color:var(--m3-primary); background:color-mix(in srgb,var(--m3-primary) 8%, transparent)}
.m3-fieldlabel{display:block; font-weight:600; font-size:13px; margin:0 0 6px; color:var(--m3-on-surface)}
.m3-hint{color:var(--m3-on-surface-variant); font-size:12px; line-height:1.55; margin:2px 0 10px}
.m3-input, select.m3-input, textarea.m3-input{width:100%; background:var(--m3-surface-container-high); color:var(--m3-on-surface);
  border:1px solid var(--m3-outline-variant); border-radius:var(--m3-shape-s);
  padding:12px 14px; font-size:14px; font-family:var(--m3-font); transition:border-color .15s, box-shadow .15s, background-color .35s, color .35s;
  color-scheme:dark}
body.light .m3-input, body[data-theme="light"] .m3-input{color-scheme:light}
.m3-input::placeholder{color:var(--m3-on-surface-variant); opacity:.75}
.m3-input:focus{outline:none; border-color:var(--m3-primary);
  box-shadow:0 0 0 4px color-mix(in srgb, var(--m3-primary) 25%, transparent)}
textarea.m3-input{min-height:92px; resize:vertical; line-height:1.55}
.m3-field-grid{display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.m3-check{display:flex; align-items:center; gap:8px; font-size:13px; color:var(--m3-on-surface-variant)}
.m3-check input{accent-color:var(--m3-primary); width:16px; height:16px}
.m3-adv{display:inline-flex; align-items:center; gap:8px; background:none; border:none;
  color:var(--m3-primary); font-weight:700; font-size:13.5px; cursor:pointer; padding:6px 0; font-family:var(--m3-font)}
.m3-divider{height:1px; background:var(--m3-outline-variant); border:none; margin:22px 0}
.m3-footer{color:var(--m3-on-surface-variant); font-size:12.5px; line-height:1.6;
  border-top:1px solid var(--m3-outline-variant); padding-top:18px; margin-top:30px}
.m3-code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px;
  background:var(--m3-surface-container-high); color:var(--m3-on-surface); padding:2px 7px; border-radius:6px}
.m3-bartrack{position:relative; background:var(--m3-surface-container-high);
  border:1px solid var(--m3-outline-variant); border-radius:var(--m3-shape-full);
  height:18px; min-width:150px; overflow:hidden}
.m3-bar{height:18px; border-radius:var(--m3-shape-full);
  background:linear-gradient(90deg,var(--m3-primary),var(--m3-secondary),var(--m3-tertiary))}
.m3-barval{position:absolute; right:8px; top:0; font-size:11px; line-height:18px; color:#fff; font-weight:700}
.m3-progress-track{background:var(--m3-surface-container-high); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-full); height:12px; overflow:hidden}
.m3-progress-fill{height:12px; border-radius:var(--m3-shape-full); width:0%;
  background:linear-gradient(90deg,var(--m3-primary),var(--m3-secondary),var(--m3-tertiary));
  transition:width .45s ease; box-shadow:0 0 12px color-mix(in srgb,var(--m3-secondary) 60%,transparent)}
.m3-progress-block{margin:16px 0 4px}
.m3-barlabel{display:flex; justify-content:space-between; font-size:12.5px; color:var(--m3-on-surface-variant);
  margin-bottom:8px; font-weight:600; letter-spacing:.3px}
.m3-console{background:var(--m3-surface-container-highest); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m); padding:14px 16px; height:240px; overflow:auto;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px;
  color:var(--m3-on-surface); line-height:1.55}
.m3-console .log-err{color:var(--m3-error)}
.m3-console .log-ok{color:var(--m3-tertiary)}
.m3-issue{border-radius:var(--m3-shape-m); padding:14px 17px;
  background:var(--m3-surface-container-low); border:1px solid var(--m3-outline-variant);
  box-shadow:var(--m3-shadow-1)}
.feat-list{display:grid; gap:16px; margin:16px 0}
.feat{display:grid; grid-template-columns:60px 1fr; gap:18px; background:var(--m3-surface-container-low);
  border:1px solid var(--m3-outline-variant); border-radius:var(--m3-shape-m);
  padding:20px 22px; box-shadow:var(--m3-shadow-1)}
.feat-num{width:58px; height:58px; border-radius:var(--m3-shape-m); background:var(--m3-primary-container);
  color:var(--m3-on-primary-container); font-weight:800; font-size:22px; display:flex; align-items:center;
  justify-content:center; box-shadow:var(--m3-shadow-1)}
.feat-body h3{margin:0 0 8px; font-size:16px; font-weight:700; color:var(--m3-on-surface)}
.feat-body p{margin:0 0 8px; color:var(--m3-on-surface-variant); font-size:13.5px; line-height:1.65}
.feat-body ul{margin:0 0 10px; padding-left:18px; color:var(--m3-on-surface-variant); font-size:13px; line-height:1.6}
.feat-metrics{display:flex; gap:8px; flex-wrap:wrap; margin-top:8px}
table.kv{width:100%; border-collapse:separate; border-spacing:0; background:var(--m3-surface-container-low);
  border:1px solid var(--m3-outline-variant); border-radius:var(--m3-shape-m); overflow:hidden; font-size:13px; color:var(--m3-on-surface)}
table.kv td{padding:11px 14px; border-bottom:1px solid var(--m3-outline-variant); vertical-align:top; color:var(--m3-on-surface)}
table.kv tr:last-child td{border-bottom:none}
table.kv td:first-child{color:var(--m3-on-surface-variant); width:46%; background:var(--m3-surface-container);
  font-weight:600}
.verify-card{border-radius:var(--m3-shape-m); border:1px solid var(--m3-outline-variant); padding:18px 20px; margin:14px 0;
  background:var(--m3-surface-container-low); box-shadow:var(--m3-shadow-1)}
.verify-card.ok{border-color:var(--m3-tertiary)}
.verify-card.partial{border-color:#E8A317}
.verify-head{display:flex; align-items:center; gap:12px; margin-bottom:14px; font-weight:700; color:var(--m3-on-surface)}
.verify-badge{background:var(--m3-primary); color:var(--m3-on-primary); border-radius:var(--m3-shape-xs);
  padding:5px 13px; font-size:12px; font-weight:800}
.verify-card.partial .verify-badge{background:var(--m3-tertiary-container); color:var(--m3-on-tertiary-container)}
.verify-note{color:var(--m3-on-surface-variant); font-size:12.5px; line-height:1.6; margin:10px 0 0}
.dl-row{display:flex; gap:10px; flex-wrap:wrap; margin-top:14px}
.dl{background:var(--m3-secondary-container); color:var(--m3-on-secondary-container); text-decoration:none;
  font-weight:700; padding:11px 18px; border-radius:var(--m3-shape-full); font-size:13px;
  box-shadow:var(--m3-shadow-1); transition:.15s}
.dl:hover{background:var(--m3-primary); color:var(--m3-on-primary); text-decoration:none; transform:translateY(-1px)}
.lead{color:var(--m3-on-surface-variant); font-size:15px; line-height:1.7; margin:6px 0 16px; max-width:880px}
.step-wrap{display:flex; gap:0; align-items:center; margin:6px 0 22px; flex-wrap:wrap}
.step{display:flex; align-items:center; gap:10px; padding:10px 16px; border-radius:var(--m3-shape-full);
  background:var(--m3-surface-container); border:1px solid var(--m3-outline-variant);
  color:var(--m3-on-surface-variant); font-weight:600; font-size:13px; cursor:pointer; transition:.2s var(--m3-ease)}
.step .num{width:24px; height:24px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; background:var(--m3-surface-container-high); border:1px solid var(--m3-outline-variant);
  font-size:12px; font-weight:800}
.step.active{border-color:var(--m3-primary); color:var(--m3-on-surface); box-shadow:var(--m3-shadow-1)}
.step.active .num{background:var(--m3-primary); color:var(--m3-on-primary); border-color:transparent}
.step.done{border-color:var(--m3-tertiary)}
.step.done .num{background:var(--m3-secondary-container); color:var(--m3-on-secondary-container)}
.step-sep{flex:1 1 24px; height:2px; min-width:24px; background:var(--m3-outline-variant); margin:0 8px}
.page{display:none}
.page.active{display:block; animation:pageIn .45s var(--m3-ease)}
@keyframes pageIn{from{opacity:0; transform:translateY(10px)} to{opacity:1; transform:none}}
iframe.ent-frame{width:100%; height:82vh; border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m); background:var(--m3-surface-container-lowest); box-shadow:var(--m3-shadow-2);
  color-scheme:dark}
body.light iframe.ent-frame, body[data-theme="light"] iframe.ent-frame{color-scheme:light}
@media (max-width:760px){
  .m3-app-inner{flex-wrap:wrap}
  .m3-nav{margin-left:0}
  .feat{grid-template-columns:1fr}
  .feat-num{width:48px; height:48px}
}
@media (prefers-reduced-motion:reduce){
  *, *::before, *::after{animation-duration:.001s !important; transition-duration:.001s !important}
  html{scroll-behavior:auto}
}
/* ---- severity issue cards: bold, theme-safe highlighting ---- */
.iss-wrap{margin:14px 0 6px}
.iss-head{display:flex; align-items:center; gap:10px; font-weight:800; font-size:15px;
  letter-spacing:-.2px; color:var(--m3-on-surface); margin:0 0 10px}
.iss-count{background:var(--m3-error); color:var(--m3-on-error); font-size:11px; font-weight:800;
  min-width:22px; height:22px; border-radius:99px; display:inline-flex; align-items:center;
  justify-content:center; padding:0 6px}
.iss{display:flex; gap:12px; align-items:flex-start; border-radius:var(--m3-shape-m);
  padding:13px 16px; margin:0 0 10px; border:1px solid var(--m3-outline-variant);
  border-left-width:6px; box-shadow:var(--m3-shadow-1); background:var(--m3-surface-container-low)}
.iss-critical{background:color-mix(in srgb, var(--m3-error-container) 42%, var(--m3-surface-container-low));
  border-color:var(--m3-error); border-left-color:var(--m3-error)}
.iss-high{background:color-mix(in srgb, #E8A317 16%, var(--m3-surface-container-low));
  border-color:#E8A317; border-left-color:#E8A317}
.iss-medium{background:color-mix(in srgb, var(--m3-tertiary-container) 45%, var(--m3-surface-container-low));
  border-color:var(--m3-tertiary); border-left-color:var(--m3-tertiary)}
.iss-good{background:color-mix(in srgb, var(--m3-primary-container) 45%, var(--m3-surface-container-low));
  border-color:var(--m3-primary); border-left-color:var(--m3-primary)}
.iss-body{display:flex; flex-direction:column; gap:3px; font-size:13px; line-height:1.55;
  color:var(--m3-on-surface)}
.iss-body b{font-size:13.5px}
.iss-body span{color:var(--m3-on-surface-variant)}
.sev{flex:0 0 auto; font-size:10px; font-weight:800; letter-spacing:.7px; padding:4px 10px;
  border-radius:8px; margin-top:1px; white-space:nowrap}
.sev-critical{background:var(--m3-error); color:var(--m3-on-error)}
.sev-high{background:#E8A317; color:#1D1B20}
.sev-medium{background:var(--m3-tertiary-container); color:var(--m3-on-tertiary-container)}
.sev-good{background:var(--m3-primary-container); color:var(--m3-on-primary-container)}
tr.row-critical td{background:color-mix(in srgb, var(--m3-error-container) 38%, transparent) !important;
  font-weight:600}
tr.row-high td{background:color-mix(in srgb, #E8A317 14%, transparent) !important}
tr.row-good td{background:color-mix(in srgb, var(--m3-primary-container) 38%, transparent) !important}
"""


def get_style(surface: str = "webapp") -> str:
    """Return the complete shared stylesheet for a surface.

    ``surface`` selects how many tokens to include:
    * ``full`` (webapp): dark + light palettes and the font-face, so the UI can
      switch themes at runtime and narrative fragments inherit component styles.
    * ``report`` (self-contained dashboard / PDF preview): a single mood, fully
      inlined so the HTML can be opened offline and even emailed.

    The font face is always base64-embedded (no CDN).
    """
    font = _FONT_FACE_CSS
    dark_tokens = material_css("dark")
    components = components_css("dark")
    if surface == "report":
        body_theme = """
body{color:var(--m3-on-surface); background:
  radial-gradient(1200px 600px at 12% -12%, color-mix(in srgb,var(--m3-primary) 18%, transparent), transparent 60%),
  radial-gradient(1000px 520px at 102% -4%, color-mix(in srgb,var(--m3-tertiary) 12%, transparent), transparent 55%),
  var(--m3-surface);}
"""
        return font + "\n" + dark_tokens + "\n" + components + "\n" + body_theme

    # webapp: dark :root tokens + light palette scoped to body.light AND
    # body[data-theme="light"] for runtime theme toggle. Component styles are
    # emitted once (they reference token vars). Both selectors carry the full
    # light palette so every color re-renders correctly on mode change.
    light_tokens = (
        material_css("light", selector='body.light')
        + "\n"
        + material_css("light", selector='body[data-theme="light"]')
    )
    body_theme = """
body{color:var(--m3-on-surface); background:
  radial-gradient(1200px 600px at 12% -12%, color-mix(in srgb,var(--m3-primary) 16%, transparent), transparent 60%),
  radial-gradient(1000px 520px at 102% -4%, color-mix(in srgb,var(--m3-tertiary) 11%, transparent), transparent 55%),
  var(--m3-surface);}
"""
    return (font + "\n" + dark_tokens + "\n" + components + "\n"
            + light_tokens + "\n" + body_theme)
