from PyQt5.QtWidgets import QMainWindow, QTabWidget

from .lspr_paired_prediction_widget import LSPRPairedPredictionWidget
from .lspr_spectrum_comparison_widget import LSPRSpectrumComparisonWidget
from ..ml.lspr_ai_service import LSPRAIService


class LSPRAIWorkbench(QMainWindow):
    def __init__(self, config=None, service=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self._service = service

        self.setWindowTitle("LSPR AI Workbench")
        self.resize(1100, 760)

        self.tab_widget = QTabWidget(self)
        self.setCentralWidget(self.tab_widget)

        self.paired_spectrum_tab = LSPRPairedPredictionWidget(
            self._get_service, config=self.config, parent=self
        )
        self.single_spectrum_tab = self.paired_spectrum_tab
        self.spectrum_comparison_tab = LSPRSpectrumComparisonWidget(parent=self)
        self.paired_spectrum_tab.prediction_ready.connect(self._handle_prediction)

        self.tab_widget.addTab(self.paired_spectrum_tab, "Paired Quantification")
        self.tab_widget.addTab(self.spectrum_comparison_tab, "Spectrum Comparison")

    def _get_service(self):
        if self._service is None:
            self._service = LSPRAIService(config=self.config)
        return self._service

    def set_input_spectrum(self, wavelengths, intensities, metadata=None):
        self.single_spectrum_tab.set_input_spectrum(wavelengths, intensities, metadata=metadata)
        self.tab_widget.setCurrentWidget(self.single_spectrum_tab)

    def _handle_prediction(self, result):
        del result
