from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"


def test_pyinstaller_spec_declares_gui_resources_and_vendor_drivers():
    spec = (PACKAGING / "nanosense.spec").read_text(encoding="utf-8")

    for required_path in (
        "nanosense/gui/assets/app_icon.ico",
        "nanosense/gui/assets/splash.png",
        "nanosense/translations/chinese.qm",
        "drivers/IdeaOptics.dll",
        "drivers/CyUSB.DLL",
        "drivers/Oceandirect/oceandirect/lib/OceanDirect.dll",
    ):
        assert required_path in spec

    assert "console=False" in spec
    assert "name=\"NanoSense\"" in spec


def test_windows_build_script_defines_both_distribution_artifacts():
    script = (PACKAGING / "build_windows.ps1").read_text(encoding="utf-8")

    assert "nanosense.spec" in script
    assert "Portable" in script
    assert "NanoSense-Setup" in script
    assert "iscc" in script.lower()


def test_inno_setup_script_installs_the_frozen_application():
    script = (PACKAGING / "NanoSense.iss").read_text(encoding="utf-8")

    assert 'AppName=NanoSense' in script
    assert 'OutputBaseFilename=NanoSense-Setup' in script
    assert 'Source: "..\\dist\\NanoSense\\*"' in script
    assert 'Filename: "{app}\\NanoSense.exe"' in script
