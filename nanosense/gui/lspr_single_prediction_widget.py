from typing import Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from .lspr_paired_prediction_widget import LSPRPairedPredictionWidget


class LSPRSinglePredictionWidget(LSPRPairedPredictionWidget):
    """Compatibility shell; single-spectrum prediction is intentionally disabled."""

    comparison_ready = pyqtSignal(object)

    def __init__(self, service, config: Optional[dict] = None, parent=None):
        service_factory = service if callable(service) else (lambda: service)
        super().__init__(service_factory, config=config, parent=parent)
        self.input_status_label = self.response_status_label
        self.summary_widget = self.result_label

    def set_input_spectrum(self, wavelengths, intensities, metadata=None):
        self.set_response_spectrum(wavelengths, intensities, metadata=metadata)

    def _run_prediction(self):
        if self._reference_spectrum is None:
            QMessageBox.warning(
                self,
                "LSPR AI Workbench",
                "A paired reference spectrum is required; single-spectrum prediction is disabled.",
            )
            return
        super()._run_prediction()
