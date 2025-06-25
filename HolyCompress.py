# Holy jpeg compressor by Drago

import os
import time
import random
from io import BytesIO
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Tuple, NamedTuple, Dict, Optional

from PIL import Image
import numpy as np

# ==============================================================================
# SCRIPT CONFIGURATION
# ==============================================================================

# --- I/O Settings ---
INPUT_FOLDER: str = "input"
OUTPUT_FOLDER: str = "output"
SUPPORTED_EXTENSIONS: Tuple[str, ...] = (".png", ".webp", ".bmp", ".tiff", ".gif")

# --- Concurrency Settings ---
# Set the number of worker processes. os.cpu_count() is a good default.
WORKER_COUNT: int = os.cpu_count() or 4

# --- Compression Strategy ---
# Set to True to enable "Target Size" mode (iteratively compress to a specific KB).
# Set to False to enable "Relative Quality" mode (set quality based on original size).
TARGET_SIZE_MODE: bool = True

# --- General Quality Settings ---
MIN_QUALITY: int = 70        # The absolute minimum quality an image can be compressed to.
MAX_QUALITY: int = 98        # The absolute maximum quality.

# --- "Relative Quality" Mode Settings (if TARGET_SIZE_MODE is False) ---
BASE_QUALITY: int = 92      # The quality used for an image of average size.

# --- "Target Size" Mode Settings (if TARGET_SIZE_MODE is True) ---
TARGET_SIZE_KB: int = 250    # The desired file size in kilobytes.


# If a file can't be compressed to the target size, should we save the best attempt?
SAVE_ON_TARGET_FAILURE: bool = True


# ==============================================================================
# HOLY TYPE DEFINITIONS for clear data structures
# ==============================================================================

class ImageStats(NamedTuple):
    """Holds pre-calculated statistics about the input images."""
    total_count: int
    total_size_kb: float
    avg_size_kb: float
    min_size_kb: float
    max_size_kb: float
    file_paths: List[str]

class ProcessResult(NamedTuple):
    """Holds the result of a single image processing task."""
    success: bool
    original_path: str
    original_size_kb: float
    final_size_kb: Optional[float]
    final_quality: Optional[int]
    message: str
    best_effort_size_kb: Optional[float] = None
    best_effort_quality: Optional[int] = None

# ==============================================================================
# HOLY CORE FUNCTIONS
# ==============================================================================

def gather_statistics(folder_path: str, extensions: Tuple[str, ...]) -> Optional[ImageStats]:
    """Scans the input folder and calculates statistics for all supported images."""
    print(f"🔍 Gathering statistics from '{folder_path}'...")
    try:
        all_files = os.listdir(folder_path)
        image_paths = [
            os.path.join(folder_path, f)
            for f in all_files
            if f.lower().endswith(extensions) and os.path.isfile(os.path.join(folder_path, f))
        ]
    except FileNotFoundError:
        print(f"❌ Error: Input folder '{folder_path}' not found.")
        return None

    if not image_paths:
        print(f"⚠️ No images with extensions {extensions} found in '{folder_path}'.")
        print("   Folder contents:", all_files if all_files else "Empty")
        return None

    sizes_kb = [os.path.getsize(p) / 1024 for p in image_paths]
    
    stats = ImageStats(
        total_count=len(image_paths),
        total_size_kb=sum(sizes_kb),
        avg_size_kb=np.mean(sizes_kb),
        min_size_kb=min(sizes_kb),
        max_size_kb=max(sizes_kb),
        file_paths=image_paths,
    )
    
    print("📊 Statistics gathered:")
    print(f"   - Images found: {stats.total_count}")
    print(f"   - Total size: {stats.total_size_kb:,.2f} KB")
    print(f"   - Average size: {stats.avg_size_kb:.2f} KB")
    print(f"   - Size range: {stats.min_size_kb:.2f} KB to {stats.max_size_kb:.2f} KB\n")
    return stats


