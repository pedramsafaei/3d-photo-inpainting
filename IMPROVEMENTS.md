# Recent Improvements to 3D Photo Inpainting

This document describes recent bug fixes and enhancements made to improve code quality, usability, and compatibility.

## Bug Fixes

### 1. Removed Deprecated scipy.misc
- **Issue**: `scipy.misc` was removed in scipy 1.3.0
- **Fix**: Removed all unused `scipy.misc` imports (the code already uses `imageio` for image I/O)
- **Impact**: Now compatible with modern scipy versions (>=1.4.0)

### 2. Improved Exception Handling
- **Issue**: Bare `except:` clauses made debugging difficult
- **Fix**: Replaced with specific exception types (e.g., `KeyError`, `ValueError`, `ZeroDivisionError`)
- **Impact**: Better error messages and easier debugging

### 3. Updated Dependencies
- **Issue**: Old fixed versions in requirements.txt
- **Fix**: Updated to modern version ranges while maintaining compatibility
- **Impact**: Works with newer Python environments and packages

## Enhancements

### 1. Professional Logging
All `print()` statements replaced with Python's `logging` module:
```python
# Before
print("Running depth extraction")

# After
logger.info("Running depth extraction")
```

**Benefits**:
- Timestamps on all messages
- Configurable log levels (DEBUG, INFO, WARNING, ERROR)
- Easy to redirect logs to files

### 2. Input Validation
Comprehensive validation of configuration and inputs:
- Checks if config file exists
- Validates required parameters
- Verifies model checkpoints exist
- Confirms source images are present
- Provides helpful error messages with solutions

**Example Error**:
```
Configuration file not found: custom.yml
Please ensure the file exists or create one using the example: config_example.yml
```

### 3. Documentation
- Added comprehensive docstrings to main functions
- Created `config_example.yml` with detailed parameter explanations
- Enhanced command-line help

### 4. Better User Feedback
- Progress bars with descriptions
- Clear status messages at each stage
- Helpful warnings and error messages
- Suggestions for fixing common issues

## Quick Start

### Installation
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install PyTorch (adjust for your CUDA version)
conda install pytorch==1.4.0 torchvision==0.5.0 cudatoolkit==10.1.243 -c pytorch

# Download model checkpoints
chmod +x download.sh
./download.sh
```

### Usage
```bash
# Basic usage with default config
python main.py --config argument.yml

# Get help
python main.py --help

# Use custom configuration
python main.py --config my_config.yml
```

### Configuration
Copy and customize `config_example.yml`:
```bash
cp config_example.yml my_config.yml
# Edit my_config.yml with your preferred settings
python main.py --config my_config.yml
```

## What's New in requirements.txt

Updated dependencies with version ranges for better compatibility:
```
opencv-python>=4.2.0,<5.0.0
vispy>=0.6.4,<0.7.0
moviepy>=1.0.2,<2.0.0
scikit-image>=0.16.2,<0.20.0
imageio>=2.6.0,<3.0.0
numpy>=1.18.0,<1.24.0
scipy>=1.4.0,<2.0.0
PyYAML>=5.3,<7.0
tqdm>=4.40.0
```

## Configuration Tips

From `config_example.yml`:
- Increase `longer_side_len` for higher quality (but slower processing)
- Adjust `sparse_iter` (3-7) for depth refinement quality
- Modify `context_thickness` (100-200) to control inpainting region size
- Set `offscreen_rendering: True` for servers without display
- Use `gpu_ids: -1` to force CPU processing

## Error Messages

The code now provides helpful error messages:

**Missing images**:
```
No .jpg images found in image/
Please add images to process or check the 'img_format' parameter in your config.
```

**Missing models**:
```
Model checkpoint(s) not found:
  - Depth edge model: checkpoints/edge-model.pth
  - MiDaS depth estimation model: MiDaS/model.pt

Please download the models by running: ./download.sh
```

**GPU not available**:
```
GPU 0 requested but CUDA not available. Falling back to CPU.
Note: Processing will be significantly slower on CPU.
```

## Logging Output

Example of the new logging format:
```
============================================================
3D Photo Inpainting - Starting processing
============================================================
2024-01-15 10:30:00 - __main__ - INFO - Configuration validated successfully
2024-01-15 10:30:00 - __main__ - INFO - Running on GPU device 0
2024-01-15 10:30:00 - __main__ - INFO - Found 1 image(s) to process
Processing images: 100%|████████████| 1/1 [02:34<00:00, 154.23s/it]
2024-01-15 10:30:15 - __main__ - INFO - Processing source image: moon
2024-01-15 10:30:15 - __main__ - INFO - Running depth extraction
2024-01-15 10:30:45 - __main__ - INFO - Performing bilateral filtering
2024-01-15 10:30:50 - __main__ - INFO - Starting 3D Photo inpainting pipeline
2024-01-15 10:30:50 - __main__ - INFO - Loading edge model
2024-01-15 10:31:00 - __main__ - INFO - Loading depth model
2024-01-15 10:31:10 - __main__ - INFO - Loading RGB inpainting model
2024-01-15 10:31:20 - __main__ - INFO - Generating 3D mesh with depth inpainting
2024-01-15 10:32:00 - __main__ - INFO - Rendering output videos
2024-01-15 10:32:45 - __main__ - INFO - Successfully processed moon
============================================================
3D Photo Inpainting - Processing complete!
============================================================
```

## Troubleshooting

### ImportError: No module named 'numpy'
Install dependencies: `pip install -r requirements.txt`

### CUDA out of memory
- Reduce `longer_side_len` in config (e.g., from 960 to 640)
- Set `gpu_ids: -1` to use CPU instead

### No images found
- Ensure images are in the `src_folder` (default: `image/`)
- Check that images match `img_format` (default: `.jpg`)
- Verify image file permissions

### Model checkpoints not found
Run the download script: `./download.sh`

## Contributing

When making changes:
- Use logging instead of print statements
- Add docstrings to new functions
- Use specific exception types in try-except blocks
- Update config_example.yml if adding new parameters
- Test with various configurations

## For More Information

See:
- [DOCUMENTATION.md](DOCUMENTATION.md) - Detailed documentation
- [config_example.yml](config_example.yml) - Configuration reference
- [README.md](README.md) - Project overview
