"""
Example configurations for the Text Generator Filter.

This file contains various configuration examples for different use cases
of the TextGeneratorFilter and SingleTextGeneratorFilter.
"""

from text_generator_filter import TextGeneratorConfig, SingleTextGeneratorConfig

# Example 1: Basic multi-text configuration
BASIC_MULTI_TEXT_CONFIG = TextGeneratorConfig(
    output_main=True,
    output_crops=True,
    crop_topic_prefix='text_crop_',
    frame_width=800,
    frame_height=600,
    texts=[
        {"text": "Hello World", "x": 100, "y": 150, "font_scale": 2.0, "color": (255, 255, 255)},
        {"text": "OpenFilter", "x": 300, "y": 250, "font_scale": 1.5, "color": (255, 255, 0)},
        {"text": "OCR Test", "x": 500, "y": 350, "font_scale": 1.0, "color": (0, 255, 255)}
    ]
)

# Example 2: Crops-only configuration (no main frame)
CROPS_ONLY_CONFIG = TextGeneratorConfig(
    output_main=False,
    output_crops=True,
    crop_topic_prefix='crop_',
    frame_width=800,
    frame_height=600,
    texts=[
        {"text": "First Text", "x": 100, "y": 150, "font_scale": 2.0, "color": (255, 255, 255)},
        {"text": "Second Text", "x": 300, "y": 250, "font_scale": 1.5, "color": (255, 255, 0)},
        {"text": "Third Text", "x": 500, "y": 350, "font_scale": 1.0, "color": (0, 255, 255)}
    ]
)

# Example 3: License plate style configuration
LICENSE_PLATE_CONFIG = TextGeneratorConfig(
    output_main=True,
    output_crops=True,
    crop_topic_prefix='plate_',
    frame_width=640,
    frame_height=480,
    texts=[
        {"text": "ABC123", "x": 200, "y": 200, "font_scale": 3.0, "color": (255, 255, 255)},
        {"text": "XYZ789", "x": 200, "y": 300, "font_scale": 3.0, "color": (255, 255, 255)}
    ]
)

# Example 4: Document text configuration
DOCUMENT_TEXT_CONFIG = TextGeneratorConfig(
    output_main=True,
    output_crops=True,
    crop_topic_prefix='doc_text_',
    frame_width=1200,
    frame_height=800,
    texts=[
        {"text": "Invoice", "x": 50, "y": 100, "font_scale": 2.5, "color": (255, 255, 255)},
        {"text": "Date: 2024-01-15", "x": 50, "y": 200, "font_scale": 1.5, "color": (255, 255, 255)},
        {"text": "Amount: $1,234.56", "x": 50, "y": 300, "font_scale": 1.5, "color": (255, 255, 255)},
        {"text": "Customer: John Doe", "x": 50, "y": 400, "font_scale": 1.5, "color": (255, 255, 255)}
    ]
)

# Example 5: Single text configuration
SINGLE_TEXT_CONFIG = SingleTextGeneratorConfig(
    text='Sample Text',
    x=100,
    y=150,
    font_scale=2.0,
    color=(255, 255, 255),
    frame_width=400,
    frame_height=300,
    crop_topic='single_text_crop'
)

# Example 6: Large text configuration
LARGE_TEXT_CONFIG = SingleTextGeneratorConfig(
    text='LARGE TEXT',
    x=50,
    y=200,
    font_scale=4.0,
    color=(255, 255, 255),
    frame_width=600,
    frame_height=400,
    crop_topic='large_text_crop'
)

# Example 7: Colored text configuration
COLORED_TEXT_CONFIG = TextGeneratorConfig(
    output_main=True,
    output_crops=True,
    crop_topic_prefix='colored_',
    frame_width=800,
    frame_height=600,
    texts=[
        {"text": "Red Text", "x": 100, "y": 150, "font_scale": 2.0, "color": (0, 0, 255)},  # Red in BGR
        {"text": "Green Text", "x": 300, "y": 250, "font_scale": 2.0, "color": (0, 255, 0)},  # Green in BGR
        {"text": "Blue Text", "x": 500, "y": 350, "font_scale": 2.0, "color": (255, 0, 0)},  # Blue in BGR
        {"text": "Yellow Text", "x": 100, "y": 450, "font_scale": 2.0, "color": (0, 255, 255)},  # Yellow in BGR
        {"text": "Magenta Text", "x": 300, "y": 450, "font_scale": 2.0, "color": (255, 0, 255)},  # Magenta in BGR
        {"text": "Cyan Text", "x": 500, "y": 450, "font_scale": 2.0, "color": (255, 255, 0)}  # Cyan in BGR
    ]
)

