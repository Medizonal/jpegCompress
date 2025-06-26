import os
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from PIL import Image
import numpy as np

# Assuming your code is in a file named `compressor_logic.py`
# If your file has a different name, change the import below.
from compressor_logic import CompressorWorker, ImageStats, ProcessResult

# ==============================================================================
# HELPER FUNCTIONS & FIXTURES
# ==============================================================================

def create_dummy_image_file(path: Path, filename: str, size_kb: int, color: str = "blue"):
    """Creates a dummy JPEG image file of a target size."""
    img_path = path / filename
    img_size = (400, 300) 
    img = Image.new('RGB', img_size, color=color)
    
    # Save with varying quality to approximate target size
    quality = 95
    while quality > 5:
        buffer = open(img_path, "wb+")
        img.save(buffer, "JPEG", quality=quality)
        if buffer.tell() / 1024 < size_kb:
            buffer.close()
            break
        buffer.close()
        quality -= 5
    return img_path, os.path.getsize(img_path) / 1024

@pytest.fixture
def temp_folders(tmp_path: Path) -> tuple[Path, Path]:
    """Provides temporary input and output folders for tests."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    return input_dir, output_dir

@pytest.fixture
def base_config(temp_folders: tuple[Path, Path]) -> dict:
    """Provides a default configuration dictionary for the worker."""
    input_dir, output_dir = temp_folders
    return {
        "input_folder": str(input_dir),
        "output_folder": str(output_dir),
        "supported_extensions": (".jpeg", ".jpg"),
        "worker_count": 2,
        "target_size_mode": True,
        "target_size_kb": 50,
        "save_on_target_failure": True,
        "min_quality": 10,
        "max_quality": 95,
        "base_quality": 80,
    }

@pytest.fixture
def mock_image_stats() -> ImageStats:
    """Provides a pre-canned ImageStats object for testing logic."""
    return ImageStats(
        total_count=2,
        total_size_kb=300.0,
        avg_size_kb=150.0,
        min_size_kb=100.0,
        max_size_kb=200.0,
        file_paths=['/fake/path/img1.jpg', '/fake/path/img2.jpg']
    )

# ==============================================================================
# UNIT TESTS (Testing individual static methods)
# ==============================================================================

class TestCompressorUnitLogic:
    """Tests for pure, non-IO static methods of the CompressorWorker."""

    def test_compress_to_target_size_success(self, base_config):
        img = Image.new('RGB', (800, 600), 'red')
        config = base_config.copy()
        config['target_size_kb'] = 100

        data, quality, msg = CompressorWorker._compress_to_target_size(img, config)

        assert data is not None
        assert len(data) / 1024 <= config['target_size_kb']
        assert quality > config['min_quality']
        assert msg == "Success"

    def test_compress_to_target_size_failure_but_save_best(self, base_config):
        img = Image.new('RGB', (800, 600), 'green')
        config = base_config.copy()
        config['target_size_kb'] = 1 
        config['save_on_target_failure'] = True

        data, quality, msg = CompressorWorker._compress_to_target_size(img, config)

        assert data is not None
        assert len(data) / 1024 > config['target_size_kb']
        assert quality == config['min_quality']
        assert "Target not met. Saved best effort" in msg

    def test_compress_to_target_size_failure_no_save(self, base_config):
        img = Image.new('RGB', (800, 600), 'blue')
        config = base_config.copy()
        config['target_size_kb'] = 1
        config['save_on_target_failure'] = False

        data, quality, msg = CompressorWorker._compress_to_target_size(img, config)

        assert data is None
        assert quality == 0
        assert "Could not meet target size" in msg

    def test_compress_with_relative_quality(self, base_config, mock_image_stats):
        img = Image.new('RGB', (800, 600), 'yellow')
        config = base_config.copy()
        
        # Test with a larger image, expecting lower quality
        data1, quality1, msg1 = CompressorWorker._compress_with_relative_quality(
            img, 180.0, mock_image_stats, config
        )
        # Test with a smaller image, expecting higher quality
        data2, quality2, msg2 = CompressorWorker._compress_with_relative_quality(
            img, 110.0, mock_image_stats, config
        )

        assert data1 is not None and data2 is not None
        assert msg1 == "Success" and msg2 == "Success"
        assert quality1 < quality2
        assert config['min_quality'] <= quality1 <= config['max_quality']
        assert config['min_quality'] <= quality2 <= config['max_quality']

    def test_generate_summary(self, base_config, mock_image_stats):
        results = [
            ProcessResult(True, 'a.jpg', 150, 45, 80, "Success"),
            ProcessResult(False, 'b.jpg', 200, 110, 10, "Target not met"),
            ProcessResult(False, 'c.jpg', 100, None, None, "Failed to open")
        ]
        
        summary = CompressorWorker._generate_summary(self, results, mock_image_stats, time.time())
        
        assert "Total images processed: 3 / 2" in summary
        assert "Full Success: 1" in summary
        assert "Partial Success (Target not met but saved): 1" in summary
        assert "Failed (not saved): 1" in summary
        assert "Overall size reduction" in summary
        assert "Failed Files (Not Saved)" in summary
        assert "c.jpg: Failed to open" in summary

# ==============================================================================
# INTEGRATION TESTS (Testing methods with mocked IO and dependencies)
# ==============================================================================

class TestCompressorWithMockedIO:
    """Tests methods that interact with the filesystem, mocking all IO."""

    def test_gather_statistics_success(self, mocker, temp_folders, base_config):
        input_dir, _ = temp_folders
        create_dummy_image_file(input_dir, "img1.jpg", 150)
        create_dummy_image_file(input_dir, "img2.jpeg", 250)
        (input_dir / "not_an_image.txt").touch()

        worker = CompressorWorker(base_config)
        mocker.patch.object(worker, 'log_message')
        
        stats = worker._gather_statistics()

        assert stats is not None
        assert stats.total_count == 2
        assert stats.total_size_kb == pytest.approx(400, abs=15) # Allow variance
        assert len(stats.file_paths) == 2
        assert any("img1.jpg" in p for p in stats.file_paths)
        assert any("img2.jpeg" in p for p in stats.file_paths)

    def test_gather_statistics_no_images(self, mocker, temp_folders, base_config):
        input_dir, _ = temp_folders
        (input_dir / "document.txt").touch()
        worker = CompressorWorker(base_config)
        mocker.patch.object(worker, 'log_message')

        stats = worker._gather_statistics()
        assert stats is None
        worker.log_message.emit.assert_any_call(
            f"⚠️ No images with extensions {base_config['supported_extensions']} found in '{input_dir}'."
        )

    def test_gather_statistics_folder_not_found(self, mocker, base_config):
        config = base_config.copy()
        config['input_folder'] = "/non_existent_folder_12345"
        worker = CompressorWorker(config)
        mocker.patch.object(worker, 'log_message')

        stats = worker._gather_statistics()
        assert stats is None
        worker.log_message.emit.assert_any_call(
            f"❌ Error: Input folder '{config['input_folder']}' not found."
        )

    def test_save_and_report(self, temp_folders, mocker):
        mocker.patch('random.randint', return_value=1111)
        _, output_dir = temp_folders
        
        orig_path = "/fake/input/image.jpg"
        jpeg_data = b'\xff\xd8\xff\xe0' # Minimal jpeg data
        
        result = CompressorWorker._save_and_report(orig_path, 150.0, jpeg_data, 85, 1, "Success", str(output_dir))

        expected_filename = "image_0kb_q85_id1111.jpeg"
        expected_path = output_dir / expected_filename
        
        assert expected_path.exists()
        assert expected_path.read_bytes() == jpeg_data
        assert result.success is True
        assert result.original_path == orig_path
        assert result.final_quality == 85
        assert f"[Worker-1] image.jpg: 150.0 KB→ {result.final_size_kb:.1f} KB" in result.message

    def test_process_image_task_target_mode_success(self, temp_folders, base_config):
        input_dir, _ = temp_folders
        img_path, orig_size = create_dummy_image_file(input_dir, "large_image.jpg", 200)

        config = base_config.copy()
        config['target_size_kb'] = 100
        
        result = CompressorWorker._process_image_task(str(img_path), mock_image_stats(), config, 1)

        assert result.success is True
        assert result.final_size_kb is not None
        assert result.final_size_kb <= config['target_size_kb']
        assert result.original_size_kb == pytest.approx(orig_size)

    def test_process_image_task_quality_mode(self, temp_folders, base_config, mock_image_stats):
        input_dir, _ = temp_folders
        img_path, orig_size = create_dummy_image_file(input_dir, "quality_image.jpg", 150) # Middle size

        config = base_config.copy()
        config['target_size_mode'] = False
        
        result = CompressorWorker._process_image_task(str(img_path), mock_image_stats, config, 1)

        assert result.success is True
        assert result.final_quality is not None
        # Should be between min and max quality
        assert config['min_quality'] < result.final_quality < config['max_quality']

# ==============================================================================
# FULL WORKER RUN TEST (Mocking concurrency and signals)
# ==============================================================================

@patch('compressor_logic.ProcessPoolExecutor')
def test_full_run(MockExecutor, mocker, temp_folders, base_config):
    # --- Test Setup ---
    input_dir, output_dir = temp_folders
    img1_path, _ = create_dummy_image_file(input_dir, "test1.jpg", 150)
    img2_path, _ = create_dummy_image_file(input_dir, "test2.jpg", 80)
    
    config = base_config.copy()
    config['target_size_kb'] = 60
    config['worker_count'] = 1 # Easier to test serially

    worker = CompressorWorker(config)
    
    # Mock all Qt signals to check their calls later
    mocker.patch.object(worker, 'log_message', MagicMock())
    mocker.patch.object(worker, 'progress_updated', MagicMock())
    mocker.patch.object(worker, 'finished', MagicMock())
    mocker.patch.object(worker, 'error', MagicMock())
    
    # Mock time to get predictable duration
    mocker.patch('time.time', side_effect=[1000.0, 1010.5])
    mocker.patch('random.randint', side_effect=[1234, 5678])

    # --- Mock ProcessPoolExecutor to run tasks serially ---
    # This is the key to testing multiprocessing code deterministically
    def side_effect_submit(fn, *args, **kwargs):
        future = MagicMock()
        # Execute the function immediately and store result in the mock future
        future.result.return_value = fn(*args, **kwargs)
        return future

    mock_executor_instance = MockExecutor.return_value.__enter__.return_value
    mock_executor_instance.submit.side_effect = side_effect_submit
    mocker.patch('compressor_logic.as_completed', lambda futures: futures)

    # --- Execute the Worker's Run Method ---
    worker.run()

    # --- Assertions ---
    # 1. Check progress bar updates
    assert worker.progress_updated.call_count == 3
    worker.progress_updated.assert_has_calls([
        call(0, 2), # Initial
        call(1, 2), # After first file
        call(2, 2)  # After second file
    ])

    # 2. Check that the final 'finished' signal was emitted once
    worker.finished.assert_called_once()
    
    # 3. Inspect the data emitted by the 'finished' signal
    finished_args, _ = worker.finished.call_args
    results_list, stats_obj, total_time = finished_args
    
    assert len(results_list) == 2
    assert isinstance(stats_obj, ImageStats)
    assert total_time == pytest.approx(10.5)

    # 4. Check results for each image
    result1 = next(r for r in results_list if "test1.jpg" in r.original_path)
    result2 = next(r for r in results_list if "test2.jpg" in r.original_path)

    # test1.jpg (150kb) should have been compressed below 60kb
    assert result1.success is True
    assert result1.final_size_kb < 60
    
    # test2.jpg (80kb) should also have been compressed below 60kb
    assert result2.success is True
    assert result2.final_size_kb < 60

    # 5. Check that output files were created
    assert len(list(output_dir.glob('*.jpeg'))) == 2
    assert (output_dir / "test1_53kb_q75_id1234.jpeg").exists() or (output_dir / "test1_54kb_q75_id1234.jpeg").exists() # Filename depends on exact size after compression
    assert (output_dir / "test2_53kb_q85_id5678.jpeg").exists() or (output_dir / "test2_54kb_q85_id5678.jpeg").exists()

    # 6. Ensure no errors were emitted
    worker.error.assert_not_called()
