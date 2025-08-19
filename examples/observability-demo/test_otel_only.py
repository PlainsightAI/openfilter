#!/usr/bin/env python3
"""
Test script for OTEL-only functionality.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_otel_config():
    """Test OTEL configuration reading."""
    from openfilter.observability.config import read_otel_config
    
    # Test environment variable config
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://test.example.com:4317"
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = "authorization=Bearer test"
    
    config = read_otel_config()
    
    assert config is not None, "OTEL config should not be None"
    assert config["endpoint"] == "https://test.example.com:4317", f"Expected endpoint, got {config['endpoint']}"
    assert config["headers"] == "authorization=Bearer test", f"Expected headers, got {config['headers']}"
    assert config["protocol"] == "grpc", f"Expected grpc protocol, got {config['protocol']}"
    assert config["enabled"] == True, f"Expected enabled=True, got {config['enabled']}"
    
    print("✅ OTEL config test passed")

def test_metric_spec_validation():
    """Test MetricSpec validation with new fields."""
    from openfilter.observability import MetricSpec
    
    # Test valid MetricSpec
    spec = MetricSpec(
        name="test_metric",
        instrument="counter",
        value_fn=lambda d: 1,
        export_mode="aggregated",
        target="otel"
    )
    
    assert spec.export_mode == "aggregated"
    assert spec.target == "otel"
    
    # Test invalid export_mode
    try:
        MetricSpec(
            name="test_metric",
            instrument="counter", 
            value_fn=lambda d: 1,
            export_mode="invalid"
        )
        assert False, "Should have raised ValueError for invalid export_mode"
    except ValueError:
        pass
    
    # Test invalid target
    try:
        MetricSpec(
            name="test_metric",
            instrument="counter",
            value_fn=lambda d: 1,
            target="invalid"
        )
        assert False, "Should have raised ValueError for invalid target"
    except ValueError:
        pass
    
    print("✅ MetricSpec validation test passed")

def test_custom_processor_import():
    """Test importing the updated custom processor."""
    from custom_processor import CustomProcessor, CustomProcessorConfig
    
    config = CustomProcessorConfig(
        sources=["test"],
        outputs=["test"],
        export_mode="both",
        target="otel"
    )
    
    # This should not raise an exception
    processor = CustomProcessor(config)
    
    # Check that metric specs are configured correctly
    assert len(processor.metric_specs) > 0, "Should have metric specs"
    for spec in processor.metric_specs:
        assert spec.export_mode == "both", f"Expected export_mode='both', got {spec.export_mode}"
        assert spec.target == "otel", f"Expected target='otel', got {spec.target}"
    
    print("✅ Custom processor test passed")

def main():
    """Run all tests."""
    print("🧪 Testing OTEL-only functionality...")
    
    try:
        test_otel_config()
        test_metric_spec_validation()
        test_custom_processor_import()
        
        print("\n✅ All tests passed!")
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
