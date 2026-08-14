from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from leadbot_v2.goat.preconstruction.geometry.models import (
    BoundingBox,
    Point2D,
    TextSpan,
    VectorLine,
    VectorPolygon,
    VectorSheet,
)


class PDFVectorDependencyUnavailable(
    RuntimeError
):
    pass


class PDFVectorExtractor:
    """
    Extracts native vector geometry and coordinate-aware text
    from PDFs using PyMuPDF when available.

    This is intentionally separate from the takeoff engine.
    """

    def extract_page(
        self,
        *,
        path: str | Path,
        page_number: int,
        document_id: str,
        sheet_number: str,
    ) -> VectorSheet:
        try:
            import fitz
        except ImportError as exc:
            raise PDFVectorDependencyUnavailable(
                "PyMuPDF is required for vector extraction."
            ) from exc

        pdf_path = Path(path)

        if not pdf_path.exists():
            raise FileNotFoundError(
                pdf_path
            )

        if page_number < 1:
            raise ValueError(
                "page_number must be >= 1"
            )

        document = fitz.open(
            str(pdf_path)
        )

        try:
            if page_number > len(document):
                raise IndexError(
                    "page number outside PDF"
                )

            page = document[
                page_number - 1
            ]

            lines: list[
                VectorLine
            ] = []

            polygons: list[
                VectorPolygon
            ] = []

            for drawing_index, drawing in enumerate(
                page.get_drawings()
            ):
                layer = (
                    drawing.get("layer")
                    if isinstance(
                        drawing,
                        dict,
                    )
                    else None
                )

                width = (
                    drawing.get("width")
                    if isinstance(
                        drawing,
                        dict,
                    )
                    else None
                )

                items = (
                    drawing.get("items", [])
                    if isinstance(
                        drawing,
                        dict,
                    )
                    else []
                )

                for item_index, item in enumerate(
                    items
                ):
                    if not item:
                        continue

                    kind = item[0]

                    geometry_id = (
                        f"pdf_{page_number}_"
                        f"{drawing_index}_"
                        f"{item_index}"
                    )

                    if kind == "l":
                        p1 = item[1]
                        p2 = item[2]

                        lines.append(
                            VectorLine(
                                geometry_id=(
                                    geometry_id
                                ),
                                start=Point2D(
                                    float(p1.x),
                                    float(p1.y),
                                ),
                                end=Point2D(
                                    float(p2.x),
                                    float(p2.y),
                                ),
                                layer=layer,
                                stroke_width=(
                                    float(width)
                                    if width is not None
                                    else None
                                ),
                            )
                        )

                    elif kind == "re":
                        rect = item[1]

                        polygons.append(
                            VectorPolygon(
                                geometry_id=(
                                    geometry_id
                                ),
                                points=(
                                    Point2D(
                                        float(rect.x0),
                                        float(rect.y0),
                                    ),
                                    Point2D(
                                        float(rect.x1),
                                        float(rect.y0),
                                    ),
                                    Point2D(
                                        float(rect.x1),
                                        float(rect.y1),
                                    ),
                                    Point2D(
                                        float(rect.x0),
                                        float(rect.y1),
                                    ),
                                ),
                                layer=layer,
                            )
                        )

                    elif kind == "qu":
                        quad = item[1]

                        points = (
                            Point2D(
                                float(quad.ul.x),
                                float(quad.ul.y),
                            ),
                            Point2D(
                                float(quad.ur.x),
                                float(quad.ur.y),
                            ),
                            Point2D(
                                float(quad.lr.x),
                                float(quad.lr.y),
                            ),
                            Point2D(
                                float(quad.ll.x),
                                float(quad.ll.y),
                            ),
                        )

                        polygons.append(
                            VectorPolygon(
                                geometry_id=(
                                    geometry_id
                                ),
                                points=points,
                                layer=layer,
                            )
                        )

            text_spans: list[
                TextSpan
            ] = []

            text_dict = page.get_text(
                "dict"
            )

            for block_index, block in enumerate(
                text_dict.get(
                    "blocks",
                    []
                )
            ):
                for line_index, line in enumerate(
                    block.get(
                        "lines",
                        []
                    )
                ):
                    for span_index, span in enumerate(
                        line.get(
                            "spans",
                            []
                        )
                    ):
                        text = str(
                            span.get(
                                "text",
                                ""
                            )
                        ).strip()

                        if not text:
                            continue

                        bbox = span.get(
                            "bbox"
                        )

                        if not bbox:
                            continue

                        text_spans.append(
                            TextSpan(
                                text_id=(
                                    f"text_{page_number}_"
                                    f"{block_index}_"
                                    f"{line_index}_"
                                    f"{span_index}"
                                ),
                                text=text,
                                bounds=BoundingBox(
                                    float(bbox[0]),
                                    float(bbox[1]),
                                    float(bbox[2]),
                                    float(bbox[3]),
                                ),
                                font_size=(
                                    float(
                                        span.get(
                                            "size"
                                        )
                                    )
                                    if span.get(
                                        "size"
                                    ) is not None
                                    else None
                                ),
                                font_name=(
                                    span.get(
                                        "font"
                                    )
                                ),
                            )
                        )

            return VectorSheet(
                document_id=document_id,
                sheet_number=sheet_number,
                page_number=page_number,
                width_points=float(
                    page.rect.width
                ),
                height_points=float(
                    page.rect.height
                ),
                source_ref=(
                    f"{pdf_path.name}"
                    f"#page={page_number}"
                ),
                lines=tuple(lines),
                polygons=tuple(polygons),
                text_spans=tuple(
                    text_spans
                ),
            )

        finally:
            document.close()
