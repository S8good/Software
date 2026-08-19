from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nanosense.ml.analyte_registry import get_default_analyte_registry
from nanosense.ml.lspr_ai_service import LSPRAIService, LSPRAIServiceError
from nanosense.ml.paired_spectrum import PairedSpectrumInput, Spectrum
from nanosense.utils.file_io import load_spectrum


class LSPRPairedPredictionWidget(QWidget):
    """Primary paper-aligned paired-reference prediction workflow."""

    prediction_ready = pyqtSignal(object)
    pair_changed = pyqtSignal(object)

    def __init__(self, service_factory: Callable[[], LSPRAIService], config=None, parent=None):
        super().__init__(parent)
        self._service_factory = service_factory
        self.config = dict(config or {})
        self._reference_spectrum: Optional[Spectrum] = None
        self._response_spectrum: Optional[Spectrum] = None
        self._pair: Optional[PairedSpectrumInput] = None
        self._last_result = None
        self._build_ui()
        self._populate_analytes()
        self._refresh_validation()

    def _get_service(self) -> LSPRAIService:
        return self._service_factory()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        identity_group = QGroupBox("Analyte and Pair Identity")
        identity_layout = QFormLayout(identity_group)
        self.analyte_combo = QComboBox()
        self.analyte_combo.currentIndexChanged.connect(self._refresh_validation)
        identity_layout.addRow("Analyte:", self.analyte_combo)
        self.chip_id_edit = QLineEdit()
        self.chip_id_edit.setPlaceholderText("Required, for example chip-01")
        self.chip_id_edit.textChanged.connect(self._refresh_validation)
        identity_layout.addRow("Chip ID:", self.chip_id_edit)
        self.site_id_edit = QLineEdit()
        self.site_id_edit.setPlaceholderText("Required, for example site-03")
        self.site_id_edit.textChanged.connect(self._refresh_validation)
        identity_layout.addRow("Site ID:", self.site_id_edit)
        layout.addWidget(identity_group)

        spectra_group = QGroupBox("Paired Spectra")
        spectra_layout = QFormLayout(spectra_group)
        reference_row = QHBoxLayout()
        self.reference_status_label = QLabel("Not loaded")
        self.import_reference_button = QPushButton("Import Reference...")
        self.import_reference_button.clicked.connect(self._import_reference)
        reference_row.addWidget(self.reference_status_label, stretch=1)
        reference_row.addWidget(self.import_reference_button)
        spectra_layout.addRow("BSA reference:", reference_row)
        response_row = QHBoxLayout()
        self.response_status_label = QLabel("Not loaded")
        self.import_response_button = QPushButton("Import Response...")
        self.import_response_button.clicked.connect(self._import_response)
        response_row.addWidget(self.response_status_label, stretch=1)
        response_row.addWidget(self.import_response_button)
        spectra_layout.addRow("Analyte response:", response_row)
        layout.addWidget(spectra_group)

        validation_group = QGroupBox("Validation and Model Status")
        validation_layout = QVBoxLayout(validation_group)
        self.validation_status_label = QLabel("Waiting for a paired input.")
        self.validation_status_label.setWordWrap(True)
        validation_layout.addWidget(self.validation_status_label)
        self.model_status_label = QLabel("Model status: not checked")
        self.model_status_label.setWordWrap(True)
        validation_layout.addWidget(self.model_status_label)
        layout.addWidget(validation_group)

        self.predict_button = QPushButton("Run Paired Prediction")
        self.predict_button.setEnabled(False)
        self.predict_button.clicked.connect(self._run_prediction)
        layout.addWidget(self.predict_button)

        result_group = QGroupBox("Result")
        result_layout = QVBoxLayout(result_group)
        self.result_label = QLabel("No prediction.")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)
        layout.addWidget(result_group)
        layout.addStretch(1)

    def _populate_analytes(self):
        self.analyte_combo.clear()
        registry = get_default_analyte_registry()
        for definition in registry.all():
            label = definition.display_name
            if not definition.is_supported:
                label += " (model not supplied)"
            self.analyte_combo.addItem(label, definition.analyte_id)

    def _selected_analyte_id(self) -> str:
        return str(self.analyte_combo.currentData() or "")

    def set_analyte(self, analyte_id: str):
        index = self.analyte_combo.findData(analyte_id)
        if index < 0:
            return False
        self.analyte_combo.setCurrentIndex(index)
        return True

    def set_reference_spectrum(self, wavelengths, intensities, metadata=None):
        self._reference_spectrum = Spectrum(
            wavelengths,
            intensities,
            role="reference",
            metadata=dict(metadata or {}),
        )
        self.reference_status_label.setText(
            "%d points" % len(self._reference_spectrum.wavelengths)
        )
        self._refresh_validation()

    def set_response_spectrum(self, wavelengths, intensities, metadata=None):
        self._response_spectrum = Spectrum(
            wavelengths,
            intensities,
            role="response",
            metadata=dict(metadata or {}),
        )
        self.response_status_label.setText(
            "%d points" % len(self._response_spectrum.wavelengths)
        )
        self._refresh_validation()

    def set_input_spectrum(self, wavelengths, intensities, metadata=None):
        """Compatibility entry point; the supplied spectrum is the response half."""
        self.set_response_spectrum(wavelengths, intensities, metadata=metadata)

    def set_paired_spectra(
        self,
        reference_wavelengths,
        reference_intensities,
        response_wavelengths,
        response_intensities,
        chip_id: str,
        site_id: str,
        analyte_id: str = "cea",
        metadata: Optional[Mapping[str, Any]] = None,
    ):
        self.set_analyte(analyte_id)
        self.chip_id_edit.setText(chip_id)
        self.site_id_edit.setText(site_id)
        self.set_reference_spectrum(reference_wavelengths, reference_intensities, metadata)
        self.set_response_spectrum(response_wavelengths, response_intensities, metadata)

    def _import_reference(self):
        self._import_spectrum("reference")

    def _import_response(self):
        self._import_spectrum("response")

    def _import_spectrum(self, role: str):
        wavelengths, intensities, source_file = load_spectrum(
            self, self.config.get("default_load_path", "")
        )
        if wavelengths is None or intensities is None:
            return
        metadata = {"source": "file_import", "source_file": source_file}
        try:
            if role == "reference":
                self.set_reference_spectrum(wavelengths, intensities, metadata)
            else:
                self.set_response_spectrum(wavelengths, intensities, metadata)
        except Exception as exc:
            QMessageBox.warning(self, "Paired Spectrum", str(exc))

    def _build_pair(self) -> PairedSpectrumInput:
        if self._reference_spectrum is None or self._response_spectrum is None:
            raise LSPRAIServiceError(
                "spectrum_missing",
                "Both the reference and response spectra are required.",
            )
        return PairedSpectrumInput(
            analyte_id=self._selected_analyte_id(),
            chip_id=self.chip_id_edit.text().strip(),
            site_id=self.site_id_edit.text().strip(),
            reference_spectrum=self._reference_spectrum,
            response_spectrum=self._response_spectrum,
        )

    def _refresh_validation(self):
        self._pair = None
        self.pair_changed.emit(None)
        self.predict_button.setEnabled(False)
        if self._reference_spectrum is None or self._response_spectrum is None:
            self.validation_status_label.setText("Load both paired spectra before validation.")
            self.model_status_label.setText("Model status: not checked")
            return
        try:
            pair = self._build_pair()
            service = self._get_service()
            definition = service.validate_paired_input(pair)
            self._pair = pair
            self.pair_changed.emit(pair)
            self.validation_status_label.setText(
                "Pair valid: %s (%s)" % (pair.pair_id, definition.display_name)
            )
            adapter = service.analyte_adapters[definition.analyte_id]
            health = adapter.health_check()
            if health.ok:
                self.model_status_label.setText("Model status: ready")
                self.predict_button.setEnabled(True)
            else:
                self.model_status_label.setText("Model status: %s" % health.message)
        except (LSPRAIServiceError, ValueError) as exc:
            self.validation_status_label.setText("Pair invalid: %s" % exc)
            self.model_status_label.setText("Model status: not checked")

    def _run_prediction(self):
        if self._pair is None:
            self._refresh_validation()
            return
        try:
            result = self._get_service().predict_paired(self._pair)
        except LSPRAIServiceError as exc:
            QMessageBox.warning(self, "Paired Prediction", str(exc))
            self.result_label.setText("No prediction: %s" % exc)
            return
        self._last_result = result
        self.result_label.setText(
            "%s: %.6g %s\nQC: %s\nModel: %s"
            % (
                result.analyte_id,
                result.predicted_concentration_ng_ml,
                result.target_unit,
                dict(result.qc).get("status", "not reported"),
                dict(result.provenance).get("model_version", "unknown"),
            )
        )
        self.prediction_ready.emit(result)
