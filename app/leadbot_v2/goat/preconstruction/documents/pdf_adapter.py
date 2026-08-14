from __future__ import annotations

from pathlib import Path

from leadbot_v2.goat.preconstruction.documents.intelligence import (
    RawPage,
)


class PDFDependencyUnavailable(RuntimeError):
    pass


class PDFTextExtractor:
    """
    Thin adapter around PyMuPDF when available.

    This keeps PDF parsing separate from GOAT's construction intelligence.

    Later adapters can add:
      - vector geometry
      - text coordinates
      - drawing primitives
      - raster fallback
      - OCR
      - CAD/BIM
    """

    def extract(
        self,
        path: str | Path,
    ) -> tuple[RawPage, ...]:
        try:
            import fitz
        except ImportError as exc:
            raise PDFDependencyUnavailable(
                "PyMuPDF is not installed. "
                "Install package 'pymupdf' "
                "to enable direct PDF extraction."
            ) from exc

        pdf_path = Path(path)

        if not pdf_path.exists():
            raise FileNotFoundError(
                pdf_path
            )

        document = fitz.open(
            str(pdf_path)
        )

        try:
            pages = []

            for index, page in enumerate(
                document,
                start=1,
            ):
                pages.append(
                    RawPage(
                        page_number=index,
                        text=page.get_text(
                            "text"
                        ),
                        source_ref=(
                            f"{pdf_path.name}"
                            f"#page={index}"
                        ),
                    )
                )

            return tuple(pages)

        finally:
            document.close()
