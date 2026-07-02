import fire
import cv2
import numpy as np
import rich
from rich.progress import Progress
from pathlib import Path
from sonocrop import vid
from scipy.ndimage import binary_fill_holes
import json
from typing import Tuple
from .backscan import find_linear_fov, pre_dsc_image, pre_dsc_image_vectorized,dsc_image_vectorized

from .utils import *


class _NpEncoder(json.JSONEncoder):
    """JSON encoder compatible numpy >= 2.0 (float32/int64 non sérialisables nativement)."""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def removeLayout(input_dir: str, output_dir: str,
                 thresh: float = -1,
                 FOV_tresh: int = 100,
                 back_scan_conversion: bool = True,
                 backscan_width: int = 512,
                 backscan_height: int = 512,
                 save_mask: bool = True,
                 save_cropped_mask = True,
                 save_info = True) -> str:
    """_summary_
    removeLayout for a dir of videos.
    input_dir contains multiples videos
    output_dir: path to generate one dire per video with extracted stuff

    Args:
        input_dir (str): _description_
        output_dir (str): _description_
        thresh (float, optional): _description_. Defaults to 0.05.
        back_scan_conversion (bool, optional): _description_. Defaults to True.
        backscan_width (int, optional): _description_. Defaults to 512.
        backscan_height (int, optional): _description_. Defaults to 512.
        save_mask (bool, optional): _description_. Defaults to True.
        save_cropped_mask (bool, optional): _description_. Defaults to True.
        save_info (bool, optional): _description_. Defaults to True.

    Returns:
        str: _description_
    """
    path_videos = list(Path(input_dir).glob("*.mp4"))
    
    for path_video in path_videos:
        video_output_dir = Path(output_dir) / path_video.stem
        
        if (video_output_dir / "backscan_video.mp4").exists():
            continue
        
        removeLayoutFile(str(path_video), video_output_dir,
                        thresh=thresh,
                        FOV_tresh=FOV_tresh,
                        back_scan_conversion=back_scan_conversion,
                        backscan_width=backscan_width,
                        backscan_height=backscan_height,
                        save_mask=save_mask,
                        save_cropped_mask=save_cropped_mask,
                        save_info=save_info)


def scanConversion(IRSC: str, output_file: str, dc: float, rc: float, theta_c: float, xoffset: int, yoffset: int,
                   scan_width: int, scan_height: int, backscan_width: int = 512, backscan_height: int = 512) -> None:

    v, fps, f, height, width = vid.loadvideo(IRSC)

    rich.print(f"video: [underline]{IRSC}[/underline]")
    rich.print(f"  Frames: {f}")
    rich.print(f"  FPS: {fps}")
    rich.print(f"  Width x height: {width} x {height}")
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(output_file), fourcc, fps, (scan_width, scan_height), False)

    with Progress() as progress:
        task = progress.add_task("[green] Scan conversion in progress...", total=f)
        for i in range(f):
            frame = dsc_image_vectorized(v[i], dc, rc, theta_c, yoffset, xoffset, scan_width, scan_height, backscan_width, backscan_height)
            out.write(frame.astype(np.uint8))               
            progress.update(task, advance=1)        
    out.release()