def calculate_relative_quality(
    image_size_kb: float, stats: ImageStats
) -> int:
    """Calculates JPEG quality based on image size relative to the average."""
    if stats.max_size_kb == stats.min_size_kb:
        return BASE_QUALITY

    normalized_size = (image_size_kb - stats.min_size_kb) / (stats.max_size_kb - stats.min_size_kb)
    quality = MAX_QUALITY - (normalized_size * (MAX_QUALITY - MIN_QUALITY))
    return int(np.clip(quality, MIN_QUALITY, MAX_QUALITY))


def process_image(
    file_path: str,
    stats: ImageStats,
    worker_id: int
) -> ProcessResult:
    """
    Worker function to compress a single image using one of the two strategies.
    This function is executed in a separate process.
    """
    filename = os.path.basename(file_path)
    prefix = f"[Worker-{worker_id}]"
    orig_size_kb = os.path.getsize(file_path) / 1024

    try:
        img = Image.open(file_path).convert("RGB")
        jpeg_data: Optional[bytes] = None
        final_quality: int = 0
        
        if TARGET_SIZE_MODE:
            # --- "Target Size" Strategy ---
            current_quality = MAX_QUALITY
            best_attempt_buffer = BytesIO()
            best_size_kb = float('inf')
            best_quality = 0

            while current_quality >= MIN_QUALITY:
                buffer = BytesIO()
                img.save(buffer, "JPEG", quality=current_quality, optimize=True)
                size_kb = len(buffer.getvalue()) / 1024

                # Track the best result so far
                if size_kb < best_size_kb:
                    best_size_kb = size_kb
                    best_quality = current_quality
                    best_attempt_buffer = buffer

                if size_kb <= TARGET_SIZE_KB:
                    final_quality = current_quality
                    jpeg_data = buffer.getvalue()
                    break  # Success!

                overshoot_ratio = size_kb / TARGET_SIZE_KB
                quality_drop = 10 if overshoot_ratio > 1.5 else 5 if overshoot_ratio > 1.1 else 2
                current_quality -= quality_drop
            
            if not jpeg_data: # Target was not met
                if SAVE_ON_TARGET_FAILURE:
                    jpeg_data = best_attempt_buffer.getvalue()
                    final_quality = best_quality
                    msg = (f"Target not met. Saved best effort: {best_size_kb:.1f}KB @ Q{best_quality}")
                    return save_and_report(file_path, orig_size_kb, jpeg_data, final_quality, prefix, msg)
                else:
                    msg = (f"Could not meet target size of {TARGET_SIZE_KB}KB. "
                           f"Smallest achievable size was {best_size_kb:.1f}KB at quality {best_quality}.")
                    return ProcessResult(False, file_path, orig_size_kb, None, None, msg, best_size_kb, best_quality)

        else:
            # --- "Relative Quality" Strategy ---
            final_quality = calculate_relative_quality(orig_size_kb, stats)
            buffer = BytesIO()
            img.save(buffer, "JPEG", quality=final_quality, optimize=True)
            jpeg_data = buffer.getvalue()
        
        return save_and_report(file_path, orig_size_kb, jpeg_data, final_quality, prefix, "Success")

    except Exception as e:
        message = f"❌ {prefix} Failed to process {filename}: {e}"
        print(message)
        return ProcessResult(False, file_path, orig_size_kb, None, None, str(e))

def save_and_report(
    original_path: str,
    orig_size_kb: float,
    jpeg_data: bytes,
    quality: int,
    prefix: str,
    status_message: str
) -> ProcessResult:
    """Helper function to save data to a file and create a ProcessResult."""
    final_size_kb = len(jpeg_data) / 1024
    filename = os.path.basename(original_path)
    
    output_filename = f"{os.path.splitext(filename)[0]}_{int(final_size_kb)}kb_q{quality}_id{random.randint(1000, 9999)}.jpeg"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    
    with open(output_path, "wb") as f_out:
        f_out.write(jpeg_data)

    ratio = (final_size_kb / orig_size_kb) * 100 if orig_size_kb > 0 else 0
    message = (
        f"{prefix} {filename}: {orig_size_kb:.1f} KB → {final_size_kb:.1f} KB "
        f"(Quality: {quality}, Ratio: {ratio:.1f}%) saved as {output_filename}"
    )
    print(message)
    
    is_success = status_message == "Success" # Only true success counts for the summary
    return ProcessResult(is_success, original_path, orig_size_kb, final_size_kb, quality, status_message)


