import pytest
from PySide6.QtCore import Qt


from main import ImageCompressorApp, CONFIG_DEFAULTS
@pytest.fixture
def app(qtbot):
    """
    Creates an instance of our main application window for testing.
    The 'qtbot' fixture handles adding the widget and cleaning it up.
    """
    window = ImageCompressorApp()
    qtbot.addWidget(window)
    return window

# --- SIMPLE TEST CASES ---

def test_initial_state(app: ImageCompressorApp):
    """
    Test 1: Check if the application starts with the correct default values.
    This is a simple "smoke test" to ensure the UI initializes correctly.
    """
    assert app.windowTitle() == "Advanced Image Compressor"
    
    # Check if a few key fields are populated from CONFIG_DEFAULTS
    assert app.input_folder_edit.text() == CONFIG_DEFAULTS['input_folder']
    assert app.output_folder_edit.text() == CONFIG_DEFAULTS['output_folder']
    assert app.worker_spinbox.value() == CONFIG_DEFAULTS['worker_count']
    assert app.target_size_spinbox.value() == CONFIG_DEFAULTS['target_size_kb']
    assert app.min_quality_spinbox.value() == CONFIG_DEFAULTS['min_quality']
    
    # Check that the "Target Size" mode is enabled by default
    assert app.target_size_radio.isChecked()
    assert app.target_size_group.isEnabled()
    assert not app.relative_quality_group.isEnabled()

def test_get_config_from_ui(app: ImageCompressorApp):
    """
    Test 2: Check if the get_config_from_ui method accurately reads widget values.
    We'll change some UI elements and see if the method picks up the changes.
    """
    # Change some values in the UI
    app.input_folder_edit.setText("/my/test/input")
    app.output_folder_edit.setText("/my/test/output")
    app.worker_spinbox.setValue(1)
    app.target_size_spinbox.setValue(123)
    app.save_on_failure_checkbox.setChecked(False)

    # Call the method to get the config
    config = app.get_config_from_ui()

    # Assert that the returned dictionary matches our changes
    assert config["input_folder"] == "/my/test/input"
    assert config["output_folder"] == "/my/test/output"
    assert config["worker_count"] == 1
    assert config["target_size_kb"] == 123
    assert not config["save_on_target_failure"]
    assert config["target_size_mode"] is True # This should not have changed

def test_strategy_toggle(app: ImageCompressorApp, qtbot):
    """
    Test 3: Check that clicking the strategy radio buttons correctly
    enables and disables the settings groups.
    """
    # Initial state (already tested, but good for clarity)
    assert app.target_size_group.isEnabled()
    assert not app.relative_quality_group.isEnabled()

    # Simulate a click on the "Relative Quality" radio button
    # qtbot.mouseClick is the standard way to do this.
    qtbot.mouseClick(app.relative_quality_radio, Qt.LeftButton)

    # Now, the state should be flipped
    assert not app.target_size_group.isEnabled()
    assert app.relative_quality_group.isEnabled()

    # Simulate a click to go back to "Target Size" mode
    qtbot.mouseClick(app.target_size_radio, Qt.LeftButton)
    
    # Assert that it's back to the original state
    assert app.target_size_group.isEnabled()
    assert not app.relative_quality_group.isEnabled()

def test_file_dialog_mocking(app: ImageCompressorApp, mocker, qtbot):
    """
    Test 4: A simple test showing how to mock a file dialog.
    We will simulate the user selecting a folder and check if the line edit updates.
    """
    # We mock QFileDialog.getExistingDirectory to immediately return a fake path
    # without actually opening a dialog window.
    mock_get_dir = mocker.patch('PySide6.QtWidgets.QFileDialog.getExistingDirectory', return_value="/fake/selected/folder")

    # Call the slot function that would normally be triggered by the button click
    app._select_input_folder()

    # Assert that the mock was called
    mock_get_dir.assert_called_once()
    # Assert that the line edit was updated with the path from our mock
    assert app.input_folder_edit.text() == "/fake/selected/folder"
