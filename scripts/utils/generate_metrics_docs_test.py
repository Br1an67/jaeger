# Copyright (c) 2025 The Jaeger Authors.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for generate_metrics_docs.py"""

import unittest
from generate_metrics_docs import (
    parse_prometheus_metrics,
    get_category,
    format_labels_for_docs,
    generate_markdown_documentation,
    MetricFamily,
)


class TestParsePrometheusMetrics(unittest.TestCase):
    """Tests for parse_prometheus_metrics function."""

    def test_parse_simple_counter(self):
        """Test parsing a simple counter metric."""
        content = """# HELP jaeger_collector_spans_received_total Total spans received
# TYPE jaeger_collector_spans_received_total counter
jaeger_collector_spans_received_total{debug="false",format="jaeger"} 123
"""
        metrics = parse_prometheus_metrics(content)

        self.assertIn('jaeger_collector_spans_received_total', metrics)
        metric = metrics['jaeger_collector_spans_received_total']
        self.assertEqual(metric.metric_type, 'counter')
        self.assertEqual(metric.help_text, 'Total spans received')
        self.assertEqual(len(metric.samples), 1)
        self.assertEqual(metric.samples[0]['labels']['debug'], 'false')
        self.assertEqual(metric.samples[0]['labels']['format'], 'jaeger')

    def test_parse_gauge(self):
        """Test parsing a gauge metric."""
        content = """# TYPE jaeger_collector_queue_length gauge
jaeger_collector_queue_length{host="localhost"} 42
"""
        metrics = parse_prometheus_metrics(content)

        self.assertIn('jaeger_collector_queue_length', metrics)
        self.assertEqual(metrics['jaeger_collector_queue_length'].metric_type, 'gauge')

    def test_parse_histogram(self):
        """Test parsing histogram metrics."""
        content = """# TYPE http_request_duration histogram
http_request_duration_bucket{le="0.1"} 10
http_request_duration_bucket{le="0.5"} 25
http_request_duration_bucket{le="+Inf"} 50
http_request_duration_sum 12.5
http_request_duration_count 50
"""
        metrics = parse_prometheus_metrics(content)

        self.assertIn('http_request_duration_bucket', metrics)
        self.assertIn('http_request_duration_sum', metrics)
        self.assertIn('http_request_duration_count', metrics)

    def test_parse_no_labels(self):
        """Test parsing metric without labels."""
        content = "process_uptime 12345.6\n"
        metrics = parse_prometheus_metrics(content)

        self.assertIn('process_uptime', metrics)
        self.assertEqual(len(metrics['process_uptime'].samples), 1)
        self.assertEqual(metrics['process_uptime'].samples[0]['labels'], {})


class TestGetCategory(unittest.TestCase):
    """Tests for get_category function."""

    def test_jaeger_prefix(self):
        """Test categorization of Jaeger metrics."""
        self.assertEqual(get_category('jaeger_collector_spans'), 'Jaeger Core Metrics')

    def test_otelcol_prefix(self):
        """Test categorization of OTel Collector metrics."""
        self.assertEqual(get_category('otelcol_processor_batch'), 'OpenTelemetry Collector Metrics')

    def test_receiver_prefix(self):
        """Test categorization of receiver metrics."""
        self.assertEqual(get_category('receiver_accepted_spans'), 'Receiver Metrics')

    def test_unknown_prefix(self):
        """Test categorization of unknown metrics."""
        self.assertEqual(get_category('unknown_metric'), 'Other Metrics')


class TestFormatLabelsForDocs(unittest.TestCase):
    """Tests for format_labels_for_docs function."""

    def test_empty_labels(self):
        """Test formatting empty labels."""
        result = format_labels_for_docs({})
        self.assertEqual(result, '')

    def test_simple_labels(self):
        """Test formatting simple labels."""
        result = format_labels_for_docs({'service': 'test', 'operation': 'get'})
        self.assertIn('`service`', result)
        self.assertIn('`operation`', result)

    def test_exclude_instance_labels(self):
        """Test that instance labels are excluded by default."""
        result = format_labels_for_docs({
            'service': 'test',
            'service_instance_id': 'abc123'
        }, exclude_instance=True)
        self.assertIn('`service`', result)
        self.assertIn('_instance:', result)
        self.assertIn('`service_instance_id`', result)

    def test_include_instance_labels(self):
        """Test including instance labels."""
        result = format_labels_for_docs({
            'service': 'test',
            'service_instance_id': 'abc123'
        }, exclude_instance=False)
        self.assertIn('`service`', result)
        self.assertIn('`service_instance_id`', result)
        self.assertNotIn('_instance:', result)


class TestGenerateMarkdownDocumentation(unittest.TestCase):
    """Tests for generate_markdown_documentation function."""

    def test_basic_documentation(self):
        """Test generating basic documentation."""
        metrics = {
            'jaeger_collector_spans': MetricFamily('jaeger_collector_spans', 'counter', 'Number of spans')
        }
        metrics['jaeger_collector_spans'].add_sample({'service': 'test'}, '100')

        result = generate_markdown_documentation(metrics, title='Test Metrics')

        self.assertIn('# Test Metrics', result)
        self.assertIn('jaeger_collector_spans', result)
        self.assertIn('## Jaeger Core Metrics', result)

    def test_documentation_with_description(self):
        """Test generating documentation with description."""
        metrics = {
            'test_metric': MetricFamily('test_metric', 'gauge')
        }

        result = generate_markdown_documentation(
            metrics,
            title='Test',
            description='This is a test description.'
        )

        self.assertIn('This is a test description.', result)

    def test_metrics_categorization(self):
        """Test that metrics are properly categorized."""
        metrics = {
            'jaeger_collector_spans': MetricFamily('jaeger_collector_spans', 'counter'),
            'receiver_accepted_spans': MetricFamily('receiver_accepted_spans', 'counter'),
            'unknown_metric': MetricFamily('unknown_metric', 'gauge'),
        }

        result = generate_markdown_documentation(metrics)

        self.assertIn('## Jaeger Core Metrics', result)
        self.assertIn('## Receiver Metrics', result)
        self.assertIn('## Other Metrics', result)


if __name__ == '__main__':
    unittest.main()
