"""
3D Photo Inpainting - Main execution script

This script converts single RGB-D input images into 3D photos using context-aware
layered depth inpainting. It processes images through depth estimation, inpainting,
and video rendering stages.

Usage:
    python main.py --config argument.yml

For more information, see the project documentation.
"""

import numpy as np
import argparse
import glob
import os
from functools import partial
import vispy
from tqdm import tqdm
import yaml
import time
import sys
import logging
from pathlib import Path
from mesh import write_ply, read_ply, output_3d_photo
from utils import get_MiDaS_samples, read_MiDaS_depth
import torch
import cv2
from skimage.transform import resize
import imageio
import copy
from networks import Inpaint_Color_Net, Inpaint_Depth_Net, Inpaint_Edge_Net
from MiDaS.run import run_depth
from MiDaS.monodepth_net import MonoDepthNet
import MiDaS.MiDaS_utils as MiDaS_utils
from bilateral_filtering import sparse_bilateral_filtering

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def validate_config(config_path):
    """
    Validate configuration file and its required parameters.
    
    Args:
        config_path (str): Path to the YAML configuration file
        
    Returns:
        dict: Loaded configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If required parameters are missing or invalid
        yaml.YAMLError: If config file has invalid YAML syntax
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please ensure the file exists or create one using the example: "
            f"config_example.yml"
        )
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(
            f"Error parsing YAML configuration file: {config_path}\n"
            f"Details: {str(e)}"
        )
    
    # Validate required parameters
    required_params = [
        'depth_edge_model_ckpt', 'depth_feat_model_ckpt', 'rgb_feat_model_ckpt',
        'MiDaS_model_ckpt', 'src_folder', 'depth_folder', 'mesh_folder', 'video_folder'
    ]
    
    missing_params = [param for param in required_params if param not in config]
    if missing_params:
        raise ValueError(
            f"Missing required parameters in configuration file: {', '.join(missing_params)}\n"
            f"Please check your configuration file against the example: config_example.yml"
        )
    
    # Validate source folder exists
    if not os.path.exists(config['src_folder']):
        raise FileNotFoundError(
            f"Source image folder not found: {config['src_folder']}\n"
            f"Please create the folder and add your .jpg images to process."
        )
    
    # Check if source folder has images
    img_format = config.get('img_format', '.jpg')
    images = glob.glob(os.path.join(config['src_folder'], f'*{img_format}'))
    if not images:
        raise FileNotFoundError(
            f"No {img_format} images found in {config['src_folder']}\n"
            f"Please add images to process or check the 'img_format' parameter in your config."
        )
    
    # Validate model checkpoints exist
    model_ckpts = [
        ('depth_edge_model_ckpt', 'Depth edge model'),
        ('depth_feat_model_ckpt', 'Depth feature model'),
        ('rgb_feat_model_ckpt', 'RGB feature model'),
        ('MiDaS_model_ckpt', 'MiDaS depth estimation model')
    ]
    
    missing_models = []
    for param, name in model_ckpts:
        if not os.path.exists(config[param]):
            missing_models.append(f"{name}: {config[param]}")
    
    if missing_models:
        raise FileNotFoundError(
            f"Model checkpoint(s) not found:\n" + "\n".join(f"  - {m}" for m in missing_models) +
            f"\n\nPlease download the models by running: ./download.sh"
        )
    
    logger.info(f"Configuration validated successfully: {config_path}")
    return config


def setup_device(config):
    """
    Setup computation device (GPU or CPU).
    
    Args:
        config (dict): Configuration dictionary
        
    Returns:
        str or int: Device identifier for PyTorch
    """
    if isinstance(config["gpu_ids"], int) and (config["gpu_ids"] >= 0):
        device = config["gpu_ids"]
        if torch.cuda.is_available():
            logger.info(f"Running on GPU device {device}")
        else:
            logger.warning(
                f"GPU {device} requested but CUDA not available. Falling back to CPU.\n"
                f"Note: Processing will be significantly slower on CPU."
            )
            device = "cpu"
    else:
        device = "cpu"
        logger.info("Running on CPU device")
    
    return device


def main():
    """
    Main execution function for 3D photo inpainting.
    
    Processes input images through the following stages:
    1. Load and validate configuration
    2. Run depth estimation using MiDaS
    3. Perform bilateral filtering for depth refinement
    4. Load neural network models for inpainting
    5. Generate 3D mesh with depth inpainting
    6. Render videos with various camera motions
    
    The function processes all images in the source folder specified in the config.
    """
    parser = argparse.ArgumentParser(
        description='3D Photo Inpainting - Convert 2D images to 3D photos',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --config argument.yml
  python main.py --config custom_config.yml

For more information, visit: https://github.com/vt-vl-lab/3d-photo-inpainting
        """
    )
    parser.add_argument(
        '--config',
        type=str,
        default='argument.yml',
        help='Path to YAML configuration file (default: argument.yml)'
    )
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("3D Photo Inpainting - Starting processing")
    logger.info("=" * 60)
    
    # Validate configuration
    try:
        config = validate_config(args.config)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as e:
        logger.error(f"Configuration error: {str(e)}")
        sys.exit(1)
    
    # Setup rendering backend
    if config.get('offscreen_rendering', False):
        vispy.use(app='egl')
        logger.info("Using offscreen rendering (EGL)")
    
    # Create output directories
    try:
        os.makedirs(config['mesh_folder'], exist_ok=True)
        os.makedirs(config['video_folder'], exist_ok=True)
        os.makedirs(config['depth_folder'], exist_ok=True)
        logger.info("Output directories created/verified")
    except OSError as e:
        logger.error(f"Failed to create output directories: {str(e)}")
        sys.exit(1)
    
    # Get sample list
    try:
        sample_list = get_MiDaS_samples(
            config['src_folder'],
            config['depth_folder'],
            config,
            config.get('specific', '')
        )
        logger.info(f"Found {len(sample_list)} image(s) to process")
    except Exception as e:
        logger.error(f"Failed to get image samples: {str(e)}")
        sys.exit(1)
    
    normal_canvas, all_canvas = None, None
    device = setup_device(config)

    # Process each image
    for idx in tqdm(range(len(sample_list)), desc="Processing images"):
        depth = None
        sample = sample_list[idx]
        logger.info(f"Processing source image: {sample['src_pair_name']}")
        mesh_fi = os.path.join(config['mesh_folder'], sample['src_pair_name'] + '.ply')
        
        try:
            image = imageio.imread(sample['ref_img_fi'])
        except Exception as e:
            logger.error(f"Failed to read image {sample['ref_img_fi']}: {str(e)}")
            continue

        logger.info("Running depth extraction")
        try:
            run_depth(
                [sample['ref_img_fi']],
                config['src_folder'],
                config['depth_folder'],
                config['MiDaS_model_ckpt'],
                MonoDepthNet,
                MiDaS_utils,
                target_w=640
            )
        except Exception as e:
            logger.error(f"Depth extraction failed: {str(e)}")
            continue
        
        try:
            config['output_h'], config['output_w'] = np.load(sample['depth_fi']).shape[:2]
            frac = config['longer_side_len'] / max(config['output_h'], config['output_w'])
            config['output_h'], config['output_w'] = int(config['output_h'] * frac), int(config['output_w'] * frac)
            config['original_h'], config['original_w'] = config['output_h'], config['output_w']
        except Exception as e:
            logger.error(f"Failed to load depth map: {str(e)}")
            continue
        
        # Handle grayscale images
        if image.ndim == 2:
            image = image[..., None].repeat(3, -1)
        if np.sum(np.abs(image[..., 0] - image[..., 1])) == 0 and np.sum(np.abs(image[..., 1] - image[..., 2])) == 0:
            config['gray_image'] = True
        else:
            config['gray_image'] = False
        
        image = cv2.resize(image, (config['output_w'], config['output_h']), interpolation=cv2.INTER_AREA)
        depth = read_MiDaS_depth(sample['depth_fi'], 3.0, config['output_h'], config['output_w'])
        mean_loc_depth = depth[depth.shape[0]//2, depth.shape[1]//2]
        
        # Generate or load 3D mesh
        if not(config.get('load_ply', False) and os.path.exists(mesh_fi)):
            logger.info("Performing bilateral filtering")
            vis_photos, vis_depths = sparse_bilateral_filtering(
                depth.copy(),
                image.copy(),
                config,
                num_iter=config['sparse_iter'],
                spdb=False
            )
            depth = vis_depths[-1]
            model = None
            torch.cuda.empty_cache()
            
            logger.info("Starting 3D Photo inpainting pipeline")
            
            # Load edge model
            logger.info("Loading edge model")
            try:
                depth_edge_model = Inpaint_Edge_Net(init_weights=True)
                depth_edge_weight = torch.load(
                    config['depth_edge_model_ckpt'],
                    map_location=torch.device(device)
                )
                depth_edge_model.load_state_dict(depth_edge_weight)
                depth_edge_model = depth_edge_model.to(device)
                depth_edge_model.eval()
            except Exception as e:
                logger.error(f"Failed to load edge model: {str(e)}")
                continue

            # Load depth model
            logger.info("Loading depth model")
            try:
                depth_feat_model = Inpaint_Depth_Net()
                depth_feat_weight = torch.load(
                    config['depth_feat_model_ckpt'],
                    map_location=torch.device(device)
                )
                depth_feat_model.load_state_dict(depth_feat_weight, strict=True)
                depth_feat_model = depth_feat_model.to(device)
                depth_feat_model.eval()
            except Exception as e:
                logger.error(f"Failed to load depth model: {str(e)}")
                continue
            
            # Load RGB model
            logger.info("Loading RGB inpainting model")
            try:
                rgb_model = Inpaint_Color_Net()
                rgb_feat_weight = torch.load(
                    config['rgb_feat_model_ckpt'],
                    map_location=torch.device(device)
                )
                rgb_model.load_state_dict(rgb_feat_weight)
                rgb_model.eval()
                rgb_model = rgb_model.to(device)
            except Exception as e:
                logger.error(f"Failed to load RGB model: {str(e)}")
                continue
            
            graph = None

            logger.info("Generating 3D mesh with depth inpainting")
            try:
                rt_info = write_ply(
                    image,
                    depth,
                    sample['int_mtx'],
                    mesh_fi,
                    config,
                    rgb_model,
                    depth_edge_model,
                    depth_edge_model,
                    depth_feat_model
                )
            except Exception as e:
                logger.error(f"Failed to generate 3D mesh: {str(e)}")
                continue

            if rt_info is False:
                logger.warning(f"Mesh generation returned False for {sample['src_pair_name']}, skipping")
                continue
            
            # Clean up models
            rgb_model = None
            color_feat_model = None
            depth_edge_model = None
            depth_feat_model = None
            torch.cuda.empty_cache()
        
        # Load mesh data
        if config.get('save_ply', False) or config.get('load_ply', False):
            logger.info(f"Loading mesh from {mesh_fi}")
            try:
                verts, colors, faces, Height, Width, hFov, vFov = read_ply(mesh_fi)
            except Exception as e:
                logger.error(f"Failed to load mesh: {str(e)}")
                continue
        else:
            verts, colors, faces, Height, Width, hFov, vFov = rt_info

        # Generate videos
        logger.info("Rendering output videos")
        try:
            videos_poses, video_basename = copy.deepcopy(sample['tgts_poses']), sample['tgt_name']
            top = (config.get('original_h') // 2 - sample['int_mtx'][1, 2] * config['output_h'])
            left = (config.get('original_w') // 2 - sample['int_mtx'][0, 2] * config['output_w'])
            down, right = top + config['output_h'], left + config['output_w']
            border = [int(xx) for xx in [top, down, left, right]]
            
            normal_canvas, all_canvas = output_3d_photo(
                verts.copy(), colors.copy(), faces.copy(),
                copy.deepcopy(Height), copy.deepcopy(Width),
                copy.deepcopy(hFov), copy.deepcopy(vFov),
                copy.deepcopy(sample['tgt_pose']), sample['video_postfix'],
                copy.deepcopy(sample['ref_pose']),
                copy.deepcopy(config['video_folder']),
                image.copy(), copy.deepcopy(sample['int_mtx']),
                config, image, videos_poses, video_basename,
                config.get('original_h'), config.get('original_w'),
                border=border, depth=depth,
                normal_canvas=normal_canvas, all_canvas=all_canvas,
                mean_loc_depth=mean_loc_depth
            )
            logger.info(f"Successfully processed {sample['src_pair_name']}")
        except Exception as e:
            logger.error(f"Failed to render videos: {str(e)}")
            continue
    
    logger.info("=" * 60)
    logger.info("3D Photo Inpainting - Processing complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

