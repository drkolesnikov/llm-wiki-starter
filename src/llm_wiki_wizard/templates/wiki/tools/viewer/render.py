#!/usr/bin/env python3
"""Governance-aware static HTML renderer for the LLM wiki graph.

``render_html(graph) -> str`` serialises a :class:`GraphModel` produced by
``tools/viewer/extract.py`` into a fully self-contained HTML page:

- Embedded graph data (JSON in a ``<script>`` tag) — parseable back to dict.
- Force-directed graph (pure JS, NO external network requests).
- Detail pane showing governance frontmatter, body excerpt, citations, backlinks.
- Controls: search, type filter, status / tier highlight, legend.
- Governance encoding:
    - ``status``  → node colour (CSS class ``status-<value>``).
    - ``source_tier`` → secondary ring / badge (CSS class ``tier-<value>``).
    - ``zero-source`` knowledge artifacts → ``data-zero-source`` attribute + loud badge.
    - ``needs-review`` / ``conflicted`` → ``data-attention`` attribute + attention styling.
    - ``description`` surfaced as SVG title tooltip.
- Output is deterministic: nodes sorted by node_id before serialisation.
- No external fonts / scripts / images — everything inlined.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.viewer.extract import GraphModel, NodeModel


# ---------------------------------------------------------------------------
# Colour / badge mappings (used in CSS and data attributes)
# ---------------------------------------------------------------------------

STATUS_COLORS: dict[str, str] = {
    "active":       "#4caf50",   # green
    "draft":        "#9e9e9e",   # grey
    "verified":     "#2196f3",   # blue
    "needs-review": "#ff9800",   # orange — loud
    "conflicted":   "#f44336",   # red   — loud
    "deprecated":   "#795548",   # brown
    "unknown":      "#607d8b",   # blue-grey
}

TIER_COLORS: dict[str, str] = {
    "primary":    "#7c4dff",
    "secondary":  "#00bcd4",
    "reference":  "#8bc34a",
    "background": "#ffc107",
    "restricted": "#e91e63",
    "unknown":    "#b0bec5",
    "zero-source": "#ff5722",
}

ATTENTION_STATUSES = {"needs-review", "conflicted"}


# ---------------------------------------------------------------------------
# Graph-data serialisation helper
# ---------------------------------------------------------------------------

def _node_to_dict(node: "NodeModel") -> dict:
    """Convert a NodeModel to a plain dict suitable for JSON embedding."""
    return {
        "id":            node.node_id,
        "title":         node.title,
        "artifact_type": node.artifact_type,
        "status":        node.status,
        "source_tier":   node.source_tier,
        "source_count":  node.source_count,
        "sources":       sorted(node.sources),
        "tags":          node.tags,
        "description":   node.description or "",
        "body_excerpt":  node.body[:400].replace("\n", " "),
        "zero_source":   (
            node.source_tier == "zero-source"
            or (node.artifact_type == "knowledge-note" and node.source_count == 0)
        ),
        "attention":     node.status in ATTENTION_STATUSES,
        "backlinks":     [e.source_id for e in node.backlinks],
        "edges":         [
            {
                "target": e.target_id,
                "kind":   e.kind,
                "resolved": e.resolved,
            }
            for e in node.edges
        ],
    }


def _build_graph_data(graph: "GraphModel") -> dict:
    """Serialise the full graph into a JSON-safe dict, deterministically."""
    sorted_nodes = sorted(graph.nodes.values(), key=lambda n: n.node_id)

    nodes_list = [_node_to_dict(n) for n in sorted_nodes]

    # Build edge list (source → target) for the force layout.
    # Deduplicate resolved edges so duplicate wikilink+markdown links don't
    # create multiple SVG paths between the same pair.
    seen_pairs: set[tuple[str, str]] = set()
    links_list: list[dict] = []
    for node in sorted_nodes:
        for edge in node.edges:
            if not edge.resolved:
                continue
            pair = (edge.source_id, edge.target_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            links_list.append({
                "source": edge.source_id,
                "target": edge.target_id,
                "kind":   edge.kind,
            })

    # Stats
    status_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    for n in sorted_nodes:
        status_counts[n.status] = status_counts.get(n.status, 0) + 1
        tier_counts[n.source_tier] = tier_counts.get(n.source_tier, 0) + 1

    warnings: list[str] = []
    zero_source_nodes = [n.node_id for n in sorted_nodes if n.source_tier == "zero-source"
                         or (n.artifact_type == "knowledge-note" and n.source_count == 0)]
    if zero_source_nodes:
        warnings.append(f"Zero-source knowledge artifacts: {', '.join(zero_source_nodes)}")

    attention_nodes = [n.node_id for n in sorted_nodes if n.status in ATTENTION_STATUSES]
    if attention_nodes:
        warnings.append(f"Attention required ({', '.join(ATTENTION_STATUSES)}): {', '.join(attention_nodes)}")

    return {
        "nodes":         nodes_list,
        "links":         links_list,
        "node_count":    len(nodes_list),
        "edge_count":    len(links_list),
        "status_counts": status_counts,
        "tier_counts":   tier_counts,
        "warnings":      warnings,
        "root":          str(graph.root),
    }


# ---------------------------------------------------------------------------
# Inline JS (force-directed graph, no external deps)
# ---------------------------------------------------------------------------

# A minimal force-directed graph implemented in vanilla JS + Canvas.
# All SVG drawing is done inline — no D3, no external imports.
_GRAPH_JS = r"""
(function() {
  'use strict';

  // ---- Simulation parameters ----
  const REPULSION = 3000;
  const LINK_DIST  = 120;
  const CENTER_FORCE = 0.03;
  const DAMPING    = 0.85;
  const ITERATIONS = 300;  // run layout eagerly for determinism

  function runLayout(nodes, links, width, height) {
    // Initialise positions deterministically from index
    nodes.forEach(function(n, i) {
      var angle = (2 * Math.PI * i) / nodes.length;
      n.x = width / 2 + Math.cos(angle) * (Math.min(width, height) * 0.35);
      n.y = height / 2 + Math.sin(angle) * (Math.min(width, height) * 0.35);
      n.vx = 0; n.vy = 0;
    });

    var indexById = {};
    nodes.forEach(function(n) { indexById[n.id] = n; });

    for (var iter = 0; iter < ITERATIONS; iter++) {
      // Repulsion between all pairs
      for (var i = 0; i < nodes.length; i++) {
        for (var j = i + 1; j < nodes.length; j++) {
          var a = nodes[i], b = nodes[j];
          var dx = b.x - a.x, dy = b.y - a.y;
          var dist = Math.sqrt(dx*dx + dy*dy) || 1;
          var force = REPULSION / (dist * dist);
          var fx = (dx / dist) * force, fy = (dy / dist) * force;
          a.vx -= fx; a.vy -= fy;
          b.vx += fx; b.vy += fy;
        }
      }
      // Attraction along links
      links.forEach(function(l) {
        var a = indexById[l.source], b = indexById[l.target];
        if (!a || !b) return;
        var dx = b.x - a.x, dy = b.y - a.y;
        var dist = Math.sqrt(dx*dx + dy*dy) || 1;
        var force = (dist - LINK_DIST) * 0.03;
        var fx = (dx / dist) * force, fy = (dy / dist) * force;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      });
      // Centre pull
      nodes.forEach(function(n) {
        n.vx += (width / 2 - n.x) * CENTER_FORCE;
        n.vy += (height / 2 - n.y) * CENTER_FORCE;
        n.vx *= DAMPING; n.vy *= DAMPING;
        n.x += n.vx; n.y += n.vy;
      });
    }
  }

  // ---- Status / tier colours (mirrored from Python) ----
  var STATUS_COLORS = {
    'active':       '#4caf50',
    'draft':        '#9e9e9e',
    'verified':     '#2196f3',
    'needs-review': '#ff9800',
    'conflicted':   '#f44336',
    'deprecated':   '#795548',
    'unknown':      '#607d8b'
  };
  var TIER_COLORS = {
    'primary':    '#7c4dff',
    'secondary':  '#00bcd4',
    'reference':  '#8bc34a',
    'background': '#ffc107',
    'restricted': '#e91e63',
    'unknown':    '#b0bec5',
    'zero-source':'#ff5722'
  };

  function nodeColor(n) { return STATUS_COLORS[n.status] || '#607d8b'; }
  function tierColor(n) { return TIER_COLORS[n.source_tier] || '#b0bec5'; }

  // ---- Canvas renderer ----
  var canvas, ctx, tooltip, detailPane, searchInput, typeFilter, highlightSelect;
  var graphData, simNodes, simLinks, nodeMap;
  var transform = { scale: 1, dx: 0, dy: 0 };
  var dragging = null, dragStart = null;
  var activeNode = null;

  function worldToScreen(wx, wy) {
    return {
      x: wx * transform.scale + transform.dx,
      y: wy * transform.scale + transform.dy
    };
  }
  function screenToWorld(sx, sy) {
    return {
      x: (sx - transform.dx) / transform.scale,
      y: (sy - transform.dy) / transform.scale
    };
  }

  function nodeRadius(n) {
    var base = 10;
    if (n.attention) base += 4;
    if (n.zero_source) base += 2;
    return base;
  }

  function draw() {
    var W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.translate(transform.dx, transform.dy);
    ctx.scale(transform.scale, transform.scale);

    // Links
    simLinks.forEach(function(l) {
      var a = nodeMap[l.source], b = nodeMap[l.target];
      if (!a || !b) return;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = l.kind === 'wikilink' ? '#90a4ae' : '#bdbdbd';
      ctx.lineWidth = l.kind === 'wikilink' ? 1.5 : 1;
      ctx.globalAlpha = 0.6;
      ctx.stroke();
      ctx.globalAlpha = 1;
    });

    // Nodes
    simNodes.forEach(function(n) {
      var r = nodeRadius(n);
      var filtered = applyFilters(n);
      ctx.globalAlpha = filtered ? 1.0 : 0.25;

      // Tier ring
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + 4, 0, 2 * Math.PI);
      ctx.fillStyle = tierColor(n);
      ctx.fill();

      // Status fill
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = nodeColor(n);
      ctx.fill();

      // Attention pulse ring
      if (n.attention) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 8, 0, 2 * Math.PI);
        ctx.strokeStyle = nodeColor(n);
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Zero-source X mark
      if (n.zero_source) {
        ctx.strokeStyle = '#ff5722';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(n.x - 5, n.y - 5);
        ctx.lineTo(n.x + 5, n.y + 5);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(n.x + 5, n.y - 5);
        ctx.lineTo(n.x - 5, n.y + 5);
        ctx.stroke();
      }

      // Label
      ctx.fillStyle = '#212121';
      ctx.font = '11px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(n.title.substring(0, 20), n.x, n.y + r + 14);

      ctx.globalAlpha = 1;
    });

    ctx.restore();
  }

  function applyFilters(n) {
    var search = searchInput ? searchInput.value.toLowerCase() : '';
    var typeVal = typeFilter ? typeFilter.value : '';
    var highlight = highlightSelect ? highlightSelect.value : '';
    if (search && n.title.toLowerCase().indexOf(search) < 0 &&
        n.id.toLowerCase().indexOf(search) < 0) return false;
    if (typeVal && n.artifact_type !== typeVal) return false;
    if (highlight === 'needs-review' && n.status !== 'needs-review') return false;
    if (highlight === 'conflicted' && n.status !== 'conflicted') return false;
    if (highlight === 'zero-source' && !n.zero_source) return false;
    return true;
  }

  function findNodeAt(sx, sy) {
    var w = screenToWorld(sx, sy);
    var best = null, bestDist = Infinity;
    simNodes.forEach(function(n) {
      var dx = n.x - w.x, dy = n.y - w.y;
      var d = Math.sqrt(dx*dx + dy*dy);
      if (d < nodeRadius(n) + 8 && d < bestDist) { best = n; bestDist = d; }
    });
    return best;
  }

  function showDetail(n) {
    activeNode = n;
    if (!detailPane) return;
    if (!n) { detailPane.innerHTML = '<p style="color:#888">Click a node to inspect.</p>'; return; }
    var html = '<h3 style="margin:0 0 8px">' + esc(n.title) + '</h3>';
    html += badge('status', n.status, STATUS_COLORS[n.status] || '#607d8b');
    html += badge('tier', n.source_tier, TIER_COLORS[n.source_tier] || '#b0bec5');
    if (n.zero_source) html += badge('!', 'zero-source', '#ff5722');
    if (n.attention)   html += badge('!', n.status, '#f44336');
    html += '<table style="margin-top:10px;border-collapse:collapse;width:100%;font-size:12px">';
    var rows = [
      ['Type',         n.artifact_type || '—'],
      ['Status',       n.status],
      ['Tier',         n.source_tier],
      ['Source count', String(n.source_count)],
      ['Tags',         n.tags.join(', ') || '—'],
      ['Sources',      n.sources.join(', ') || '—'],
    ];
    if (n.description) rows.splice(0, 0, ['Description', n.description]);
    rows.forEach(function(r) {
      html += '<tr><td style="padding:2px 6px;color:#666;white-space:nowrap">' + esc(r[0]) +
              '</td><td style="padding:2px 6px">' + esc(r[1]) + '</td></tr>';
    });
    html += '</table>';
    if (n.backlinks && n.backlinks.length) {
      html += '<p style="margin:10px 0 4px;font-size:12px;color:#555">Backlinks: ' +
              n.backlinks.map(esc).join(', ') + '</p>';
    }
    if (n.body_excerpt) {
      html += '<p style="margin:10px 0 4px;font-size:11px;color:#555;font-family:monospace">' +
              esc(n.body_excerpt.substring(0, 300)) + '</p>';
    }
    detailPane.innerHTML = html;
  }

  function badge(label, value, color) {
    return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;background:' +
           color + ';color:#fff;font-size:11px;margin:2px">' + esc(label + ':' + value) + '</span>';
  }

  function esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function buildLegend() {
    var el = document.getElementById('legend');
    if (!el) return;
    var html = '<b style="display:block;margin-bottom:4px">Status</b>';
    Object.keys(STATUS_COLORS).forEach(function(s) {
      html += '<span style="display:inline-flex;align-items:center;margin:2px 6px 2px 0">' +
              '<span style="width:12px;height:12px;border-radius:50%;background:' +
              STATUS_COLORS[s] + ';display:inline-block;margin-right:4px"></span>' + s + '</span>';
    });
    html += '<b style="display:block;margin:8px 0 4px">Tier (ring)</b>';
    Object.keys(TIER_COLORS).forEach(function(t) {
      html += '<span style="display:inline-flex;align-items:center;margin:2px 6px 2px 0">' +
              '<span style="width:12px;height:12px;border-radius:50%;background:' +
              TIER_COLORS[t] + ';display:inline-block;margin-right:4px"></span>' + t + '</span>';
    });
    el.innerHTML = html;
  }

  function populateTypeFilter() {
    if (!typeFilter) return;
    var types = {};
    simNodes.forEach(function(n) { if (n.artifact_type) types[n.artifact_type] = true; });
    typeFilter.innerHTML = '<option value="">All types</option>';
    Object.keys(types).sort().forEach(function(t) {
      typeFilter.innerHTML += '<option value="' + esc(t) + '">' + esc(t) + '</option>';
    });
  }

  function init() {
    canvas = document.getElementById('graph-canvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');
    detailPane   = document.getElementById('detail-pane');
    searchInput  = document.getElementById('search');
    typeFilter   = document.getElementById('type-filter');
    highlightSelect = document.getElementById('highlight-select');
    tooltip      = document.getElementById('tooltip');

    graphData = window.GRAPH_DATA;
    if (!graphData) return;

    // Clone nodes for simulation (add x,y,vx,vy)
    simNodes = graphData.nodes.map(function(n) { return Object.assign({}, n); });
    simLinks = graphData.links.slice();
    nodeMap  = {};
    simNodes.forEach(function(n) { nodeMap[n.id] = n; });

    var W = canvas.clientWidth || canvas.width;
    var H = canvas.clientHeight || canvas.height;
    canvas.width  = W;
    canvas.height = H;

    runLayout(simNodes, simLinks, W, H);
    populateTypeFilter();
    buildLegend();
    showDetail(null);
    draw();

    // Events
    canvas.addEventListener('mousedown', function(e) {
      var rect = canvas.getBoundingClientRect();
      var sx = e.clientX - rect.left, sy = e.clientY - rect.top;
      var n = findNodeAt(sx, sy);
      if (n) { dragging = n; dragStart = { mx: sx, my: sy, nx: n.x, ny: n.y }; }
      else    { dragging = null; dragStart = { mx: sx, my: sy, dx: transform.dx, dy: transform.dy }; }
    });
    canvas.addEventListener('mousemove', function(e) {
      var rect = canvas.getBoundingClientRect();
      var sx = e.clientX - rect.left, sy = e.clientY - rect.top;
      if (dragStart) {
        var ddx = sx - dragStart.mx, ddy = sy - dragStart.my;
        if (dragging) {
          dragging.x = dragStart.nx + ddx / transform.scale;
          dragging.y = dragStart.ny + ddy / transform.scale;
        } else {
          transform.dx = dragStart.dx + ddx;
          transform.dy = dragStart.dy + ddy;
        }
        draw();
      }
      // Tooltip
      var n = findNodeAt(sx, sy);
      if (n && tooltip) {
        tooltip.style.display = 'block';
        tooltip.style.left = (e.clientX + 12) + 'px';
        tooltip.style.top  = (e.clientY + 12) + 'px';
        tooltip.textContent = n.description || n.title;
      } else if (tooltip) {
        tooltip.style.display = 'none';
      }
    });
    canvas.addEventListener('mouseup', function(e) {
      if (dragStart && !dragging) {
        var rect = canvas.getBoundingClientRect();
        var sx = e.clientX - rect.left, sy = e.clientY - rect.top;
        var ddx = Math.abs(sx - dragStart.mx), ddy = Math.abs(sy - dragStart.my);
        if (ddx < 4 && ddy < 4) {
          var n = findNodeAt(sx, sy);
          showDetail(n || null);
        }
      }
      dragging = null; dragStart = null;
    });
    canvas.addEventListener('wheel', function(e) {
      e.preventDefault();
      var rect = canvas.getBoundingClientRect();
      var sx = e.clientX - rect.left, sy = e.clientY - rect.top;
      var factor = e.deltaY < 0 ? 1.1 : 0.9;
      transform.dx = sx - factor * (sx - transform.dx);
      transform.dy = sy - factor * (sy - transform.dy);
      transform.scale *= factor;
      draw();
    });

    if (searchInput)     searchInput.addEventListener('input', draw);
    if (typeFilter)      typeFilter.addEventListener('change', draw);
    if (highlightSelect) highlightSelect.addEventListener('change', draw);

    document.getElementById('btn-reset') && document.getElementById('btn-reset').addEventListener('click', function() {
      transform = { scale: 1, dx: 0, dy: 0 };
      draw();
    });
    document.getElementById('btn-fit') && document.getElementById('btn-fit').addEventListener('click', function() {
      if (!simNodes.length) return;
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      simNodes.forEach(function(n) {
        if (n.x < minX) minX = n.x; if (n.x > maxX) maxX = n.x;
        if (n.y < minY) minY = n.y; if (n.y > maxY) maxY = n.y;
      });
      var padX = (maxX - minX) * 0.1, padY = (maxY - minY) * 0.1;
      minX -= padX; maxX += padX; minY -= padY; maxY += padY;
      var W = canvas.width, H = canvas.height;
      var scale = Math.min(W / (maxX - minX), H / (maxY - minY), 2);
      transform.scale = scale;
      transform.dx = (W - (minX + maxX) * scale) / 2;
      transform.dy = (H - (minY + maxY) * scale) / 2;
      draw();
    });
  }

  // Init after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLM Wiki Graph — {title}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{display:flex;flex-direction:column;height:100vh;font-family:system-ui,sans-serif;background:#f5f5f5;color:#212121}}
