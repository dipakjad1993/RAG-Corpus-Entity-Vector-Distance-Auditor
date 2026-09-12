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

# Authentic Material 3 color tokens.
# mood -> {"light": {...}, "dark": {...}} with M3 role names.
_M3_DARK = {
    "primary": "#D0BCFF", "on-primary": "#381E72",
    "primary-container": "#4F378B", "on-primary-container": "#EADDFF",
    "secondary": "#CCC2DC", "on-secondary": "#332D41", "secondary-container": "#4A4458",
    "tertiary": "#EFB8C8", "on-tertiary": "#492532", "tertiary-container": "#633B48",
    "error": "#F2B8B5", "on-error": "#601410", "error-container": "#8C1D18",
    "surface": "#141218", "surface-dim": "#141218", "surface-bright": "#3B383E",
    "surface-container-lowest": "#0E0D11", "surface-container-low": "#1C1A20",
    "surface-container": "#211F26", "surface-container-high": "#2B292F",
    "surface-container-highest": "#36343B",
    "on-surface": "#E6E0E9", "on-surface-variant": "#CAC4D0",
    "outline": "#938F99", "outline-variant": "#49454F", "scrim": "#000000",
}

_M3_LIGHT = {
    "primary": "#6750A4", "on-primary": "#FFFFFF",
    "primary-container": "#EADDFF", "on-primary-container": "#21005D",
    "secondary": "#625B71", "on-secondary": "#FFFFFF", "secondary-container": "#E8DEF8",
    "tertiary": "#7D5260", "on-tertiary": "#FFFFFF", "tertiary-container": "#FFD8E4",
    "error": "#BA1A1A", "on-error": "#FFFFFF", "error-container": "#FFDAD6",
    "surface": "#FFFBFE", "surface-dim": "#DED8E1", "surface-bright": "#FFFBFE",
    "surface-container-lowest": "#FFFFFF", "surface-container-low": "#F7F2FA",
    "surface-container": "#F3EDF7", "surface-container-high": "#ECE6F0",
    "surface-container-highest": "#E6E0E9",
    "on-surface": "#1D1B20", "on-surface-variant": "#49454F",
    "outline": "#79747E", "outline-variant": "#CAC4D0", "scrim": "#000000",
}

# M3 elevation tints approximate surface-container-high/highest progression.
_DARK_ELEVATION = ["#141218", "#211F26", "#2B292F", "#36343B", "#3B383E"]
_LIGHT_ELEVATION = ["#FFFBFE", "#F3EDF7", "#ECE6F0", "#E6E0E9", "#E0D6E3"]


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

    For the webapp the light palette is scoped under ``body.light`` so the dark
    ``:root`` tokens stay intact for runtime theme toggling. Component styles are
    emitted separately once via :func:`components_css`.
    """
    p = _palette(mood)
    elev = _LIGHT_ELEVATION if mood == "light" else _DARK_ELEVATION

    def v(name: str) -> str:
        return str(p.get(name, ""))

    # Type scale (display/headline/title/body/label) in Roboto Flex.
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
    color_block = f"""
  color-scheme:{'light' if mood == 'light' else 'dark'};
  --m3-primary:{v('primary')};
  --m3-on-primary:{v('on-primary')};
  --m3-primary-container:{v('primary-container')};
  --m3-on-primary-container:{v('on-primary-container')};
  --m3-secondary:{v('secondary')};
  --m3-on-secondary:{v('on-secondary')};
  --m3-secondary-container:{v('secondary-container')};
  --m3-tertiary:{v('tertiary')};
  --m3-on-tertiary:{v('on-tertiary')};
  --m3-tertiary-container:{v('tertiary-container')};
  --m3-error:{v('error')};
  --m3-on-error:{v('on-error')};
  --m3-error-container:{v('error-container')};
  --m3-surface:{v('surface')};
  --m3-surface-dim:{v('surface-dim')};
  --m3-surface-bright:{v('surface-bright')};
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
  --m3-font:'{FONT_FAMILY}',{_FONT_FALLBACK};
  --m3-shadow-1:0 1px 3px rgba(0,0,0,.3),0 1px 2px rgba(0,0,0,.24);
  --m3-shadow-2:0 2px 6px rgba(0,0,0,.24),0 1px 4px rgba(0,0,0,.22);
  --m3-shadow-3:0 6px 14px rgba(0,0,0,.26),0 2px 8px rgba(0,0,0,.20);