# Example 8: Small text configuration (for testing OCR with small text)
SMALL_TEXT_CONFIG = TextGeneratorConfig(
    output_main=True,
    output_crops=True,
    crop_topic_prefix='small_',
    frame_width=800,
    frame_height=600,
    texts=[
        {"text": "Small Text 1", "x": 100, "y": 150, "font_scale": 0.5, "color": (255, 255, 255)},
        {"text": "Small Text 2", "x": 300, "y": 250, "font_scale": 0.7, "color": (255, 255, 255)},
        {"text": "Small Text 3", "x": 500, "y": 350, "font_scale": 0.3, "color": (255, 255, 255)}
    ]
)

# Example 9: Mixed font sizes configuration
MIXED_FONT_CONFIG = TextGeneratorConfig(
    output_main=True,
    output_crops=True,
    crop_topic_prefix='mixed_',
    frame_width=1000,
    frame_height=700,
    texts=[
        {"text": "Large Title", "x": 50, "y": 100, "font_scale": 3.0, "color": (255, 255, 255)},
        {"text": "Medium Subtitle", "x": 50, "y": 200, "font_scale": 2.0, "color": (255, 255, 255)},
        {"text": "Normal Text", "x": 50, "y": 300, "font_scale": 1.0, "color": (255, 255, 255)},
        {"text": "Small Caption", "x": 50, "y": 400, "font_scale": 0.7, "color": (255, 255, 255)},
        {"text": "Tiny Text", "x": 50, "y": 500, "font_scale": 0.5, "color": (255, 255, 255)}
    ]
)

# Example 10: Dense text configuration (many texts close together)
DENSE_TEXT_CONFIG = TextGeneratorConfig(
    output_main=True,
    output_crops=True,
    crop_topic_prefix='dense_',
    frame_width=800,
    frame_height=600,
    texts=[
        {"text": "Text1", "x": 50, "y": 100, "font_scale": 1.0, "color": (255, 255, 255)},
        {"text": "Text2", "x": 150, "y": 100, "font_scale": 1.0, "color": (255, 255, 255)},
        {"text": "Text3", "x": 250, "y": 100, "font_scale": 1.0, "color": (255, 255, 255)},
        {"text": "Text4", "x": 350, "y": 100, "font_scale": 1.0, "color": (255, 255, 255)},
        {"text": "Text5", "x": 450, "y": 100, "font_scale": 1.0, "color": (255, 255, 255)},
        {"text": "Text6", "x": 50, "y": 200, "font_scale": 1.0, "color": (255, 255, 255)},
        {"text": "Text7", "x": 150, "y": 200, "font_scale": 1.0, "color": (255, 255, 255)},
        {"text": "Text8", "x": 250, "y": 200, "font_scale": 1.0, "color": (255, 255, 255)},
        {"text": "Text9", "x": 350, "y": 200, "font_scale": 1.0, "color": (255, 255, 255)},
        {"text": "Text10", "x": 450, "y": 200, "font_scale": 1.0, "color": (255, 255, 255)}
    ]
)


def get_config_by_name(config_name):
    """Get a configuration by name."""
    configs = {
        'basic': BASIC_MULTI_TEXT_CONFIG,
        'crops_only': CROPS_ONLY_CONFIG,
        'license_plate': LICENSE_PLATE_CONFIG,
        'document': DOCUMENT_TEXT_CONFIG,
        'single': SINGLE_TEXT_CONFIG,
        'large': LARGE_TEXT_CONFIG,
        'colored': COLORED_TEXT_CONFIG,
        'small': SMALL_TEXT_CONFIG,
        'mixed': MIXED_FONT_CONFIG,
        'dense': DENSE_TEXT_CONFIG
    }
    
    return configs.get(config_name, BASIC_MULTI_TEXT_CONFIG)


def list_available_configs():
    """List all available configurations."""
    configs = {
        'basic': 'Basic multi-text configuration',
        'crops_only': 'Crops-only configuration (no main frame)',
        'license_plate': 'License plate style configuration',
        'document': 'Document text configuration',
        'single': 'Single text configuration',
        'large': 'Large text configuration',
        'colored': 'Colored text configuration',
        'small': 'Small text configuration',
        'mixed': 'Mixed font sizes configuration',
        'dense': 'Dense text configuration'
    }
    
    print("Available configurations:")
    for name, description in configs.items():
        print(f"  {name}: {description}")


if __name__ == '__main__':
    list_available_configs() 