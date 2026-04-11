"""
dependency_mapper.py — Advanced Network Dependency Analysis Engine (V2)
========================================================================

V2 upgrades:
  - Full NetworkX graph analysis with SCC, betweenness centrality, critical path
  - Blast radius simulation: "if service X fails, what breaks?"
  - Migration readiness score per workload (0-100)
  - Mermaid diagram export (paste-ready markdown)
  - D3.js JSON export for interactive browser visualization
  - Hub service detection (top services by betweenness centrality)
"""

from __future__ import annotations

import json
import textwrap
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


@dataclass
class WorkloadNode:
    id: str
    name: str
    workload_type: str
    business_criticality: str = "medium"
    strategy: str = "Rehost"
    wave: int | None = None
    migration_readiness_score: int = 50


@dataclass
class DependencyEdge:
    source_id: str
    target_id: str
    dependency_type: str = "runtime"
    strength: str = "tight"
    traffic_mbps: float = 0.0
    calls_per_hour: int = 0

    @property
    def is_blocking(self) -> bool:
        return self.strength == "tight"


@dataclass
class MigrationCluster:
    cluster_id: str
    workload_ids: list[str]
    reason: str
    is_circular: bool = False
    recommended_strategy_override: str | None = None


@dataclass
class DependencyGraph:
    graph: nx.DiGraph
    nodes: dict[str, WorkloadNode]
    edges: list[DependencyEdge]
    clusters: list[MigrationCluster]
    topological_order: list[str]
    circular_dependencies: list[list[str]]
    critical_path: list[str]
    orphan_nodes: list[str]
    scc_map: dict[str, int]                    # node_id -> SCC index
    betweenness_centrality: dict[str, float]   # node_id -> 0.0-1.0
    hub_services: list[str]                    # top 5 by betweenness
    blast_radius_map: dict[str, list[str]]     # node_id -> list of impacted node_ids