#toolbar{{display:flex;align-items:center;gap:8px;padding:8px 12px;background:#263238;color:#eceff1;flex-shrink:0;flex-wrap:wrap}}
#toolbar h1{{font-size:14px;font-weight:600;margin-right:8px;white-space:nowrap}}
#toolbar input,#toolbar select{{font-size:12px;padding:4px 8px;border:none;border-radius:4px;background:#37474f;color:#eceff1;min-width:120px}}
#toolbar button{{font-size:12px;padding:4px 10px;border:none;border-radius:4px;background:#546e7a;color:#fff;cursor:pointer}}
#toolbar button:hover{{background:#78909c}}
#main{{display:flex;flex:1;overflow:hidden}}
#graph-area{{flex:1;position:relative;overflow:hidden}}
#graph-canvas{{display:block;width:100%;height:100%;background:#fafafa;cursor:grab}}
#graph-canvas:active{{cursor:grabbing}}
#tooltip{{position:fixed;display:none;background:rgba(38,50,56,0.92);color:#eceff1;padding:6px 10px;border-radius:6px;font-size:12px;max-width:260px;pointer-events:none;z-index:100}}
#sidebar{{width:280px;display:flex;flex-direction:column;border-left:1px solid #cfd8dc;overflow:hidden;background:#fff}}
#detail-pane{{flex:1;overflow-y:auto;padding:12px;font-size:13px}}
#legend{{padding:10px 12px;border-top:1px solid #cfd8dc;font-size:11px;color:#555;line-height:1.6}}
#stats-bar{{font-size:11px;color:#90a4ae;padding:4px 12px;background:#263238;flex-shrink:0}}
.status-needs-review,.status-conflicted{{font-weight:700}}
</style>
</head>
<body>
<div id="toolbar">
  <h1>LLM Wiki Graph</h1>
  <input id="search" type="search" placeholder="Search nodes…" autocomplete="off">
  <select id="type-filter"></select>
  <select id="highlight-select">
    <option value="">Highlight…</option>
    <option value="needs-review">needs-review</option>
    <option value="conflicted">conflicted</option>
    <option value="zero-source">zero-source</option>
  </select>
  <button id="btn-reset">Reset view</button>
  <button id="btn-fit">Fit all</button>
