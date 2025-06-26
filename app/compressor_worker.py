import os
import time
import random
from io import BytesIO
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Tuple, NamedTuple, Dict, Optional, Any

from PIL import Image
import numpy as np
from PySide6.QtCore import QObject, Signal

# ==============================================================================
# TYPE DEFINITIONS 
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
# WORKER CLASS
# ==============================================================================

class CompressorWorker(QObject):
    """
    Manages the image compression logic in a separate thread.
    Communicates with the GUI via signals.
    """
    # --- Signals ---
    # Signal to send log messages to the GUI
    log_message = Signal(str)
    # Signal to update the progress bar: (current_value, max_value)
    progress_updated = Signal(int, int)
    # Signal emitted when the entire process is finished
    # Sends back results, stats, and total time
    finished = Signal(list, object, float)
    # Signal to indicate a critical error occurred
    error = Signal(str)

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config
        self.is_running = True

    def stop(self):
        """Flags the worker to stop processing."""
        self.log_message.emit("🛑 Stop signal received. Finishing current tasks...")
        self.is_running = False

    def run(self):
        """The main entry point for the compression task."""
        start_time = time.time()
        try:
            # Step 1: Gather statistics
            stats = self._gather_statistics()
            if not stats:
                self.error.emit("Failed to gather statistics. Aborting.")
                return

            # Step 2: Prepare for processing
            self.log_message.emit(f"🚀 Starting compression with {self.config['worker_count']} workers...")
            mode_str = '"Target Size"' if self.config['target_size_mode'] else '"Relative Quality"'
            self.log_message.emit(f"Strategy: {mode_str}\n")
            
            results: List[ProcessResult] = []
            
            # Step 3: Run the processing pool
            with ProcessPoolExecutor(max_workers=self.config['worker_count']) as executor:
                # We pass the full config to each worker process
                futures = {
                    executor.submit(self._process_image_task, path, stats, self.config, (i % self.config['worker_count']) + 1): path
                    for i, path in enumerate(stats.file_paths)
                }
                
                total_files = len(stats.file_paths)
                self.progress_updated.emit(0, total_files)

                for i, future in enumerate(as_completed(futures)):
                    if not self.is_running:
                        # Attempt to gracefully shut down the executor
                        executor.shutdown(wait=False, cancel_futures=True)
                        self.log_message.emit("Processing stopped by user.")
                        break
                    
                    try:
                        result = future.result()
                        results.append(result)
                        # We use the result's message for detailed logging
                        self.log_message.emit(result.message)
                    except Exception as e:
                        path = futures[future]
                        error_msg = f"CRITICAL ERROR processing {os.path.basename(path)}: {e}"
                        self.log_message.emit(f"❌ {error_msg}")
                        results.append(ProcessResult(False, path, 0, None, None, error_msg))
                    
                    self.progress_updated.emit(i + 1, total_files)

            # Step 4: Finalize and emit results
            self.log_message.emit("\n" + "="*50)
            self.log_message.emit("✅ COMPRESSION JOB COMPLETE")
            self.log_message.emit("="*50)

            summary_text = self._generate_summary(results, stats, start_time)
            self.log_message.emit(summary_text)

            self.finished.emit(results, stats, time.time() - start_time)

        except Exception as e:
            self.error.emit(f"An unexpected error occurred in the worker thread: {e}")

    def _gather_statistics(self) -> Optional[ImageStats]:
        """Scans the input folder and calculates statistics."""
        folder_path = self.config['input_folder']
        extensions = self.config['supported_extensions']
        self.log_message.emit(f"🔍 Gathering statistics from '{folder_path}'...")
        
        if not os.path.isdir(folder_path):
            self.log_message.emit(f"❌ Error: Input folder '{folder_path}' not found.")
            return None

        try:
            all_files = os.listdir(folder_path)
            image_paths = [
                os.path.join(folder_path, f)
                for f in all_files
                if f.lower().endswith(extensions) and os.path.isfile(os.path.join(folder_path, f))
            ]
        except Exception as e:
            self.log_message.emit(f"❌ Error reading folder '{folder_path}': {e}")
            return None

        if not image_paths:
            self.log_message.emit(f"⚠️ No images with extensions {extensions} found in '{folder_path}'.")
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
        
        self.log_message.emit("📊 Statistics gathered:")
        self.log_message.emit(f"   - Images found: {stats.total_count}")
        self.log_message.emit(f"   - Total size: {stats.total_size_kb:,.2f} KB")
        self.log_message.emit(f"   - Average size: {stats.avg_size_kb:.2f} KB\n")
        return stats

    @staticmethod
    def _process_image_task(file_path: str, stats: ImageStats, config: Dict[str, Any], worker_id: int) -> ProcessResult:
        """
        Static method to be called by ProcessPoolExecutor.
        It contains the logic for processing a single image.
        """
        filename = os.path.basename(file_path)
        orig_size_kb = os.path.getsize(file_path) / 1024

        try:
            img = Image.open(file_path).convert("RGB")
            
            if config['target_size_mode']:
                result = CompressorWorker._compress_to_target_size(img, config)
            else:
                result = CompressorWorker._compress_with_relative_quality(img, orig_size_kb, stats, config)

            # Unpack result tuple (jpeg_data, final_quality, status_message)
            jpeg_data, final_quality, status_message = result
            
            if jpeg_data:
                return CompressorWorker._save_and_report(file_path, orig_size_kb, jpeg_data, final_quality, worker_id, status_message, config['output_folder'])
            else: # Target not met and not saved
                # status_message here contains the failure details
                return ProcessResult(False, file_path, orig_size_kb, None, None, status_message)

        except Exception as e:
            message = f"❌ [Worker-{worker_id}] Failed to process {filename}: {e}"
            return ProcessResult(False, file_path, orig_size_kb, None, None, message)

    @staticmethod
    def _compress_to_target_size(img: Image.Image, config: Dict[str, Any]) -> Tuple[Optional[bytes], int, str]:
        current_quality = config['max_quality']
        best_attempt_buffer = BytesIO()
        best_size_kb = float('inf')
        best_quality = 0
        target_size_kb = config['target_size_kb']

        while current_quality >= config['min_quality']:
            buffer = BytesIO()
            img.save(buffer, "JPEG", quality=current_quality, optimize=True)
            size_kb = len(buffer.getvalue()) / 1024

            if size_kb < best_size_kb:
                best_size_kb = size_kb
                best_quality = current_quality
                best_attempt_buffer = buffer

            if size_kb <= target_size_kb:
                return buffer.getvalue(), current_quality, "Success"

            overshoot_ratio = size_kb / target_size_kb
            quality_drop = 10 if overshoot_ratio > 1.5 else 5 if overshoot_ratio > 1.1 else 2
            current_quality -= quality_drop
        
        if config['save_on_target_failure']:
            msg = f"Target not met. Saved best effort: {best_size_kb:.1f}KB @ Q{best_quality}"
            return best_attempt_buffer.getvalue(), best_quality, msg
        else:
            msg = (f"Could not meet target size of {target_size_kb}KB. "
                   f"Smallest achievable size was {best_size_kb:.1f}KB at quality {best_quality}.")
            return None, 0, msg

    @staticmethod
    def _compress_with_relative_quality(img: Image.Image, orig_size_kb: float, stats: ImageStats, config: Dict[str, Any]) -> Tuple[Optional[bytes], int, str]:
        if stats.max_size_kb == stats.min_size_kb:
            quality = config['base_quality']
        else:
            normalized_size = (orig_size_kb - stats.min_size_kb) / (stats.max_size_kb - stats.min_size_kb)
            quality = config['max_quality'] - (normalized_size * (config['max_quality'] - config['min_quality']))
        
        final_quality = int(np.clip(quality, config['min_quality'], config['max_quality']))
        
        buffer = BytesIO()
        img.save(buffer, "JPEG", quality=final_quality, optimize=True)
        return buffer.getvalue(), final_quality, "Success"

    @staticmethod
    def _save_and_report(original_path: str, orig_size_kb: float, jpeg_data: bytes, quality: int, worker_id: int, status_message: str, output_folder: str) -> ProcessResult:
        final_size_kb = len(jpeg_data) / 1024
        filename = os.path.basename(original_path)
        
        output_filename = f"{os.path.splitext(filename)[0]}_{int(final_size_kb)}kb_q{quality}_id{random.randint(1000, 9999)}.jpeg"
        output_path = os.path.join(output_folder, output_filename)
        
        os.makedirs(output_folder, exist_ok=True)
        with open(output_path, "wb") as f_out:
            f_out.write(jpeg_data)

        ratio = (final_size_kb / orig_size_kb) * 100 if orig_size_kb > 0 else 0
        message = (
            f"✅ [Worker-{worker_id}] {filename}: {orig_size_kb:.1f} KB→ {final_size_kb:.1f} KB "
            f"(Quality: {quality}, Ratio: {ratio:.1f}%)"
        )
        
        is_success = status_message == "Success"
        return ProcessResult(is_success, original_path, orig_size_kb, final_size_kb, quality, message)

    def _generate_summary(self, results: List[ProcessResult], stats: ImageStats, start_time: float) -> str:
        """Generates a detailed summary string of the entire compression job."""
        end_time = time.time()
        total_processed = len(results)
        successes = [r for r in results if r.success]
        saved_but_target_missed = [r for r in results if not r.success and r.final_size_kb is not None]
        failures = [r for r in results if r.final_size_kb is None]

        summary = []
        summary.append("\n--- Overall ---")
        summary.append(f"Total images processed: {total_processed} / {stats.total_count}")
        summary.append(f"  - Full Success: {len(successes)}")
        if self.config['save_on_target_failure']:
            summary.append(f"  - Partial Success (Target not met but saved): {len(saved_but_target_missed)}")
        summary.append(f"  - Failed (not saved): {len(failures)}")
        summary.append(f"Total time taken: {end_time - start_time:.2f} seconds")
        if total_processed > 0 and end_time > start_time:
            summary.append(f"Processing speed: {total_processed / (end_time - start_time):.2f} images/sec")
        
        saved_images = successes + saved_but_target_missed
        if saved_images:
            orig_sizes = [r.original_size_kb for r in saved_images]
            final_sizes = [r.final_size_kb for r in saved_images if r.final_size_kb]
            total_orig_size = sum(orig_sizes)
            total_final_size = sum(final_sizes)
            
            qualities_used = [r.final_quality for r in saved_images if r.final_quality is not None]
            
            summary.append("\n--- Statistics for ALL Saved Images ---")
            summary.append(f"Total original size: {total_orig_size:,.2f} KB")
            summary.append(f"Total final size:    {total_final_size:,.2f} KB")
            compression_ratio = (1 - (total_final_size / total_orig_size)) * 100 if total_orig_size > 0 else 0
            summary.append(f"Overall size reduction: {compression_ratio:.2f}%")
            
            if qualities_used:
                summary.append(f"Average quality used: {np.mean(qualities_used):.1f}")
                summary.append(f"Quality range used:   {min(qualities_used)} to {max(qualities_used)}")
                
        if failures:
            summary.append("\n--- Failed Files (Not Saved) ---")
            for f in failures:
                summary.append(f"  - {os.path.basename(f.original_path)}: {f.message}")

        summary.append("\n" + "="*50 + "\n")
        return "\n".join(summary)
