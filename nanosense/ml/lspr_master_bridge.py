from __future__ import annotations

import importlib
import os
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple


@dataclass
class LSPRMasterDiagnostics:
    master_root: str
    src_root: str
    models_root: str
    pretrained_root: str
    resolution_source: str
    candidate_paths: List[str] = field(default_factory=list)
    missing_files: List[str] = field(default_factory=list)
    runner_path: str = ""
    python_executable: str = ""


class LSPRMasterPathError(FileNotFoundError):
    """Raised when the LSPR Master root or its required files are unavailable."""

    def __init__(self, message: str, diagnostics: Dict[str, object]):
        super().__init__(message)
        self.diagnostics = diagnostics


class LSPRMasterBridge:
    REQUIRED_FILES = (
        ("src/core/ai_engine.py", "缺少 ai_engine.py"),
        ("src/core/digital_twin_service.py", "缺少 digital_twin_service.py"),
        ("models/pretrained/spectral_predictor_v2.pth", "缺少 spectral_predictor_v2.pth"),
        ("models/pretrained/predictor_v2_norm_params.pth", "缺少 predictor_v2_norm_params.pth"),
    )

    def __init__(self, master_root: Optional[Path] = None):
        self.master_root, self._resolution_source, self._candidate_paths = self._resolve_master_root(master_root)
        self.src_root = self.master_root / "src"
        self.models_root = self.master_root / "models"
        self.pretrained_root = self.models_root / "pretrained"
        self.validate_required_files()

    @staticmethod
    def _software_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _adjacent_candidates(cls) -> Tuple[Path, ...]:
        software_root = cls._software_root()
        return (
            software_root / "LSPR_Spectra_Master",
            software_root.parent / "DeepLearning" / "LSPR_Spectra_Master",
            software_root.parent.parent / "DeepLearning" / "LSPR_Spectra_Master",
        )

    @staticmethod
    def _normalize_path(value: Path) -> Path:
        return Path(value).expanduser().resolve()

    @classmethod
    def _resolve_master_root(
        cls, master_root: Optional[Path]
    ) -> Tuple[Path, str, List[Path]]:
        if master_root is not None and str(master_root).strip():
            candidates = [cls._normalize_path(Path(master_root))]
            source = "explicit"
        else:
            env_value = os.environ.get("LSPR_MASTER_ROOT", "").strip()
            if env_value:
                candidates = [cls._normalize_path(Path(env_value))]
                source = "environment"
            else:
                candidates = [cls._normalize_path(candidate) for candidate in cls._adjacent_candidates()]
                source = "adjacent"

        for candidate in candidates:
            if candidate.is_dir():
                return candidate, source, candidates

        candidate_text = ", ".join(str(candidate) for candidate in candidates)
        diagnostics = cls._diagnostics_payload(
            master_root=candidates[0] if candidates else None,
            resolution_source=source,
            candidate_paths=candidates,
        )
        raise LSPRMasterPathError(
            "LSPR_Spectra_Master 根目录不存在。请设置 lspr_master_root 或 "
            f"LSPR_MASTER_ROOT，或将仓库放在软件目录附近。已尝试: {candidate_text}",
            diagnostics,
        )

    @staticmethod
    def _diagnostics_payload(
        master_root: Optional[Path],
        resolution_source: str,
        candidate_paths: Sequence[Path],
        missing_files: Optional[Sequence[str]] = None,
    ) -> Dict[str, object]:
        root = Path(master_root) if master_root is not None else None
        src_root = root / "src" if root is not None else None
        models_root = root / "models" if root is not None else None
        pretrained_root = models_root / "pretrained" if models_root is not None else None
        runner_path = root / "scripts" / "lspr_bridge_runner.py" if root is not None else None
        data = LSPRMasterDiagnostics(
            master_root=str(root) if root is not None else "",
            src_root=str(src_root) if src_root is not None else "",
            models_root=str(models_root) if models_root is not None else "",
            pretrained_root=str(pretrained_root) if pretrained_root is not None else "",
            resolution_source=resolution_source,
            candidate_paths=[str(path) for path in candidate_paths],
            missing_files=list(missing_files or ()),
            runner_path=str(runner_path) if runner_path is not None else "",
            python_executable=str(Path(sys.executable).expanduser().resolve()),
        )
        return asdict(data)

    def _missing_required_files(self) -> List[str]:
        return [
            relative_path
            for relative_path, _ in self.REQUIRED_FILES
            if not (self.master_root / relative_path).is_file()
        ]

    def validate_required_files(self) -> None:
        missing_files = self._missing_required_files()
        if not missing_files:
            return
        reasons = "; ".join(
            f"{relative_path}: {self.master_root / relative_path}"
            for relative_path in missing_files
        )
        diagnostics = self._diagnostics_payload(
            master_root=self.master_root,
            resolution_source=self._resolution_source,
            candidate_paths=self._candidate_paths,
            missing_files=missing_files,
        )
        raise LSPRMasterPathError(
            "LSPR_Spectra_Master 缺少必需文件: " + reasons + "。请检查模型文件和根目录配置。",
            diagnostics,
        )

    def diagnostics(self) -> Dict[str, object]:
        return self._diagnostics_payload(
            master_root=self.master_root,
            resolution_source=self._resolution_source,
            candidate_paths=self._candidate_paths,
            missing_files=self._missing_required_files(),
        )
        return data.__dict__.copy()

    @contextmanager
    def import_context(self) -> Iterator[None]:
        root_str = str(self.master_root)
        inserted = False
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
            inserted = True
        try:
            yield
        finally:
            if inserted and root_str in sys.path:
                sys.path.remove(root_str)

    def import_module(self, module_name: str):
        with self.import_context():
            return importlib.import_module(module_name)

    def create_ai_engine(self):
        module = self.import_module("src.core.ai_engine")
        return module.FullSpectrumAIEngine(models_dir=str(self.models_root))

    def create_digital_twin_service(self):
        module = self.import_module("src.core.digital_twin_service")
        return module.DigitalTwinService(base_dir=str(self.master_root))

    def list_available_model_modes(self):
        engine = self.create_ai_engine()
        return list(engine.available_model_modes())