"""

    return selector + "{\n" + color_block + type_scale + "}\n"


def components_css(mood: str) -> str:
    """Component styles (emitted once) building on the M3 tokens."""
    return _COMPONENTS(mood, _palette(mood).get)


def _COMPONENTS(mood: str, v) -> str:
    """Shared component styles built on the M3 tokens above."""
    if mood == "light":
        hover = "background:rgba(103,80,164,.08);"
        nav_active_bg = "background:var(--m3-secondary-container); color:var(--m3-on-secondary-container);"
    else:
        hover = "background:rgba(208,188,255,.08);"
        nav_active_bg = "background:var(--m3-secondary-container); color:var(--m3-on-secondary-container);"

    return f"""
*{{box-sizing:border-box}}
html,body{{height:100%}}
body{{
  margin:0; color:var(--m3-on-surface); font-family:var(--m3-font);
  font-size:14px; line-height:1.65; letter-spacing:.1px;
  -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
  background:var(--m3-surface);
}}
a{{color:var(--m3-primary); text-decoration:none}}
a:hover{{text-decoration:underline}}
.m3-app-bar{{
  position:sticky; top:0; z-index:20; backdrop-filter:blur(14px);
  background:color-mix(in srgb,var(--m3-surface-c) 88%, transparent);
  border-bottom:1px solid var(--m3-outline-variant);
}}
.m3-app-inner{{max-width:1180px; margin:0 auto; padding:12px 22px; display:flex;
  align-items:center; gap:16px}}
.m3-logo{{width:40px; height:40px; border-radius:12px; flex:0 0 auto;
  background:linear-gradient(135deg,var(--m3-primary),var(--m3-tertiary));
  color:var(--m3-on-primary); font-weight:800; font-size:15px;
  display:flex; align-items:center; justify-content:center;
  box-shadow:var(--m3-shadow-2)}}
.m3-title{{font-weight:700; font-size:17px; letter-spacing:-.2px; line-height:1.1}}
.m3-title small{{display:block; color:var(--m3-on-surface-variant); font-weight:500; font-size:11.5px}}
.m3-nav{{display:flex; gap:6px; margin-left:auto; flex-wrap:wrap}}
.m3-nav a{{color:var(--m3-on-surface-variant); padding:9px 14px; border-radius:var(--m3-shape-full);
  font-weight:600; font-size:13.5px; transition:.15s; white-space:nowrap}}
.m3-nav a:hover{{ {hover} color:var(--m3-on-surface); text-decoration:none}}
.m3-nav a.on{{ {nav_active_bg} }}
.m3-container{{max-width:1180px; margin:0 auto; padding:22px 22px 64px}}
.m3-h1{{font-size:30px; line-height:1.15; font-weight:750; letter-spacing:-.5px; margin:4px 0 6px}}
.m3-h2{{font-size:20px; font-weight:700; letter-spacing:-.2px; margin:30px 0 10px;
  display:flex; align-items:center; gap:10px}}
.m3-h3{{font-size:15px; font-weight:600; margin:18px 0 6px}}
.m3-lead{{color:var(--m3-on-surface-variant); font-size:15px; max-width:820px;
  line-height:1.7; margin:6px 0 18px}}
.m3-sub{{color:var(--m3-on-surface-variant); font-size:13px}}
.muted{{color:var(--m3-on-surface-variant)}}
.m3-card{{
  background:var(--m3-surface-container-low); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-l); padding:22px 24px; box-shadow:var(--m3-shadow-1);
  transition:transform .3s var(--m3-ease), box-shadow .3s var(--m3-ease)}}
