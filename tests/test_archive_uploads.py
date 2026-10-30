from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from review_system.archive_utils import ArchiveError, safe_extract_archive
from review_system.extractors import extract_design_objects_from_path


class ArchiveUploadTests(unittest.TestCase):
    def test_plain_zip_extracts_geojson_object(self) -> None:
        feature_collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "point-1",
                    "properties": {"name": "测试点", "object_type": "site"},
                    "geometry": {"type": "Point", "coordinates": [8.7, 50.0]},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "design.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
                output.writestr("design.geojson", json.dumps(feature_collection, ensure_ascii=False))
            objects = extract_design_objects_from_path(archive.name, archive)
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].name, "测试点")

    def test_zip_rejects_parent_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "unsafe.zip"
            target = Path(temp_dir) / "output"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../outside.geojson", "{}")
            with self.assertRaises(ArchiveError):
                safe_extract_archive(archive, target)

    @unittest.skipUnless(shutil.which("unrar") or Path(r"C:\Program Files\WinRAR\UnRAR.exe").is_file(), "UnRAR is not installed")
    def test_project_rar_extracts_gis_files(self) -> None:
        archives = list((Path(__file__).resolve().parents[1] / "test").glob("*.rar"))
        if not archives:
            self.skipTest("No project RAR fixture is available")
        with tempfile.TemporaryDirectory() as temp_dir:
            extracted = safe_extract_archive(archives[0], Path(temp_dir))
        self.assertTrue(any(path.suffix.lower() == ".gpkg" for path in extracted))


if __name__ == "__main__":
    unittest.main()
