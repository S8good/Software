import logging

import pandas as pd

from nanosense.utils.file_io import export_experiments_to_excel, load_spectrum_from_path


def test_missing_spectrum_file_is_logged_without_console_output(caplog, capsys, tmp_path):
    missing_path = tmp_path / "missing-spectrum.csv"

    with caplog.at_level(logging.WARNING, logger="nanosense.utils.file_io"):
        wavelengths, intensities = load_spectrum_from_path(str(missing_path))

    assert wavelengths is None
    assert intensities is None
    assert any(
        "event=spectrum_file_missing" in record.getMessage()
        and "missing-spectrum.csv" in record.getMessage()
        for record in caplog.records
    )
    assert capsys.readouterr().out == ""


def test_experiment_export_failure_is_logged(monkeypatch, caplog, tmp_path):
    class FailingExcelWriter:
        def __init__(self, *args, **kwargs):
            raise OSError("disk full")

    monkeypatch.setattr(pd, "ExcelWriter", FailingExcelWriter)

    with caplog.at_level(logging.ERROR, logger="nanosense.utils.file_io"):
        ok, message = export_experiments_to_excel([], str(tmp_path / "report.xlsx"))

    assert ok is False
    assert message == "disk full"
    assert any(
        "event=experiment_export_failed" in record.getMessage()
        for record in caplog.records
    )