def print_summary(results: List[ProcessResult], stats: ImageStats, start_time: float) -> None:
    """Prints a detailed summary of the entire compression job."""
    end_time = time.time()
    total_processed = len(results)
    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    partial_successes = [r for r in results if not r.success and r.message.startswith("Target not met")]

    print("\n" + "="*50)
    print("✅ COMPRESSION JOB COMPLETE")
    print("="*50)

    print(f"\n--- Overall ---")
    print(f"Total images processed: {total_processed} / {stats.total_count}")
    print(f"  - Full Success: {len(successes)}")
    if SAVE_ON_TARGET_FAILURE:
         print(f"  - Partial Success (Target not met but saved): {len(partial_successes)}")
    print(f"  - Failed:  {len(failures) - len(partial_successes)}")
    print(f"Total time taken: {end_time - start_time:.2f} seconds")
    if total_processed > 0 and end_time > start_time:
        print(f"Processing speed: {total_processed / (end_time - start_time):.2f} images/sec")
    
    # Statistics for all saved images (full and partial successes)
    saved_images = [r for r in results if r.final_size_kb is not None]
    if saved_images:
        orig_sizes = [r.original_size_kb for r in saved_images]
        final_sizes = [r.final_size_kb for r in saved_images]
        total_orig_size = sum(orig_sizes)
        total_final_size = sum(final_sizes)
        
        qualities_used = [r.final_quality for r in saved_images if r.final_quality is not None]
        
        print("\n--- Statistics for ALL Saved Images ---")
        print(f"Total original size: {total_orig_size:,.2f} KB")
        print(f"Total final size:    {total_final_size:,.2f} KB")
        compression_ratio = (1 - (total_final_size / total_orig_size)) * 100 if total_orig_size > 0 else 0
        print(f"Overall size reduction: {compression_ratio:.2f}%")
        
        if qualities_used:
            print("\n--- Quality Statistics ---")
            print(f"Average quality used: {np.mean(qualities_used):.1f}")
            print(f"Quality range used:   {min(qualities_used)} to {max(qualities_used)}")
            
    # List pure failures
    pure_failures = [r for r in failures if r not in partial_successes]
    if pure_failures:
        print("\n--- Failed Files (Not Saved) ---")
        for f in pure_failures:
            print(f"  - {os.path.basename(f.original_path)}: {f.message}")

    print("\n" + "="*50 + "\n")


def main() -> None:
    """Main function to orchestrate the image processing pipeline."""
    start_time = time.time()
    
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    stats = gather_statistics(INPUT_FOLDER, SUPPORTED_EXTENSIONS)
    if not stats:
        return
        
    mode_str = '"Target Size"' if TARGET_SIZE_MODE else '"Relative Quality"'
    print(f"🚀 Starting compression with {WORKER_COUNT} workers...")
    print(f"Strategy: {mode_str}\n")
    
    results: List[ProcessResult] = []
    
    with ProcessPoolExecutor(max_workers=WORKER_COUNT) as executor:
        futures = {
            executor.submit(process_image, path, stats, (i % WORKER_COUNT) + 1): path
            for i, path in enumerate(stats.file_paths)
        }
        
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                path = futures[future]
                print(f"CRITICAL ERROR processing {path}: {e}")
                results.append(ProcessResult(False, path, 0, None, None, f"Critical executor error: {e}"))

    print_summary(results, stats, start_time)


if __name__ == "__main__":
    # Make sure you have the required libraries: pip install Pillow numpy
    main()
