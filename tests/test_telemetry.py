"""
Tests for the telemetry system.
"""

import unittest
from unittest.mock import Mock, patch
from openfilter.observability import MetricSpec, TelemetryRegistry, read_allowlist


class TestMetricSpec(unittest.TestCase):
    """Test MetricSpec functionality."""
    
    def test_metric_spec_creation(self):
        """Test creating a MetricSpec."""
        spec = MetricSpec(
            name="test_metric",
            instrument="counter",
            value_fn=lambda d: 1
        )
        
        self.assertEqual(spec.name, "test_metric")
        self.assertEqual(spec.instrument, "counter")
        self.assertIsNone(spec._otel_inst)
    
    def test_metric_spec_with_boundaries(self):
        """Test creating a histogram MetricSpec with boundaries."""
        spec = MetricSpec(
            name="test_histogram",
            instrument="histogram",
            value_fn=lambda d: len(d.get("items", [])),
            boundaries=[0, 1, 2, 5]
        )
        
        self.assertEqual(spec.name, "test_histogram")
        self.assertEqual(spec.instrument, "histogram")
        self.assertEqual(spec.boundaries, [0, 1, 2, 5])


class TestTelemetryRegistry(unittest.TestCase):
    """Test TelemetryRegistry functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_meter = Mock()
        self.mock_counter = Mock()
        self.mock_histogram = Mock()
        
        self.mock_meter.create_counter.return_value = self.mock_counter
        self.mock_meter.create_histogram.return_value = self.mock_histogram
        
        self.specs = [
            MetricSpec(
                name="test_counter",
                instrument="counter",
                value_fn=lambda d: 1
            ),
            MetricSpec(
                name="test_histogram",
                instrument="histogram",
                value_fn=lambda d: len(d.get("items", [])),
                boundaries=[0, 1, 2, 5]
            )
        ]
    
    def test_registry_creation(self):
        """Test creating a TelemetryRegistry."""
        registry = TelemetryRegistry(self.mock_meter, self.specs)
        
        # Verify instruments were created
        self.mock_meter.create_counter.assert_called_once_with("test_counter")
        self.mock_meter.create_histogram.assert_called_once_with(
            "test_histogram", explicit_bucket_boundaries_advisory=[0, 1, 2, 5]
        )
        
        # Verify instruments were assigned
        self.assertEqual(self.specs[0]._otel_inst, self.mock_counter)
        self.assertEqual(self.specs[1]._otel_inst, self.mock_histogram)
    
    def test_registry_recording(self):
        """Test recording metrics."""
        registry = TelemetryRegistry(self.mock_meter, self.specs)
        
        # Record metrics
        frame_data = {"items": ["a", "b", "c"]}
        registry.record(frame_data)
        
        # Verify counter was called
        self.mock_counter.add.assert_called_once_with(1)
        
        # Verify histogram was called
        self.mock_histogram.record.assert_called_once_with(3)
    
    def test_registry_recording_none_value(self):
        """Test recording when value_fn returns None."""
        specs = [
            MetricSpec(
                name="test_none",
                instrument="counter",
                value_fn=lambda d: None
            )
        ]
        
        registry = TelemetryRegistry(self.mock_meter, specs)
        frame_data = {"test": "data"}
        registry.record(frame_data)
        
        # Should not call the instrument
        specs[0]._otel_inst.add.assert_not_called()


class TestConfig(unittest.TestCase):
    """Test configuration functionality."""
    
    @patch.dict('os.environ', {}, clear=True)
    def test_read_allowlist_empty(self):
        """Test reading allowlist when no config is set."""
        allowlist = read_allowlist()
        self.assertEqual(allowlist, set())
    
    @patch.dict('os.environ', {'OF_SAFE_METRICS': 'metric1,metric2,metric3'})
    def test_read_allowlist_env(self):
        """Test reading allowlist from environment variable."""
        allowlist = read_allowlist()
        self.assertEqual(allowlist, {'metric1', 'metric2', 'metric3'})
    
    @patch.dict('os.environ', {'OF_SAFE_METRICS': 'metric1, metric2 , metric3'})
    def test_read_allowlist_env_with_spaces(self):
        """Test reading allowlist with spaces."""
        allowlist = read_allowlist()
        self.assertEqual(allowlist, {'metric1', 'metric2', 'metric3'})


if __name__ == '__main__':
    unittest.main() 