#!/usr/bin/env python3

# Copyright (c) 2025 The Jaeger Authors.
# SPDX-License-Identifier: Apache-2.0

"""
Script to generate documentation-friendly markdown from Prometheus metrics.

This script can be used to generate metrics documentation for the Jaeger
documentation website. It parses Prometheus metrics from files or URLs and
outputs structured markdown documentation.

Usage:
    python3 generate_metrics_docs.py --input metrics.txt --output metrics.md
    python3 generate_metrics_docs.py --url http://localhost:8888/metrics --output metrics.md
"""

import argparse
import re
import sys
from collections import defaultdict
from typing import Dict, List, Optional, TextIO

# Labels that are typically instance-specific and should be noted but not emphasized
INSTANCE_LABELS = {
    'service_instance_id',
    'service_name',
    'service_version',
    'otel_scope_version',
    'otel_scope_schema_url',
}

# Known Jaeger metric prefixes and their descriptions
METRIC_CATEGORIES = {
    'jaeger_': 'Jaeger Core Metrics',
    'otelcol_': 'OpenTelemetry Collector Metrics',
    'receiver_': 'Receiver Metrics',
    'exporter_': 'Exporter Metrics',
    'processor_': 'Processor Metrics',
    'batch_': 'Batch Processor Metrics',
    'rpc_': 'RPC Metrics',
    'http_': 'HTTP Metrics',
    'process_': 'Process Metrics',
    'go_': 'Go Runtime Metrics',
}

# Description templates for known metrics
METRIC_DESCRIPTIONS = {
    'jaeger_collector_spans_received_total': 'Total number of spans received by the collector',
    'jaeger_collector_spans_saved_by_svc_total': 'Total number of spans saved by the collector, grouped by service',
    'jaeger_collector_spans_dropped_total': 'Total number of spans dropped by the collector',
    'jaeger_collector_spans_rejected_total': 'Total number of spans rejected by the collector',
    'jaeger_collector_traces_received_total': 'Total number of traces received by the collector',
    'jaeger_collector_traces_saved_by_svc_total': 'Total number of traces saved by the collector, grouped by service',
    'jaeger_collector_traces_rejected_total': 'Total number of traces rejected by the collector',
    'jaeger_collector_queue_length': 'Current number of items in the collector queue',
    'jaeger_collector_queue_capacity': 'Maximum capacity of the collector queue',
    'jaeger_collector_in_queue_latency': 'Latency of items in the collector queue',
    'jaeger_collector_save_latency': 'Latency of saving items to storage',
    'jaeger_collector_batch_size': 'Number of spans in the current batch',
    'jaeger_collector_spans_bytes': 'Size of spans in bytes',
    'jaeger_collector_http_server_requests_total': 'Total number of HTTP server requests',
    'jaeger_collector_http_server_errors_total': 'Total number of HTTP server errors',
    'jaeger_collector_http_request_duration': 'Duration of HTTP requests',
    'jaeger_query_requests_total': 'Total number of query requests',
    'jaeger_query_responses': 'Number of query responses',
    'jaeger_query_latency': 'Latency of query operations',
    'jaeger_build_info': 'Build information for the Jaeger binary',
    'receiver_accepted_spans': 'Number of spans accepted by the receiver',
    'receiver_refused_spans': 'Number of spans refused by the receiver',
    'exporter_sent_spans': 'Number of spans sent by the exporter',
    'exporter_send_failed_spans': 'Number of spans that failed to send',
    'processor_batch_batch_send_size': 'Number of units in a batch sent',
    'processor_batch_batch_send_size_bytes': 'Size of batch in bytes',
    'processor_batch_metadata_cardinality': 'Number of distinct metadata value combinations',
    'processor_batch_timeout_trigger_send': 'Number of times batch was sent due to timeout',
    'rpc_server_duration': 'Duration of RPC server requests',
    'rpc_server_request_size': 'Size of RPC server requests',
    'rpc_server_response_size': 'Size of RPC server responses',
    'rpc_server_requests_per_rpc': 'Number of requests per RPC',
    'rpc_server_responses_per_rpc': 'Number of responses per RPC',
    'process_uptime': 'Process uptime in seconds',
    'process_cpu_seconds': 'Total CPU seconds',
    'process_memory_rss': 'Resident memory size in bytes',
    'process_runtime_heap_alloc_bytes': 'Bytes of allocated heap objects',
    'process_runtime_total_alloc_bytes': 'Cumulative bytes allocated for heap objects',
    'process_runtime_total_sys_memory_bytes': 'Total bytes of memory obtained from the OS',
}


