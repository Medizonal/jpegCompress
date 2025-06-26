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

class HolyImageOmens(NamedTuple):
    """Holds pre-calculated statistics about the input images."""
    total_count: int
    total_size_kb: float
    avg_size_kb: float
    min_size_kb: float
    max_size_kb: float
    file_paths: List[str]

class TransmutationOutcome(NamedTuple):
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

class SacredImageCondenserAcolyte(QObject):
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

    def __init__(self, sacred_directives: Dict[str, Any]):
        super().__init__()
        self.sacred_directives = sacred_directives
        self.is_running = True

    def stop(self):
        """Flags the worker to stop processing."""
        self.log_message.emit("🛑 Stop signal received. Finishing current tasks...")
        self.is_running = False

    def perform_sacred_image_condensation_ritual(self):
        """The main entry point for the compression task."""
        start_time = time.time()
        try:
            # Step 1: Gather statistics
            holy_image_omens_collected = self._collect_holy_image_omens()
            if not holy_image_omens_collected:
                self.error.emit("Failed to gather statistics. Aborting.")
                return

            # Step 2: Prepare for processing
            self.log_message.emit(f"🚀 Starting compression with {self.sacred_directives['worker_count']} workers...")
            mode_str = '"Target Size"' if self.sacred_directives['target_size_mode'] else '"Relative Quality"'
            self.log_message.emit(f"Strategy: {mode_str}\n")

            transmutation_outcomes: List[TransmutationOutcome] = []

            # Step 3: Run the processing pool
            with ProcessPoolExecutor(max_workers=self.sacred_directives['worker_count']) as executor:
                # We pass the full config to each worker process
                futures = {
                    executor.submit(self._transmute_sacred_image_essence_task, path, holy_image_omens_collected, self.sacred_directives, (i % self.sacred_directives['worker_count']) + 1): path
                    for i, path in enumerate(holy_image_omens_collected.file_paths)
                }

                total_files = len(holy_image_omens_collected.file_paths)
                self.progress_updated.emit(0, total_files)

                for i, future in enumerate(as_completed(futures)):
                    if not self.is_running:
                        # Attempt to gracefully shut down the executor
                        executor.shutdown(wait=False, cancel_futures=True)
                        self.log_message.emit("Processing stopped by user.")
                        break

                    try:
                        result = future.result()
                        transmutation_outcomes.append(result)
                        # We use the result's message for detailed logging
                        self.log_message.emit(result.message)
                    except Exception as e:
                        path = futures[future]
                        error_msg = f"CRITICAL ERROR processing {os.path.basename(path)}: {e}"
                        self.log_message.emit(f"❌ {error_msg}")
                        transmutation_outcomes.append(TransmutationOutcome(False, path, 0, None, None, error_msg))

                    self.progress_updated.emit(i + 1, total_files)

            # Step 4: Finalize and emit results
            self.log_message.emit("\n" + "="*50)
            self.log_message.emit("✅ COMPRESSION JOB COMPLETE")
            self.log_message.emit("="*50)

            summary_text = self._compile_sacred_condensation_annals(transmutation_outcomes, holy_image_omens_collected, start_time)
            self.log_message.emit(summary_text)

            self.finished.emit(transmutation_outcomes, holy_image_omens_collected, time.time() - start_time)

        except Exception as e:
            self.error.emit(f"An unexpected error occurred in the worker thread: {e}")

    def _collect_holy_image_omens(self) -> Optional[HolyImageOmens]:
        """Scans the input folder and calculates statistics."""
        folder_path = self.sacred_directives['input_folder']
        extensions = self.sacred_directives['supported_extensions']
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

        holy_image_omens_collected = HolyImageOmens(
            total_count=len(image_paths),
            total_size_kb=sum(sizes_kb),
            avg_size_kb=np.mean(sizes_kb),
            min_size_kb=min(sizes_kb),
            max_size_kb=max(sizes_kb),
            file_paths=image_paths,
        )

        self.log_message.emit("📊 Statistics gathered:")
        self.log_message.emit(f"   - Images found: {holy_image_omens_collected.total_count}")
        self.log_message.emit(f"   - Total size: {holy_image_omens_collected.total_size_kb:,.2f} KB")
        self.log_message.emit(f"   - Average size: {holy_image_omens_collected.avg_size_kb:.2f} KB\n")
        return holy_image_omens_collected

    @staticmethod
    def _transmute_sacred_image_essence_task(sacred_image_scroll_path: str, holy_image_omens_collected: HolyImageOmens, sacred_directives: Dict[str, Any], worker_id: int) -> TransmutationOutcome:
        """
        Static method to be called by ProcessPoolExecutor.
        It contains the logic for processing a single image.
        """
        filename = os.path.basename(sacred_image_scroll_path)
        initial_scroll_weight_kb = os.path.getsize(sacred_image_scroll_path) / 1024

        try:
            sacred_visage = Image.open(sacred_image_scroll_path).convert("RGB")

            if sacred_directives['target_size_mode']:
                transmutation_result_tuple = SacredImageCondenserAcolyte._condense_visage_to_divine_limit(sacred_visage, sacred_directives)
            else:
                transmutation_result_tuple = SacredImageCondenserAcolyte._condense_visage_by_relative_sanctity(sacred_visage, initial_scroll_weight_kb, holy_image_omens_collected, sacred_directives)

            # Unpack result tuple (condensed_sacred_pixels, resulting_divine_focus, transmutation_report)
            condensed_sacred_pixels, resulting_divine_focus, transmutation_report = transmutation_result_tuple

            if condensed_sacred_pixels:
                return SacredImageCondenserAcolyte._enshrine_and_document_transmutation(sacred_image_scroll_path, initial_scroll_weight_kb, condensed_sacred_pixels, resulting_divine_focus, worker_id, transmutation_report, sacred_directives['output_folder'])
            else: # Target not met and not saved
                # transmutation_report here contains the failure details
                return TransmutationOutcome(False, sacred_image_scroll_path, initial_scroll_weight_kb, None, None, transmutation_report)

        except Exception as e:
            message = f"❌ [Worker-{worker_id}] Failed to process {filename}: {e}"
            return TransmutationOutcome(False, sacred_image_scroll_path, initial_scroll_weight_kb, None, None, message)

    @staticmethod
    def _condense_visage_to_divine_limit(sacred_visage: Image.Image, sacred_directives: Dict[str, Any]) -> Tuple[Optional[bytes], int, str]:
        current_focus_level = sacred_directives['max_quality']
        closest_offering_chalice = BytesIO()
        closest_offering_weight_kb = float('inf')
        closest_focus_achieved = 0
        divine_weight_limit_kb = sacred_directives['target_size_kb']

        while current_focus_level >= sacred_directives['min_quality']:
            offering_chalice = BytesIO()
            sacred_visage.save(offering_chalice, "JPEG", quality=current_focus_level, optimize=True)
            offering_weight_kb = len(offering_chalice.getvalue()) / 1024

            if offering_weight_kb < closest_offering_weight_kb:
                closest_offering_weight_kb = offering_weight_kb
                closest_focus_achieved = current_focus_level
                closest_offering_chalice = offering_chalice

            if offering_weight_kb <= divine_weight_limit_kb:
                return offering_chalice.getvalue(), current_focus_level, "Success"

            overshoot_ratio = offering_weight_kb / divine_weight_limit_kb
            quality_drop = 10 if overshoot_ratio > 1.5 else 5 if overshoot_ratio > 1.1 else 2
            current_focus_level -= quality_drop

        if sacred_directives['save_on_target_failure']:
            msg = f"Target not met. Saved best effort: {closest_offering_weight_kb:.1f}KB @ Q{closest_focus_achieved}"
            return closest_offering_chalice.getvalue(), closest_focus_achieved, msg
        else:
            msg = (f"Could not meet target size of {divine_weight_limit_kb}KB. "
                   f"Smallest achievable size was {closest_offering_weight_kb:.1f}KB at quality {closest_focus_achieved}.")
            return None, 0, msg

    @staticmethod
    def _condense_visage_by_relative_sanctity(sacred_visage: Image.Image, initial_scroll_weight_kb: float, holy_image_omens_collected: HolyImageOmens, sacred_directives: Dict[str, Any]) -> Tuple[Optional[bytes], int, str]:
        if holy_image_omens_collected.max_size_kb == holy_image_omens_collected.min_size_kb:
            focus_level = sacred_directives['base_quality']
        else:
            normalized_size = (initial_scroll_weight_kb - holy_image_omens_collected.min_size_kb) / (holy_image_omens_collected.max_size_kb - holy_image_omens_collected.min_size_kb)
            focus_level = sacred_directives['max_quality'] - (normalized_size * (sacred_directives['max_quality'] - sacred_directives['min_quality']))

        final_focus_level = int(np.clip(focus_level, sacred_directives['min_quality'], sacred_directives['max_quality']))

        offering_chalice = BytesIO()
        sacred_visage.save(offering_chalice, "JPEG", quality=final_focus_level, optimize=True)
        return offering_chalice.getvalue(), final_focus_level, "Success"

    @staticmethod
    def _enshrine_and_document_transmutation(source_scroll_path: str, initial_scroll_weight_kb: float, condensed_sacred_pixels: bytes, resulting_divine_focus: int, worker_id: int, transmutation_report: str, output_folder: str) -> TransmutationOutcome:
        enshrined_weight_kb = len(condensed_sacred_pixels) / 1024
        filename = os.path.basename(source_scroll_path)

        sacred_relic_name = f"{os.path.splitext(filename)[0]}_{int(enshrined_weight_kb)}kb_q{resulting_divine_focus}_id{random.randint(1000, 9999)}.jpeg"
        reliquary_path = os.path.join(output_folder, sacred_relic_name)

        os.makedirs(output_folder, exist_ok=True)
        with open(reliquary_path, "wb") as f_out:
            f_out.write(condensed_sacred_pixels)

        ratio = (enshrined_weight_kb / initial_scroll_weight_kb) * 100 if initial_scroll_weight_kb > 0 else 0
        message = (
            f"✅ [Worker-{worker_id}] {filename}: {initial_scroll_weight_kb:.1f} KB→ {enshrined_weight_kb:.1f} KB "
            f"(Quality: {resulting_divine_focus}, Ratio: {ratio:.1f}%)"
        )

        is_success = transmutation_report == "Success"
        return TransmutationOutcome(is_success, source_scroll_path, initial_scroll_weight_kb, enshrined_weight_kb, resulting_divine_focus, message)

    def _compile_sacred_condensation_annals(self, transmutation_outcomes: List[TransmutationOutcome], holy_image_omens_collected: HolyImageOmens, start_time: float) -> str:
        """Generates a detailed summary string of the entire compression job."""
        end_time = time.time()
        total_processed = len(transmutation_outcomes)
        successful_transmutations = [r for r in transmutation_outcomes if r.success]
        partial_transmutations_enshrined = [r for r in transmutation_outcomes if not r.success and r.final_size_kb is not None]
        failed_transmutations = [r for r in transmutation_outcomes if r.final_size_kb is None]

        annals_chapters = []
        annals_chapters.append("\n--- Overall ---")
        annals_chapters.append(f"Total images processed: {total_processed} / {holy_image_omens_collected.total_count}")
        annals_chapters.append(f"  - Full Success: {len(successful_transmutations)}")
        if self.sacred_directives['save_on_target_failure']:
            annals_chapters.append(f"  - Partial Success (Target not met but saved): {len(partial_transmutations_enshrined)}")
        annals_chapters.append(f"  - Failed (not saved): {len(failed_transmutations)}")
        annals_chapters.append(f"Total time taken: {end_time - start_time:.2f} seconds")
        if total_processed > 0 and end_time > start_time:
            annals_chapters.append(f"Processing speed: {total_processed / (end_time - start_time):.2f} images/sec")

        enshrined_relics = successful_transmutations + partial_transmutations_enshrined
        if enshrined_relics:
            initial_scroll_weights = [r.original_size_kb for r in enshrined_relics]
            enshrined_relic_weights = [r.final_size_kb for r in enshrined_relics if r.final_size_kb]
            total_initial_weight = sum(initial_scroll_weights)
            total_enshrined_weight = sum(enshrined_relic_weights)

            focus_levels_applied = [r.final_quality for r in enshrined_relics if r.final_quality is not None]

            annals_chapters.append("\n--- Statistics for ALL Saved Images ---")
            annals_chapters.append(f"Total original size: {total_initial_weight:,.2f} KB")
            annals_chapters.append(f"Total final size:    {total_enshrined_weight:,.2f} KB")
            compression_ratio = (1 - (total_enshrined_weight / total_initial_weight)) * 100 if total_initial_weight > 0 else 0
            annals_chapters.append(f"Overall size reduction: {compression_ratio:.2f}%")

            if focus_levels_applied:
                annals_chapters.append(f"Average quality used: {np.mean(focus_levels_applied):.1f}")
                annals_chapters.append(f"Quality range used:   {min(focus_levels_applied)} to {max(focus_levels_applied)}")

        if failed_transmutations:
            annals_chapters.append("\n--- Failed Files (Not Saved) ---")
            for f in failed_transmutations:
                annals_chapters.append(f"  - {os.path.basename(f.original_path)}: {f.message}")

        annals_chapters.append("\n" + "="*50 + "\n")
        return "\n".join(annals_chapters)
