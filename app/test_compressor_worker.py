# balls
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image
import numpy as np

from compressor_worker import CompressorWorker, ImageStats, ProcessResult

# ==============================================================================
# HELPER FUNCTIONS & FIXTURES
# ==============================================================================

def create_dummy_image_file(path: Path, filename: str, size_kb: int, color: str = "blue"):
    """Creates a dummy JPEG image file of a target size."""
    img_path = path / filename
    img_size = (400, 300) 
    img = Image.new('RGB', img_size, color=color)
    quality = 95
    while quality > 5:
        with open(img_path, "wb+") as buffer:
            img.save(buffer, "JPEG", quality=quality)
            if buffer.tell() / 1024 < size_kb:
                break
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
# WORKING UNIT TESTS
# ==============================================================================

class TestCompressorUnitLogic:
    def test_compress_to_target_size_success(self, base_config):
        img = Image.new('RGB', (800, 600), 'red')
        config = base_config.copy()
        config['target_size_kb'] = 100
        data, quality, msg = CompressorWorker._compress_to_target_size(img, config)
        assert data is not None
        assert len(data) / 1024 <= config['target_size_kb']
        assert msg == "Success"

    def test_compress_to_target_size_failure_but_save_best(self, base_config):
        img = Image.new('RGB', (800, 600), 'green')
        config = base_config.copy()
        config['target_size_kb'] = 1
        config['save_on_target_failure'] = True
        data, quality, msg = CompressorWorker._compress_to_target_size(img, config)
        assert data is not None
        assert len(data) / 1024 > config['target_size_kb']
        assert config['min_quality'] <= quality <= config['max_quality']

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
        data1, quality1, msg1 = CompressorWorker._compress_with_relative_quality(img, 180.0, mock_image_stats, config)
        data2, quality2, msg2 = CompressorWorker._compress_with_relative_quality(img, 110.0, mock_image_stats, config)
        assert data1 is not None and data2 is not None
        assert msg1 == "Success" and msg2 == "Success"
        assert quality1 < quality2

    def test_generate_summary(self, base_config, mock_image_stats):
        results = [
            ProcessResult(True, 'a.jpg', 150, 45, 80, "Success"),
            ProcessResult(False, 'b.jpg', 200, 110, 10, "Target not met"),
            ProcessResult(False, 'c.jpg', 100, None, None, "Failed to open")
        ]
        worker = CompressorWorker(base_config)
        summary = worker._generate_summary(results, mock_image_stats, time.time())
        assert "Total images processed: 3 / 2" in summary
        assert "Full Success: 1" in summary
        assert "Partial Success (Target not met but saved): 1" in summary
        assert "Failed (not saved): 1" in summary
        assert "Failed Files (Not Saved)" in summary

# ==============================================================================
# WORKING INTEGRATION TESTS
# ==============================================================================

class TestCompressorWithMockedIO:
    def test_gather_statistics_success(self, mocker, temp_folders, base_config):
        input_dir, _ = temp_folders
        create_dummy_image_file(input_dir, "img1.jpg", 150)
        (input_dir / "not_an_image.txt").touch()
        worker = CompressorWorker(base_config)
        mocker.patch.object(worker, 'log_message')
        stats = worker._gather_statistics()
        assert stats is not None
        assert stats.total_count == 1

    def test_gather_statistics_no_images(self, mocker, temp_folders, base_config):
        input_dir, _ = temp_folders
        (input_dir / "document.txt").touch()
        worker = CompressorWorker(base_config)
        mocker.patch.object(worker, 'log_message')
        stats = worker._gather_statistics()
        assert stats is None

    def test_gather_statistics_folder_not_found(self, mocker, base_config):
        config = base_config.copy()
        config['input_folder'] = "/non_existent_folder_12345"
        worker = CompressorWorker(config)
        mocker.patch.object(worker, 'log_message')
        stats = worker._gather_statistics()
        assert stats is None

    def test_save_and_report(self, temp_folders, mocker):
        mocker.patch('random.randint', return_value=1111)
        _, output_dir = temp_folders
        jpeg_data = b'\xff\xd8\xff\xe0'
        result = CompressorWorker._save_and_report("image.jpg", 150.0, jpeg_data, 85, 1, "Success", str(output_dir))
        expected_filename = "image_0kb_q85_id1111.jpeg"
        expected_path = output_dir / expected_filename
        assert expected_path.exists()
        assert result.success is True

    def test_process_image_task_target_mode_success(self, temp_folders, base_config, mock_image_stats):
        input_dir, _ = temp_folders
        img_path, _ = create_dummy_image_file(input_dir, "large_image.jpg", 200)
        config = base_config.copy()
        config['target_size_kb'] = 100
        result = CompressorWorker._process_image_task(str(img_path), mock_image_stats, config, 1)
        assert result.success is True
        assert result.final_size_kb <= config['target_size_kb']

    def test_process_image_task_quality_mode(self, temp_folders, base_config, mock_image_stats):
        input_dir, _ = temp_folders
        img_path, _ = create_dummy_image_file(input_dir, "quality_image.jpg", 150)
        config = base_config.copy()
        config['target_size_mode'] = False
        result = CompressorWorker._process_image_task(str(img_path), mock_image_stats, config, 1)
        assert result.success is True
        assert result.final_quality is not None
        assert config['min_quality'] <= result.final_quality <= config['max_quality']

if __name__ == "__main__":
    pytest.main(['-v', __file__])