class MetricFamily:
    """Represents a Prometheus metric family with its samples."""

    def __init__(self, name: str, metric_type: str = 'unknown', help_text: str = ''):
        self.name = name
        self.metric_type = metric_type
        self.help_text = help_text
        self.samples: List[Dict] = []

    def add_sample(self, labels: Dict[str, str], value: str):
        self.samples.append({'labels': labels, 'value': value})


def parse_prometheus_metrics(content: str) -> Dict[str, MetricFamily]:
    """
    Parse Prometheus text format metrics into metric families.

    Args:
        content: Raw Prometheus metrics text

    Returns:
        Dictionary mapping metric names to MetricFamily objects
    """
    metrics: Dict[str, MetricFamily] = {}
    current_metric: Optional[MetricFamily] = None

    for line in content.split('\n'):
        line = line.strip()

        if not line or line.startswith('#'):
            if line.startswith('# HELP '):
                parts = line[7:].split(' ', 1)
                if len(parts) >= 1:
                    name = parts[0]
                    help_text = parts[1] if len(parts) > 1 else ''
                    if name not in metrics:
                        metrics[name] = MetricFamily(name)
                    metrics[name].help_text = help_text
                    current_metric = metrics[name]
            elif line.startswith('# TYPE '):
                parts = line[7:].split(' ', 1)
                if len(parts) >= 2:
                    name = parts[0]
                    metric_type = parts[1]
                    if name not in metrics:
                        metrics[name] = MetricFamily(name)
                    metrics[name].metric_type = metric_type
                    current_metric = metrics[name]
            continue

        # Parse metric line: name{labels} value or name value
        match = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)((?:\{[^}]*\})?)?\s+(.+)$', line)
        if match:
            name = match.group(1)
            labels_str = match.group(2) or ''
            value = match.group(3)

            # Parse labels
            labels = {}
            if labels_str:
                # Simple label parsing: key="value" or key=value
                label_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)=(?:"([^"]*)"|([^,}]*))'
                for label_match in re.finditer(label_pattern, labels_str):
                    key = label_match.group(1)
                    val = label_match.group(2) or label_match.group(3)
                    labels[key] = val

            if name not in metrics:
                metrics[name] = MetricFamily(name)
            metrics[name].add_sample(labels, value)

    return metrics


def get_category(metric_name: str) -> str:
    """Determine the category for a metric based on its prefix."""
    for prefix, category in METRIC_CATEGORIES.items():
        if metric_name.startswith(prefix):
            return category
    return 'Other Metrics'


def format_labels_for_docs(labels: Dict[str, str], exclude_instance: bool = True) -> str:
    """Format labels for documentation display."""
    if not labels:
        return ''

    filtered_labels = {}
    instance_labels = {}

    for key, value in sorted(labels.items()):
        if exclude_instance and key in INSTANCE_LABELS:
            instance_labels[key] = value
        else:
            filtered_labels[key] = value

    parts = []
    if filtered_labels:
        parts.append(', '.join(f'`{k}`' for k in filtered_labels.keys()))
    if instance_labels:
        parts.append(f'_instance: {", ".join(f"`{k}`" for k in instance_labels.keys())}_')

    return ' | '.join(parts) if parts else ''


