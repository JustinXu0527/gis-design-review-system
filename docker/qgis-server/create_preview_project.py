#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

from osgeo import ogr
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsProject, QgsVectorLayer


def gpkg_layers(path: Path) -> list[str]:
    dataset = ogr.Open(str(path))
    if dataset is None:
        return []
    return [dataset.GetLayer(index).GetName() for index in range(dataset.GetLayerCount())]


def load_style(layer: QgsVectorLayer, path: Path, layer_name: str) -> None:
    candidates = [
        path.with_suffix(".qml"),
        path.parent / f"{layer_name}.qml",
        path.with_suffix(".sld"),
        path.parent / f"{layer_name}.sld",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        layer.loadNamedStyle(str(candidate))
        return


def add_layer(project: QgsProject, uri: str, name: str, style_path: Path, first_crs: QgsCoordinateReferenceSystem | None) -> QgsCoordinateReferenceSystem | None:
    layer = QgsVectorLayer(uri, name, "ogr")
    if not layer.isValid():
        print(f"skip invalid layer: {name} -> {uri}", file=sys.stderr)
        return first_crs
    load_style(layer, style_path, name)
    project.addMapLayer(layer)
    if first_crs is None and layer.crs().isValid():
        return layer.crs()
    return first_crs


def build_project(work_dir: Path, output_project: Path) -> None:
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        project.setFileName(str(output_project))

        first_crs: QgsCoordinateReferenceSystem | None = None
        for gpkg in sorted(work_dir.rglob("*.gpkg")):
            for layer_name in gpkg_layers(gpkg):
                uri = f"{gpkg}|layername={layer_name}"
                first_crs = add_layer(project, uri, layer_name, gpkg, first_crs)

        for path in sorted([*work_dir.rglob("*.shp"), *work_dir.rglob("*.geojson")]):
            first_crs = add_layer(project, str(path), path.stem, path, first_crs)

        if first_crs and first_crs.isValid():
            project.setCrs(first_crs)
        else:
            project.setCrs(QgsCoordinateReferenceSystem("EPSG:25832"))

        if not project.mapLayers():
            raise RuntimeError(f"no valid GIS layers found in {work_dir}")
        if not project.write(str(output_project)):
            raise RuntimeError(f"failed to write {output_project}")
    finally:
        app.exitQgis()


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: create_preview_project.py <work-dir> <output-project>", file=sys.stderr)
        return 2
    build_project(Path(sys.argv[1]), Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