.m3-card:hover{{transform:translateY(-2px); box-shadow:var(--m3-shadow-2)}}
.m3-grid{{display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); margin:16px 0}}
.m3-kpi{{background:var(--m3-surface-container-low); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m); padding:18px 20px; box-shadow:var(--m3-shadow-1)}}
.m3-kpi .v{{font-size:30px; font-weight:780; line-height:1.05; letter-spacing:-.5px}}
.m3-kpi .l{{color:var(--m3-on-surface-variant); font-size:11px; text-transform:uppercase;
  letter-spacing:.8px; margin-top:6px; font-weight:600}}
.m3-table{{
  width:100%; border-collapse:separate; border-spacing:0; margin:10px 0 4px;
  background:var(--m3-surface-container-low); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m); overflow:hidden; font-size:13px}}
.m3-table th,.m3-table td{{text-align:left; padding:12px 14px;
  border-bottom:1px solid var(--m3-outline-variant); vertical-align:top}}
.m3-table th{{color:var(--m3-on-surface-variant); text-transform:uppercase;
  font-size:11px; letter-spacing:.7px; background:var(--m3-surface-container); font-weight:700}}
.m3-table tbody tr:last-child td{{border-bottom:none}}
.m3-table tbody tr:hover{{background:{hover}}}
.m3-chip{{display:inline-flex; align-items:center; gap:6px; background:var(--m3-surface-container-high);
  border:1px solid var(--m3-outline-variant); color:var(--m3-on-surface);
  border-radius:var(--m3-shape-full); padding:6px 14px; font-size:12.5px; font-weight:600}}
.m3-chip b{{color:var(--m3-primary); margin-right:3px}}
.m3-chip-row{{display:flex; gap:8px; flex-wrap:wrap; margin:6px 0}}
.m3-badge{{background:var(--m3-primary-container); color:var(--m3-on-primary-container);
  border-radius:var(--m3-shape-xs); padding:3px 10px; font-size:11px; font-weight:800;
  letter-spacing:.5px; display:inline-block}}
.m3-badge.on-primary{{background:var(--m3-primary); color:var(--m3-on-primary)}}
.m3-badge.error{{background:var(--m3-error-container); color:var(--m3-on-error-container)}}
.m3-btn{{background:var(--m3-primary); color:var(--m3-on-primary); border:none;
  border-radius:20px; padding:14px 26px; font-weight:700; font-size:14px;
  cursor:pointer; box-shadow:var(--m3-shadow-1); transition:.25s var(--m3-ease); font-family:var(--m3-font)}}
.m3-btn:hover{{box-shadow:var(--m3-shadow-3); filter:brightness(1.05); transform:translateY(-1px); text-decoration:none; color:var(--m3-on-primary)}}
.m3-btn:active{{transform:translateY(0) scale(.98)}}
.m3-btn.tonal{{background:var(--m3-secondary-container); color:var(--m3-on-secondary-container)}}
.m3-btn.tonal:hover{{color:var(--m3-on-secondary-container)}}
.m3-btn.outlined{{background:transparent; color:var(--m3-primary);
  border:1px solid var(--m3-outline)}}
.m3-btn.outlined:hover{{color:var(--m3-primary)}}
.m3-fieldlabel{{display:block; font-weight:600; font-size:13px; margin:0 0 6px; color:var(--m3-on-surface)}}
.m3-hint{{color:var(--m3-on-surface-variant); font-size:12px; line-height:1.55; margin:2px 0 10px}}
.m3-input{{width:100%; background:var(--m3-surface-container-high); color:var(--m3-on-surface);
  border:1px solid var(--m3-outline-variant); border-radius:var(--m3-shape-s);
  padding:12px 14px; font-size:14px; font-family:inherit; transition:border-color .15s, box-shadow .15s}}