def generate_markdown_documentation(
    metrics: Dict[str, MetricFamily],
    title: str = 'Jaeger Metrics Reference',
    description: str = None,
    include_instance_labels: bool = False,
) -> str:
    """
    Generate markdown documentation from parsed metrics.

    Args:
        metrics: Dictionary of metric families
        title: Document title
        description: Optional document description
        include_instance_labels: Whether to include instance-specific labels

    Returns:
        Markdown formatted string
    """
    lines = []

    # Header
    lines.append(f'# {title}')
    lines.append('')
    if description:
        lines.append(description)
        lines.append('')

    lines.append('This document lists all metrics exported by Jaeger components.')
    lines.append('Metrics are exposed in Prometheus format and can be scraped from the')
    lines.append('metrics endpoint (default: `http://localhost:8888/metrics`).')
    lines.append('')
    lines.append('## Overview')
    lines.append('')

    # Group metrics by category
    categories: Dict[str, List[str]] = defaultdict(list)
    for name in metrics:
        categories[get_category(name)].append(name)

    # Table of contents
    lines.append('### Categories')
    lines.append('')
    for category in sorted(categories.keys()):
        anchor = category.lower().replace(' ', '-').replace('/', '-')
        lines.append(f'- [{category}](#{anchor}) ({len(categories[category])} metrics)')
    lines.append('')

    # Metrics by category
    for category in sorted(categories.keys()):
        anchor = category.lower().replace(' ', '-').replace('/', '-')
        lines.append(f'## {category}')
        lines.append('')

        category_metrics = sorted(categories[category])

        # Summary table
        lines.append('| Metric | Type | Labels | Description |')
        lines.append('|--------|------|--------|-------------|')

        for name in category_metrics:
            metric = metrics[name]

            # Get all unique labels from samples
            all_labels = set()
            for sample in metric.samples:
                all_labels.update(sample.keys())

            labels_str = format_labels_for_docs(
                {k: '' for k in all_labels},
                exclude_instance=not include_instance_labels
            )

            # Get description
            desc = METRIC_DESCRIPTIONS.get(name, metric.help_text)
            if len(desc) > 80:
                desc = desc[:77] + '...'

            lines.append(f'| `{name}` | {metric.metric_type} | {labels_str} | {desc} |')

        lines.append('')

    # Detailed metrics section
    lines.append('---')
    lines.append('')
    lines.append('## Detailed Metrics')
    lines.append('')

    for category in sorted(categories.keys()):
        category_metrics = sorted(categories[category])
        if not category_metrics:
            continue

        lines.append(f'### {category}')
        lines.append('')

        for name in category_metrics:
            metric = metrics[name]

            lines.append(f'#### `{name}`')
            lines.append('')

            if metric.help_text:
                lines.append(f'*{metric.help_text}*')
                lines.append('')

            known_desc = METRIC_DESCRIPTIONS.get(name)
            if known_desc and known_desc != metric.help_text:
                lines.append(f'{known_desc}')
                lines.append('')

            lines.append(f'- **Type**: `{metric.metric_type}`')
            lines.append(f'- **Samples**: {len(metric.samples)}')

            # Collect unique labels
            all_labels = set()
            for sample in metric.samples:
                all_labels.update(sample.keys())

            if all_labels:
                lines.append('')
                lines.append('**Labels**:')
                lines.append('')
                for label in sorted(all_labels):
                    is_instance = label in INSTANCE_LABELS
                    marker = ' *(instance-specific)*' if is_instance else ''
                    lines.append(f'- `{label}`{marker}')

            lines.append('')

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Generate documentation markdown from Prometheus metrics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Generate docs from a metrics file
  python3 generate_metrics_docs.py --input metrics.txt --output metrics.md

  # Generate docs from a URL
  python3 generate_metrics_docs.py --url http://localhost:8888/metrics --output metrics.md

  # Include instance-specific labels
  python3 generate_metrics_docs.py --input metrics.txt --include-instance-labels
        '''
    )

    parser.add_argument(
        '--input', '-i',
        help='Input file containing Prometheus metrics (text format)'
    )
    parser.add_argument(
        '--url', '-u',
        help='URL to fetch Prometheus metrics from'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output markdown file (default: stdout)'
    )
    parser.add_argument(
        '--title', '-t',
        default='Jaeger Metrics Reference',
        help='Document title'
    )
    parser.add_argument(
        '--description', '-d',
        help='Document description'
    )
    parser.add_argument(
        '--include-instance-labels',
        action='store_true',
        help='Include instance-specific labels in documentation'
    )

    args = parser.parse_args()

    if not args.input and not args.url:
        parser.error('Either --input or --url must be specified')

    # Read metrics content
    if args.url:
        try:
            import urllib.request
            with urllib.request.urlopen(args.url) as response:
                content = response.read().decode('utf-8')
        except Exception as e:
            print(f'Error fetching metrics from URL: {e}', file=sys.stderr)
            sys.exit(1)
    else:
        with open(args.input, 'r') as f:
            content = f.read()

    # Parse metrics
    metrics = parse_prometheus_metrics(content)

    if not metrics:
        print('No metrics found in input', file=sys.stderr)
        sys.exit(1)

    print(f'Parsed {len(metrics)} metric families', file=sys.stderr)

    # Generate documentation
    markdown = generate_markdown_documentation(
        metrics,
        title=args.title,
        description=args.description,
        include_instance_labels=args.include_instance_labels,
    )

    # Output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(markdown)
        print(f'Documentation written to {args.output}', file=sys.stderr)
    else:
        print(markdown)


if __name__ == '__main__':
    main()