</div>
<div id="stats-bar">{stats_line}</div>
<div id="main">
  <div id="graph-area">
    <canvas id="graph-canvas"></canvas>
    <div id="tooltip"></div>
  </div>
  <div id="sidebar">
    <div id="detail-pane"><p style="color:#888">Click a node to inspect.</p></div>
    <div id="legend"></div>
  </div>
</div>
<script>
window.GRAPH_DATA = {graph_data_json};
</script>
<script>
{graph_js}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_html(graph: "GraphModel") -> str:
    """Serialise *graph* into a fully self-contained, offline-capable HTML page.

    The output is deterministic: given the same GraphModel content the bytes
    produced are identical across runs (node order is stabilised by sorting on
    node_id before serialisation).

    No external URLs are referenced — all scripts and styles are inlined.
    """
    data = _build_graph_data(graph)

    # Sort keys for determinism
    graph_data_json = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=None)

    node_count = data["node_count"]
    edge_count = data["edge_count"]
    warnings = data["warnings"]
    stats_line = (
        f"Nodes: {node_count}  |  Edges: {edge_count}"
        + (f"  |  ⚠ {len(warnings)} warning(s)" if warnings else "")
    )
    title = graph.root.name or str(graph.root)

    html = _HTML_TEMPLATE.format(
        title=title,
        stats_line=stats_line,
        graph_data_json=graph_data_json,
        graph_js=_GRAPH_JS,
    )
    return html


def render_bundle(graph: "GraphModel", output_dir: Path) -> dict[str, Path]:
    """Write a self-contained browsable bundle into *output_dir*.

    Returns a dict mapping ``"html"`` to the written HTML file path and
    ``"data"`` to the embedded JSON data file (for machine consumers).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    html_content = render_html(graph)
    html_path = output_dir / "index.html"
    html_path.write_text(html_content, encoding="utf-8")

    # Also write the graph data as a standalone JSON for programmatic use.
    data = _build_graph_data(graph)
    json_path = output_dir / "graph-data.json"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )

    return {"html": html_path, "data": json_path}