.m3-input:focus{{outline:none; border-color:var(--m3-primary);
  box-shadow:0 0 0 4px color-mix(in srgb, var(--m3-primary) 25%, transparent)}}
textarea.m3-input{{min-height:92px; resize:vertical; line-height:1.55}}
.m3-field-grid{{display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}}
.m3-check{{display:flex; align-items:center; gap:8px; font-size:13px; color:var(--m3-on-surface-variant)}}
.m3-adv{{display:inline-flex; align-items:center; gap:8px; background:none; border:none;
  color:var(--m3-primary); font-weight:700; font-size:13.5px; cursor:pointer; padding:6px 0; font-family:var(--m3-font)}}
.m3-divider{{height:1px; background:var(--m3-outline-variant); border:none; margin:22px 0}}
.m3-footer{{color:var(--m3-on-surface-variant); font-size:12.5px; line-height:1.6;
  border-top:1px solid var(--m3-outline-variant); padding-top:18px; margin-top:30px}}
.m3-code{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px;
  background:var(--m3-surface-container-high); padding:2px 7px; border-radius:6px}}
.m3-bartrack{{position:relative; background:var(--m3-surface-container-high);
  border:1px solid var(--m3-outline-variant); border-radius:var(--m3-shape-full);
  height:18px; min-width:150px; overflow:hidden}}
.m3-bar{{height:18px; border-radius:var(--m3-shape-full);
  background:linear-gradient(90deg,var(--m3-primary),var(--m3-tertiary))}}
.m3-barval{{position:absolute; right:8px; top:0; font-size:11px; line-height:18px; color:#fff; font-weight:700}}
.m3-progress-track{{background:var(--m3-surface-container-high); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-full); height:12px; overflow:hidden}}
.m3-progress-fill{{height:12px; border-radius:var(--m3-shape-full); width:0%;
  background:linear-gradient(90deg,var(--m3-primary),var(--m3-tertiary));
  transition:width .45s ease; box-shadow:0 0 12px color-mix(in srgb,var(--m3-primary) 60%,transparent)}}
.m3-progress-block{{margin:16px 0 4px}}
.m3-barlabel{{display:flex; justify-content:space-between; font-size:12.5px; color:var(--m3-on-surface-variant);
  margin-bottom:8px; font-weight:600; letter-spacing:.3px}}
.m3-console{{background:var(--m3-surface-container-high); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m); padding:14px 16px; height:240px; overflow:auto;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px;
  color:var(--m3-primary); line-height:1.55; box-shadow:inset 0 0 0 1px rgba(255,255,255,.02)}}
.m3-issue{{border-radius:var(--m3-shape-m); padding:14px 17px;
  background:var(--m3-surface-container-low); border:1px solid var(--m3-outline-variant);
  box-shadow:var(--m3-shadow-1)}}
.feat-list{{display:grid; gap:16px; margin:16px 0}}
.feat{{display:grid; grid-template-columns:60px 1fr; gap:18px; background:var(--m3-surface-container-low);
  border:1px solid var(--m3-outline-variant); border-radius:var(--m3-shape-m);
  padding:20px 22px; box-shadow:var(--m3-shadow-1)}}
.feat-num{{width:58px; height:58px; border-radius:var(--m3-shape-m); background:var(--m3-primary-container);
  color:var(--m3-on-primary-container); font-weight:800; font-size:22px; display:flex; align-items:center;
  justify-content:center; box-shadow:var(--m3-shadow-1)}}
.feat-body h3{{margin:0 0 8px; font-size:16px; font-weight:700; color:var(--m3-on-surface)}}
.feat-body p{{margin:0 0 8px; color:var(--m3-on-surface-variant); font-size:13.5px; line-height:1.65}}
.feat-body ul{{margin:0 0 10px; padding-left:18px; color:var(--m3-on-surface-variant); font-size:13px; line-height:1.6}}
.feat-metrics{{display:flex; gap:8px; flex-wrap:wrap; margin-top:8px}}
table.kv{{width:100%; border-collapse:separate; border-spacing:0; background:var(--m3-surface-container-low);
  border:1px solid var(--m3-outline-variant); border-radius:var(--m3-shape-m); overflow:hidden; font-size:13px}}