class DependencyMapper:
    """
    V2 advanced workload dependency graph analyzer.

    New capabilities:
    - SCC detection with node-level SCC membership
    - Betweenness centrality — identify "hub" services
    - Critical path analysis for wave sequencing
    - Blast radius simulation per node
    - Mermaid + D3.js export
    """

    def __init__(self) -> None:
        self._nodes: dict[str, WorkloadNode] = {}
        self._edges: list[DependencyEdge] = []
        self._graph = nx.DiGraph()

    def add_node(self, node: WorkloadNode) -> None:
        self._nodes[node.id] = node
        self._graph.add_node(
            node.id,
            label=node.name,
            workload_type=node.workload_type,
            criticality=node.business_criticality,
            strategy=node.strategy,
            migration_readiness=node.migration_readiness_score,
        )

    def add_nodes(self, nodes: list[WorkloadNode]) -> None:
        for node in nodes:
            self.add_node(node)

    def add_edge(self, edge: DependencyEdge) -> None:
        if edge.source_id not in self._nodes:
            raise ValueError(f"Source node '{edge.source_id}' not found.")
        if edge.target_id not in self._nodes:
            raise ValueError(f"Target node '{edge.target_id}' not found.")
        self._edges.append(edge)
        self._graph.add_edge(
            edge.source_id,
            edge.target_id,
            dependency_type=edge.dependency_type,
            strength=edge.strength,
            traffic_mbps=edge.traffic_mbps,
            calls_per_hour=edge.calls_per_hour,
        )

    def add_edges(self, edges: list[DependencyEdge]) -> None:
        for edge in edges:
            self.add_edge(edge)

    # -----------------------------------------------------------------------
    # Analysis methods
    # -----------------------------------------------------------------------

    def _compute_scc_map(self) -> dict[str, int]:
        """Assign each node its Strongly Connected Component index."""
        sccs = list(nx.strongly_connected_components(self._graph))
        scc_map: dict[str, int] = {}
        for idx, scc in enumerate(sccs):
            for node_id in scc:
                scc_map[node_id] = idx
        return scc_map

    def _compute_betweenness(self) -> dict[str, float]:
        """Compute betweenness centrality for all nodes."""
        try:
            return dict(nx.betweenness_centrality(self._graph, normalized=True))
        except Exception:
            return {n: 0.0 for n in self._graph.nodes()}

    def _compute_blast_radius(self) -> dict[str, list[str]]:
        """
        For each node, compute the blast radius:
        the set of nodes that would be impacted if this node failed during migration.
        Uses BFS on reversed graph (dependents).
        """
        blast: dict[str, list[str]] = {}
        reversed_g = self._graph.reverse(copy=True)

        for node_id in self._graph.nodes():
            # All nodes reachable from this node in reversed graph = dependents
            try:
                impacted = set(nx.descendants(reversed_g, node_id))
                impacted.discard(node_id)
                blast[node_id] = list(impacted)
            except Exception:
                blast[node_id] = []

        return blast

    def _find_clusters(self, scc_map: dict[str, int]) -> list[MigrationCluster]:
        clusters: list[MigrationCluster] = []

        # Circular clusters: SCCs with size > 1
        scc_groups: dict[int, list[str]] = defaultdict(list)
        for node_id, scc_idx in scc_map.items():
            scc_groups[scc_idx].append(node_id)

        for i, (scc_idx, members) in enumerate(scc_groups.items()):
            if len(members) > 1:
                cluster = MigrationCluster(
                    cluster_id=f"CIRCULAR-{i+1:02d}",
                    workload_ids=members,
                    reason=(
                        f"Circular dependency detected — {len(members)} workloads form a dependency cycle. "
                        f"Must containerize or Refactor to break the loop."
                    ),
                    is_circular=True,
                    recommended_strategy_override="Refactor",
                )
                clusters.append(cluster)

        # Tight clusters: weakly connected via tight edges
        tight_edges = [(e.source_id, e.target_id) for e in self._edges if e.strength == "tight"]
        tight_graph = nx.DiGraph()
        tight_graph.add_nodes_from(self._nodes.keys())
        tight_graph.add_edges_from(tight_edges)

        already_clustered_nodes: set[str] = set()
        for c in clusters:
            already_clustered_nodes.update(c.workload_ids)

        for i, component in enumerate(nx.weakly_connected_components(tight_graph)):
            if len(component) < 2:
                continue
            if component.issubset(already_clustered_nodes):
                continue
            names = [self._nodes[nid].name for nid in component if nid in self._nodes]
            clusters.append(MigrationCluster(
                cluster_id=f"TIGHT-{i+1:02d}",
                workload_ids=list(component),
                reason=f"Tightly coupled via runtime/database dependencies: {', '.join(names[:3])}{'...' if len(names) > 3 else ''}",
                is_circular=False,
            ))

        return clusters

    def _find_circular_dependencies(self) -> list[list[str]]:
        try:
            return [c for c in nx.simple_cycles(self._graph) if len(c) > 1]
        except Exception:
            return []

    def _find_critical_path(self) -> list[str]:
        if nx.is_directed_acyclic_graph(self._graph):
            dag = self._graph
        else:
            dag = self._graph.copy()
            for cycle in nx.simple_cycles(dag):
                if len(cycle) >= 2:
                    dag.remove_edge(cycle[0], cycle[1])
        try:
            return nx.dag_longest_path(dag)
        except Exception:
            return list(self._nodes.keys())[:5]

    def _get_topological_order(self) -> list[str]:
        if nx.is_directed_acyclic_graph(self._graph):
            return list(reversed(list(nx.topological_sort(self._graph))))
        dag = self._graph.copy()
        for cycle in nx.simple_cycles(dag):
            if len(cycle) >= 2:
                dag.remove_edge(cycle[0], cycle[1])
        return list(reversed(list(nx.topological_sort(dag))))

    def _find_orphans(self) -> list[str]:
        return [
            n for n in self._graph.nodes()
            if self._graph.in_degree(n) == 0 and self._graph.out_degree(n) == 0
        ]

    def analyze(self) -> DependencyGraph:
        """Run full dependency analysis. Returns DependencyGraph."""
        scc_map = self._compute_scc_map()
        betweenness = self._compute_betweenness()
        blast_radius = self._compute_blast_radius()
        clusters = self._find_clusters(scc_map)
        circular = self._find_circular_dependencies()
        topo_order = self._get_topological_order()
        critical_path = self._find_critical_path()
        orphans = self._find_orphans()

        # Top 5 hub services by betweenness centrality
        hub_services = sorted(
            betweenness.keys(), key=lambda n: betweenness[n], reverse=True
        )[:5]

        return DependencyGraph(
            graph=self._graph.copy(),
            nodes=dict(self._nodes),
            edges=list(self._edges),
            clusters=clusters,
            topological_order=topo_order,
            circular_dependencies=circular,
            critical_path=critical_path,
            orphan_nodes=orphans,
            scc_map=scc_map,
            betweenness_centrality=betweenness,
            hub_services=hub_services,
            blast_radius_map=blast_radius,
        )

    # -----------------------------------------------------------------------
    # Visualization / Export
    # -----------------------------------------------------------------------

    def print_ascii_graph(self, dep_graph: DependencyGraph) -> None:
        """Print layered ASCII dependency visualization."""
        g = dep_graph.graph
        nodes = dep_graph.nodes

        roots = [n for n in g.nodes() if g.in_degree(n) == 0]
        if not roots:
            roots = list(g.nodes())[:3]

        layers: dict[str, int] = {}
        for root in roots:
            layers[root] = 0
            try:
                for node, successors in nx.bfs_successors(g, root):
                    layer = layers.get(node, 0)
                    for s in successors:
                        layers[s] = max(layers.get(s, 0), layer + 1)
            except Exception:
                pass

        layer_groups: dict[int, list[str]] = defaultdict(list)
        for nid, layer in layers.items():
            layer_groups[layer].append(nid)
        for nid in g.nodes():
            if nid not in layers:
                layer_groups[max(layer_groups.keys(), default=0) + 1].append(nid)

        console.print("\n[bold blue]Dependency Graph — Migration Wave Layers[/bold blue]")
        console.print("[dim](upper layers migrate first — leaf nodes have no blocking dependencies)[/dim]\n")

        max_layer = max(layer_groups.keys(), default=0)
        hub_ids = set(dep_graph.hub_services)

        for layer_num in range(max_layer + 1):
            nodes_in_layer = layer_groups.get(layer_num, [])
            if not nodes_in_layer:
                continue

            node_strs = []
            for nid in nodes_in_layer:
                node = nodes.get(nid)
                if node:
                    strategy_colors = {
                        "Rehost": "green", "Replatform": "cyan",
                        "Refactor": "yellow", "Repurchase": "magenta",
                        "Retire": "red", "Retain": "blue",
                    }
                    color = strategy_colors.get(node.strategy, "white")
                    short_name = (node.name[:16] + "..") if len(node.name) > 18 else node.name
                    hub_marker = " [HUB]" if nid in hub_ids else ""
                    scc_id = dep_graph.scc_map.get(nid)
                    blast_count = len(dep_graph.blast_radius_map.get(nid, []))
                    blast_str = f" blast:{blast_count}" if blast_count > 0 else ""
                    node_strs.append(
                        f"[{color}][{short_name}{hub_marker}{blast_str}][/{color}]"
                    )
                else:
                    node_strs.append(f"[dim][{nid}][/dim]")

            layer_label = f"Layer {layer_num}" if layer_num > 0 else "Layer 0 (Independent)"
            console.print(f"  [bold]{layer_label}:[/bold]  " + "  -->  ".join(node_strs))

            if layer_num < max_layer:
                next_layer_nodes = layer_groups.get(layer_num + 1, [])
                for nid in nodes_in_layer:
                    succs = [s for s in g.successors(nid) if s in next_layer_nodes]
                    for succ in succs[:2]:
                        src_name = nodes[nid].name[:14] if nid in nodes else nid
                        tgt_name = nodes[succ].name[:14] if succ in nodes else succ
                        edge_data = g.get_edge_data(nid, succ, {})
                        dep_type = edge_data.get("dependency_type", "runtime")
                        console.print(f"    [dim]{src_name} --[{dep_type}]--> {tgt_name}[/dim]")
                console.print()

        # Circular dependency warnings
        if dep_graph.circular_dependencies:
            console.print(
                f"\n[bold red]CRITICAL DEPENDENCY LOOP DETECTED — {len(dep_graph.circular_dependencies)} cycle(s)[/bold red]"
            )
            for cycle in dep_graph.circular_dependencies[:3]:
                cycle_names = [nodes[n].name if n in nodes else n for n in cycle]
                console.print(f"  [red]Cycle: {' --> '.join(cycle_names)} --> {cycle_names[0]}[/red]")
            console.print(
                "[yellow]  Recommendation: These workloads MUST be containerized together or Refactored "
                "to break the circular dependency before migration.[/yellow]"
            )

        # Hub services warning
        if dep_graph.hub_services:
            hub_names = [nodes[h].name if h in nodes else h for h in dep_graph.hub_services[:3]]
            console.print(
                f"\n[bold yellow]HUB SERVICES (high betweenness centrality — schedule carefully):[/bold yellow]"
            )
            for h_id, h_name in zip(dep_graph.hub_services[:3], hub_names):
                centrality = dep_graph.betweenness_centrality.get(h_id, 0.0)
                blast = len(dep_graph.blast_radius_map.get(h_id, []))
                console.print(
                    f"  [yellow]{h_name}[/yellow] — centrality: {centrality:.3f}, blast radius: {blast} services"
                )

        console.print(
            Panel(
                f"  Total workloads:        {g.number_of_nodes():>4}\n"
                f"  Total dependencies:     {g.number_of_edges():>4}\n"
                f"  Migration layers:       {max_layer + 1:>4}\n"
                f"  Tight clusters:         {len(dep_graph.clusters):>4}\n"
                f"  Circular deps (SCC):    {len(dep_graph.circular_dependencies):>4}\n"
                f"  Orphan nodes:           {len(dep_graph.orphan_nodes):>4}\n"
                f"  Hub services:           {len(dep_graph.hub_services):>4}",
                title="[bold]Dependency Graph Summary[/bold]",
                border_style="blue",
            )
        )

        if dep_graph.clusters:
            cluster_table = Table(
                title="Migration Clusters (must migrate together)",
                box=box.SIMPLE,
                header_style="bold white",
            )
            cluster_table.add_column("Cluster ID", style="bold", min_width=12)
            cluster_table.add_column("Type", justify="center")
            cluster_table.add_column("Size", justify="center")
            cluster_table.add_column("Reason", min_width=45)
            cluster_table.add_column("Override", justify="center")

            for cluster in dep_graph.clusters:
                cluster_type = "[red]CIRCULAR[/red]" if cluster.is_circular else "[cyan]TIGHT[/cyan]"
                override = (
                    f"[yellow]{cluster.recommended_strategy_override}[/yellow]"
                    if cluster.recommended_strategy_override else "[dim]None[/dim]"
                )
                cluster_table.add_row(
                    cluster.cluster_id,
                    cluster_type,
                    str(len(cluster.workload_ids)),
                    textwrap.shorten(cluster.reason, 65),
                    override,
                )
            console.print(cluster_table)

    def export_mermaid(self, dep_graph: DependencyGraph) -> str:
        """
        Export dependency graph as a Mermaid diagram string.
        Paste into any Markdown file to get an interactive visual.
        """
        lines = ["```mermaid", "graph TD"]

        strategy_mermaid_styles = {
            "Rehost": "fill:#27ae60,color:#fff",
            "Replatform": "fill:#2980b9,color:#fff",
            "Refactor": "fill:#f39c12,color:#fff",
            "Repurchase": "fill:#8e44ad,color:#fff",
            "Retire": "fill:#c0392b,color:#fff",
            "Retain": "fill:#7f8c8d,color:#fff",
        }

        # Add nodes with strategy-colored boxes
        for nid, node in dep_graph.nodes.items():
            safe_id = nid.replace("-", "_")
            is_hub = nid in dep_graph.hub_services
            is_circular = any(nid in c.workload_ids and c.is_circular for c in dep_graph.clusters)
            label = node.name
            if is_hub:
                label += " [HUB]"
            if is_circular:
                label += " [CYCLE]"
            lines.append(f'    {safe_id}["{label}"]')

        # Add edges
        for edge in dep_graph.edges:
            src = edge.source_id.replace("-", "_")
            tgt = edge.target_id.replace("-", "_")
            arrow = "-->" if edge.strength == "tight" else "-.->"
            label = edge.dependency_type
            lines.append(f"    {src} {arrow}|{label}| {tgt}")

        # Style nodes by strategy
        strategy_groups: dict[str, list[str]] = defaultdict(list)
        for nid, node in dep_graph.nodes.items():
            strategy_groups[node.strategy].append(nid.replace("-", "_"))

        for strategy, node_ids in strategy_groups.items():
            style = strategy_mermaid_styles.get(strategy, "fill:#ecf0f1")
            for nid in node_ids:
                lines.append(f"    style {nid} {style}")

        # Mark hub services with thick border
        for hub_id in dep_graph.hub_services:
            safe_id = hub_id.replace("-", "_")
            lines.append(f"    style {safe_id} stroke:#e74c3c,stroke-width:4px")

        lines.append("```")
        return "\n".join(lines)

    def export_d3_json(self, dep_graph: DependencyGraph) -> dict[str, Any]:
        """
        Export dependency graph as D3.js force-directed graph JSON.
        Load in browser with D3.js for interactive visualization.
        """
        strategy_colors = {
            "Rehost": "#27ae60",
            "Replatform": "#2980b9",
            "Refactor": "#f39c12",
            "Repurchase": "#8e44ad",
            "Retire": "#c0392b",
            "Retain": "#7f8c8d",
        }

        d3_nodes = []
        for nid, node in dep_graph.nodes.items():
            d3_nodes.append({
                "id": nid,
                "name": node.name,
                "workload_type": node.workload_type,
                "strategy": node.strategy,
                "color": strategy_colors.get(node.strategy, "#ecf0f1"),
                "criticality": node.business_criticality,
                "betweenness": round(dep_graph.betweenness_centrality.get(nid, 0.0), 4),
                "is_hub": nid in dep_graph.hub_services,
                "is_circular": any(
                    nid in c.workload_ids and c.is_circular for c in dep_graph.clusters
                ),
                "blast_radius_count": len(dep_graph.blast_radius_map.get(nid, [])),
                "scc_id": dep_graph.scc_map.get(nid, -1),
                "migration_readiness": node.migration_readiness_score,
                "radius": 8 + int(dep_graph.betweenness_centrality.get(nid, 0.0) * 30),
            })

        d3_links = []
        for edge in dep_graph.edges:
            d3_links.append({
                "source": edge.source_id,
                "target": edge.target_id,
                "type": edge.dependency_type,
                "strength": edge.strength,
                "color": "#e74c3c" if edge.strength == "tight" else "#95a5a6",
                "width": 3 if edge.strength == "tight" else 1,
            })

        return {
            "nodes": d3_nodes,
            "links": d3_links,
            "metadata": {
                "total_nodes": len(d3_nodes),
                "total_edges": len(d3_links),
                "hub_services": dep_graph.hub_services,
                "circular_dependency_groups": dep_graph.circular_dependencies,
                "critical_path": dep_graph.critical_path,
            },
        }

    def export_dot(self, dep_graph: DependencyGraph, output_path: str) -> None:
        """Export DOT format for Graphviz rendering."""
        strategy_colors = {
            "Rehost": "#27ae60", "Replatform": "#2980b9", "Refactor": "#f39c12",
            "Repurchase": "#8e44ad", "Retire": "#c0392b", "Retain": "#7f8c8d",
        }

        lines = [
            'digraph MigrationScout {',
            '  rankdir=TB;',
            '  node [shape=box, style=filled, fontname="Helvetica", fontsize=10];',
            '  edge [fontsize=8, color="#555555"];',
            '',
            '  // Nodes',
        ]

        for nid, node in dep_graph.nodes.items():
            color = strategy_colors.get(node.strategy, "#ecf0f1")
            label = node.name.replace('"', '\\"')
            is_hub = nid in dep_graph.hub_services
            blast = len(dep_graph.blast_radius_map.get(nid, []))
            extra = f"\\n[HUB, blast:{blast}]" if is_hub else f"\\n[blast:{blast}]"
            border = ', penwidth=3, color="#e74c3c"' if is_hub else ""
            lines.append(
                f'  "{nid}" [label="{label}\\n[{node.workload_type}]{extra}", '
                f'fillcolor="{color}", fontcolor="white"{border}];'
            )

        lines.append('')
        lines.append('  // Edges')

        for edge in dep_graph.edges:
            style = "solid" if edge.strength == "tight" else "dashed"
            color = "#e74c3c" if edge.strength == "tight" else "#95a5a6"
            lines.append(
                f'  "{edge.source_id}" -> "{edge.target_id}" '
                f'[style={style}, color="{color}", label="{edge.dependency_type}"];'
            )

        lines.append('')
        for i, cluster in enumerate(dep_graph.clusters):
            cluster_color = "#ffcccc" if cluster.is_circular else "#cce5ff"
            lines.append(f'  subgraph cluster_{i} {{')
            lines.append(f'    style=filled;')
            lines.append(f'    fillcolor="{cluster_color}";')
            lines.append(f'    label="{cluster.cluster_id}";')
            for wid in cluster.workload_ids:
                lines.append(f'    "{wid}";')
            lines.append('  }')

        lines.append('}')

        with open(output_path, 'w') as f:
            f.write('\n'.join(lines))
        console.print(f"[green]DOT file exported to: {output_path}[/green]")

    def get_migration_order(self, dep_graph: DependencyGraph) -> list[WorkloadNode]:
        return [dep_graph.nodes[nid] for nid in dep_graph.topological_order if nid in dep_graph.nodes]

    def get_node_metrics(self, dep_graph: DependencyGraph) -> dict[str, dict[str, Any]]:
        """Per-node metrics including blast radius and SCC membership."""
        g = dep_graph.graph
        metrics: dict[str, dict[str, Any]] = {}
        for nid in g.nodes():
            metrics[nid] = {
                "in_degree": g.in_degree(nid),
                "out_degree": g.out_degree(nid),
                "betweenness_centrality": round(dep_graph.betweenness_centrality.get(nid, 0.0), 4),
                "is_critical_path": nid in dep_graph.critical_path,
                "is_orphan": nid in dep_graph.orphan_nodes,
                "is_hub": nid in dep_graph.hub_services,
                "scc_id": dep_graph.scc_map.get(nid, -1),
                "blast_radius": dep_graph.blast_radius_map.get(nid, []),
                "blast_radius_count": len(dep_graph.blast_radius_map.get(nid, [])),
            }
        return metrics

    def simulate_blast_radius(
        self, dep_graph: DependencyGraph, failing_node_id: str
    ) -> dict[str, Any]:
        """
        Simulate what happens if a specific workload fails during migration.
        Returns impacted services, estimated downtime risk, and recovery priority order.
        """
        if failing_node_id not in dep_graph.nodes:
            return {"error": f"Node {failing_node_id} not found"}

        impacted_ids = dep_graph.blast_radius_map.get(failing_node_id, [])
        impacted_nodes = [
            dep_graph.nodes[nid] for nid in impacted_ids if nid in dep_graph.nodes
        ]

        critical_impacted = [
            n for n in impacted_nodes if n.business_criticality in ("high", "critical")
        ]

        # Recovery priority: critical services first, then by betweenness centrality
        recovery_priority = sorted(
            impacted_nodes,
            key=lambda n: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(n.business_criticality, 2),
                -dep_graph.betweenness_centrality.get(n.id, 0.0),
            ),
        )

        return {
            "failing_node": failing_node_id,
            "failing_node_name": dep_graph.nodes[failing_node_id].name,
            "total_impacted": len(impacted_ids),
            "critical_impacted": len(critical_impacted),
            "impacted_services": [
                {
                    "id": n.id,
                    "name": n.name,
                    "criticality": n.business_criticality,
                    "strategy": n.strategy,
                }
                for n in impacted_nodes
            ],
            "recovery_priority": [n.name for n in recovery_priority[:10]],
            "risk_rating": (
                "CRITICAL" if len(critical_impacted) > 3
                else "HIGH" if len(critical_impacted) > 0
                else "MEDIUM" if len(impacted_ids) > 5
                else "LOW"
            ),
            "recommendation": (
                f"Schedule '{dep_graph.nodes[failing_node_id].name}' migration during low-traffic window. "
                f"Pre-provision rollback for {len(impacted_ids)} downstream services."
            ),
        }