def removeLayoutFile(input_file: str, output_dir: str,
                 thresh: float = 0.05,
                 FOV_tresh: int = 100,
                 back_scan_conversion: bool = True,
                 backscan_width: int = 512,
                 backscan_height: int = 512,
                 save_mask: bool = True,
                 save_cropped_mask = True,
                 save_info = True) -> str:
    """
    Blackout static pixels in an ultrasound.

    Args:
        input_file (str): Path to input video (must be mp4, mov, or avi).
        output_dir (str): File path for video output.
        thresh (float, optional): Threshold value for counting unique pixels. Defaults to 0.05.
    Returns:
        str: A string indicating the operation is done.
    """

    v, fps, f, height, width = vid.loadvideo(input_file)

    rich.print(f"video: [underline]{input_file}[/underline]")
    rich.print(f"  Frames: {f}")
    rich.print(f"  FPS: {fps}")
    rich.print(f"  Width x height: {width} x {height}")

    # Count unique pixels
    with Progress() as progress:
        task = progress.add_task("[green] Finding static video pixels...", total=height)
        u = np.zeros((height, width), np.uint8)
        for i in range(height):
            u[i] = np.apply_along_axis(vid.countUniquePixels, 0, v[:, i, :])
            progress.update(task, advance=1)

    u_avg = u / f
      
    if thresh == -1:
        # auto treshold based on mean values
        # Calculate the histogram with 10 bins
        _, bin_edges = np.histogram(u_avg, bins=20)       
        thresh = bin_edges[3]
    rich.print(f"  Thresh: {thresh}")

    # create binary mask
    mask = u_avg > thresh
    mask_img = mask.astype(np.uint8)
    mask_largest_img = keep_largest_component(mask_img)
    mask_mirrored_largest_img = sync_halves(np.copy(mask_largest_img))
    
    boolean_mask = binary_fill_holes((mask_mirrored_largest_img / 255).astype(bool))
    
    # Apply morphological operations to denoise the image
    boolean_mask = (boolean_mask*255).astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    denoised_image = cv2.morphologyEx(boolean_mask, cv2.MORPH_OPEN, kernel)
    denoised_image = cv2.morphologyEx(denoised_image, cv2.MORPH_CLOSE, kernel)
       
    boolean_mask = (denoised_image / 255).astype(bool)   
    
    cropped_boolean_mask, ymin, ymax, xmin, xmax = crop_single_object(np.copy(boolean_mask))
    
    # prepare dir
    input_name = Path(input_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    table = rich.table.Table(show_lines=False, show_edge=False)
    table.add_column("", no_wrap=True)
    table.add_column("Path")
    
    # crop and save masked video
    path_cropped_video = output_dir / "video.mp4"
    y = vid.applyMask(v.copy(), boolean_mask)
    y_cropped = y[:, ymin:ymax, xmin:xmax]

    table.add_row("Saving infos to file:", 
                    rich.text.Text(str(path_cropped_video), style="green underline"))
    
    # backscan conversion on masked cropped video
    if back_scan_conversion:
        path_backscan_video = output_dir / "backscan_video.mp4"       
        params= find_linear_fov((cropped_boolean_mask * 255).astype(np.uint8), threshold=FOV_tresh)
        if params:
            xoffset, yoffset, rc, theta_c, dc = params
        else:
            rich.print("[red] find_linear_fov failled!")
            
            if thresh > 0.005:
                thresh = thresh*0.8
                rich.print(f"[red] retry with thresh={thresh} and FOV_tresh={int(FOV_tresh*0.9)}...")
            else:
                return
                           
            return removeLayoutFile(str(input_file), str(output_dir),
                        thresh=thresh,
                        FOV_tresh=int(FOV_tresh*0.9),
                        back_scan_conversion=back_scan_conversion,
                        backscan_width=backscan_width,
                        backscan_height=backscan_height,
                        save_mask=save_mask,
                        save_cropped_mask=save_cropped_mask,
                        save_info=save_info)

        # frame = pre_dsc_image(y_cropped[0], dc, rc, theta_c, yoffset, xoffset, backscan_width, backscan_height)
        # mmcv.imshow(frame)
        f, _, _ = y_cropped.shape
        
        mask_valid = pre_dsc_image_vectorized(y_cropped[0], dc, rc, theta_c, 
                                              yoffset, xoffset, backscan_width, backscan_height, get_IUSI_FOV=True)
        cv2.imwrite(str(output_dir / "mask.png"), mask_valid)
        
        y_cropped = v[:, ymin:ymax, xmin:xmax]
        y_cropped = vid.applyMask(y_cropped, (mask_valid / 255).astype(bool))
        vid.savevideo(str(path_cropped_video), y_cropped, fps)
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(path_backscan_video), fourcc, fps, (backscan_width, backscan_height), False)

        with Progress() as progress:
            task = progress.add_task("[green] Backscan conversion in progress...", total=f)
            for i in range(f):
                frame = pre_dsc_image_vectorized(y_cropped[i], dc, rc, theta_c, yoffset, xoffset, backscan_width, backscan_height)
                out.write(frame.astype(np.uint8))               
                progress.update(task, advance=1)        
        out.release()
        table.add_row("Saving backscan converted video to file:", 
                rich.text.Text(str(path_backscan_video), style="green underline"))
            
    # Save the binary image to disk
    if save_mask:
        path_binary_mask = output_dir / "binary_mask.png"
        cv2.imwrite(str(path_binary_mask), (boolean_mask * 255).astype(np.uint8))
        #rich.print(f"[green] Saving binary mask to file: [underline]{path_binary_mask}[/underline]")
        table.add_row("Saving binary mask to file:", 
                      rich.text.Text(str(path_binary_mask), style="green underline"))
        
    if save_cropped_mask:
        path_cropped_binary_mask = output_dir / "cropped_binary_mask.png"
        cv2.imwrite(str(path_cropped_binary_mask), (cropped_boolean_mask * 255).astype(np.uint8))
        table.add_row("Saving cropped binary mask to file:", 
                      rich.text.Text(str(path_cropped_binary_mask), style="green underline"))
            
    if save_info:
        path_info = output_dir / "info.json"
        data = {
            "crop": {
                "ymin": int(ymin),
                "ymax": int(ymax),
                "xmin": int(xmin),
                "xmax": int(xmax)
            },
            "original_shape": {
                "width": int(width),
                "height": int(height)
            },
            "threshold": thresh,
        }
        if back_scan_conversion:
            data["backscan"] = {
                "width": int(backscan_width),
                "height": int(backscan_height),
                "xoffset": xoffset,
                "yoffset": yoffset,
                "rc": rc,
                "dc": dc,
                "theta_c": theta_c
            }
        with open(str(path_info), "w") as file:
            json.dump(data, file, cls=_NpEncoder)
        table.add_row("Saving infos to file:", 
                      rich.text.Text(str(path_info), style="green underline"))
               

    
    # print saved files info
    rich.print(table)

    return "Done"

def main():
    fire.Fire()


if __name__ == "__main__":
    main()