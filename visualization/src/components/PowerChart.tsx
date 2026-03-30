import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import type { BookConfig } from '../types/pipelineArtifacts';
import type { PowerDistributionUnified } from '../types/unified';

interface PowerChartProps {
  bookConfig: BookConfig | null;
  data: PowerDistributionUnified[];
  onPowerClick?: (power: PowerDistributionUnified) => void;
}

export function PowerChart({ bookConfig, data, onPowerClick }: PowerChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartTitle = `${bookConfig?.title ?? '文本'}所属势力分布`;

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || data.length === 0) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = 340;
    const margin = { top: 36, right: 24, bottom: 84, left: 56 };

    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3.select(svgRef.current).attr('width', width).attr('height', height);
    const topData = data.slice(0, 10);

    const xScale = d3
      .scaleBand()
      .domain(topData.map((d) => d.power))
      .range([margin.left, width - margin.right])
      .padding(0.26);

    const yScale = d3
      .scaleLinear()
      .domain([0, d3.max(topData, (d) => d.count) || 0])
      .nice()
      .range([height - margin.bottom, margin.top]);

    const colorScale = d3
      .scaleOrdinal<string, string>()
      .domain(topData.map((d) => d.power))
      .range(['#7a3c17', '#bc7a32', '#d7a55b', '#a44c2d', '#5f3d26', '#87604a', '#ba9154', '#6e4b2f', '#cfb37c', '#8f5c30']);

    svg
      .append('g')
      .attr('transform', `translate(0, ${height - margin.bottom})`)
      .call(d3.axisBottom(xScale))
      .selectAll('text')
      .attr('transform', 'rotate(-36)')
      .style('text-anchor', 'end')
      .style('font-size', '11px')
      .style('fill', '#413325');

    svg
      .append('g')
      .attr('transform', `translate(${margin.left}, 0)`)
      .call(d3.axisLeft(yScale).ticks(5))
      .selectAll('text')
      .style('fill', '#413325');

    svg
      .selectAll('.bar')
      .data(topData)
      .enter()
      .append('rect')
      .attr('class', 'bar')
      .attr('x', (d) => xScale(d.power) || 0)
      .attr('y', (d) => yScale(d.count))
      .attr('width', xScale.bandwidth())
      .attr('height', (d) => height - margin.bottom - yScale(d.count))
      .attr('fill', (d) => colorScale(d.power))
      .attr('rx', 14)
      .style('cursor', 'pointer')
      .on('click', (_, d) => onPowerClick?.(d))
      .on('mouseover', function () {
        d3.select(this).attr('opacity', 0.85);
      })
      .on('mouseout', function () {
        d3.select(this).attr('opacity', 1);
      });

    svg
      .selectAll('.label')
      .data(topData)
      .enter()
      .append('text')
      .attr('class', 'label')
      .attr('x', (d) => (xScale(d.power) || 0) + xScale.bandwidth() / 2)
      .attr('y', (d) => yScale(d.count) - 10)
      .attr('text-anchor', 'middle')
      .style('font-size', '11px')
      .style('font-weight', '700')
      .style('fill', '#413325')
      .text((d) => d.count);

    svg
      .append('text')
      .attr('x', width / 2)
      .attr('y', 18)
      .attr('text-anchor', 'middle')
      .style('font-size', '15px')
      .style('font-weight', '700')
      .style('fill', '#2b170b')
      .text(chartTitle);
  }, [chartTitle, data, onPowerClick]);

  return (
    <div ref={containerRef} className="view-shell">
      <div className="view-header">
        <div>
          <h3 className="view-title">所属势力分布</h3>
          <p className="view-copy">用当前范围内的角色提及次数和所属势力归属，快速看出这一段文本由哪些势力主导。</p>
        </div>
        <div className="float-stat">前 {Math.min(data.length, 10)} 个所属势力</div>
      </div>
      {data.length === 0 ? (
        <div className="empty-state">当前范围暂时没有所属势力分布数据。</div>
      ) : (
        <svg ref={svgRef} className="w-full" />
      )}
    </div>
  );
}
