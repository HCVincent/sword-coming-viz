import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import type { RoleLinkUnified, RoleNodeUnified } from '../types/unified';

interface NetworkGraphProps {
  allNodes: RoleNodeUnified[];
  linkedNodes: RoleNodeUnified[];
  isolatedNodes: RoleNodeUnified[];
  links: RoleLinkUnified[];
  totalRoleCount: number;
  linkedRoleCount: number;
  spotlightRoleName?: string | null;
  onNodeClick?: (node: RoleNodeUnified) => void;
  onLinkClick?: (sourceId: string, targetId: string) => void;
  focusNodeId?: string | null;
  onFocusNodeHandled?: () => void;
}

type GraphMode = 'overview' | 'mainline';
type GraphNode = RoleNodeUnified & { x?: number; y?: number; fx?: number | null; fy?: number | null; importanceScore: number; linkCount: number; weightSum: number; clusterKey: string };
type GraphLink = Omit<RoleLinkUnified, 'source' | 'target'> & { source: string; target: string; edgeScore: number; unitSpan: number; isMainline: boolean };
type GraphEndpoint = string | GraphNode | { id: string; name?: string } | null | undefined;

const GRAPH_HEIGHT = 800;
const DEFAULT_EDGE_DENSITY = 34;
const MIN_GRAPH_WIDTH = 360;
const ARROW_MARKER_ID = 'network-arrowhead';
const PRIMARY_ROLE_FALLBACK = '陈平安';
const ACTION_STRENGTH: Record<string, number> = { 冲突: 4, 对峙: 4, 交手: 4, 敌对: 4, 对话: 3, 会见: 3, 同行: 3, 试探: 3, 拜访: 2, 庇护: 2, 归属: 2, 指点: 2, 师承: 2, 等待: 1 };

function buildClusterPositions(keys: string[], width: number, height: number) {
  const positions = new Map<string, { x: number; y: number }>();
  const cols = Math.max(2, Math.ceil(Math.sqrt(keys.length || 1)));
  const rows = Math.max(1, Math.ceil((keys.length || 1) / cols));
  keys.forEach((key, index) => {
    positions.set(key, {
      x: 110 + ((width - 220) * ((index % cols) + 0.5)) / cols,
      y: 110 + ((height - 220) * (Math.floor(index / cols) + 0.5)) / rows,
    });
  });
  return positions;
}

function buildNodeRadius(node: GraphNode, compact: boolean) {
  return Math.min(compact ? 14 : 18, (compact ? 4.5 : 6) + Math.log2((node.appearances ?? 0) + 1) * (compact ? 0.9 : 1.3) + node.linkCount * 0.18);
}

function isGraphEndpointObject(endpoint: GraphEndpoint): endpoint is GraphNode | { id: string; name?: string } {
  return typeof endpoint === 'object' && endpoint !== null && 'id' in endpoint && typeof endpoint.id === 'string';
}

function getGraphEndpointId(endpoint: GraphEndpoint) {
  if (typeof endpoint === 'string') return endpoint;
  if (isGraphEndpointObject(endpoint)) return endpoint.id;
  return '';
}

function createDataKey(nodes: RoleNodeUnified[], links: Array<{ source: GraphEndpoint; target: GraphEndpoint }>) {
  return `${nodes.map((node) => node.id).sort().join(',')}|${links.map((link) => `${getGraphEndpointId(link.source)}-${getGraphEndpointId(link.target)}`).sort().join(',')}`;
}

function isLinkConnectedToNode(link: GraphLink, nodeId: string | null) {
  if (!nodeId) return false;
  const sourceId = getGraphEndpointId(link.source as GraphEndpoint);
  const targetId = getGraphEndpointId(link.target as GraphEndpoint);
  return sourceId === nodeId || targetId === nodeId;
}

function getLinkEndpoints(source: GraphNode, target: GraphNode, sourceRadius: number, targetRadius: number) {
  const dx = (target.x ?? 0) - (source.x ?? 0);
  const dy = (target.y ?? 0) - (source.y ?? 0);
  const distance = Math.sqrt(dx * dx + dy * dy) || 1;
  const maxInset = Math.max(0, distance / 2 - 3);
  const sourceInset = Math.min(Math.max(0, sourceRadius + 1.5), maxInset);
  const targetInset = Math.min(Math.max(0, targetRadius - 1.5), maxInset);
  const ux = dx / distance;
  const uy = dy / distance;

  return {
    x1: (source.x ?? 0) + ux * sourceInset,
    y1: (source.y ?? 0) + uy * sourceInset,
    x2: (target.x ?? 0) - ux * targetInset,
    y2: (target.y ?? 0) - uy * targetInset,
  };
}

function shouldShowLinkArrow(link: GraphLink, graphMode: GraphMode, activeNodeId: string | null) {
  if (!activeNodeId) return false;
  if (!isLinkConnectedToNode(link, activeNodeId)) return false;
  if (graphMode === 'mainline') return true;
  return true;
}