table.kv td{{padding:11px 14px; border-bottom:1px solid var(--m3-outline-variant); vertical-align:top}}
table.kv tr:last-child td{{border-bottom:none}}
table.kv td:first-child{{color:var(--m3-on-surface-variant); width:46%; background:var(--m3-surface-container);
  font-weight:600}}
.verify-card{{border-radius:var(--m3-shape-m); border:1px solid var(--m3-outline-variant); padding:18px 20px; margin:14px 0;
  background:var(--m3-surface-container-low); box-shadow:var(--m3-shadow-1)}}
.verify-card.ok{{border-color:var(--m3-tertiary)}}
.verify-card.partial{{border-color:#FBBF24}}
.verify-head{{display:flex; align-items:center; gap:12px; margin-bottom:14px; font-weight:700; color:var(--m3-on-surface)}}
.verify-badge{{background:var(--m3-primary); color:var(--m3-on-primary); border-radius:var(--m3-shape-xs);
  padding:5px 13px; font-size:12px; font-weight:800}}
.verify-card.partial .verify-badge{{background:var(--m3-tertiary-container); color:var(--m3-on-tertiary-container)}}
.verify-note{{color:var(--m3-on-surface-variant); font-size:12.5px; line-height:1.6; margin:10px 0 0}}
.dl-row{{display:flex; gap:10px; flex-wrap:wrap; margin-top:14px}}
.dl{{background:var(--m3-secondary-container); color:var(--m3-on-secondary-container); text-decoration:none;
  font-weight:700; padding:11px 18px; border-radius:var(--m3-shape-full); font-size:13px;
  box-shadow:var(--m3-shadow-1); transition:.15s}}
.dl:hover{{background:var(--m3-primary); color:var(--m3-on-primary); text-decoration:none; transform:translateY(-1px)}}
.lead{{color:var(--m3-on-surface-variant); font-size:15px; line-height:1.7; margin:6px 0 16px; max-width:860px}}
.step-wrap{{display:flex; gap:0; align-items:center; margin:6px 0 22px; flex-wrap:wrap}}
.step{{display:flex; align-items:center; gap:10px; padding:10px 16px; border-radius:var(--m3-shape-full);
  background:var(--m3-surface-container); border:1px solid var(--m3-outline-variant);
  color:var(--m3-on-surface-variant); font-weight:600; font-size:13px}}
.step .num{{width:24px; height:24px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; background:var(--m3-surface-container-high); border:1px solid var(--m3-outline-variant);
  font-size:12px; font-weight:800}}
.step.active{{border-color:var(--m3-primary); color:var(--m3-on-surface)}}
.step.active .num{{background:var(--m3-primary); color:var(--m3-on-primary); border-color:transparent}}
.step.done .num{{background:var(--m3-secondary-container); color:var(--m3-on-secondary-container)}}
.step-sep{{flex:1 1 24px; height:2px; min-width:24px; background:var(--m3-outline-variant); margin:0 8px}}
.page{{display:none}}
.page.active{{display:block}}
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

    # webapp: dark :root tokens + light palette scoped to body.light for runtime
    # theme toggle. Component styles are emitted once (they reference token vars).
    light_tokens = material_css("light", selector="body.light")
    body_theme = """
body{color:var(--m3-on-surface); background:
  radial-gradient(1200px 600px at 12% -12%, color-mix(in srgb,var(--m3-primary) 16%, transparent), transparent 60%),
  radial-gradient(1000px 520px at 102% -4%, color-mix(in srgb,var(--m3-tertiary) 11%, transparent), transparent 55%),
  var(--m3-surface);}
"""
    return (font + "\n" + dark_tokens + "\n" + components + "\n"
            + light_tokens + "\n" + body_theme)
