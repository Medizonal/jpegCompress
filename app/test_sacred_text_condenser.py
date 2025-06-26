# balls
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image
import numpy as np

from sacred_text_condenser import SacredImageCondenserAcolyte, HolyImageOmens, TransmutationOutcome

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
def mock_holy_image_omens() -> HolyImageOmens:
    """Provides a pre-canned HolyImageOmens object for testing logic."""
    return HolyImageOmens(
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

class TestSacredCondensationUnitAltar:
    def test_condense_visage_to_divine_limit_success(self, base_config):
        img = Image.new('RGB', (800, 600), 'red')
        config = base_config.copy()
        config['target_size_kb'] = 100
        data, quality, msg = SacredImageCondenserAcolyte._condense_visage_to_divine_limit(img, config)
        assert data is not None
        assert len(data) / 1024 <= config['target_size_kb']
        assert msg == "Success"

    def test_condense_visage_to_divine_limit_failure_but_save_best(self, base_config):
        img = Image.new('RGB', (800, 600), 'green')
        config = base_config.copy()
        config['target_size_kb'] = 1
        config['save_on_target_failure'] = True
        data, quality, msg = SacredImageCondenserAcolyte._condense_visage_to_divine_limit(img, config)
        assert data is not None
        assert len(data) / 1024 > config['target_size_kb']
        assert config['min_quality'] <= quality <= config['max_quality']

    def test_condense_visage_to_divine_limit_failure_no_save(self, base_config):
        img = Image.new('RGB', (800, 600), 'blue')
        config = base_config.copy()
        config['target_size_kb'] = 1
        config['save_on_target_failure'] = False
        data, quality, msg = SacredImageCondenserAcolyte._condense_visage_to_divine_limit(img, config)
        assert data is None
        assert quality == 0
        assert "Could not meet target size" in msg

    def test_condense_visage_by_relative_sanctity(self, base_config, mock_holy_image_omens):
        img = Image.new('RGB', (800, 600), 'yellow')
        config = base_config.copy()
        data1, quality1, msg1 = SacredImageCondenserAcolyte._condense_visage_by_relative_sanctity(img, 180.0, mock_holy_image_omens, config)
        data2, quality2, msg2 = SacredImageCondenserAcolyte._condense_visage_by_relative_sanctity(img, 110.0, mock_holy_image_omens, config)
        assert data1 is not None and data2 is not None
        assert msg1 == "Success" and msg2 == "Success"
        assert quality1 < quality2

    def test_compile_sacred_condensation_annals(self, base_config, mock_holy_image_omens):
        results = [
            TransmutationOutcome(True, 'a.jpg', 150, 45, 80, "Success"),
            TransmutationOutcome(False, 'b.jpg', 200, 110, 10, "Target not met"),
            TransmutationOutcome(False, 'c.jpg', 100, None, None, "Failed to open")
        ]
        worker = SacredImageCondenserAcolyte(base_config)
        summary = worker._compile_sacred_condensation_annals(results, mock_holy_image_omens, time.time())
        assert "Total images processed: 3 / 2" in summary
        assert "Full Success: 1" in summary
        assert "Partial Success (Target not met but saved): 1" in summary
        assert "Failed (not saved): 1" in summary
        assert "Failed Files (Not Saved)" in summary

# ==============================================================================
# WORKING INTEGRATION TESTS
# ==============================================================================

class TestSacredCondenserWithMockedSanctuaryIO:
    def test_collect_holy_image_omens_success(self, mocker, temp_folders, base_config):
        input_dir, _ = temp_folders
        create_dummy_image_file(input_dir, "img1.jpg", 150)
        (input_dir / "not_an_image.txt").touch()
        worker = SacredImageCondenserAcolyte(base_config)
        mocker.patch.object(worker, 'log_message')
        omens = worker._collect_holy_image_omens()
        assert omens is not None
        assert omens.total_count == 1

    def test_collect_holy_image_omens_no_images(self, mocker, temp_folders, base_config):
        input_dir, _ = temp_folders
        (input_dir / "document.txt").touch()
        worker = SacredImageCondenserAcolyte(base_config)
        mocker.patch.object(worker, 'log_message')
        omens = worker._collect_holy_image_omens()
        assert omens is None

    def test_collect_holy_image_omens_folder_not_found(self, mocker, base_config):
        config = base_config.copy()
        config['input_folder'] = "/non_existent_folder_12345"
        worker = SacredImageCondenserAcolyte(config)
        mocker.patch.object(worker, 'log_message')
        omens = worker._collect_holy_image_omens()
        assert omens is None

    def test_enshrine_and_document_transmutation(self, temp_folders, mocker):
        mocker.patch('random.randint', return_value=1111)
        _, output_dir = temp_folders
        jpeg_data = b'\xff\xd8\xff\xe0' # A minimal valid JPEG
        # Corrected call: source_scroll_path, initial_scroll_weight_kb, condensed_sacred_pixels, resulting_divine_focus, worker_id, transmutation_report, output_folder
        result = SacredImageCondenserAcolyte._enshrine_and_document_transmutation("image.jpg", 150.0, jpeg_data, 85, 1, "Success", str(output_dir))
        # The filename generated includes actual size of jpeg_data (0kb for the minimal one) and quality
        final_size_kb = len(jpeg_data)/1024
        expected_filename = f"image_{int(final_size_kb)}kb_q85_id1111.jpeg"
        expected_path = output_dir / expected_filename
        assert expected_path.exists()
        assert result.success is True

    def test_transmute_sacred_image_essence_task_target_mode_success(self, temp_folders, base_config, mock_holy_image_omens):
        input_dir, _ = temp_folders
        img_path, _ = create_dummy_image_file(input_dir, "large_image.jpg", 200)
        config = base_config.copy()
        config['target_size_kb'] = 100
        result = SacredImageCondenserAcolyte._transmute_sacred_image_essence_task(str(img_path), mock_holy_image_omens, config, 1)
        assert result.success is True
        assert result.final_size_kb is not None # Ensure final_size_kb is populated
        assert result.final_size_kb <= config['target_size_kb']

    def test_transmute_sacred_image_essence_task_quality_mode(self, temp_folders, base_config, mock_holy_image_omens):
        input_dir, _ = temp_folders
        img_path, _ = create_dummy_image_file(input_dir, "quality_image.jpg", 150)
        config = base_config.copy()
        config['target_size_mode'] = False
        result = SacredImageCondenserAcolyte._transmute_sacred_image_essence_task(str(img_path), mock_holy_image_omens, config, 1)
        assert result.success is True
        assert result.final_quality is not None
        assert config['min_quality'] <= result.final_quality <= config['max_quality']

if __name__ == "__main__":
    pytest.main(['-v', __file__])