function getLinkMarkerEnd(link: GraphLink, graphMode: GraphMode, activeNodeId: string | null) {
  return shouldShowLinkArrow(link, graphMode, activeNodeId) ? `url(#${ARROW_MARKER_ID})` : null;
}

function cloneGraphLink(link: GraphLink, overrides?: Partial<GraphLink>): GraphLink {
  return {
    ...link,
    source: getGraphEndpointId(link.source as GraphEndpoint),
    target: getGraphEndpointId(link.target as GraphEndpoint),
    ...overrides,
  };
}

export function NetworkGraph({
  allNodes,
  linkedNodes,
  isolatedNodes,
  links,
  totalRoleCount,
  linkedRoleCount,
  spotlightRoleName,
  onNodeClick,
  onLinkClick,
  focusNodeId,
  onFocusNodeHandled,
}: NetworkGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const simulationRef = useRef<d3.Simulation<GraphNode, d3.SimulationLinkDatum<GraphNode>> | null>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const onNodeClickRef = useRef(onNodeClick);
  const onLinkClickRef = useRef(onLinkClick);
  const pinnedNodeIdRef = useRef<string | null>(null);
  const focusNodeIdRef = useRef<string | null>(null);
  const searchResultIdRef = useRef<string | null>(null);
  const activeEdgeNodeIdRef = useRef<string | null>(null);

  const [searchTerm, setSearchTerm] = useState('');
  const [importanceFilter, setImportanceFilter] = useState(0);
  const [selectedPower, setSelectedPower] = useState('all');
  const [showIsolated, setShowIsolated] = useState(false);
  const [graphMode, setGraphMode] = useState<GraphMode>('overview');
  const [edgeDensity, setEdgeDensity] = useState(DEFAULT_EDGE_DENSITY);
  const [highlightedNode, setHighlightedNode] = useState<string | null>(null);
  const [pinnedNodeId, setPinnedNodeId] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; node: GraphNode } | null>(null);
  const [notFoundMessage, setNotFoundMessage] = useState<string | null>(null);
  const [containerWidth, setContainerWidth] = useState(MIN_GRAPH_WIDTH);

  useEffect(() => void (onNodeClickRef.current = onNodeClick), [onNodeClick]);
  useEffect(() => void (onLinkClickRef.current = onLinkClick), [onLinkClick]);
  useEffect(() => void (pinnedNodeIdRef.current = pinnedNodeId), [pinnedNodeId]);
  useEffect(() => void (focusNodeIdRef.current = focusNodeId ?? null), [focusNodeId]);
  useEffect(() => {
    if (!containerRef.current) return;
    const element = containerRef.current;
    const updateWidth = (nextWidth?: number) => {
      const measured = Math.max(MIN_GRAPH_WIDTH, Math.round(nextWidth ?? element.clientWidth ?? MIN_GRAPH_WIDTH));
      setContainerWidth((current) => (current === measured ? current : measured));
    };
    updateWidth();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      updateWidth(entry.contentRect.width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const availablePowers = useMemo(() => Array.from(new Set(allNodes.map((node) => node.power).filter(Boolean) as string[])).sort(), [allNodes]);
  const baseNodes = useMemo(() => (showIsolated ? [...linkedNodes, ...isolatedNodes] : linkedNodes), [isolatedNodes, linkedNodes, showIsolated]);
  const powerNodes = useMemo(() => baseNodes.filter((node) => selectedPower === 'all' || node.power === selectedPower), [baseNodes, selectedPower]);

  const scoredNodes = useMemo(() => {
    const nodeIds = new Set(powerNodes.map((node) => node.id));
    const stats = new Map<string, { linkCount: number; weightSum: number }>();
    powerNodes.forEach((node) => stats.set(node.id, { linkCount: 0, weightSum: 0 }));
    links.forEach((link) => {
      const source = typeof link.source === 'object' ? (link.source as never as { id: string }).id : link.source;
      const target = typeof link.target === 'object' ? (link.target as never as { id: string }).id : link.target;
      if (!nodeIds.has(source) || !nodeIds.has(target)) return;
      const sourceStats = stats.get(source);
      const targetStats = stats.get(target);
      if (sourceStats) { sourceStats.linkCount += 1; sourceStats.weightSum += link.weight; }
      if (targetStats) { targetStats.linkCount += 1; targetStats.weightSum += link.weight; }
    });
    return powerNodes.map((node) => {
      const info = stats.get(node.id) ?? { linkCount: 0, weightSum: 0 };
      return { ...node, importanceScore: info.weightSum * 2.6 + info.linkCount * 4.4 + Math.log2((node.appearances ?? 0) + 1) * 2.4, linkCount: info.linkCount, weightSum: info.weightSum, clusterKey: node.power || '未归类' } satisfies GraphNode;
    }).sort((a, b) => b.importanceScore - a.importanceScore || b.appearances - a.appearances);
  }, [links, powerNodes]);

  const filteredNodes = useMemo(() => {
    if (!scoredNodes.length || importanceFilter <= 0) return scoredNodes.map((node) => ({ ...node }));
    const sortedScores = scoredNodes.map((node) => node.importanceScore).sort((a, b) => a - b);
    const threshold = sortedScores[Math.min(sortedScores.length - 1, Math.floor((sortedScores.length - 1) * (importanceFilter / 100)))];
    return scoredNodes.filter((node) => node.importanceScore >= threshold).map((node) => ({ ...node }));
  }, [importanceFilter, scoredNodes]);

  const baseLinks = useMemo(() => {
    const visibleIds = new Set(filteredNodes.map((node) => node.id));
    return links.flatMap((link) => {
      const source = typeof link.source === 'object' ? (link.source as never as { id: string }).id : link.source;
      const target = typeof link.target === 'object' ? (link.target as never as { id: string }).id : link.target;
      if (!visibleIds.has(source) || !visibleIds.has(target)) return [];
      const actionBoost = Math.max(ACTION_STRENGTH[link.action] ?? 1, ...(link.actionTypes?.map((action) => ACTION_STRENGTH[action] ?? 1) ?? [1]));
      const unitSpan = new Set(link.sourceUnits ?? []).size;
      const progressSpan = link.progressStart != null && link.progressEnd != null ? Math.max(0, link.progressEnd - link.progressStart) : 0;
      return [{ ...link, source, target, unitSpan, edgeScore: link.weight * 5 + actionBoost * 4 + unitSpan * 2 + Math.min(progressSpan, 24) * 0.35, isMainline: false } satisfies GraphLink];
    });
  }, [filteredNodes, links]);

  const primaryRole = useMemo(() => filteredNodes.find((node) => node.name === spotlightRoleName) ?? filteredNodes.find((node) => node.name === PRIMARY_ROLE_FALLBACK) ?? filteredNodes[0] ?? null, [filteredNodes, spotlightRoleName]);
  const searchResult = useMemo(() => (!searchTerm ? null : filteredNodes.find((node) => node.name.includes(searchTerm) || node.aliases.some((alias) => alias.includes(searchTerm))) ?? null), [filteredNodes, searchTerm]);
  const activeEdgeNodeId = highlightedNode ?? pinnedNodeId ?? searchResult?.id ?? focusNodeId ?? null;
  useEffect(() => void (searchResultIdRef.current = searchResult?.id ?? null), [searchResult]);
  useEffect(() => void (activeEdgeNodeIdRef.current = activeEdgeNodeId), [activeEdgeNodeId]);

  useEffect(() => {
    if (searchResult) {
      setHighlightedNode(searchResult.id);
      return;
    }
    if (pinnedNodeId) {
      setHighlightedNode(pinnedNodeId);
      return;
    }
    if (!focusNodeId) setHighlightedNode(null);
  }, [focusNodeId, pinnedNodeId, searchResult]);

  const graphData = useMemo(() => {
    if (!filteredNodes.length || !baseLinks.length) return { nodes: filteredNodes, links: [] as GraphLink[] };
    if (graphMode === 'mainline' && primaryRole) {
      const scope = new Set<string>([primaryRole.id]);
      baseLinks
        .filter((link) => {
          const sourceId = getGraphEndpointId(link.source as GraphEndpoint);
          const targetId = getGraphEndpointId(link.target as GraphEndpoint);
          return sourceId === primaryRole.id || targetId === primaryRole.id;
        })
        .sort((a, b) => b.edgeScore - a.edgeScore)
        .slice(0, 12 + Math.round(edgeDensity * 0.1))
        .forEach((link) => {
          scope.add(getGraphEndpointId(link.source as GraphEndpoint));
          scope.add(getGraphEndpointId(link.target as GraphEndpoint));
        });
      const keptLinks = baseLinks
        .filter((link) => {
          const sourceId = getGraphEndpointId(link.source as GraphEndpoint);
          const targetId = getGraphEndpointId(link.target as GraphEndpoint);
          return scope.has(sourceId) && scope.has(targetId);
        })
        .sort((a, b) => b.edgeScore - a.edgeScore)
        .slice(0, Math.max(18, Math.round(baseLinks.length * (0.16 + edgeDensity / 160))))
        .map((link) => {
          const sourceId = getGraphEndpointId(link.source as GraphEndpoint);
          const targetId = getGraphEndpointId(link.target as GraphEndpoint);
          return cloneGraphLink(link, { isMainline: sourceId === primaryRole.id || targetId === primaryRole.id });
        });
      const ids = new Set<string>(); keptLinks.forEach((link) => { ids.add(link.source); ids.add(link.target); }); ids.add(primaryRole.id);
      return { nodes: filteredNodes.filter((node) => ids.has(node.id) || (showIsolated && node.isIsolated)), links: keptLinks };
    }
    const sorted = [...baseLinks].sort((a, b) => b.edgeScore - a.edgeScore);
    const keepCount = Math.max(filteredNodes.length - 1, Math.round(sorted.length * (0.16 + edgeDensity / 300)));
    const perNodeCap = Math.max(2, 2 + Math.round(edgeDensity / 25));
    const nodeCounts = new Map<string, number>();
    const kept = new Map<string, GraphLink>();
    filteredNodes.forEach((node) => {
      const strongest = sorted.find((link) => {
        const sourceId = getGraphEndpointId(link.source as GraphEndpoint);
        const targetId = getGraphEndpointId(link.target as GraphEndpoint);
        return sourceId === node.id || targetId === node.id;
      });
      if (!strongest) return;
      const strongestSourceId = getGraphEndpointId(strongest.source as GraphEndpoint);
      const strongestTargetId = getGraphEndpointId(strongest.target as GraphEndpoint);
      const key = strongestSourceId < strongestTargetId ? `${strongestSourceId}::${strongestTargetId}` : `${strongestTargetId}::${strongestSourceId}`;
      if (kept.has(key)) return;
      kept.set(key, cloneGraphLink(strongest));
      nodeCounts.set(strongestSourceId, (nodeCounts.get(strongestSourceId) ?? 0) + 1);
      nodeCounts.set(strongestTargetId, (nodeCounts.get(strongestTargetId) ?? 0) + 1);
    });
    sorted.forEach((link) => {
      if (kept.size >= keepCount) return;
      const sourceId = getGraphEndpointId(link.source as GraphEndpoint);
      const targetId = getGraphEndpointId(link.target as GraphEndpoint);
      const key = sourceId < targetId ? `${sourceId}::${targetId}` : `${targetId}::${sourceId}`;
      if (kept.has(key)) return;
      if ((nodeCounts.get(sourceId) ?? 0) >= perNodeCap || (nodeCounts.get(targetId) ?? 0) >= perNodeCap) return;
      kept.set(key, cloneGraphLink(link));
      nodeCounts.set(sourceId, (nodeCounts.get(sourceId) ?? 0) + 1);
      nodeCounts.set(targetId, (nodeCounts.get(targetId) ?? 0) + 1);
    });
    const keptLinks = Array.from(kept.values()).sort((a, b) => b.edgeScore - a.edgeScore);
    const ids = new Set<string>(); keptLinks.forEach((link) => { ids.add(link.source); ids.add(link.target); });
    return { nodes: filteredNodes.filter((node) => ids.has(node.id) || (showIsolated && node.isIsolated)), links: keptLinks };
  }, [baseLinks, edgeDensity, filteredNodes, graphMode, primaryRole, showIsolated]);

  const renderedNodes = graphData.nodes;
  const renderedLinks = graphData.links;
  const buildKey = useMemo(() => `${graphMode}|${containerWidth}|${edgeDensity}|${createDataKey(renderedNodes, renderedLinks)}`, [containerWidth, edgeDensity, graphMode, renderedLinks, renderedNodes]);
  const connectedLabelIds = useMemo(() => {
    if (!activeEdgeNodeId) return new Set<string>();
    const ids = new Set<string>([activeEdgeNodeId]);
    renderedLinks.forEach((link) => {
      const sourceId = getGraphEndpointId(link.source as GraphEndpoint);
      const targetId = getGraphEndpointId(link.target as GraphEndpoint);
      if (sourceId === activeEdgeNodeId) ids.add(targetId);
      if (targetId === activeEdgeNodeId) ids.add(sourceId);
    });
    return ids;
  }, [activeEdgeNodeId, renderedLinks]);

  const labelIds = useMemo(() => {
    const ids = new Set<string>();
    renderedNodes.forEach((node) => ids.add(node.id));
    if (activeEdgeNodeId) {
      connectedLabelIds.forEach((id) => ids.add(id));
    }
    if (primaryRole) ids.add(primaryRole.id);
    if (focusNodeId) ids.add(focusNodeId);
    if (highlightedNode) ids.add(highlightedNode);
    return ids;
  }, [activeEdgeNodeId, connectedLabelIds, focusNodeId, highlightedNode, primaryRole, renderedNodes]);

  const centerOnNode = useCallback((nodeId: string) => {
    if (!svgRef.current || !zoomRef.current) return;
    const node = nodesRef.current.find((item) => item.id === nodeId);
    if (!node || node.x == null || node.y == null) return;
    const width = containerWidth;
    d3.select(svgRef.current).transition().duration(700).call(zoomRef.current.transform, d3.zoomIdentity.translate(width / 2 - node.x * 1.45, GRAPH_HEIGHT / 2 - node.y * 1.45).scale(1.45));
  }, [containerWidth]);

  useEffect(() => {
    if (!focusNodeId) return;
    const visible = renderedNodes.find((node) => node.id === focusNodeId || node.name === focusNodeId);
    if (visible) {
      setHighlightedNode(visible.id);
      setSearchTerm('');
      setTimeout(() => centerOnNode(visible.id), 100);
      onFocusNodeHandled?.();
      return;
    }
    const existing = allNodes.find((node) => node.id === focusNodeId || node.name === focusNodeId);
    if (existing) {
      setGraphMode('overview'); setEdgeDensity(65); setImportanceFilter(0); setSelectedPower('all');
      if (existing.isIsolated) setShowIsolated(true);
      setHighlightedNode(existing.id);
      setTimeout(() => centerOnNode(existing.id), 180);
    } else {
      setNotFoundMessage(`“${focusNodeId}”当前没有进入关系图数据。`);
      window.setTimeout(() => setNotFoundMessage(null), 2600);
    }
    onFocusNodeHandled?.();
  }, [allNodes, centerOnNode, focusNodeId, onFocusNodeHandled, renderedNodes]);

  useEffect(() => {
    if (!svgRef.current || !renderedNodes.length || !containerWidth) return;
    simulationRef.current?.stop();

    const width = containerWidth;
    const compact = renderedNodes.length >= 90;
    const colorScale = d3.scaleOrdinal<string, string>(d3.schemeTableau10).domain([...new Set(renderedNodes.map((node) => node.clusterKey))]);
    const clusterPositions = buildClusterPositions([...new Set(renderedNodes.map((node) => node.clusterKey))], width, GRAPH_HEIGHT);
    const radiusMap = new Map(renderedNodes.map((node) => [node.id, buildNodeRadius(node, compact)]));
    const simulationLinks = renderedLinks.map((link) => cloneGraphLink(link));
    const seededNodes = renderedNodes.map((node, index) => {
      const cluster = clusterPositions.get(node.clusterKey) ?? { x: width / 2, y: GRAPH_HEIGHT / 2 };
      return { ...node, x: cluster.x + ((index % 6) - 3) * 16, y: cluster.y + (Math.floor(index / 6) % 6 - 3) * 14 };
    });

    d3.select(svgRef.current).selectAll('*').remove();
    const svg = d3.select(svgRef.current).attr('width', width).attr('height', GRAPH_HEIGHT).attr('viewBox', [0, 0, width, GRAPH_HEIGHT]);
    const root = svg.append('g');
    const zoom = d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.32, 4.2]).on('zoom', (event) => root.attr('transform', event.transform));
    svg.call(zoom);
    zoomRef.current = zoom;
    svg.on('click', () => {
      setPinnedNodeId(null);
      setHighlightedNode(searchResultIdRef.current ?? focusNodeIdRef.current ?? null);
      setTooltip(null);
    });
    svg.append('defs')
      .append('marker')
      .attr('id', ARROW_MARKER_ID)
      .attr('viewBox', '0 -4 8 8')
      .attr('refX', 7.2)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerUnits', 'userSpaceOnUse')
      .attr('markerWidth', 5)
      .attr('markerHeight', 5)
      .append('path')
      .attr('d', 'M 0,-3.2 L 7.2,0 L 0,3.2 Z')
      .attr('fill', '#7f98a0');

    const simulation = d3.forceSimulation<GraphNode>(seededNodes)
      .force('link', d3.forceLink<GraphNode, d3.SimulationLinkDatum<GraphNode>>(simulationLinks as unknown as d3.SimulationLinkDatum<GraphNode>[]).id((node) => node.id).distance((link) => Math.max(80, (graphMode === 'mainline' ? 118 : 148) - ((link as never as GraphLink).edgeScore * 1.2))).strength((link) => Math.min(0.9, 0.15 + (link as never as GraphLink).edgeScore / 120)))
      .force('charge', d3.forceManyBody().strength(graphMode === 'mainline' ? -(380 + renderedNodes.length * 4) : -(520 + renderedNodes.length * 6)))
      .force('collision', d3.forceCollide<GraphNode>().radius((node) => (radiusMap.get(node.id) ?? 8) + 18))
      .force('x', d3.forceX<GraphNode>((node) => (clusterPositions.get(node.clusterKey) ?? { x: width / 2 }).x).strength(graphMode === 'mainline' ? 0.08 : 0.16))
      .force('y', d3.forceY<GraphNode>((node) => (clusterPositions.get(node.clusterKey) ?? { y: GRAPH_HEIGHT / 2 }).y).strength(graphMode === 'mainline' ? 0.08 : 0.16))
      .force('center', d3.forceCenter(width / 2, GRAPH_HEIGHT / 2).strength(0.04));

    simulationRef.current = simulation;
    nodesRef.current = seededNodes;

    const linkSelection = root.append('g').selectAll('line').data(simulationLinks).enter().append('line')
      .attr('stroke', (link) => (link.isMainline ? '#7b1e1e' : '#7f98a0'))
      .attr('stroke-opacity', (link) => (link.isMainline ? 0.68 : 0.24))
      .attr('stroke-width', (link) => Math.min(3.2, 0.85 + link.edgeScore / 22))
      .attr('marker-end', (link) => getLinkMarkerEnd(link, graphMode, activeEdgeNodeIdRef.current))
      .style('cursor', (link) => (isLinkConnectedToNode(link, activeEdgeNodeIdRef.current) ? 'pointer' : 'default'))
      .style('pointer-events', (link) => (isLinkConnectedToNode(link, activeEdgeNodeIdRef.current) ? 'stroke' : 'none'))
      .on('click', (event, link) => {
        if (!isLinkConnectedToNode(link, activeEdgeNodeIdRef.current)) return;
        event.preventDefault();
        event.stopPropagation();
        onLinkClickRef.current?.(getGraphEndpointId(link.source as GraphEndpoint), getGraphEndpointId(link.target as GraphEndpoint));
      });

    const dragBehavior = d3.drag<SVGGElement, GraphNode>()
      .on('start', (event, node) => { if (!event.active) simulation.alphaTarget(0.22).restart(); node.fx = node.x; node.fy = node.y; })
      .on('drag', (event, node) => { node.fx = event.x; node.fy = event.y; })
      .on('end', (event, node) => { if (!event.active) simulation.alphaTarget(0); node.fx = null; node.fy = null; });

    const nodeSelection = root.append('g').selectAll<SVGGElement, GraphNode>('g').data(seededNodes).enter().append('g').attr('class', 'node-group').style('cursor', 'pointer')
      .call(dragBehavior as never)
      .on('click', (event, node) => {
        event.preventDefault();
        event.stopPropagation();
        setPinnedNodeId(node.id);
        setHighlightedNode(node.id);
        onNodeClickRef.current?.(node);
      })
      .on('mouseover', (event, node) => {
        setTooltip({ x: event.pageX, y: event.pageY, node });
        setHighlightedNode(node.id);
      })
      .on('mouseout', () => {
        setTooltip(null);
        setHighlightedNode(searchResultIdRef.current ?? pinnedNodeIdRef.current ?? focusNodeIdRef.current ?? null);
      });

    nodeSelection.append('circle')
      .attr('r', (node) => radiusMap.get(node.id) ?? 8)
      .attr('fill', (node) => colorScale(node.clusterKey))
      .attr('fill-opacity', (node) => (node.isIsolated ? 0.32 : 0.92))
      .attr('stroke', (node) => (node.id === primaryRole?.id ? '#7b1e1e' : '#ffffff'))
      .attr('stroke-width', (node) => (node.id === primaryRole?.id ? 2.8 : node.isIsolated ? 1.3 : 1.9))
      .attr('stroke-dasharray', (node) => (node.isIsolated ? '3,2' : null));

    nodeSelection.append('text')
      .attr('class', 'node-label')
      .attr('x', 0).attr('y', (node) => -(radiusMap.get(node.id) ?? 8) - 7).attr('text-anchor', 'middle')
      .style('font-size', compact ? '9px' : '10px').style('font-weight', (node) => (node.id === primaryRole?.id ? '700' : '500'))
      .style('fill', '#183441').style('paint-order', 'stroke').style('stroke', 'rgba(249,252,252,0.92)').style('stroke-width', '3px').style('stroke-linejoin', 'round')
      .style('opacity', (node) => (labelIds.has(node.id) ? 1 : 0)).text((node) => node.name);

    const updateLinkGeometry = () => {
      linkSelection.each(function updateGeometry(link) {
        const source = link.source as never as GraphNode;
        const target = link.target as never as GraphNode;
        const endpoints = getLinkEndpoints(
          source,
          target,
          radiusMap.get(source.id) ?? 8,
          radiusMap.get(target.id) ?? 8,
        );
        d3.select(this)
          .attr('x1', endpoints.x1)
          .attr('y1', endpoints.y1)
          .attr('x2', endpoints.x2)
          .attr('y2', endpoints.y2);
      });
    };

    simulation.on('tick', () => {
      updateLinkGeometry();
      nodeSelection.attr('transform', (node) => `translate(${node.x ?? 0}, ${node.y ?? 0})`);
    });

    updateLinkGeometry();
    nodeSelection.attr('transform', (node) => `translate(${node.x ?? 0}, ${node.y ?? 0})`);

    return () => { simulation.stop(); simulationRef.current = null; };
  }, [buildKey, containerWidth, graphMode, primaryRole, renderedLinks, renderedNodes]);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg
      .selectAll<SVGTextElement, GraphNode>('.node-label')
      .style('opacity', (node) => (labelIds.has(node.id) ? 1 : 0));
  }, [labelIds]);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg
      .selectAll<SVGLineElement, GraphLink>('line')
      .attr('marker-end', (link) => getLinkMarkerEnd(link, graphMode, activeEdgeNodeId))
      .style('cursor', (link) => (isLinkConnectedToNode(link, activeEdgeNodeId) ? 'pointer' : 'default'))
      .style('pointer-events', (link) => (isLinkConnectedToNode(link, activeEdgeNodeId) ? 'stroke' : 'none'));
  }, [activeEdgeNodeId, graphMode]);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    const nodeSelection = svg.selectAll<SVGGElement, GraphNode>('.node-group');
    const linkSelection = svg.selectAll<SVGLineElement, GraphLink>('line');
    if (!highlightedNode) { nodeSelection.style('opacity', (node) => (node.isIsolated ? 0.58 : 1)); linkSelection.style('opacity', (link) => (link.isMainline ? 0.72 : 1)); return; }
    const connected = new Set<string>([highlightedNode]);
    renderedLinks.forEach((link) => {
      const sourceId = getGraphEndpointId(link.source as GraphEndpoint);
      const targetId = getGraphEndpointId(link.target as GraphEndpoint);
      if (sourceId === highlightedNode) connected.add(targetId);
      if (targetId === highlightedNode) connected.add(sourceId);
    });
    nodeSelection.style('opacity', (node) => (connected.has(node.id) ? 1 : 0.12));
    linkSelection.style('opacity', (link) => {
      const sourceId = getGraphEndpointId(link.source as GraphEndpoint);
      const targetId = getGraphEndpointId(link.target as GraphEndpoint);
      return sourceId === highlightedNode || targetId === highlightedNode ? 1 : 0.08;
    });
  }, [highlightedNode, renderedLinks]);

  const renderedLinkedCount = renderedNodes.filter((node) =>
    renderedLinks.some((link) => {
      const sourceId = getGraphEndpointId(link.source as GraphEndpoint);
      const targetId = getGraphEndpointId(link.target as GraphEndpoint);
      return sourceId === node.id || targetId === node.id;
    }),
  ).length;
  const renderedIsolatedCount = renderedNodes.length - renderedLinkedCount;

  return (
    <div ref={containerRef} className="relative overflow-hidden rounded-[32px] border border-[rgba(49,86,98,0.12)] bg-white/90 p-5 shadow-[0_22px_60px_rgba(22,47,60,0.08)] md:p-6">
      <div className="flex flex-col gap-4 border-b border-[rgba(49,86,98,0.1)] pb-5">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <h3 className="text-[1.55rem] font-semibold tracking-[0.02em] text-[var(--accent-deep)]">人物关系网络图</h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">全景关系适合看群像分布，主线关系适合围绕 {primaryRole?.name ?? PRIMARY_ROLE_FALLBACK} 拆主干互动。默认图只画骨干边，关系详情仍保留当前范围内的完整记录。</p>
          </div>
          <div className="grid min-w-[280px] grid-cols-3 gap-3 text-sm">
            <div className="rounded-2xl border border-[rgba(49,86,98,0.12)] bg-[rgba(244,248,248,0.9)] px-4 py-3"><div className="text-[0.75rem] tracking-[0.08em] text-[var(--text-muted)]">知识库人物</div><div className="mt-1 text-2xl font-semibold text-[var(--accent-deep)]">{totalRoleCount}</div></div>
            <div className="rounded-2xl border border-[rgba(49,86,98,0.12)] bg-[rgba(244,248,248,0.9)] px-4 py-3"><div className="text-[0.75rem] tracking-[0.08em] text-[var(--text-muted)]">当前可见人物</div><div className="mt-1 text-2xl font-semibold text-[var(--accent-deep)]">{renderedNodes.length}</div></div>
            <div className="rounded-2xl border border-[rgba(49,86,98,0.12)] bg-[rgba(244,248,248,0.9)] px-4 py-3"><div className="text-[0.75rem] tracking-[0.08em] text-[var(--text-muted)]">当前渲染关系</div><div className="mt-1 text-2xl font-semibold text-[var(--accent-deep)]">{renderedLinks.length}</div></div>
          </div>
        </div>
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex min-w-[180px] flex-1 items-center gap-2 rounded-full border border-[rgba(49,86,98,0.14)] bg-[rgba(244,248,248,0.9)] px-4 py-2 text-sm text-[var(--text-secondary)]"><span>搜索人物</span><input type="text" value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} placeholder="输入姓名或别名" className="min-w-0 flex-1 bg-transparent text-[var(--accent-deep)] outline-none placeholder:text-[var(--text-muted)]" /></label>
            <label className="flex items-center gap-2 rounded-full border border-[rgba(49,86,98,0.14)] bg-[rgba(244,248,248,0.9)] px-4 py-2 text-sm text-[var(--text-secondary)]"><span>阵营筛选</span><select value={selectedPower} onChange={(event) => setSelectedPower(event.target.value)} className="bg-transparent text-[var(--accent-deep)] outline-none"><option value="all">全部</option>{availablePowers.map((power) => <option key={power} value={power}>{power}</option>)}</select></label>
            <label className="flex items-center gap-2 rounded-full border border-[rgba(49,86,98,0.14)] bg-[rgba(244,248,248,0.9)] px-4 py-2 text-sm text-[var(--text-secondary)]"><span>显示模式</span><select value={graphMode} onChange={(event) => setGraphMode(event.target.value as GraphMode)} className="bg-transparent text-[var(--accent-deep)] outline-none"><option value="overview">全景关系</option><option value="mainline">主线关系</option></select></label>
          </div>
          <div className="flex flex-wrap items-center justify-start gap-4 lg:justify-end">
            <label className="flex items-center gap-3 text-sm text-[var(--text-secondary)]"><span>连线强度</span><input type="range" min="10" max="100" step="5" value={edgeDensity} onChange={(event) => setEdgeDensity(parseInt(event.target.value, 10))} className="w-28 accent-[var(--accent-strong)]" /><span className="w-10 text-right text-[var(--accent-deep)]">{edgeDensity}%</span></label>
            <label className="flex items-center gap-3 text-sm text-[var(--text-secondary)]"><span>重要度</span><input type="range" min="0" max="100" step="5" value={importanceFilter} onChange={(event) => setImportanceFilter(parseInt(event.target.value, 10))} className="w-24 accent-[var(--accent-strong)]" /><span className="w-10 text-right text-[var(--accent-deep)]">{importanceFilter}%</span></label>
            <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]"><input type="checkbox" checked={showIsolated} onChange={(event) => setShowIsolated(event.target.checked)} className="accent-[var(--accent-strong)]" /><span>显示孤立人物</span></label>
          </div>
        </div>
        <div className="grid gap-2 text-xs leading-6 text-[var(--text-muted)] md:grid-cols-3">
          <div>当前范围共有 {totalRoleCount} 位人物，其中 {linkedRoleCount} 位已有关系记录。</div>
          <div>当前图中保留 {renderedNodes.length} 位人物，连边人物 {renderedLinkedCount} 位，孤立人物 {renderedIsolatedCount} 位。</div>
          <div>先点人物，再看关系；没有选中人物时，关系线不会抢占鼠标。</div>
        </div>
      </div>

      <div className="relative mt-5 overflow-hidden rounded-[28px] border border-[rgba(49,86,98,0.1)] bg-[linear-gradient(180deg,rgba(250,252,252,0.98),rgba(242,247,247,0.96))]"><svg ref={svgRef} className="block w-full" /></div>

      {notFoundMessage && <div className="absolute left-1/2 top-24 z-20 -translate-x-1/2 rounded-full border border-[rgba(123,30,30,0.16)] bg-[rgba(255,248,246,0.98)] px-4 py-2 text-sm text-[#7b1e1e] shadow-lg">{notFoundMessage}</div>}

      {tooltip && <div className="pointer-events-none absolute z-20 w-[320px] max-w-[92vw] rounded-[22px] border border-[rgba(49,86,98,0.12)] bg-white/96 p-4 shadow-[0_18px_42px_rgba(22,47,60,0.18)]" style={{ left: Math.max(12, Math.min(tooltip.x - 120, (containerRef.current?.clientWidth ?? 900) - 340)), top: Math.max(12, Math.min(tooltip.y - 220, GRAPH_HEIGHT - 220)) }}><div className="flex items-start justify-between gap-3"><div><h4 className="text-lg font-semibold text-[var(--accent-deep)]">{tooltip.node.name}</h4><p className="mt-1 text-sm text-[var(--text-secondary)]">{tooltip.node.power || '未归类'}</p></div><span className="rounded-full bg-[rgba(183,59,59,0.1)] px-2.5 py-1 text-xs font-medium text-[var(--accent-strong)]">重要度 {Math.round(tooltip.node.importanceScore)}</span></div><p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{tooltip.node.description}</p><div className="mt-3 grid grid-cols-3 gap-2 text-xs text-[var(--text-muted)]"><div className="rounded-2xl bg-[rgba(244,248,248,0.92)] px-3 py-2">出场 {tooltip.node.appearances}</div><div className="rounded-2xl bg-[rgba(244,248,248,0.92)] px-3 py-2">关系 {tooltip.node.linkCount}</div><div className="rounded-2xl bg-[rgba(244,248,248,0.92)] px-3 py-2">权重 {Math.round(tooltip.node.weightSum)}</div></div><p className="mt-3 text-xs text-[var(--text-muted)]">点击可查看该人物在当前范围内的关系列表。</p></div>}
    </div>
  );
}
